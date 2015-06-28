# Copyright 2015, Oliver Nagy <olitheolix@gmail.com>
#
# This file is part of Azrael (https://github.com/olitheolix/azrael)
#
# Azrael is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# Azrael is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with Azrael. If not, see <http://www.gnu.org/licenses/>.
import json
import base64
import pytest
import azrael.dibbler

import azrael.config as config

from IPython import embed as ipshell
from azrael.types import Template, RetVal, FragDae, FragRaw, FragMeta
from azrael.test.test import getFragRaw, getFragDae, getFragNone


class TestDibbler:
    @classmethod
    def setup_class(cls):
        pass

    @classmethod
    def teardown_class(cls):
        pass

    def setup_method(self, method):
        # Flush Dibbler.
        self.dibbler = azrael.dibbler.Dibbler()
        self.dibbler.reset()
        assert self.dibbler.getNumFiles() == (True, None, 0)

    def teardown_method(self, method):
        # Flush Dibbler.
        self.dibbler.reset()
        assert self.dibbler.getNumFiles() == (True, None, 0)

    def verifyDae(self, url: str, mf: FragMeta):
        """
        fixme: this has to become part of the 'FragDae.__eq__' method.

        Verify that ``url`` contains the canned Collada Metga fragment ``mf``.

        :param str url: the URL where the Collada fragment is supposed to be.
        :param FragMeta mf: the fragment to compare it with.
        :return: None
        :raises: AssertionError if the fragment does not match.
        """
        # Convenience.
        name = mf.aid
        ref = mf.fragdata

        # Fetch- the components of the Collada file.
        r_dae = self.dibbler.getFile(url + '/{name}/{name}'.format(name=name))
        r_rgb1 = self.dibbler.getFile(url + '/{}/rgb1.png'.format(name))
        r_rgb2 = self.dibbler.getFile(url + '/{}/rgb2.jpg'.format(name))

        # Verify Dibbler could retrieve all components.
        assert r_dae.ok
        assert r_rgb1.ok
        assert r_rgb2.ok

        # Base64 encode the downloaded components and put them into a pristine
        # 'FragDae' instance.
        dae = base64.b64encode(r_dae.data).decode('utf8')
        rgb1 = base64.b64encode(r_rgb1.data).decode('utf8')
        rgb2 = base64.b64encode(r_rgb2.data).decode('utf8')
        downloaded = FragDae(dae, {'rgb1.png': rgb1, 'rgb2.jpg': rgb2})

        # Ensure the downloaded data matches the reference data.
        assert ref == downloaded

    def verifyRaw(self, url: str, mf: FragMeta):
        """
        Verify that ``url`` contains the canned Collada Metga fragment ``mf``.

        :param str url: the URL where the Collada fragment is supposed to be.
        :param FragMeta mf: the fragment to compare it with.
        :return: None
        :raises: AssertionError if the fragment does not match.
        """
        # Convenience.
        name = mf.aid
        ref = mf.fragdata

        # Fetch- the data for the Raw fragment.
        ret = self.dibbler.getFile('{}/{}/model.json'.format(url, name))
        assert ret.ok
        ret = json.loads(ret.data.decode('utf8'))

        # Construct a pristine FragRaw from the downloaded data and compare it
        # the provided reference.
        download = FragRaw(ret['vert'], ret['uv'], ret['rgb'])
        assert ref == download

    def test_addRawTemplate(self):
        """
        Add a raw template and fetch the individual files again afterwards.
        """
        # Create a Dibbler instance and flush all data.
        dibbler = self.dibbler
        assert dibbler.getNumFiles() == (True, None, 0)

        # Define a template for this test.
        frag = getFragRaw()
        t_raw = Template('_templateEmpty', [], [frag], [], [])

        # Add the first template and verify that the database now contains
        # exactly two files (a meta file, and the actual fragment data).
        ret = dibbler.addTemplate(t_raw)
        assert ret.ok
        assert dibbler.getNumFiles() == (True, None, 2)

        # Fetch- and verify the model.
        self.verifyRaw(ret.data['url'], frag)

    def test_addDaeTemplate(self):
        """
        Add a Collada template and fetch the individual files again afterwards.
        """
        dibbler = self.dibbler

        # Define a template for this test.
        frag = getFragDae()
        t_dae = Template('_templateEmpty', [], [frag], [], [])

        # Create a Dibbler instance and flush all data.
        assert dibbler.getNumFiles() == (True, None, 0)

        # Add the first template and verify that the database now contains
        # extactly fourc files (a meta file, the DAE file, and two textures).
        ret = dibbler.addTemplate(t_dae)
        assert dibbler.getNumFiles() == (True, None, 4)

        # Fetch- and verify the model.
        self.verifyDae(ret.data['url'], frag)

    def test_invalid(self):
        """
        Query a non-existing file.
        """
        ret = self.dibbler.getFile('/blah/')
        assert not ret.ok
        assert ret.data is None

    def test_spawnTemplate(self):
        """
        Add two templates, then spawn the first one twice and the second
        one once.
        """
        dibbler = self.dibbler

        # Define two templates.
        frag_raw = getFragRaw()
        frag_dae = getFragDae()
        t_raw = Template('t_name_raw', [], [frag_raw], [], [])
        t_dae = Template('t_name_dae', [], [frag_dae], [], [])

        # Add the templates and verify there are 6 files in the DB now. The
        # first template has two files (1 meta.json plus 1 for the raw data)
        # and the second has 4 files (1 meta.json plus 3 for the Collada data).
        dibbler.addTemplate(t_raw)
        dibbler.addTemplate(t_dae)
        assert dibbler.getNumFiles() == (True, None, 2 + 4)

        # Spawn some instances.
        ret_1 = dibbler.spawnTemplate(t_raw.aid, '1')
        ret_2 = dibbler.spawnTemplate(t_raw.aid, '2')
        ret_3 = dibbler.spawnTemplate(t_dae.aid, '3')
        assert ret_1.ok and ret_2.ok and ret_3.ok

        # Dibbler must now hold the original 6 files plus an additional 8 files
        # (2x2 for the two Raw instances, and another 4 for the one Collada
        # instance).
        assert dibbler.getNumFiles() == (True, None, (2 + 4) + (2 * 2 + 1 * 4))

        # Verify that all files are correct.
        self.verifyRaw(ret_1.data['url'], frag_raw)
        self.verifyRaw(ret_2.data['url'], frag_raw)
        self.verifyDae(ret_3.data['url'], frag_dae)

        # Attempt to spawn a non-existing template. This must fail and the
        # number of files in Dibbler must not change.
        assert not dibbler.spawnTemplate('blah', '10').ok
        assert dibbler.getNumFiles() == (True, None, (2 + 4) + (2 * 2 + 1 * 4))

    def test_updateFragments_all(self):
        """
        Spawn a template and update all its fragments.
        """
        dibbler = self.dibbler

        # The original template has two fragments, and we will update one of
        # them.
        frags_orig = [getFragRaw('fname_1'), getFragDae('fname_2')]
        frags_new = [getFragDae('fname_1')]
        t1 = Template('t1', [], frags_orig, [], [])

        # Add the template and spawn two instances.
        assert dibbler.addTemplate(t1).ok
        ret_11 = dibbler.spawnTemplate(t1.aid, '11')
        ret_2 = dibbler.spawnTemplate(t1.aid, '2')
        assert ret_11.ok and ret_2.ok

        self.verifyRaw(ret_11.data['url'], frags_orig[0])
        self.verifyDae(ret_11.data['url'], frags_orig[1])
        self.verifyRaw(ret_2.data['url'], frags_orig[0])
        self.verifyDae(ret_2.data['url'], frags_orig[1])

        # Attempt to change the fragment of a non-existing object.
        ret = dibbler.updateFragments('20', frags_new)
        assert not ret.ok

        # Attempt to change the fragment of another non-existing object, but
        # the object ID of this one is '1', which means it is available at
        # '/somewhere/1/...'. However, an object at '/somewhere/11/...' already
        # exists, and without the trailing '/' the first would be a sub-string
        # of the latter. The update method must therefore take care to properly
        # test for existence, especially since directories, internally, do not
        # have a trailing '/'.
        ret = dibbler.updateFragments('1', frags_new)
        assert not ret.ok

        # The previous attempts to modify fragments of non-existing objectst
        # must not have modified the fragments.
        self.verifyRaw(ret_11.data['url'], frags_orig[0])
        self.verifyDae(ret_11.data['url'], frags_orig[1])
        self.verifyRaw(ret_2.data['url'], frags_orig[0])
        self.verifyDae(ret_2.data['url'], frags_orig[1])

        # Change the first fragments of the first object.
        ret = dibbler.updateFragments('11', frags_new)
        assert ret.ok

        # Verify that only the first fragment of the '11' object has changed.
        self.verifyDae(ret_11.data['url'], frags_new[0])
        self.verifyDae(ret_11.data['url'], frags_orig[1])
        self.verifyRaw(ret_2.data['url'], frags_orig[0])
        self.verifyDae(ret_2.data['url'], frags_orig[1])

    def test_updateFragments_partial(self):
        """
        Simliar to previous test in the sense that it spawns and updates
        fragments. However, this time some fragments will be removed
        altogether, instead of just being updated.
        """
        dibbler = self.dibbler

        # The original template has the following three fragments:
        frags_orig = [
            getFragRaw('fname_1'),
            getFragDae('fname_2'),
            getFragRaw('fname_3')
        ]
        t1 = Template('t1', [], frags_orig, [], [])

        # The fragment update will use the following data. It translates to
        # keeping the first intact, removing the second, and modifying the
        # fragment type for the third one.
        frags_new = [
            getFragNone('fname_2'),
            getFragDae('fname_3'),
        ]

        # Add the template, spawn one instance, and verify all fragments.
        assert dibbler.addTemplate(t1).ok
        ret = dibbler.spawnTemplate(t1.aid, '1')
        assert ret.ok
        self.verifyRaw(ret.data['url'], frags_orig[0])
        self.verifyDae(ret.data['url'], frags_orig[1])
        self.verifyRaw(ret.data['url'], frags_orig[2])

        # Record the current number of files in Dibbler. There must be one
        # 'meta.json', two raw files (one each), 3 Collada files (dae + 2
        # textures). These files exist twice, one in the template store and one
        # in the instance store.
        file_cnt = dibbler.getNumFiles().data
        assert file_cnt == 2 * (1 + 2 * 1 + 1 * 3)

        # Update the fragments: keep first (raw, +0), delete second (dae, -3),
        # convert third from raw to dae (-1 + 3).
        assert dibbler.updateFragments('1', frags_new).ok

        # Record the current number of files in Dibbler.
        assert dibbler.getNumFiles().data == file_cnt + (0) + (-3) + (-1 + 3)

        # Verify that the first fragment is still intact, the second does not
        # exist anymore, and the third was updated.
        self.verifyRaw(ret.data['url'], frags_orig[0])
        with pytest.raises(AssertionError):
            self.verifyDae(ret.data['url'], frags_orig[1])
        self.verifyDae(ret.data['url'], frags_new[1])

    def test_deleteTemplate(self):
        """
        Add and remove a template.
        """
        dibbler = self.dibbler

        # Define two templates.
        frag_raw = getFragRaw()
        frag_dae = getFragDae()
        t11 = Template('name11', [], [frag_raw], [], [])
        t1 = Template('name1', [], [frag_dae], [], [])

        # Verify that Dibbler is pristine.
        assert dibbler.getNumFiles() == (True, None, 0)

        # Add- and verify the Raw template.
        ret = dibbler.addTemplate(t11)
        assert dibbler.getNumFiles() == (True, None, 2)
        self.verifyRaw(ret.data['url'], frag_raw)

        # Remove the Raw template and ensure it does not exist anymore.
        assert dibbler.deleteTemplate('name11').ok
        assert dibbler.getNumFiles() == (True, None, 0)
        with pytest.raises(AssertionError):
            self.verifyRaw(ret.data['url'], frag_raw)

        # Attempt to remove the Raw template once more. Dibbler must not delte
        # any files, albeit the call itself must succeed.
        assert dibbler.deleteTemplate('blah').ok
        assert dibbler.getNumFiles() == (True, None, 0)

        # Add- and verify the Raw- and Collada templates.
        del ret
        ret_raw = dibbler.addTemplate(t11)
        ret_dae = dibbler.addTemplate(t1)
        assert dibbler.getNumFiles() == (True, None, 6)
        self.verifyRaw(ret_raw.data['url'], frag_raw)
        self.verifyDae(ret_dae.data['url'], frag_dae)

        # Remove the Collada template whose name is a substring of the first.
        assert dibbler.deleteTemplate('name1') == (True, None, 4)
        assert dibbler.getNumFiles() == (True, None, 2)
        self.verifyRaw(ret_raw.data['url'], frag_raw)
        with pytest.raises(AssertionError):
            self.verifyRaw(ret_dae.data['url'], frag_dae)

        # Remove the Collada template again. No files must be deleted this
        # time.
        assert dibbler.deleteTemplate('name1') == (True, None, 0)
        assert dibbler.getNumFiles() == (True, None, 2)

        # Attempt to remove a non-existing template. The call must succeed but
        # Dibbler must not delete any files.
        assert dibbler.deleteTemplate('blah') == (True, None, 0)
        assert dibbler.getNumFiles() == (True, None, 2)

        # Delete the one remaining template (Raw template) and verify that
        # Dibbler does not hold any files anymore whatsoever afterwards.
        assert dibbler.deleteTemplate('name11') == (True, None, 2)
        assert dibbler.getNumFiles() == (True, None, 0)
        with pytest.raises(AssertionError):
            self.verifyRaw(ret_raw.data['url'], frag_raw)
        with pytest.raises(AssertionError):
            self.verifyRaw(ret_dae.data['url'], frag_dae)

    def test_deleteInstance(self):
        """
        Add and remove an instance.
        """
        dibbler = self.dibbler

        # Define two templates.
        frag_raw = getFragRaw()
        frag_dae = getFragDae()
        t_raw = Template('temp_raw', [], [frag_raw], [], [])
        t_dae = Template('temp_dae', [], [frag_dae], [], [])

        # Verify that Dibbler is empty.
        assert dibbler.getNumFiles() == (True, None, 0)

        # Add- and verify a Raw- and Collada template. The raw template 2 files
        # (meta.json plus model.json) whereas the Collada template has 4 files
        # (meta.json plus 1 dae file plus 2 textures).
        ret = dibbler.addTemplate(t_raw)
        assert dibbler.getNumFiles() == (True, None, 2)
        self.verifyRaw(ret.data['url'], frag_raw)
        ret = dibbler.addTemplate(t_dae)
        assert dibbler.getNumFiles() == (True, None, 2 + 4)
        self.verifyDae(ret.data['url'], frag_dae)

        # Spawn some instances.
        assert dibbler.spawnTemplate('temp_raw', '1').ok
        assert dibbler.spawnTemplate('temp_dae', '2').ok
        assert dibbler.spawnTemplate('temp_raw', '3').ok
        self.verifyRaw('{}/1'.format(config.url_instances), frag_raw)
        self.verifyDae('{}/2'.format(config.url_instances), frag_dae)
        self.verifyRaw('{}/3'.format(config.url_instances), frag_raw)
        base_cnt = (2 + 4) + 2 * 2 + 1 * 4
        assert dibbler.getNumFiles() == (True, None, base_cnt)

        # Remove a non-existing object. This must succeed but Dibbler must not
        # have removed any files.
        assert dibbler.deleteInstance('10') == (True, None, 0)
        assert dibbler.getNumFiles() == (True, None, base_cnt)

        # Remove the first Raw object. This must remove two files and leave the
        # other two instances intact.
        assert dibbler.deleteInstance('1') == (True, None, 2)
        base_cnt -= 2
        assert dibbler.getNumFiles() == (True, None, base_cnt)
        with pytest.raises(AssertionError):
            self.verifyRaw('{}/1'.format(config.url_instances), frag_raw)
        self.verifyDae('{}/2'.format(config.url_instances), frag_dae)
        self.verifyRaw('{}/3'.format(config.url_instances), frag_raw)

        # Remove the same instance again. This must succeed but Dibbler must
        # not remove any files.
        assert dibbler.deleteInstance('1') == (True, None, 0)

        # Remove the Collada instance. This must delete four files (meta.json +
        # dae + 2 textures).
        assert dibbler.deleteInstance('2') == (True, None, 4)
        base_cnt -= 4
        assert dibbler.getNumFiles() == (True, None, base_cnt)
        with pytest.raises(AssertionError):
            self.verifyRaw('{}/1'.format(config.url_instances), frag_raw)
        with pytest.raises(AssertionError):
            self.verifyDae('{}/2'.format(config.url_instances), frag_dae)
        self.verifyRaw('{}/3'.format(config.url_instances), frag_raw)

        # Remove the second Raw instance.
        assert dibbler.deleteInstance('3') == (True, None, 2)
        base_cnt -= 2
        assert dibbler.getNumFiles() == (True, None, base_cnt)
        with pytest.raises(AssertionError):
            self.verifyRaw('{}/1'.format(config.url_instances), frag_raw)
        with pytest.raises(AssertionError):
            self.verifyDae('{}/2'.format(config.url_instances), frag_dae)
        with pytest.raises(AssertionError):
            self.verifyRaw('{}/3'.format(config.url_instances), frag_raw)
