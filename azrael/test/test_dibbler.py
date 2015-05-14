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

"""
"""

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


# fixme: delete this section once new tests are complete.
# class TestDibbler(tornado.testing.AsyncHTTPTestCase):
#     def test_remove_template(self):
#         """
#         Add a template, verify it exists, remove it, verify it does not exist
#         anymore.
#         """
#         self.resetDibbler()

#         # Create two Templates with one Raw fragment each.
#         frags = [MetaFragment('bar', 'raw', createFragRaw())]
#         t1 = Template('t1', [1, 2, 3, 4], frags, [], [])
#         t2 = Template('t2', [5, 6, 7, 8], frags, [], [])
#         del frags

#         def _templateOk(url, frag):
#             try:
#                 # Load the meta file for this template which must contain a
#                 # list of all fragment names.
#                 ret = self.downloadJSON(url + '/meta.json')
#                 assert ret['fragments'] == {'bar': 'raw'}

#                 # Download the model and verify it matches the one we uploaded.
#                 url = url + '/bar/model.json'
#                 assert self.downloadFragRaw(url) == frag.data
#             except AssertionError:
#                 return False
#             return True

#         # Add both templates and verify they now exist.
#         ret1 = self.addTemplate(t1)
#         ret2 = self.addTemplate(t2)
#         assert ret1.ok
#         assert ret2.ok
#         assert _templateOk(ret1.data['url'], t1.fragments[0])
#         assert _templateOk(ret2.data['url'], t2.fragments[0])

#         # Attempt to delete non-existing template.
#         req = {'cmd': 'del_template', 'data': 'blah'}
#         assert not self.sendRequest(req).ok
#         assert _templateOk(ret1.data['url'], t1.fragments[0])
#         assert _templateOk(ret2.data['url'], t2.fragments[0])

#         # Delete second template.
#         req = {'cmd': 'del_template', 'data': t2.name}
#         assert self.sendRequest(req).ok
#         assert _templateOk(ret1.data['url'], t1.fragments[0])
#         assert not _templateOk(ret2.data['url'], t2.fragments[0])

#         # Delete first template.
#         req = {'cmd': 'del_template', 'data': t1.name}
#         assert self.sendRequest(req).ok
#         assert not _templateOk(ret1.data['url'], t1.fragments[0])
#         assert not _templateOk(ret2.data['url'], t2.fragments[0])

#         # Attempt to delete the first template again.
#         req = {'cmd': 'del_template', 'data': t1.name}
#         assert not self.sendRequest(req).ok
#         assert not _templateOk(ret1.data['url'], t1.fragments[0])
#         assert not _templateOk(ret2.data['url'], t2.fragments[0])

#         print('Test passed')

#     def test_remove_instance(self):
#         """
#         Spawn an instance, verify it exists, remove it, and verify it does not
#         exist anymore.
#         """
#         self.resetDibbler()

#         # Create a Templates with a Raw fragment.
#         frags = [MetaFragment('bar', 'raw', createFragRaw())]
#         t1 = Template('t1', [1, 2, 3, 4], frags, [], [])
#         del frags

#         def _instanceOk(url, frag):
#             try:
#                 # Load the meta file for this template which must contain a
#                 # list of  all fragment names.
#                 ret = self.downloadJSON(url + '/meta.json')
#                 assert ret['fragments'] == {'bar': 'raw'}

#                 # Download the model and verify it matches the one we uploaded.
#                 url = url + '/bar/model.json'
#                 assert self.downloadFragRaw(url) == frag.data
#             except AssertionError:
#                 return False
#             return True

#         # Add the template.
#         assert self.addTemplate(t1).ok

#         # Spawn two instances.
#         ret1 = self.sendRequest(
#             {'cmd': 'spawn', 'data': {'name': t1.name, 'objID': '1'}})
#         ret2 = self.sendRequest(
#             {'cmd': 'spawn', 'data': {'name': t1.name, 'objID': '2'}})
#         assert ret1.ok
#         assert ret2.ok

