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
fixme: add tests for
  * send invalid fragment data
  * spawnTemplate
  * updateGeometry
  * delete instance
  * write 'startDibbler' function to start Dibbler Tornado process
  * integration test with urllib and an actual Tornado process
"""

import os
import json
import shutil
import base64
import pytest
import pickle
import tornado.web
import azrael.dibbler
import tornado.testing

import numpy as np
import unittest.mock as mock
import azrael.config as config

from IPython import embed as ipshell

from azrael.util import Template, RetVal
from azrael.util import FragDae, FragRaw, MetaFragment


class TestDibbler(tornado.testing.AsyncHTTPTestCase):
    def get_app(self):
        handlers = []
        # Static HTML files.
        FH = azrael.dibbler.MyStaticFileHandler

        # fixme: the static paths used below should be temporary directories

        self.dirNameBase = '/tmp/dibbler'
        self.dirNames = {
            'templates': os.path.join(self.dirNameBase, 'templates'),
            'instances': os.path.join(self.dirNameBase, 'instances')}

        # Template models.
        handlers.append(
            ('/templates/(.*)', FH, {'path': self.dirNames['templates']}))

        # Instance models.
        handlers.append(
            ('/instances/(.*)', FH, {'path': self.dirNames['instances']}))

        # Dibbler API.
        handlers.append(('/dibbler', azrael.dibbler.Dibbler, self.dirNames))

        return tornado.web.Application(handlers)

    def resetDibbler(self):
        for dirname in self.dirNames.values():
            azrael.dibbler.rmtree([dirname], ignore_errors=True)

    def createFragDae(self):
        b = os.path.dirname(__file__)
        dae_file = open(b + '/cube.dae', 'rb').read()
        dae_rgb1 = open(b + '/rgb1.png', 'rb').read()
        dae_rgb2 = open(b + '/rgb2.jpg', 'rb').read()
        frag = FragDae(dae=dae_file,
                        rgb={'rgb1.png': dae_rgb1,
                             'rgb2.jpg': dae_rgb2})
        return frag

    def createFragRaw(self):
        vert = np.random.randint(0, 100, 9).tolist()
        uv = np.random.randint(0, 100, 2).tolist()
        rgb = np.random.randint(0, 100, 3).tolist()
        return FragRaw(vert, uv, rgb)

    def sendRequest(self, req):
        req = base64.b64encode(pickle.dumps(req))

        # Make a request to add the template. This must succeed and return the
        # URL where it can be downloaded.
        ret = self.fetch(config.url_dibbler, method='POST', body=req)
        try:
            ret = json.loads(ret.body.decode('utf-8'))
        except ValueError:
            # This typically happens when the server responded with a 404
            # error, usually because we did not provide a valid URL to 'fetch'.
            return RetVal(False, 'JSON decoding error', None)
        return RetVal(**ret)

    def addTemplate(self, template: Template):
        # Compile the Dibbler request.
        req = {'cmd': 'add_template', 'data': template}
        return self.sendRequest(req)
        
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

        
    def test_template_raw(self):
        """
        Add and query a template with one Raw fragment.
        """
        self.resetDibbler()
        
        # Create two Templates with one Raw fragment each.
        frags = [MetaFragment('bar', 'raw', self.createFragRaw())]
        t1 = Template('t1', [1, 2, 3, 4], frags, [], [])
        t2 = Template('t2', [5, 6, 7, 8], frags, [], [])
        del frags

        def _verifyTemplate(url, frag):
            # Load the meta file for this template which must contain a list of
            # all fragment names.
            ret = self.downloadJSON(url + '/meta.json')
            assert ret['fragments'] == {'bar': 'raw'}

            # Download the model and verify it matches the one we uploaded.
            assert self.downloadFragRaw(url + '/bar/model.json') == frag.data

        # Add the first template.
        ret1 = self.addTemplate(t1)
        assert ret1.ok and ret1.data['url'] == config.url_template + '/t1'

        # Attempt to add the template a second time. This must fail.
        assert not self.addTemplate(t1).ok

        # Verify the first template.
        _verifyTemplate(ret1.data['url'], t1.fragments[0])
            
        # Add the second template.
        ret2 = self.addTemplate(t2)
        assert ret2.ok and ret2.data['url'] == config.url_template + '/t2'

        # Verify that both templates now exist.
        _verifyTemplate(ret1.data['url'], t1.fragments[0])
        _verifyTemplate(ret2.data['url'], t2.fragments[0])

        print('Test passed')

    def test_template_collada(self):
        """
        Add and query a template with one Collada fragment.
        """
        self.resetDibbler()
        
        # Create two Templates with one Collada fragment each.
        frags = [MetaFragment('bar', 'dae', self.createFragDae())]
        t1 = Template('t1', [1, 2, 3, 4], frags, [], [])
        t2 = Template('t2', [5, 6, 7, 8], frags, [], [])
        del frags

        def _verifyTemplate(url, frag):
            # Load the meta file for this template which must contain a list of
            # all fragment names.
            ret = self.downloadJSON(url + '/meta.json')
            assert ret['fragments'] == {'bar': 'dae'}

            # Check the Collada fragment.
            ret = self.downloadFragDae(
                url + '/bar/', 'bar', ['rgb1.png', 'rgb2.jpg'])
            assert ret == frag.data

        # Add the first template and verify it.
        ret1 = self.addTemplate(t1)
        assert ret1.ok and ret1.data['url'] == config.url_template + '/t1'
        _verifyTemplate(ret1.data['url'], t1.fragments[0])

        # Attempt to add the template a second time. This must fail.
        assert not self.addTemplate(t1).ok

        # Add the second template.
        ret2 = self.addTemplate(t2)
        assert ret2.ok and ret2.data['url'] == config.url_template + '/t2'

        # Verify that both templates are now available.
        _verifyTemplate(ret1.data['url'], t1.fragments[0])
        _verifyTemplate(ret2.data['url'], t2.fragments[0])

        print('Test passed')

    def test_template_mixed_fragments(self):
        """
        Add templates with multiple fragments of different types.
        """
        self.resetDibbler()
        
        # Create two Templates. Each template has a Raw and Collada fragment.
        frags = [
            MetaFragment('bar_raw', 'raw', self.createFragRaw()),
            MetaFragment('bar_dae', 'dae', self.createFragDae())
        ]
        t1 = Template('t1', [1, 2, 3, 4], frags, [], [])
        t2 = Template('t2', [5, 6, 7, 8], frags, [], [])
        del frags

        def _verifyTemplate(url, frag):
            """
            Auxiliary functions to verify templates. The sole purpose of this
            function is to avoid code duplication.

            It assumes that template contains exactly two fragments where the
            first is a 'raw' fragment, and the second a 'dae' one.
            """
            # Load the meta file for this template which must contain a list of
            # all fragment names.
            ret = self.downloadJSON(url + '/meta.json')
            assert ret['fragments'] == {'bar_raw': 'raw', 'bar_dae': 'dae'}

            # Check the Raw fragment.
            tmp_url = url + '/bar_raw/model.json'
            assert self.downloadFragRaw(tmp_url) == frag[0].data
        
            # Check the Collada fragment.
            tmp_url = url + '/bar_dae/'
            ret = self.downloadFragDae(
                tmp_url, 'bar_dae', ['rgb1.png', 'rgb2.jpg'])
            assert ret == frag[1].data
            
        # Add the first template and verify it.
        ret1 = self.addTemplate(t1)
        assert ret1.ok and ret1.data['url'] == config.url_template + '/t1'
        _verifyTemplate(ret1.data['url'], t1.fragments)

        # Add the second template.
        ret2 = self.addTemplate(t2)
        assert ret2.ok and ret2.data['url'] == config.url_template + '/t2'

        # Verify that both templates are now available.
        _verifyTemplate(ret1.data['url'], t1.fragments)
        _verifyTemplate(ret2.data['url'], t2.fragments)

        print('Test passed')

    def test_template_invalid(self):
        """
        Make invalid queries to Dibbler which must handle them gracefully.
        """
        self.resetDibbler()

        # Payload is not a valid pickled Python object.
        body = base64.b64encode(b'blah')
        ret = self.fetch(config.url_dibbler, method='POST', body=body)
        ret = RetVal(**json.loads(ret.body.decode('utf-8')))
        assert not ret.ok

        # Payload is not a dictionary.
        body = [1, 2]
        body = base64.b64encode(pickle.dumps(body))
        ret = self.fetch(config.url_dibbler, method='POST', body=body)
        ret = RetVal(**json.loads(ret.body.decode('utf-8')))
        assert not ret.ok

        # Payload misses the command word.
        body = {'data': None}
        body = base64.b64encode(pickle.dumps(body))
        ret = self.fetch(config.url_dibbler, method='POST', body=body)
        ret = RetVal(**json.loads(ret.body.decode('utf-8')))
        assert not ret.ok

        # Payload misses the data.
        body = {'cmd': 'add_template'}
        body = base64.b64encode(pickle.dumps(body))
        ret = self.fetch(config.url_dibbler, method='POST', body=body)
        ret = RetVal(**json.loads(ret.body.decode('utf-8')))
        assert not ret.ok

        # Invalid command name.
        body = {'cmd': 'blah', 'data': None}
        body = base64.b64encode(pickle.dumps(body))
        ret = self.fetch(config.url_dibbler, method='POST', body=body)
        ret = RetVal(**json.loads(ret.body.decode('utf-8')))
        assert not ret.ok

        print('Test passed')

    @mock.patch('azrael.dibbler.rmtree')
    def test_reset(self, mock_rmtree):
        """
        Reset Dibbler.
        """
        assert mock_rmtree.call_count == 0

        # Tell Dibbler to delete all template- and instance data.
        req = {'cmd': 'reset', 'data': 'empty'}
        req = base64.b64encode(pickle.dumps(req))
        ret = self.fetch(config.url_dibbler, method='POST', body=req)
        ret = json.loads(ret.body.decode('utf-8'))
        assert RetVal(**ret).ok

        # The 'rmtree' function must have been called twice (once for the
        # 'templates' and once for the 'instances').
        assert mock_rmtree.call_count == 1

    def test_remove_template(self):
        """
        Add a template, verify it exists, remove it, verify it does not exist
        anymore.
        """
        self.resetDibbler()

        # Create two Templates with one Raw fragment each.
        frags = [MetaFragment('bar', 'raw', self.createFragRaw())]
        t1 = Template('t1', [1, 2, 3, 4], frags, [], [])
        t2 = Template('t2', [5, 6, 7, 8], frags, [], [])
        del frags

        def _templateOk(url, frag):
            try:
                # Load the meta file for this template which must contain a list of
                # all fragment names.
                ret = self.downloadJSON(url + '/meta.json')
                assert ret['fragments'] == {'bar': 'raw'}

                # Download the model and verify it matches the one we uploaded.
                url = url + '/bar/model.json'
                assert self.downloadFragRaw(url) == frag.data
            except AssertionError:
                return False
            return True

        # Add both templates and verify they now exist.
        ret1 = self.addTemplate(t1)
        ret2 = self.addTemplate(t2)
        assert ret1.ok
        assert ret2.ok
        assert _templateOk(ret1.data['url'], t1.fragments[0])
        assert _templateOk(ret2.data['url'], t2.fragments[0])

        # Attempt to delete non-existing template.
        req = {'cmd': 'del_template', 'data': 'blah'}
        assert not self.sendRequest(req).ok
        assert _templateOk(ret1.data['url'], t1.fragments[0])
        assert _templateOk(ret2.data['url'], t2.fragments[0])
        
        # Delete second template.
        req = {'cmd': 'del_template', 'data': t2.name}
        assert self.sendRequest(req).ok
        assert _templateOk(ret1.data['url'], t1.fragments[0])
        assert not _templateOk(ret2.data['url'], t2.fragments[0])
        
        # Delete first template.
        req = {'cmd': 'del_template', 'data': t1.name}
        assert self.sendRequest(req).ok
        assert not _templateOk(ret1.data['url'], t1.fragments[0])
        assert not _templateOk(ret2.data['url'], t2.fragments[0])
        
        # Attempt to delete the first template again.
        req = {'cmd': 'del_template', 'data': t1.name}
        assert not self.sendRequest(req).ok
        assert not _templateOk(ret1.data['url'], t1.fragments[0])
        assert not _templateOk(ret2.data['url'], t2.fragments[0])
        
        print('Test passed')

    def test_spawn_template(self):
        """
        Add a template and spawn it. The net effect must be that the instance
        data must be available via Dibbler.
        """
        self.resetDibbler()

        # Create a Templates with a Raw fragment.
        frags = [MetaFragment('bar', 'raw', self.createFragRaw())]
        t1 = Template('t1', [1, 2, 3, 4], frags, [], [])
        del frags

        def _instanceOk(url, frag):
            try:
                # Load the meta file for this template which must contain a list of
                # all fragment names.
                ret = self.downloadJSON(url + '/meta.json')
                assert ret['fragments'] == {'bar': 'raw'}

                # Download the model and verify it matches the one we uploaded.
                url = url + '/bar/model.json'
                assert self.downloadFragRaw(url) == frag.data
            except AssertionError:
                return False
            return True

        # Add the template.
        assert self.addTemplate(t1).ok

        # Attempt to spawn a non-existing template.
        req = {'cmd': 'spawn', 'data': {'name': 'blah', 'objID': '1'}}
        assert not self.sendRequest(req).ok

        # Spawn a valid template.
        req = {'cmd': 'spawn', 'data': {'name': t1.name, 'objID': '1'}}
        ret = self.sendRequest(req)
        assert ret.ok
        assert ret.data['url'] == config.url_instance + '/1'
        assert _instanceOk(ret.data['url'], t1.fragments[0])

        # Attempt to spawn another template with the same objID.
        req = {'cmd': 'spawn', 'data': {'name': t1.name, 'objID': '1'}}
        assert not self.sendRequest(req).ok
        assert _instanceOk(ret.data['url'], t1.fragments[0])

        print('Test passed')
