import json
import pytest
import base64
import tornado.web
import azrael.clerk
import azrael.clacks
import azrael.wsclient
import tornado.testing
import azrael.config as config
import azrael.rb_state as rb_state

from IPython import embed as ipshell
from azrael.types import Template, RetVal, FragDae, FragRaw, MetaFragment
from azrael.test.test import createFragRaw, createFragDae
from azrael.test.test_bullet_api import getCSEmpty, getCSBox, getCSSphere


class TestClacks(tornado.testing.AsyncHTTPTestCase):
    @classmethod
    def setup_class(cls):
        pass

    @classmethod
    def teardown_class(cls):
        pass

    def setup_method(self, method):
        pass

    def teardown_method(self, method):
        pass

    def get_app(self):
        # Dibbler instance is necessary because this test suite contains
        # several integration tests between Dibbler and Clacks.
        self.dibbler = azrael.dibbler.Dibbler()

        # Handler to serve up models.
        FH = azrael.clacks.MyGridFSHandler
        handlers = [(config.url_templates + '/(.*)', FH),
                    (config.url_instances + '/(.*)', FH)]
        return tornado.web.Application(handlers)

    def downloadFragRaw(self, url: str):
        """
        Download and unpack the Raw model from ``url`` and return it as a
        ``FragRaw`` instance.

        Example: downloadFragRaw('/instances/3/raw1/')

        :param str url: download URL
        :return: Raw model
        :rtype: FragRaw
        :raises: AssertionError if there was a problem.
        """
        ret = self.fetch(url + 'model.json', method='GET')
        try:
            ret = json.loads(ret.body.decode('utf8'))
        except ValueError:
            assert False
        return FragRaw(**(ret))

    def downloadFragDae(self, url: str, dae: str, textures: list):
        """
        Download and unpack the Collada model from ``url`` and return it as a
        ``FragDae`` instance.

        Example: downloadFragDae('/instances/1/name1/')

        :param str url: download URL
        :param str dae: name of Collada model.
        :param list textures: list of strings denoting the texture files.
        :return: Dae model
        :rtype: FragDae
        :raises: AssertionError if there was a problem.
        """
        # Download the Collada file itself.
        dae = self.fetch(url + dae, method='GET').body

        # Download all the textures.
        rgb = {}
        for texture in textures:
            rgb[texture] = self.fetch(url + texture, method='GET').body

        # Convert the fields to Base64 encode strings and construct a new
        # FragDae instance.
        b64enc = base64.b64encode
        dae = b64enc(dae).decode('utf8')
        rgb = {k: b64enc(v).decode('utf8') for (k, v) in rgb.items()}
        return FragDae(dae=dae, rgb=rgb)

    def verifyTemplate(self, url, template):
        """
        Raise an error if ``template`` is not available at ``url``.

        This method will automatically adapt to the model type and verify
        associated texture (if any) as well.

        :param str url: base location of template
        :param Template template: the template (can contain multiple
                                  fragments).
        :raises: AssertionError if not all fragments in ``template`` match
                 those available at ``url``.
        """
        # Fetch- and decode the meta file.
        ret = self.fetch(url + '/meta.json', method='GET')
        try:
            ret = json.loads(ret.body.decode('utf8'))
        except ValueError:
            assert False

        # Verify that the meta file contains the correct fragment names.
        expected_fragment_names = {_.id: _.type for _ in template}
        assert ret['fragments'] == expected_fragment_names

        # Download- and verify each template.
        # fixme: must use __eq__ method of Frag{Raw,Dae}
        for tt in template:
            if tt.type == 'raw':
                tmp_url = url + '/{name}/'.format(name=tt.id)
                assert self.downloadFragRaw(tmp_url) == tt.data
            elif tt.type == 'dae':
                tmp_url = url + '/{name}/'.format(name=tt.id)
                texture_names = list(tt.data.rgb.keys())
                ret = self.downloadFragDae(tmp_url, tt.id, texture_names)
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
        frags_t1 = [MetaFragment('raw', 'foo1', createFragRaw()),
                    MetaFragment('dae', 'bar2', createFragDae()),
                    MetaFragment('dae', 'bar3', createFragDae())]
        frags_t2 = [MetaFragment('raw', 'foo4', createFragRaw()),
                    MetaFragment('raw', 'foo5', createFragRaw()),
                    MetaFragment('dae', 'bar6', createFragDae())]
        t1 = Template('t1', [getCSSphere()], frags_t1, [], [])
        t2 = Template('t2', [getCSBox()], frags_t2, [], [])
        del frags_t1, frags_t2

        # Add the first template.
        assert clerk.addTemplates([t1]).ok

        # Attempt to add the template a second time. This must fail.
        assert not clerk.addTemplates([t1]).ok

        # Verify the first template.
        url_template = config.url_templates
        self.verifyTemplate('{}/t1'.format(url_template), t1.fragments)

        # Add the second template and verify both.
        assert clerk.addTemplates([t2]).ok
        self.verifyTemplate('{}/t1'.format(url_template), t1.fragments)
        self.verifyTemplate('{}/t2'.format(url_template), t2.fragments)

    def test_spawnTemplates(self):
        """
        Spawn a template and verify it is available via Clacks.
        """
        self.dibbler.reset()
        azrael.database.init()
        clerk = azrael.clerk.Clerk()

        # Create two Templates with one Raw fragment each.
        frags_t1 = [MetaFragment('raw', 'raw1', createFragRaw()),
                    MetaFragment('dae', 'dae2', createFragDae()),
                    MetaFragment('dae', 'dae3', createFragDae())]
        frags_t2 = [MetaFragment('raw', 'raw4', createFragRaw()),
                    MetaFragment('raw', 'raw5', createFragRaw()),
                    MetaFragment('dae', 'dae6', createFragDae())]
        t1 = Template('t1', [getCSSphere()], frags_t1, [], [])
        t2 = Template('t2', [getCSBox()], frags_t2, [], [])
        del frags_t1, frags_t2

        # Add both templates and verify they are available.
        assert clerk.addTemplates([t1]).ok
        assert clerk.addTemplates([t2]).ok
        self.verifyTemplate('{}/t1'.format(config.url_templates), t1.fragments)
        self.verifyTemplate('{}/t2'.format(config.url_templates), t2.fragments)

        # No object instance with ID=1 must exist yet.
        url_inst = config.url_instances
        with pytest.raises(AssertionError):
            self.verifyTemplate('{}/{}'.format(url_inst, 1), t1.fragments)

        # Spawn the first template (it will must get objID=1).
        sv_1 = rb_state.RigidBodyState(imass=1)
        ret = clerk.spawn([('t1', sv_1)])
        assert ret.data == (1, )
        self.verifyTemplate('{}/{}'.format(url_inst, 1), t1.fragments)

        # Spawn two more templates and very the instance models.
        ret = clerk.spawn([('t2', sv_1), ('t1', sv_1)])
        assert ret.data == (2, 3)
        self.verifyTemplate('{}/{}'.format(url_inst, 2), t2.fragments)
        self.verifyTemplate('{}/{}'.format(url_inst, 3), t1.fragments)

    def test_updateFragments(self):
        """
        Modify the fragments of a spawned object.
        """
        self.dibbler.reset()
        azrael.database.init()
        clerk = azrael.clerk.Clerk()

        # Create two Templates with one Raw fragment each.
        frags_old = [MetaFragment('raw', 'name1', createFragRaw()),
                     MetaFragment('dae', 'name2', createFragDae()),
                     MetaFragment('dae', 'name3', createFragDae())]
        frags_new = [MetaFragment('dae', 'name1', createFragDae()),
                     MetaFragment('dae', 'name2', createFragDae()),
                     MetaFragment('raw', 'name3', createFragRaw())]
        t1 = Template('t1', [getCSSphere()], frags_old, [], [])

        # Add-, spawn-, and verify the template.
        assert clerk.addTemplates([t1]).ok
        self.verifyTemplate('{}/t1'.format(config.url_templates), t1.fragments)
        sv_1 = rb_state.RigidBodyState(imass=1)
        ret = clerk.spawn([('t1', sv_1)])
        assert ret.data == (1, )

        # Verify that the instance has the old fragments, not the new ones.
        url_inst = config.url_instances
        self.verifyTemplate('{}/{}'.format(url_inst, 1), frags_old)
        with pytest.raises(AssertionError):
            self.verifyTemplate('{}/{}'.format(url_inst, 1), frags_new)

        # Update the fragments.
        clerk.setFragmentGeometries(objID=1, fragments=frags_new)

        # Verify that the instance now has the new fragments, but not the old
        # ones anymore.
        self.verifyTemplate('{}/{}'.format(url_inst, 1), frags_new)
        with pytest.raises(AssertionError):
            self.verifyTemplate('{}/{}'.format(url_inst, 1), frags_old)

    def test_deleteInstance(self):
        """
        Add/remove an instance from Dibbler via Clerk and verify via Clacks.
        """
        self.dibbler.reset()
        azrael.database.init()
        clerk = azrael.clerk.Clerk()

        # Create two Templates with one Raw fragment each.
        frags = [MetaFragment('raw', 'name1', createFragRaw())]
        t1 = Template('t1', [getCSSphere()], frags, [], [])

        # Add-, spawn-, and verify the template.
        assert clerk.addTemplates([t1]).ok
        self.verifyTemplate('{}/t1'.format(config.url_templates), t1.fragments)
        sv_1 = rb_state.RigidBodyState(imass=1)
        ret = clerk.spawn([('t1', sv_1)])
        assert ret.data == (1, )

        # Verify that the instance exists.
        url_inst = config.url_instances
        self.verifyTemplate('{}/{}'.format(url_inst, 1), frags)

        # Delete the instance and verify it is now gone.
        cnt = self.dibbler.getNumFiles().data
        assert clerk.removeObject(objID=1) == (True, None, None)
        self.dibbler.getNumFiles().data == cnt - 2
        with pytest.raises(AssertionError):
            self.verifyTemplate('{}/{}'.format(url_inst, 1), frags)


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