#         assert _instanceOk(ret1.data['url'], t1.fragments[0])
#         assert _instanceOk(ret2.data['url'], t1.fragments[0])

#         # Attempt to delete non-existing instance.
#         assert not self.sendRequest({'cmd': 'del_instance', 'data': '100'}).ok
#         assert _instanceOk(ret1.data['url'], t1.fragments[0])
#         assert _instanceOk(ret2.data['url'], t1.fragments[0])

#         # Delete second instance.
#         assert self.sendRequest({'cmd': 'del_instance', 'data': '2'}).ok
#         assert _instanceOk(ret1.data['url'], t1.fragments[0])
#         assert not _instanceOk(ret2.data['url'], t1.fragments[0])

#         # Delete first instance.
#         assert self.sendRequest({'cmd': 'del_instance', 'data': '1'}).ok
#         assert not _instanceOk(ret1.data['url'], t1.fragments[0])
#         assert not _instanceOk(ret2.data['url'], t1.fragments[0])

#         # Attempt to delete the first instance again.
#         assert not self.sendRequest({'cmd': 'del_instance', 'data': '1'}).ok
#         assert not _instanceOk(ret1.data['url'], t1.fragments[0])
#         assert not _instanceOk(ret2.data['url'], t1.fragments[0])

#         print('Test passed')


class TestDibblerAPI:
    @classmethod
    def setup_class(cls):
        pass

    @classmethod
    def teardown_class(cls):
        pass

    def setup_method(self, method):
        self.dibbler = azrael.dibbler.DibblerAPI()
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
        ret_1 = dibbler.spawnTemplate({'name': t_raw.name, 'objID': '1'})
        ret_2 = dibbler.spawnTemplate({'name': t_raw.name, 'objID': '2'})
        ret_3 = dibbler.spawnTemplate({'name': t_dae.name, 'objID': '3'})
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
        assert not dibbler.spawnTemplate({'name': 'blah', 'objID': '10'}).ok
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
        ret_11 = dibbler.spawnTemplate({'name': t1.name, 'objID': '11'})
        ret_2 = dibbler.spawnTemplate({'name': t1.name, 'objID': '2'})
        assert ret_11.ok and ret_2.ok

        self.verifyRaw(ret_11.data['url'], frag_orig)
        self.verifyRaw(ret_2.data['url'], frag_orig)

        # Create a replacement fragment.
        frag_new = MetaFragment('bar', 'raw', createFragRaw())

        # Attempt to change the fragment of a non-existing object.
        ret = dibbler.updateFragments({'objID': '20', 'frags': [frag_new]})
        assert not ret.ok

        # Attempt to change the fragment of another non-existing object, but
        # the object ID of this one is '1', which means it is available at
        # '/somewhere/1/...'. However, an object at '/somewhere/11/...' already
        # exists, and without the trailing '/' the first would be a sub-string
        # of the latter. The update method must therefore take care to properly
        # test for existence, especially since directories, internally, do not
        # have a trailing '/'.
        ret = dibbler.updateFragments({'objID': '1', 'frags': [frag_new]})
        assert not ret.ok

        # The old fragments must not have changed.
        self.verifyRaw(ret_11.data['url'], frag_orig)
        self.verifyRaw(ret_2.data['url'], frag_orig)

        # Change the fragment models for the first object.
        ret = dibbler.updateFragments({'objID': '11', 'frags': [frag_new]})
        assert ret.ok

        # Verify that the models are correct.
        self.verifyRaw(ret_11.data['url'], frag_new)
        self.verifyRaw(ret_2.data['url'], frag_orig)

    def test_removeTemplate(self):
        """
        Add and remove a template.
        """
        assert False

    def test_removeInstance(self):
        """
        Add and remove an instance.
        """
        assert False
