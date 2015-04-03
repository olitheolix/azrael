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
import shutil
import base64
import pytest
import pickle
import tornado.web
import azrael.dibbler
import tornado.testing
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

        # Template geometries.
        handlers.append(
            ('/templates/(.*)', FH, {'path': self.dirNames['templates']}))

        # Instance geometries.
        handlers.append(
            ('/instances/(.*)', FH, {'path': self.dirNames['instances']}))

        # Dibbler API.
        handlers.append(('/dibbler', azrael.dibbler.Dibbler, self.dirNames))

        return tornado.web.Application(handlers)

    def resetDibbler(self):
        for dirname in self.dirNames.values():
            azrael.dibbler.rmtree([dirname], ignore_errors=True)

    def test_template_raw(self):
        """
        Add and query a template with one Raw fragment.

        fixme: add tests for Collada; multi-fragments; mixed fragments;
               spawnTemplate; updateGeometry
        """
        self.resetDibbler()
        
        # Create a Template instance.
        cs = [1, 2, 3, 4]
        vert = list(range(9))
        uv, rgb = [9, 10], [1, 2, 250]
        frags = [MetaFragment('bar', 'raw', FragRaw(vert, uv, rgb))]
        data = Template('t1', cs, frags, [], [])

        # Compile the Dibbler command structure.
        body = {'cmd': 'add_template', 'data': data}
        body = base64.b64encode(pickle.dumps(body))

        # Make a request to add the template. This must succeed and return the
        # URL where it can be downloaded.
        ret = self.fetch(config.url_dibbler, method='POST', body=body)
        ret = json.loads(ret.body.decode('utf-8'))
        ret = RetVal(**ret)
        assert ret.ok
        assert ret.data['url'] == config.url_template + '/t1'

        # Attempt to add the template a second time. This must fail.
        ret2 = self.fetch(config.url_dibbler, method='POST', body=body)
        ret2 = json.loads(ret2.body.decode('utf-8'))
        ret2 = RetVal(**ret2)
        assert not ret2.ok
        del ret2

        # Download the model and verify it matches the one we uploaded.
        url = ret.data['url'] + '/bar/model.json'
        ret = self.fetch(url, method='GET')
        ret = json.loads(ret.body.decode('utf8'))
        ret = FragRaw(**(ret))
        assert ret == FragRaw(vert, uv, rgb)

        # Load the meta files for this template. It must contain a list of all
        # fragment names.
        url = config.url_template + '/t1/meta.json'
        ret = self.fetch(url, method='GET')
        ret = json.loads(ret.body.decode('utf8'))
        ret['frag_names'] == ['bar']

        print('Test passed')

    def test_template_invalid(self):
        """
        Make invalid queries to Dibbler which must handle them gracefully.
        """
        self.resetDibbler()

        # Paylod is not a valid pickled Python object.
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

        # Paylod misses the command word.
        body = {'data': None}
        body = base64.b64encode(pickle.dumps(body))
        ret = self.fetch(config.url_dibbler, method='POST', body=body)
        ret = RetVal(**json.loads(ret.body.decode('utf-8')))
        assert not ret.ok

        # Paylod misses the data.
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

        # the 'rmtree' function must have been called twice (once for the
        # 'templates' and once for the 'instances').
        assert mock_rmtree.call_count == 1
