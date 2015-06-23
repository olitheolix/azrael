import json
import pytest
import base64
import tornado.web
import azrael.clerk
import azrael.clacks
import azrael.wsclient
import tornado.testing
import azrael.types as types
import azrael.config as config

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

    def verifyTemplate(self, url, fragments):
        """
        Raise an error if the ``fragments`` are not available at ``url``.

        This method will automatically adapts to the fragment type and verifies
        the associated textures (if any).

        :param str url: base location of template
        :param list[MetaFragment] fragments: reference fragments
        :raises: AssertionError if not all fragments in ``fragments`` match
                 those available at ``url``.
        """
        # Fetch- and decode the meta file.
        ret = self.fetch(url + '/meta.json', method='GET')
        try:
            ret = json.loads(ret.body.decode('utf8'))
        except ValueError:
            assert False

        # Verify that the meta file contains the correct fragment names.
        expected_fragment_names = {_.aid: _.fragtype for _ in fragments}
        assert ret['fragments'] == expected_fragment_names

        # Download- and verify each fragment.
        for frag in fragments:
            ftype = frag.fragtype.upper()
            if ftype == 'RAW':
                tmp_url = url + '/{name}/'.format(name=frag.aid)
                assert self.downloadFragRaw(tmp_url) == frag.fragdata
            elif ftype == 'DAE':
                tmp_url = url + '/{name}/'.format(name=frag.aid)
                texture_names = list(frag.fragdata.rgb.keys())
                ret = self.downloadFragDae(tmp_url, frag.aid, texture_names)
                assert ret == frag.fragdata
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
        frags_t1 = [MetaFragment('raw1', 'raw', createFragRaw()),
                    MetaFragment('dae2', 'dae', createFragDae()),
                    MetaFragment('dae3', 'dae', createFragDae())]
        frags_t2 = [MetaFragment('raw4', 'raw', createFragRaw()),
                    MetaFragment('raw5', 'raw', createFragRaw()),
                    MetaFragment('dae6', 'dae', createFragDae())]
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
        sv_1 = types.RigidBodyState(imass=1)
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
        frags_old = [MetaFragment('name1', 'raw', createFragRaw()),
                     MetaFragment('name2', 'dae', createFragDae()),
                     MetaFragment('name3', 'dae', createFragDae())]
        frags_new = [MetaFragment('name1', 'dae', createFragDae()),
                     MetaFragment('name2', 'dae', createFragDae()),
                     MetaFragment('name3', 'raw', createFragRaw())]
        t1 = Template('t1', [getCSSphere()], frags_old, [], [])

        # Add-, spawn-, and verify the template.
        assert clerk.addTemplates([t1]).ok
        self.verifyTemplate('{}/t1'.format(config.url_templates), t1.fragments)
        sv_1 = types.RigidBodyState(imass=1)
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
        frags = [MetaFragment('name1', 'raw', createFragRaw())]
        t1 = Template('t1', [getCSSphere()], frags, [], [])

        # Add-, spawn-, and verify the template.
        assert clerk.addTemplates([t1]).ok
        self.verifyTemplate('{}/t1'.format(config.url_templates), t1.fragments)
        sv_1 = types.RigidBodyState(imass=1)
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
