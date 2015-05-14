import json
import pytest
import tornado.web
import azrael.clerk
import azrael.clacks
import azrael.wsclient
import tornado.testing
import azrael.config as config
import azrael.bullet_data as bullet_data

from IPython import embed as ipshell
from azrael.types import Template, RetVal, FragDae, FragRaw, MetaFragment
from azrael.test.test import createFragRaw, createFragDae


class TestClacks(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        # Dibbler instance is necessary because this test suite contains
        # several integration tests between Dibbler and Clacks.
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

    def verifyTemplate(self, url, template):
        # Fetch- and decode the meta file.
        ret = self.fetch(url + '/meta.json', method='GET')
        try:
            ret = json.loads(ret.body.decode('utf8'))
        except ValueError:
            assert False

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

    def test_addTemplates(self):
        """
        Add and query a template with one Raw fragment.
        """
        self.dibbler.reset()
        azrael.database.init()
        clerk = azrael.clerk.Clerk()

        # Create two Templates with one Raw fragment each.
        frags_t1 = [MetaFragment('foo1', 'raw', createFragRaw()),
                    MetaFragment('bar2', 'dae', createFragDae()),
                    MetaFragment('bar3', 'dae', createFragDae())]
        frags_t2 = [MetaFragment('foo4', 'raw', createFragRaw()),
                    MetaFragment('foo5', 'raw', createFragRaw()),
                    MetaFragment('bar6', 'dae', createFragDae())]
        t1 = Template('t1', [1, 2, 3, 4], frags_t1, [], [])
        t2 = Template('t2', [5, 6, 7, 8], frags_t2, [], [])
        del frags_t1, frags_t2

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

    def test_spawnTemplates(self):
        """
        Spawn a template and verify it is available via Clacks.
        """
        self.dibbler.reset()
        azrael.database.init()
        clerk = azrael.clerk.Clerk()

        # Create two Templates with one Raw fragment each.
        frags_t1 = [MetaFragment('raw1', 'raw', createFragRaw()),
                    MetaFragment('dae2', 'dae', createFragDae()),
                    MetaFragment('dae3', 'dae', createFragDae())]
        frags_t2 = [MetaFragment('raw4', 'raw', createFragRaw()),
                    MetaFragment('raw5', 'raw', createFragRaw()),
                    MetaFragment('dae6', 'dae', createFragDae())]
        t1 = Template('t1', [1, 2, 3, 4], frags_t1, [], [])
        t2 = Template('t2', [5, 6, 7, 8], frags_t2, [], [])
        del frags_t1, frags_t2

        # Add both templates and verify they are available.
        assert clerk.addTemplates([t1]).ok
        assert clerk.addTemplates([t2]).ok
        self.verifyTemplate('/templates/t1', t1.fragments)
        self.verifyTemplate('/templates/t2', t2.fragments)

        # No object instance with ID=1 must exist yet.
        with pytest.raises(AssertionError):
            self.verifyTemplate('/instances/{}'.format(1), t1.fragments)

        # Spawn the first template (it will must get objID=1).
        sv_1 = bullet_data.MotionState(imass=1)
        ret = clerk.spawn([('t1', sv_1)])
        assert ret.data == (1, )
        self.verifyTemplate('/instances/{}'.format(1), t1.fragments)

        # Spawn two more templates and very the instance models.
        ret = clerk.spawn([('t2', sv_1), ('t1', sv_1)])
        assert ret.data == (2, 3)
        self.verifyTemplate('/instances/{}'.format(2), t2.fragments)
        self.verifyTemplate('/instances/{}'.format(3), t1.fragments)

    def test_updateFragments(self):
        """
        Modify the fragments of a spawned object.
        """
        self.dibbler.reset()
        azrael.database.init()
        clerk = azrael.clerk.Clerk()

        # Create two Templates with one Raw fragment each.
        frags_old = [MetaFragment('name1', 'raw', createFragRaw()),
                     MetaFragment('name2', 'dae', createFragDae()),
                     MetaFragment('name3', 'dae', createFragDae())]
        frags_new = [MetaFragment('name1', 'dae', createFragDae()),
                     MetaFragment('name2', 'dae', createFragDae()),
                     MetaFragment('name3', 'raw', createFragRaw())]
        t1 = Template('t1', [1, 2, 3, 4], frags_old, [], [])

        # Add-, spawn-, and verify the template.
        assert clerk.addTemplates([t1]).ok
        self.verifyTemplate('/templates/t1', t1.fragments)
        sv_1 = bullet_data.MotionState(imass=1)
        ret = clerk.spawn([('t1', sv_1)])
        assert ret.data == (1, )

        # Verify that the instance has the old fragments, not the new ones.
        self.verifyTemplate('/instances/{}'.format(1), frags_old)
        with pytest.raises(AssertionError):
            self.verifyTemplate('/instances/{}'.format(1), frags_new)

        # Update the fragments.
        clerk.updateFragments(objID=1, fragments=frags_new)

        # Verify that the instance now has the new fragments, but not the old
        # ones anymore.
        self.verifyTemplate('/instances/{}'.format(1), frags_new)
        with pytest.raises(AssertionError):
            self.verifyTemplate('/instances/{}'.format(1), frags_old)

    def test_removeInstance(self):
        """
        Add/remove an instance from Dibbler via Clerk and verify via Clacks.
        """
        self.dibbler.reset()
        azrael.database.init()
        clerk = azrael.clerk.Clerk()

        # Create two Templates with one Raw fragment each.
        frags = [MetaFragment('name1', 'raw', createFragRaw())]
        t1 = Template('t1', [1, 2, 3, 4], frags, [], [])

        # Add-, spawn-, and verify the template.
        assert clerk.addTemplates([t1]).ok
        self.verifyTemplate('/templates/t1', t1.fragments)
        sv_1 = bullet_data.MotionState(imass=1)
        ret = clerk.spawn([('t1', sv_1)])
        assert ret.data == (1, )

        # Verify that the instance exists.
        self.verifyTemplate('/instances/{}'.format(1), frags)

        # Delete the instance and verify it is now gone.
        cnt = self.dibbler.getNumFiles().data
        assert clerk.removeObject(objID=1) == (True, None, None)
        self.dibbler.getNumFiles().data == cnt - 2
        with pytest.raises(AssertionError):
            self.verifyTemplate('/instances/{}'.format(1), frags)


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
