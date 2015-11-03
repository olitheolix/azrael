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
from azrael.aztypes import FragDae
from azrael.test.test import getFragNone, getTemplate, getFragRaw, getFragDae, getFragObj


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

    def verifyDae(self, url: str, aid, fragments: dict):
        """
        fixme: docu
        fixme: process the body in a loop

        Verify that ``url`` contains the Collada model.

        fixme: types of aid
        fixme: missing 'fragments' description

        :param str url: the URL where the Collada fragment is supposed to be.
        :param FragMeta mf: the fragment to compare it with.
        :return: None
        :raises: AssertionError if the fragment does not match.
        """
        # Convenience.
        name = aid
        ref = fragments[aid].fragdata

        # Fetch- the components of the Collada file.
        r_dae = self.dibbler.getFile(url + '/{}/model.dae'.format(name))
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
        downloaded = FragDae({'model.dae': dae, 'rgb1.png': rgb1, 'rgb2.jpg': rgb2})

        # Ensure the downloaded data matches the reference data.
        assert ref == downloaded

    def verifyObj(self, url: str, aid, fragments: dict):
        """
        fixme: docu
        fixme: process the body in a loop

        Verify that ``url`` contains the OBJ model.

        fixme: types of aid
        fixme: missing 'fragments' description

        :param str url: the URL where the Collada fragment is supposed to be.
        :param aid: Azrael's ID for the model to verify.
        :param dict fragments:
        :return: None
        :raises: AssertionError if the fragment does not match.
        """
        # Convenience.
        name = aid
        ref = fragments[aid].fragdata

        # Fetch- the components of the Collada file.
        r_obj = self.dibbler.getFile(url + '/{}/house.obj'.format(name))
        r_mtl = self.dibbler.getFile(url + '/{}/house.mtl'.format(name))
        r_jpg = self.dibbler.getFile(url + '/{}/house.jpg'.format(name))

        # Verify Dibbler could retrieve all components.
        assert r_obj.ok
        assert r_mtl.ok
        assert r_jpg.ok

        # Base64 encode the downloaded components and put them into a pristine
        # 'FragDae' instance.
        obj = base64.b64encode(r_obj.data).decode('utf8')
        mtl = base64.b64encode(r_mtl.data).decode('utf8')
        jpg = base64.b64encode(r_jpg.data).decode('utf8')
        downloaded = FragDae({'house.obj': obj, 'house.mtl': mtl, 'house.jpg': jpg})

        # Ensure the downloaded data matches the reference data.
        assert ref == downloaded

    def verifyRaw(self, url: str, aid: str, fragments: dict):
        """
        Verify that ``url`` contains the geometry of a RAW geometry.

        :param str url: the URL where the Collada fragment is supposed to be.
        :param FragMeta mf: the fragment to compare it with.
        :return: None
        :raises: AssertionError if the fragment does not match.
        """
        # Convenience.
        name = aid
        ref = fragments[aid].fragdata

        # Fetch- the data for the Raw fragment.
        ret = self.dibbler.getFile('{}/{}/model.json'.format(url, name))
        assert ret.ok
        model = base64.b64encode(ret.data).decode('utf8')
        assert model == ref.files['model.json']

    def test_addTemplate_with_no_fragments(self):
        """
        Add a template that has no fragments. This must still create a
        'meta.json' file (but nothing else).
        """
        # Create a Dibbler instance and flush all data.
        dibbler = self.dibbler
        assert dibbler.getNumFiles() == (True, None, 0)

        # Define a template for this test.
        t_raw = getTemplate('_templateEmpty')

        # Add the template and verify that the database now contains
        # exactly one file.
        ret = dibbler.addTemplate(t_raw)
        assert ret.ok
        assert dibbler.getNumFiles() == (True, None, 1)
        url = ret.data['url_frag']

        # Download the one- and only meta file and verify that it reports an
        # empty 'fragment' list.
        ret = self.dibbler.getFile('{}/meta.json'.format(url))
        assert ret.ok
        ret = json.loads(ret.data.decode('utf8'))
        assert ret['fragments'] == {}

    def test_addRawTemplate(self):
        """
        Add a raw template and fetch the individual files again afterwards.
        """
        # Create a Dibbler instance and flush all data.
        dibbler = self.dibbler
        assert dibbler.getNumFiles() == (True, None, 0)

        # Define a template for this test.
        frags = {'foo': getFragRaw()}
        t_raw = getTemplate('_templateEmpty', fragments=frags)

        # Add the first template and verify that the database now contains
        # exactly two files (a meta file, and the actual fragment data).
        ret = dibbler.addTemplate(t_raw)
        assert ret.ok
        assert dibbler.getNumFiles() == (True, None, 2)

        # Fetch- and verify the model.
        self.verifyRaw(ret.data['url_frag'], 'foo', frags)

    def test_addDaeTemplate(self):
        """
        Add a Collada template and fetch the individual files again afterwards.
        """
        dibbler = self.dibbler

        # Define a template for this test.
        frag = {'foo': getFragDae()}
        t_dae = getTemplate('_templateEmpty', fragments=frag)

        # Create a Dibbler instance and verify it is empty.
        assert dibbler.getNumFiles() == (True, None, 0)

        # Add the first template and verify the database now contains
        # exactly four files (a meta file, the DAE file, and two textures).
        ret = dibbler.addTemplate(t_dae)
        assert ret.ok
        assert dibbler.getNumFiles() == (True, None, 4)

        # Fetch- and verify the model.
        self.verifyDae(ret.data['url_frag'], 'foo', frag)

    def test_addObjTemplate(self):
        """
        Add an OBJ template and fetch the individual files again afterwards.
        """
        dibbler = self.dibbler

        # Define a template for this test.
        frag = {'foo': getFragObj()}
        t_dae = getTemplate('_templateEmpty', fragments=frag)

        # Create a Dibbler instance and verify it is empty.
        assert dibbler.getNumFiles() == (True, None, 0)

        # Add the first template and verify the database now contains
        # exactly four files (a meta file, the obj file, one textures, and one
        # .mtl file).
        ret = dibbler.addTemplate(t_dae)
        assert ret.ok
        assert dibbler.getNumFiles() == (True, None, 4)

        # Fetch- and verify the model.
        self.verifyObj(ret.data['url_frag'], 'foo', frag)

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
        frag_raw = {'fraw': getFragRaw()}
        frag_dae = {'fdae': getFragDae()}
        t_raw = getTemplate('t_name_raw', fragments=frag_raw)
        t_dae = getTemplate('t_name_dae', fragments=frag_dae)

        # Add the templates and verify there are 6 files in the DB now. The
        # first template has two files (1 meta.json plus 1 for the raw data)
        # and the second has 4 files (1 meta.json plus 3 for the Collada data).
        dibbler.addTemplate(t_raw)
        dibbler.addTemplate(t_dae)
        assert dibbler.getNumFiles() == (True, None, 2 + 4)

        # Spawn some instances.
        ret_1 = dibbler.spawnTemplate(1, t_raw.aid)
        ret_2 = dibbler.spawnTemplate(2, t_raw.aid)
        ret_3 = dibbler.spawnTemplate(3, t_dae.aid)
        assert ret_1.ok and ret_2.ok and ret_3.ok

        # Dibbler must now hold the original 6 files plus an additional 8 files
        # (2x2 for the two Raw instances, and another 4 for the one Collada
        # instance).
        assert dibbler.getNumFiles() == (True, None, (2 + 4) + (2 * 2 + 1 * 4))

        # Verify that all files are correct.
        self.verifyRaw(ret_1.data['url_frag'], 'fraw', frag_raw)
        self.verifyRaw(ret_2.data['url_frag'], 'fraw', frag_raw)
        self.verifyDae(ret_3.data['url_frag'], 'fdae', frag_dae)

        # Attempt to spawn a non-existing template. This must fail and the
        # number of files in Dibbler must not change.
        assert not dibbler.spawnTemplate(10, 'blah').ok
        assert dibbler.getNumFiles() == (True, None, (2 + 4) + (2 * 2 + 1 * 4))

    def test_updateFragments_all(self):
        """
        Spawn a template and update all its fragments.
        """
        dibbler = self.dibbler

        # The original template has two fragments, and we will update one of
        # them.
        frags_orig = {'o1': getFragRaw(),
                      'o2': getFragDae()}
        frags_new = {'o1': getFragDae()}
        t1 = getTemplate('t1', fragments=frags_orig)

        # Add the template and spawn two instances.
        assert dibbler.addTemplate(t1).ok
        ret_11 = dibbler.spawnTemplate(11, t1.aid)
        ret_2 = dibbler.spawnTemplate(2, t1.aid)
        assert ret_11.ok and ret_2.ok

        self.verifyRaw(ret_11.data['url_frag'], 'o1', frags_orig)
        self.verifyDae(ret_11.data['url_frag'], 'o2', frags_orig)
        self.verifyRaw(ret_2.data['url_frag'], 'o1', frags_orig)
        self.verifyDae(ret_2.data['url_frag'], 'o2', frags_orig)

        # Attempt to change the fragment of a non-existing object.
        assert not dibbler.updateFragments(20, frags_new).ok

        # Attempt to change the fragment of another non-existing object, but
        # the object ID of this one is '1', which means it is available at
        # '/somewhere/1/...'. However, an object at '/somewhere/11/...' already
        # exists, and without the trailing '/' the first would be a sub-string
        # of the latter. The update method must therefore take care to properly
        # test for existence, especially since directories, internally, do not
        # have a trailing '/'.
        assert not dibbler.updateFragments(1, frags_new).ok

        # The previous attempts to modify fragments of non-existing objectst
        # must not have modified the fragments.
        self.verifyRaw(ret_11.data['url_frag'], 'o1', frags_orig)
        self.verifyDae(ret_11.data['url_frag'], 'o2', frags_orig)
        self.verifyRaw(ret_2.data['url_frag'], 'o1', frags_orig)
        self.verifyDae(ret_2.data['url_frag'], 'o2', frags_orig)

        # Change the first fragments of the first object.
        assert dibbler.updateFragments(11, frags_new).ok

        # Verify that only the first fragment of the '11' object has changed.
        self.verifyDae(ret_11.data['url_frag'], 'o1', frags_new)
        self.verifyDae(ret_11.data['url_frag'], 'o2', frags_orig)
        self.verifyRaw(ret_2.data['url_frag'], 'o1', frags_orig)
        self.verifyDae(ret_2.data['url_frag'], 'o2', frags_orig)

    def test_updateFragments_partial(self):
        """
        Simliar to previous test in the sense that it spawns and updates
        fragments. However, this time some fragments will be removed
        altogether, instead of just being updated.
        """
        dibbler = self.dibbler

        # The original template has the following three fragments:
        frags_orig = {
            'f1': getFragRaw(),
            'f2': getFragDae(),
            'f3': getFragRaw()
        }
        t1 = getTemplate('t1', fragments=frags_orig)

        # The fragment update will use the following data. It translates to
        # keeping the first intact, removing the second, and modifying the
        # fragment type for the third one.
        frags_new = {
            'f2': getFragNone(),
            'f3': getFragDae(),
        }

        # Add the template, spawn one instance, and verify all fragments.
        assert dibbler.addTemplate(t1).ok
        ret = dibbler.spawnTemplate(1, t1.aid)
        assert ret.ok
        self.verifyRaw(ret.data['url_frag'], 'f1', frags_orig)
        self.verifyDae(ret.data['url_frag'], 'f2', frags_orig)
        self.verifyRaw(ret.data['url_frag'], 'f3', frags_orig)

        # Record the current number of files in Dibbler. There must be one
        # 'meta.json', two raw files (one each), 3 Collada files (dae + 2
        # textures). These files exist twice, once in the template store and
        # once in the instance store.
        file_cnt = dibbler.getNumFiles().data
        assert file_cnt == 2 * (1 + 2 * 1 + 1 * 3)

        # Update the fragments: keep first (raw, +0), delete second (dae, -3),
        # convert third from raw to dae (-1 + 3).
        assert dibbler.updateFragments(1, frags_new).ok

        # Record the current number of files in Dibbler.
        assert dibbler.getNumFiles().data == file_cnt + (0) + (-3) + (-1 + 3)

        # Verify that the first fragment is still intact, the second does not
        # exist anymore, and the third was updated.
        self.verifyRaw(ret.data['url_frag'], 'f1', frags_orig)
        with pytest.raises(AssertionError):
            self.verifyDae(ret.data['url_frag'], 'f2', frags_orig)
        self.verifyDae(ret.data['url_frag'], 'f3', frags_new)

    def test_deleteTemplate(self):
        """
        Add two templates and then delete them. This functions also tests some
        corner cases where the delete-request is a substring of another
        template.
        """
        dibbler = self.dibbler

        # Define two templates.
        frag_raw = {'foo': getFragRaw()}
        frag_dae = {'bar': getFragDae()}
        t1 = getTemplate('name1', fragments=frag_dae)
        t11 = getTemplate('name11', fragments=frag_raw)

        # Verify that Dibbler's database is pristine.
        assert dibbler.getNumFiles() == (True, None, 0)

        # Add- and verify the Raw template.
        ret = dibbler.addTemplate(t11)
        assert dibbler.getNumFiles() == (True, None, 2)
        self.verifyRaw(ret.data['url_frag'], 'foo', frag_raw)

        # Remove the Raw template and ensure it does not exist anymore.
        assert dibbler.deleteTemplate('name11').ok
        assert dibbler.getNumFiles() == (True, None, 0)
        with pytest.raises(AssertionError):
            self.verifyRaw(ret.data['url_frag'], 'foo', frag_raw)

        # Attempt to remove the Raw template once more. Dibbler must not delete
        # any files, albeit the call itself must succeed.
        assert dibbler.deleteTemplate('blah').ok
        assert dibbler.getNumFiles() == (True, None, 0)

        # Add- and verify the Raw- and Collada templates.
        del ret
        ret_raw = dibbler.addTemplate(t11)
        ret_dae = dibbler.addTemplate(t1)
        assert dibbler.getNumFiles() == (True, None, 6)
        self.verifyRaw(ret_raw.data['url_frag'], 'foo', frag_raw)
        self.verifyDae(ret_dae.data['url_frag'], 'bar', frag_dae)

        # Remove the Collada template whose name is a substring of the first.
        assert dibbler.deleteTemplate('name1') == (True, None, 4)
        assert dibbler.getNumFiles() == (True, None, 2)
        self.verifyRaw(ret_raw.data['url_frag'], 'foo', frag_raw)
        with pytest.raises(AssertionError):
            self.verifyRaw(ret_dae.data['url_frag'], 'bar', frag_dae)

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
            self.verifyRaw(ret_raw.data['url_frag'], 'foo', frag_raw)
        with pytest.raises(AssertionError):
            self.verifyRaw(ret_dae.data['url_frag'], 'bar', frag_dae)

    def test_deleteInstance(self):
        """
        Add and remove an instance.
        """
        dibbler = self.dibbler

        # Define two templates.
        frag_raw = {'foo': getFragRaw()}
        frag_dae = {'bar': getFragDae()}
        t_raw = getTemplate('temp_raw', fragments=frag_raw)
        t_dae = getTemplate('temp_dae', fragments=frag_dae)

        # Verify that Dibbler is empty.
        assert dibbler.getNumFiles() == (True, None, 0)

        # Add- and verify a Raw- and Collada template. The raw template 2 files
        # (meta.json plus model.json) whereas the Collada template has 4 files
        # (meta.json plus 1 dae file plus 2 textures).
        ret = dibbler.addTemplate(t_raw)
        assert dibbler.getNumFiles() == (True, None, 2)
        self.verifyRaw(ret.data['url_frag'], 'foo', frag_raw)
        ret = dibbler.addTemplate(t_dae)
        assert dibbler.getNumFiles() == (True, None, 2 + 4)
        self.verifyDae(ret.data['url_frag'], 'bar', frag_dae)

        # Spawn some instances.
        assert dibbler.spawnTemplate(1, 'temp_raw').ok
        assert dibbler.spawnTemplate(2, 'temp_dae').ok
        assert dibbler.spawnTemplate(3, 'temp_raw').ok
        self.verifyRaw('{}/1'.format(config.url_instances), 'foo', frag_raw)
        self.verifyDae('{}/2'.format(config.url_instances), 'bar', frag_dae)
        self.verifyRaw('{}/3'.format(config.url_instances), 'foo', frag_raw)
        base_cnt = (2 + 4) + 2 * 2 + 1 * 4
        assert dibbler.getNumFiles() == (True, None, base_cnt)

        # Remove a non-existing object. This must succeed but Dibbler must not
        # have removed any files.
        assert dibbler.deleteInstance(10) == (True, None, 0)
        assert dibbler.getNumFiles() == (True, None, base_cnt)

        # Remove the first Raw object. This must remove two files and leave the
        # other two instances intact.
        assert dibbler.deleteInstance(1) == (True, None, 2)
        base_cnt -= 2
        assert dibbler.getNumFiles() == (True, None, base_cnt)
        with pytest.raises(AssertionError):
            self.verifyRaw('{}/1'.format(config.url_instances), 'foo', frag_raw)
        self.verifyDae('{}/2'.format(config.url_instances), 'bar', frag_dae)
        self.verifyRaw('{}/3'.format(config.url_instances), 'foo', frag_raw)

        # Remove the same instance again. This must succeed but Dibbler must
        # not remove any files.
        assert dibbler.deleteInstance(1) == (True, None, 0)

        # Remove the Collada instance. This must delete four files (meta.json +
        # dae + 2 textures).
        assert dibbler.deleteInstance(2) == (True, None, 4)
        base_cnt -= 4
        assert dibbler.getNumFiles() == (True, None, base_cnt)
        with pytest.raises(AssertionError):
            self.verifyRaw('{}/1'.format(config.url_instances), 'foo', frag_raw)
        with pytest.raises(AssertionError):
            self.verifyDae('{}/2'.format(config.url_instances), 'bar', frag_dae)
        self.verifyRaw('{}/3'.format(config.url_instances), 'foo', frag_raw)

        # Remove the second Raw instance.
        assert dibbler.deleteInstance(3) == (True, None, 2)
        base_cnt -= 2
        assert dibbler.getNumFiles() == (True, None, base_cnt)
        with pytest.raises(AssertionError):
            self.verifyRaw('{}/1'.format(config.url_instances), 'foo', frag_raw)
        with pytest.raises(AssertionError):
            self.verifyDae('{}/2'.format(config.url_instances), 'bar', frag_dae)
        with pytest.raises(AssertionError):
            self.verifyRaw('{}/3'.format(config.url_instances), 'foo', frag_raw)

    def test_get_put_basic(self):
        """
        Put files into Dibbler and retrieve them.
        """
        dibbler = self.dibbler
        assert dibbler.getNumFiles() == (True, None, 0)

        files = {'foo': b'foo', 'dir/bar': b'bar'}

        # Put two files into dibbler. One is in the root directory and the
        # other in a sub-folder.
        assert dibbler.put(files).ok
        assert dibbler.getNumFiles() == (True, None, len(files))

        # Fetch the two files and verify their content.
        ret = dibbler.get(['foo', 'dir/bar'])
        assert ret.ok and ret.data == files

        # Fetch only one file.
        ret = dibbler.get(['dir/bar'])
        assert ret.ok and ret.data == {'dir/bar': files['dir/bar']}

        # Attempt to fetch a non-existing file. This must not return an error.
        # It must also not return any files.
        ret = dibbler.get(['blah'])
        assert ret.ok and ret.data == {}

        # Request two files. One exists, the other does not.
        ret = dibbler.get(['foo', 'blah'])
        assert ret.ok and ret.data == {'foo': files['foo']}

    def test_get_put_overwrite(self):
        """
        Overwrite existing files.
        """
        dibbler = self.dibbler
        assert dibbler.getNumFiles() == (True, None, 0)

        # Put two files into Dibbler. One in the root directory, and one in a
        # sub-folder.
        files = {'foo': b'foo', 'bar': b'bar'}
        assert dibbler.put(files).ok
        assert dibbler.getNumFiles() == (True, None, len(files))

        # Fetch the two files. Then verify their content.
        ret = dibbler.get(['foo', 'bar'])
        assert ret.ok and ret.data == files

        # Overwrite the content of 'foo'. Then fetch it and verify that it has
        # the new content. Also check that the number of files in the database
        # is still only 2.
        new_file = {'foo': b'test'}
        assert dibbler.put(new_file).ok
        assert dibbler.get(['foo']) == (True, None, new_file)
        assert dibbler.getNumFiles() == (True, None, 2)

    def test_copy_individual(self):
        """
        Create one file, then copy it to another location.
        """
        dibbler = self.dibbler
        assert dibbler.getNumFiles() == (True, None, 0)

        # Put one file into Dibbler.
        assert dibbler.put({'src': b'src'}).ok
        assert dibbler.getNumFiles() == (True, None, 1)

        # Copy the file. Verify their contents match.
        assert dibbler.copy({'src': 'dst'}) == (True, None, 1)
        assert dibbler.getNumFiles() == (True, None, 2)
        ret = dibbler.get(['src', 'dst'])
        assert ret.ok
        assert ret.data == {'src': b'src', 'dst': b'src'}

        # It is permissible to copy a file onto itself.
        assert dibbler.copy({'src': 'src'}).ok
        assert dibbler.getNumFiles() == (True, None, 2)
        assert dibbler.get(['src']) == (True, None, {'src': b'src'})

        # If a non-existing file should be copied then the operation must also
        # succeed, yet nothing must be copied.
        assert dibbler.copy({'blah': 'xyz'}).ok
        assert dibbler.getNumFiles() == (True, None, 2)

        # Copy two files at once. To make the test clearer we will first
        # overwrite the 'dst' file with new content to make it different from
        # 'src'.
        assert dibbler.put({'dst': b'dst'}).ok
        assert dibbler.copy({'src': '/newdir/src', 'dst': '/newdir/dst'})
        ret = dibbler.get(['src', 'dst', '/newdir/src', '/newdir/dst'])
        assert ret.ok and ret.data == {
            'src': b'src',
            'dst': b'dst',
            '/newdir/src': b'src',
            '/newdir/dst': b'dst'
        }

    def test_remove_files_individual(self):
        """
        Create one file, then copy it to another location.
        """
        dibbler = self.dibbler
        assert dibbler.getNumFiles() == (True, None, 0)

        # Attempt to remove a non-existing file. This must succeed but the
        # number of removed files must be zero.
        assert dibbler.remove(['foo']) == (True, None, 0)

        # Add two files, then remove them individually.
        files = {'foo': b'foo', 'bar': b'bar'}
        assert dibbler.put(files).ok
        assert dibbler.getNumFiles() == (True, None, 2)
        assert dibbler.remove(['foo']) == (True, None, 1)
        assert dibbler.getNumFiles() == (True, None, 1)
        assert dibbler.remove(['bar']) == (True, None, 1)
        assert dibbler.getNumFiles() == (True, None, 0)

        # Remove the same file multiple times.
        assert dibbler.put(files).ok
        assert dibbler.getNumFiles() == (True, None, 2)
        assert dibbler.remove(['foo']) == (True, None, 1)
        assert dibbler.getNumFiles() == (True, None, 1)
        assert dibbler.remove(['foo']) == (True, None, 0)
        assert dibbler.getNumFiles() == (True, None, 1)

        # Remove two existing files, plus one non-existing file, with a single
        # call.
        assert dibbler.put(files).ok
        assert dibbler.getNumFiles() == (True, None, 2)
        assert dibbler.remove(['foo', 'bar', 'blah']) == (True, None, 2)
        assert dibbler.getNumFiles() == (True, None, 0)

    def test_filename_sanitiser(self):
        """
        All file names must be sane {a-zA-Z0-9_.}
        """
        dibbler = self.dibbler
        assert dibbler.isValidFileName('/some/where/fooBAR_3.txt')
        assert not dibbler.isValidFileName('/some/where/fooBAR_3*.txt')

    def test_invalid_copy_arguments(self):
        """
        All copy targets must be unique. For instance, the argument
        dibbler.copy({'file1': 'dst', 'file2': dst}) is not allowed because
        both files would be copied to 'dst' and it is not clear which one takes
        precedence.
        """
        dibbler = self.dibbler
        assert dibbler.getNumFiles() == (True, None, 0)

        # Create two files.
        files = {'foo': b'foo', 'bar': b'bar'}
        assert dibbler.put(files).ok

        # Attempt to copy both files to the same target name.
        assert not dibbler.copy({'foo': 'blah', 'bar': 'blah'}).ok

    def test_remove_directory(self):
        """
        Remove all files with common prefix.
        """
        dibbler = self.dibbler
        assert dibbler.getNumFiles() == (True, None, 0)

        # Create files a small directory hierarchy.
        files = {
            'dir1/foo1': b'foo1',
            'dir1/bar1': b'bar1',
            'dir2/foo2': b'foo2',
            'dir2/bar2': b'bar2',
            'dir2/sub/foo3': b'foo3',
            'dir2/sub/bar3': b'bar3'
        }
        assert dibbler.put(files).ok
        assert dibbler.getNumFiles() == (True, None, len(files))

        # Attempt to remove a non-existing directory. The call must succeed yet
        # nothing must have been deleted.
        assert dibbler.removeDirs(['blah']) == (True, None, 0)
        assert dibbler.getNumFiles() == (True, None, len(files))

        # Attempt to remove all files in the non-existent 'dir' directory (not
        # that this is a prefix for the 'dir1/' and 'dir2' directories, and
        # Dibbler must ensure that these are _not_ deleted.
        assert dibbler.removeDirs(['dir']) == (True, None, 0)
        assert dibbler.getNumFiles() == (True, None, len(files))

        # Delete all files in dir1. Then verify the number of files.
        assert dibbler.removeDirs(['dir1']) == (True, None, 2)
        assert dibbler.getNumFiles() == (True, None, len(files) - 2)

        # Delete all files in dir2. Then verify that there are no more files
        # left.
        assert dibbler.removeDirs(['dir2']) == (True, None, 4)
        assert dibbler.getNumFiles() == (True, None, 0)

        # Populate the database again.
        assert dibbler.put(files).ok
        assert dibbler.getNumFiles() == (True, None, len(files))

        # Delete 'dir2/sub'.
        assert dibbler.removeDirs(['dir2/sub']) == (True, None, 2)
        assert dibbler.getNumFiles() == (True, None, len(files) - 2)
        fnames = ['dir1/foo1', 'dir1/bar1', 'dir2/foo2', 'dir2/bar2']
        ret = dibbler.get(fnames)
        assert ret.ok
        for fname in fnames:
            ret.data[fname] == files[fname]

        # Reset the database and populate it again.
        self.dibbler.reset()
        assert dibbler.put(files).ok
        assert dibbler.getNumFiles() == (True, None, len(files))

        # As before, delete the 'dir2/sub' directory, but this time supply a
        # trailing a slash. The result must be the same.
        assert dibbler.removeDirs(['dir2/sub/']) == (True, None, 2)
        assert dibbler.getNumFiles() == (True, None, len(files) - 2)
        fnames = ['dir1/foo1', 'dir1/bar1', 'dir2/foo2', 'dir2/bar2']
        ret = dibbler.get(fnames)
        assert ret.ok
        for fname in fnames:
            ret.data[fname] == files[fname]
