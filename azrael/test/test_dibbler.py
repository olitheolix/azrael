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
import os
import json
import time
import shutil
import base64
import pytest
import pickle
import tornado.web
import azrael.clerk
import azrael.dibbler
import urllib.request
import tornado.testing

import numpy as np
import unittest.mock as mock
import azrael.config as config

from IPython import embed as ipshell
from azrael.types import Template, RetVal, FragDae, FragRaw, MetaFragment
from azrael.test.test import createFragRaw, createFragDae


class TestDibbler:
    @classmethod
    def setup_class(cls):
        pass

    @classmethod
    def teardown_class(cls):
        pass

    def setup_method(self, method):
        self.dibbler = azrael.dibbler.Dibbler()
        self.dibbler.reset()
        assert self.dibbler.getNumFiles() == (True, None, 0)
        
    def teardown_method(self, method):
        self.dibbler.reset()
        assert self.dibbler.getNumFiles() == (True, None, 0)

    def verifyDae(self, url, ref):
        name = ref.name
        ref = ref.data

        # Fetch- and verify the file.
        ret = self.dibbler.getFile(url + '/{name}/{name}'.format(name=name))
        assert ret.ok
        assert ret.data == ref.dae

        ret = self.dibbler.getFile(url + '/{}/rgb1.png'.format(name))
        assert ret.ok
        assert ret.data == ref.rgb['rgb1.png']
        ret = self.dibbler.getFile(url + '/{}/rgb2.jpg'.format(name))
        assert ret.ok
        assert ret.data == ref.rgb['rgb2.jpg']
        
    def verifyRaw(self, url, ref):
        name = ref.name
        ref = ref.data
        
        # Fetch- and verify the file.
        ret = self.dibbler.getFile('{}/{}/model.json'.format(url, name))
        assert ret.ok
        ret = json.loads(ret.data.decode('utf8'))
        assert ret['uv'] == ref.uv
        assert ret['rgb'] == ref.rgb
        assert ret['vert'] == ref.vert
        
    def test_addRawTemplate(self):
        """
        Add a raw template and fetch the individual files again afterwards.
        """
        # Create a Dibbler instance and flush all data.
        dibbler = self.dibbler
        assert dibbler.getNumFiles() == (True, None, 0)

        # Define a template for this test.
        frag = [MetaFragment('NoNameRaw', 'raw', createFragRaw())]
        t_raw = Template('_templateNone', [0, 1, 1, 1], frag, [], [])

        # Add the first template and verify that the database now contains
        # exactly two files (a meta file, and the actual fragment data).
        ret = dibbler.addTemplate(t_raw)
        assert dibbler.getNumFiles() == (True, None, 2)
        
        # Fetch- and verify the model.
        self.verifyRaw(ret.data['url'], frag[0])

    def test_addDaeTemplate(self):
        """
        Add a Collada template and fetch the individual files again afterwards.
        """
        dibbler = self.dibbler

        # Define a template for this test.
        frag = [MetaFragment('NoNameDae', 'dae', createFragDae())]
        t_dae = Template('_templateNone', [0, 1, 1, 1], frag, [], [])

        # Create a Dibbler instance and flush all data.
        assert dibbler.getNumFiles() == (True, None, 0)

        # Add the first template and verify that the database now contains
        # extactly fourc files (a meta file, the DAE file, and two textures).
        ret = dibbler.addTemplate(t_dae)
        assert dibbler.getNumFiles() == (True, None, 4)
        
        # Fetch- and verify the model.
        self.verifyDae(ret.data['url'], frag[0])

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
        frag_raw = MetaFragment('fragname_raw', 'raw', createFragRaw())
        frag_dae = MetaFragment('fragname_dae', 'dae', createFragDae())
        t_raw = Template('t_name_raw', [0, 1, 1, 1], [frag_raw], [], [])
        t_dae = Template('t_name_dae', [0, 1, 1, 1], [frag_dae], [], [])

        # Add the templates and verify there are 6 files in the DB now (2 for
        # the Raw fragment, and 4 for the Collada fragment).
        dibbler.addTemplate(t_raw)
        dibbler.addTemplate(t_dae)
        assert dibbler.getNumFiles() == (True, None, 2 + 4)

        # Spawn some instances.
        ret_1 = dibbler.spawnTemplate(t_raw.name, '1')
        ret_2 = dibbler.spawnTemplate(t_raw.name, '2')
        ret_3 = dibbler.spawnTemplate(t_dae.name, '3')
        assert ret_1.ok and ret_2.ok and ret_3.ok

        # Dibbler must now hold the original 6 files plus an additional 8 files
        # (2x2 for the two Raw instances, and another 4 for the one Collada
        # instance).
        assert dibbler.getNumFiles() == (True, None, (2 + 4) + (2 * 2 + 4))

        # Verify that all files are correct.
        self.verifyRaw(ret_1.data['url'], frag_raw)
        self.verifyRaw(ret_2.data['url'], frag_raw)
        self.verifyDae(ret_3.data['url'], frag_dae)

        # Attempt to spawn a non-existing template. This must fail and the
        # number of files in Dibbler must not change.
        assert not dibbler.spawnTemplate('blah', '10').ok
        assert dibbler.getNumFiles() == (True, None, (2 + 4) + (2 * 2 + 4))

    def test_updateTemplate(self):
        """
        fixme: docu
        """
        dibbler = self.dibbler

        # Create a Template with a Raw fragment.
        frag_orig = MetaFragment('bar', 'raw', createFragRaw())
        t1 = Template('t1', [1, 2, 3, 4], [frag_orig], [], [])

        # Add the template and spawn two instances.
        assert dibbler.addTemplate(t1).ok
        ret_11 = dibbler.spawnTemplate(t1.name, '11')
        ret_2 = dibbler.spawnTemplate(t1.name, '2')
        assert ret_11.ok and ret_2.ok

        self.verifyRaw(ret_11.data['url'], frag_orig)
        self.verifyRaw(ret_2.data['url'], frag_orig)

        # Create a replacement fragment.
        frag_new = MetaFragment('bar', 'raw', createFragRaw())

        # Attempt to change the fragment of a non-existing object.
        ret = dibbler.updateFragments('20', [frag_new])
        assert not ret.ok

        # Attempt to change the fragment of another non-existing object, but
        # the object ID of this one is '1', which means it is available at
        # '/somewhere/1/...'. However, an object at '/somewhere/11/...' already
        # exists, and without the trailing '/' the first would be a sub-string
        # of the latter. The update method must therefore take care to properly
        # test for existence, especially since directories, internally, do not
        # have a trailing '/'.
        ret = dibbler.updateFragments('1', [frag_new])
        assert not ret.ok

        # The old fragments must not have changed.
        self.verifyRaw(ret_11.data['url'], frag_orig)
        self.verifyRaw(ret_2.data['url'], frag_orig)

        # Change the fragment models for the first object.
        ret = dibbler.updateFragments('11', [frag_new])
        assert ret.ok

        # Verify that the models are correct.
        self.verifyRaw(ret_11.data['url'], frag_new)
        self.verifyRaw(ret_2.data['url'], frag_orig)

    def test_deleteTemplate(self):
        """
        Add and remove a template.
        """
        dibbler = self.dibbler

        # Define two templates.
        frag_raw = [MetaFragment('frag_raw', 'raw', createFragRaw())]
        frag_dae = [MetaFragment('frag_dae', 'dae', createFragDae())]
        t11 = Template('name11', [0, 1, 1, 1], frag_raw, [], [])
        t1 = Template('name1', [0, 1, 1, 1], frag_dae, [], [])

        # Verify that Dibbler is pristine.
        assert dibbler.getNumFiles() == (True, None, 0)

        # Add- and verify the Raw template.
        ret = dibbler.addTemplate(t11)
        assert dibbler.getNumFiles() == (True, None, 2)
        self.verifyRaw(ret.data['url'], frag_raw[0])

        # Remove the Raw template and ensure it does not exist anymore.
        assert dibbler.removeTemplate('name11').ok
        assert dibbler.getNumFiles() == (True, None, 0)
        with pytest.raises(AssertionError):
            self.verifyRaw(ret.data['url'], frag_raw[0])

        # Attempt to remove the Raw template once more. Dibbler must not delte
        # any files, albeit the call itself must succeed.
        assert dibbler.removeTemplate('blah').ok
        assert dibbler.getNumFiles() == (True, None, 0)

        # Add- and verify the Raw- and Collada templates.
        del ret
        ret_raw = dibbler.addTemplate(t11)
        ret_dae = dibbler.addTemplate(t1)
        assert dibbler.getNumFiles() == (True, None, 6)
        self.verifyRaw(ret_raw.data['url'], frag_raw[0])
        self.verifyDae(ret_dae.data['url'], frag_dae[0])

        # Remove the Collada template whose name is a substring of the first.
        assert dibbler.removeTemplate('name1') == (True, None, 4)
        assert dibbler.getNumFiles() == (True, None, 2)
        self.verifyRaw(ret_raw.data['url'], frag_raw[0])
        with pytest.raises(AssertionError):
            self.verifyRaw(ret_dae.data['url'], frag_dae[0])

        # Remove the Collada template again. No files must be deleted this time.
        assert dibbler.removeTemplate('name1') == (True, None, 0)
        assert dibbler.getNumFiles() == (True, None, 2)

        # Attempt to remove a non-existing template. The call must succeed but
        # Dibbler must not delete any files.
        assert dibbler.removeTemplate('blah') == (True, None, 0)
        assert dibbler.getNumFiles() == (True, None, 2)

        # Delete the one remaining template (Raw template) and verify that
        # Dibbler does not hold any files anymore whatsoever afterwards.
        assert dibbler.removeTemplate('name11') == (True, None, 2)
        assert dibbler.getNumFiles() == (True, None, 0)
        with pytest.raises(AssertionError):
            self.verifyRaw(ret_raw.data['url'], frag_raw[0])
        with pytest.raises(AssertionError):
            self.verifyRaw(ret_dae.data['url'], frag_dae[0])

    def test_deleteInstance(self):
        """
        Add and remove an instance.
        """
        dibbler = self.dibbler

        # Define two templates.
        frag_raw = [MetaFragment('frag_raw', 'raw', createFragRaw())]
        frag_dae = [MetaFragment('frag_dae', 'dae', createFragDae())]
        t_raw = Template('temp_raw', [0, 1, 1, 1], frag_raw, [], [])
        t_dae = Template('temp_dae', [0, 1, 1, 1], frag_dae, [], [])

        # Verify that Dibbler is empty.
        assert dibbler.getNumFiles() == (True, None, 0)

        # Add- and verify a Raw- and Collada template.
        ret = dibbler.addTemplate(t_raw)
        assert dibbler.getNumFiles() == (True, None, 2)
        self.verifyRaw(ret.data['url'], frag_raw[0])
        ret = dibbler.addTemplate(t_dae)
        assert dibbler.getNumFiles() == (True, None, 2 + 4)
        self.verifyDae(ret.data['url'], frag_dae[0])

        # Spawn some instances.
        assert dibbler.spawnTemplate('temp_raw', '1').ok
        assert dibbler.spawnTemplate('temp_dae', '2').ok
        assert dibbler.spawnTemplate('temp_raw', '3').ok
        self.verifyRaw('/instances/1', frag_raw[0])
        self.verifyDae('/instances/2', frag_dae[0])
        self.verifyRaw('/instances/3', frag_raw[0])
        base_cnt = (2 + 4) + 2 * 2 + 4
        assert dibbler.getNumFiles() == (True, None, base_cnt)

        # Remove a non-existing object. This must succeed but Dibbler must not
        # have removed any files.
        assert dibbler.removeInstance('10') == (True, None, 0)
        assert dibbler.getNumFiles() == (True, None, base_cnt)

        # Remove the first Raw object. This must remove two files and leave the
        # other two instances intact.
        assert dibbler.removeInstance('1') == (True, None, 2)
        base_cnt -= 2
        assert dibbler.getNumFiles() == (True, None, base_cnt)
        with pytest.raises(AssertionError):
            self.verifyRaw('/instances/1', frag_raw[0])
        self.verifyDae('/instances/2', frag_dae[0])
        self.verifyRaw('/instances/3', frag_raw[0])

        # Remove the same instance again. This must succeed but Dibbler must
        # not remove any files.
        assert dibbler.removeInstance('1') == (True, None, 0)

        # Remove the collada instance. This must delete four files.
        assert dibbler.removeInstance('2') == (True, None, 4)
        base_cnt -= 4
        assert dibbler.getNumFiles() == (True, None, base_cnt)
        with pytest.raises(AssertionError):
            self.verifyRaw('/instances/1', frag_raw[0])
        with pytest.raises(AssertionError):
            self.verifyDae('/instances/2', frag_dae[0])
        self.verifyRaw('/instances/3', frag_raw[0])

        # Remove the second Raw instance.
        assert dibbler.removeInstance('3') == (True, None, 2)
        base_cnt -= 2
        assert dibbler.getNumFiles() == (True, None, base_cnt)
        with pytest.raises(AssertionError):
            self.verifyRaw('/instances/1', frag_raw[0])
        with pytest.raises(AssertionError):
            self.verifyDae('/instances/2', frag_dae[0])
        with pytest.raises(AssertionError):
            self.verifyRaw('/instances/3', frag_raw[0])
