import json
import pytest
import tornado.web
import azrael.clerk
import azrael.clacks
import azrael.wsclient
import tornado.testing
import azrael.config as config

from IPython import embed as ipshell
from azrael.types import Template, RetVal, FragDae, FragRaw, MetaFragment
from azrael.test.test import createFragRaw, createFragDae


class TestClacks(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        self.dibbler = azrael.dibbler.DibblerAPI()

        # Handler to serve up models.
        FH = azrael.clacks.MyGridFSHandler
        handlers = [('/templates/(.*)', FH), ('/instances/(.*)', FH)]
        return tornado.web.Application(handlers)

    def downloadFragRaw(self, url):
        # fixme: docu
        ret = self.fetch(url, method='GET')
        try:
            ret = json.loads(ret.body.decode('utf8'))
        except ValueError:
            assert False
        return FragRaw(**(ret))

    def downloadFragDae(self, url, dae, textures):
        # fixme: docu
        dae = self.fetch(url + dae, method='GET').body

        rgb = {}
        for texture in textures:
            tmp = self.fetch(url + texture, method='GET').body
            rgb[texture] = tmp
        return FragDae(dae=dae, rgb=rgb)

    def downloadJSON(self, url):
        # fixme: docu
        url = config.url_template + '/t1/meta.json'
        ret = self.fetch(url, method='GET')
        try:
            return json.loads(ret.body.decode('utf8'))
        except ValueError:
            assert False

    def verifyTemplate(self, url, template):
        # Fetch- and decode the meta file.
        ret = self.fetch(url + '/meta.json', method='GET')
        ret = json.loads(ret.body.decode('utf8'))

        # Verify that the meta file contains the correct fragment names.
        expected_fragment_names = {_.name: _.type for _ in template}
        assert ret['fragments'] == expected_fragment_names

        # Download- and verify each template.
        for tt in template:
            if tt.type == 'raw':
                tmp_url = url + '/{}/model.json'.format(tt.name)
                assert self.downloadFragRaw(tmp_url) == tt.data
            elif tt.type == 'dae':
                tmp_url = url + '/{name}/'.format(name=tt.name)
                texture_names = list(tt.data.rgb.keys())
                ret = self.downloadFragDae(tmp_url, tt.name, texture_names)
                assert ret == tt.data
            else:
                assert False

    def test_template_raw(self):
        """
        Add and query a template with one Raw fragment.
        """
        self.dibbler.reset()
        azrael.database.init()
        clerk = azrael.clerk.Clerk()

        # Create two Templates with one Raw fragment each.
        frags = [MetaFragment('bar', 'raw', createFragRaw())]
        t1 = Template('t1', [1, 2, 3, 4], frags, [], [])
        t2 = Template('t2', [5, 6, 7, 8], frags, [], [])
        del frags

        # Add the first template.
        assert clerk.addTemplates([t1]).ok

        # Attempt to add the template a second time. This must fail.
        assert not clerk.addTemplates([t1]).ok

        # Verify the first template.
        self.verifyTemplate('/templates/t1', t1.fragments)

        # Add the second template and verify both.
        assert clerk.addTemplates([t2]).ok
        self.verifyTemplate('/templates/t1', t1.fragments)
        self.verifyTemplate('/templates/t2', t2.fragments)

    def test_template_dae(self):
        """
        Add and query a template with one Collada fragment.
        """
        self.dibbler.reset()
        azrael.database.init()
        clerk = azrael.clerk.Clerk()

        # Create two Templates with one Collada fragment each.
        frags = [MetaFragment('bar', 'dae', createFragDae())]
        t1 = Template('t1', [1, 2, 3, 4], frags, [], [])
        t2 = Template('t2', [5, 6, 7, 8], frags, [], [])
        del frags

        # Add the first template.
        assert clerk.addTemplates([t1]).ok

        # Attempt to add the template a second time. This must fail.
        assert not clerk.addTemplates([t1]).ok

        # Verify the first template.
        self.verifyTemplate('/templates/t1', t1.fragments)

        # Add the second template and verify both.
        assert clerk.addTemplates([t2]).ok
        self.verifyTemplate('/templates/t1', t1.fragments)
        self.verifyTemplate('/templates/t2', t2.fragments)


def test_ping_clacks():
    """
    Start services and send Ping to Clacks. Then terminate clacks and verify
    that the ping fails.
    """
    # Convenience.
    WSClient = azrael.wsclient.WSClient
    ip, port = config.addr_clacks, config.port_clacks

    # Start the services.
    clerk = azrael.clerk.Clerk()
    clacks = azrael.clacks.ClacksServer()
    clerk.start()
    clacks.start()

    # Create a Websocket client.
    client = azrael.wsclient.WSClient(ip=ip, port=port, timeout=1)

    # Ping Clerk via Clacks.
    assert client.ping()
    assert client.pingClacks().ok

    # Terminate the services.
    clerk.terminate()
    clacks.terminate()
    clerk.join()
    clacks.join()

    # Ping must now be impossible.
    with pytest.raises(ConnectionRefusedError):
        WSClient(ip=ip, port=port, timeout=1)

    assert not client.pingClacks().ok
