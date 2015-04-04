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
Dibbler is a Web interface to the model library.

It provides the following features:
 * get/set the fragments for a template
 * get/set the fragments for an object instance
 * update one- or more fragments of an object instance
 * delete one- or more  object instances
 * delete all instances and/or templates

Dibbler is only accessible via HTTP POST requests. The urls are:
 * http://somewhere.com:port/template
 * http://somewhere.com:port/instance
 * http://somewhere.com:port/reset

The message body is a JSON string that specifies the action and data.
For instance, sending {'type': 'instances'} to '.../reset' will delete
all instance data.

Dibbler does not face the user. Instead, it receives all requests from
``Clerk`` instances which ensure the request is sane. The only exception
from this rule are read-only requests, most notably to query the
geometry for a specific object instance. This is almost certainly the
most common request, and since it has no side effects it is more
efficient to give users direct access instead of routing it to a
``Clerk`` every time.

This policy is not yet enforced since it is not crucial to Azrael right
now.  However, my goal is to enforce it once multi-machine (or
multi-container) deployments are a reality.

As an even longer term goal it should be possible to run several ``Dibbler``
instances behind a user facing Nginx server, but that will require changes to
how models are stored to avoid race conditions. Again, Azrael does not
yet require this level of sophistication.

fixme: update module doc string once it is clearer how everything fits.
"""
import os
import json
import shutil
import base64
import pytest
import pickle
import binascii
import subprocess
import tornado.web
import tornado.testing
import azrael.config as config

import numpy as np

from azrael.util import Template, RetVal
from azrael.util import FragDae, FragRaw, MetaFragment

from IPython import embed as ipshell
from azrael.typecheck import typecheck


@typecheck
def rmtree(dirnames: list, ignore_errors=False):
    """
    fixme: docu string
    """
    # Precaution: refuse to delete anything outside /tmp/
    for dirname in dirnames:
        assert dirname.startswith('/tmp/')
    
    for dirname in dirnames:
        shutil.rmtree(dirname, ignore_errors=ignore_errors)


@typecheck
def isGeometrySane(frag: FragRaw):
    """
    Return *True* if the geometry is consistent.

    :param Fragment frag: a geometry Fragment
    :return: Sucess
    :rtype: bool
    """
    # The number of vertices must be an integer multiple of 9 to
    # constitute a valid triangle mesh (every triangle has three
    # edges and every edge requires an (x, y, z) triplet to
    # describe its position).
    try:
        assert len(frag.vert) % 9 == 0
        assert len(frag.uv) % 2 == 0
        assert len(frag.rgb) % 3 == 0
    except AssertionError:
        return False
    return True


def saveModelDae(frag_dir, model):
    """
    Save the Collada ``model`` to ``frag_dir``.

    :param str frag_dir: directory where to store ``model``.
    :param FragDae model: the Collada model.
    :return: success
    """
    # Sanity checks.
    try:
        data = FragDae(*model.data)
        assert isinstance(data.dae, bytes)
        for v in data.rgb.values():
            assert isinstance(v, bytes)
    except KeyError:
        msg = 'Invalid data types for Collada fragments'
        return RetVal(False, msg, None)

    # Save the dae file to "templates/mymodel/name.dae".
    open(os.path.join(frag_dir, model.name), 'wb').write(data.dae)

    # Save the textures. These are stored as dictionaries with the texture
    # file name as key and the data as a binary stream, eg,
    # {'house.jpg': b'abc', 'tree.png': b'def', ...}
    for name, rgb in data.rgb.items():
        open(os.path.join(frag_dir, name), 'wb').write(rgb)

    return RetVal(True, None, 1.0)


def saveModelRaw(frag_dir, model):
    """
    Save the raw ``model`` to ``frag_dir``.

    A 'raw' model is one where the vertices, UV map, and RGB textures is
    provided directly. This is mostly useful for debugging because it
    circumvents 3D file formats altogether.

    :param str frag_dir: directory where to store ``model``.
    :param FragDae model: the Collada model.
    :return: success
    """
    # Sanity checks.
    try:
        data = FragRaw(*model.data)
        assert isinstance(data.vert, list)
        assert isinstance(data.uv, list)
        assert isinstance(data.rgb, list)
    except (AssertionError, TypeError):
        msg = 'Invalid data types for Raw fragments'
        return RetVal(False, msg, None)

    if not isGeometrySane(data):
        msg = 'Invalid geometry for template <{}>'
        return RetVal(False, msg.format(model.name), None)

    # Save the fragments as JSON data to eg "templates/mymodel/model.json".
    file_data = dict(zip(data._fields, data))
    file_data = json.dumps(file_data)
    open(os.path.join(frag_dir, 'model.json'), 'w').write(file_data)
    del file_data

    # Determine the largest possible side length of the
    # AABB. To find it, just determine the largest spatial
    # extent in any axis direction. That is the side length of
    # the AABB cube. Then multiply it with sqrt(3) to ensure
    # that any rotation angle of the object is covered. The
    # slightly larger value of sqrt(3.1) adds some slack.
    aabb = 0
    if len(data.vert) > 0:
        len_x = max(data.vert[0::3]) - min(data.vert[0::3])
        len_y = max(data.vert[1::3]) - min(data.vert[1::3])
        len_z = max(data.vert[2::3]) - min(data.vert[2::3])
        tmp = np.sqrt(3.1) * max(len_x, len_y, len_z)
        aabb = np.amax((aabb, tmp))

    return RetVal(True, None, aabb)


@typecheck
def saveModel(dirname: str, model):
    """
    Save the ``model`` to ``dirname`` and return the success.

    This function is merely a wrapper around dedicated methods to save
    individual file formats like Collada (dae) or Raw (for testing) files.

    :param str dirname: the destination directory.
    :param model: Container for the respective file format.
    :return: success.
    """
    # Create a pristine fragment directory.
    rmtree([dirname], ignore_errors=True)
    os.makedirs(dirname)
    if model.type == 'raw':
        return saveModelRaw(dirname, model)
    elif model.type == 'dae':
        return saveModelDae(dirname, model)
    else:
        msg = 'Unknown type <{}>'.format(model.type)
        return RetVal(False, msg, None)


@typecheck
def removeTemplate(dirname: str):
    """
    fixme: docu
    """
    try:
        rmtree([dirname])
        return RetVal(True, None, None)
    except FileNotFoundError:
        msg = 'Template <{}> does not exist'.format(dirname)
        return RetVal(False, msg, None)


class MyStaticFileHandler(tornado.web.StaticFileHandler):
    """
    A static file handler that tells the client to never cache anything.

    For more information see
    http://stackoverflow.com/questions/12031007/\
    disable-static-file-caching-in-tornado
    """
    def set_extra_headers(self, path):
        self.set_header('Cache-Control',
                        'no-store, no-cache, must-revalidate, max-age=0')


class Dibbler(tornado.web.RequestHandler):
    """
    """
    def __init__(self, *args, templates, instances, **kwargs):
        super().__init__(*args, **kwargs)

        self.dir_templates = templates
        self.dir_instances = instances

        # fixme: add logger instance
        # fixme: use logger instead of print

    def get(self):
        """
        fixme: delete me?
        """
        # Attempt to parse the arguments from the URL
        try:
            x = self.get_argument('x')
            y = self.get_argument('y')
        except tornado.web.MissingArgumentError:
            msg = 'Could not extract all arguments from <{}>'
            msg = msg.format(self.request.uri)
            ret = RetVal(False, msg, None)
            self.write(json.dumps(ret))
            return

        # Return message 
        data = {'name': 'test', 'x + y': '|'.join([x, y])}
        ret = RetVal(True, None, data)
        self.write(json.dumps(ret._asdict()))

    def post(self):
        # fixme: intercept all errors
        # fixme: decode payload and decide which method to call (eg
        #        addTemplate, spawnTemplate, updateModel, ...)

        # Base64 decode the payload.
        try:
            body = base64.b64decode(self.request.body)
        except (binascii.Error, TypeError):
            msg = 'Base64 decoding error'
            self.write(json.dumps(RetVal(False, msg, None)._asdict()))
            return

        # Payload is a pickled Python dictionary.
        try:
            body = pickle.loads(body)
        except (TypeError, pickle.UnpicklingError):
            msg = 'Unpickling error'
            self.write(json.dumps(RetVal(False, msg, None)._asdict()))
            return

        # The Python dictionary must contain a 'cmd' and a 'data' key. The
        # 'cmd' value must a be a string.
        try:
            cmd, data = body['cmd'], body['data']
            assert isinstance(cmd, str)
        except (TypeError, KeyError):
            msg = 'Received invalid body'
            self.write(json.dumps(RetVal(False, msg, None)._asdict()))
            return

        # Decide on the command to run.
        if cmd == 'add_template':
            ret = self.addTemplate(data)
        elif cmd == 'del_template':
            ret = removeTemplate(os.path.join(self.dir_templates, data))
        elif cmd == 'spawn':
            ret = self.spawnTemplate(data)
        elif cmd == 'del_instance':
            ret = self.deleteInstance(data)
        elif cmd == 'set_geometry':
            ret = self.setGeometry(data)
        elif cmd == 'reset' and data in ('empty',):
            if data == 'empty':
                rmtree([self.dir_templates, self.dir_instances])
            ret = RetVal(True, None, None)
        else:
            msg = 'Invalid Dibbler command <{}>'.format(body['cmd'])
            ret = RetVal(False, msg, None)

        self.write(json.dumps(ret._asdict()))
        
    def setGeometry(self, data: dict):
        try:
            assert isinstance(data, dict)
            frags, objID = data['frags'], data['objID']
            assert isinstance(objID, str)
            assert isinstance(frags, list)
            for _ in frags:
                assert isinstance(_, MetaFragment)
            int(objID)
        except (AssertionError, TypeError, ValueError, KeyError):
            msg = 'Invalid parameters in setGeometry command'
            return RetVal(False, msg, None)

        model_dir = os.path.join(self.dir_instances, objID)
        frag_names = {}
        for frag in frags:
            frag_dir = os.path.join(model_dir, frag.name)

            # Save the model data to disk.
            ret = saveModel(frag_dir, frag)
            if not ret.ok:
                rmtree([model_dir], ignore_error=True)
                return ret
            frag_names[frag.name] = frag.type
            tmp = json.dumps({'fragments': frag_names}).encode('utf8')
            open(os.path.join(model_dir, 'meta.json'), 'wb').write(tmp)
            del tmp
        return RetVal(True, None, None)        
        
    def spawnTemplate(self, data: dict):
        try:
            assert isinstance(data, dict)
            name, objID = data['name'], data['objID']
            assert isinstance(objID, str)
            int(objID)
        except (AssertionError, TypeError, ValueError, KeyError):
            msg = 'Invalid parameters in spawn command'
            return RetVal(False, msg, None)
        
        # Copy the model from the template- to the instance directory.
        src = os.path.join(self.dir_templates, name, '*')
        dst = os.path.join(self.dir_instances, objID) + '/'
        try:
            os.makedirs(dst)
        except FileExistsError:
            msg = 'Directory for instance <{}> already exists'.format(objID)
            return RetVal(False, msg, None)

        # Copy the model data from the template directory to the instance
        # directory 'dst'.
        cmd = 'cp -r {} {}'.format(src, dst)
        ret = subprocess.call(cmd, shell=True, stderr=subprocess.DEVNULL)
        if ret == 0:
            url = config.url_instance + '/{}'.format(objID)
            return RetVal(True, None, {'url': url})
        else:
            msg = 'Error creating the instance directory:\n  cmd={}'
            msg = msg.format(cmd)
            rmtree([dst])
            return RetVal(False, msg, None)

    def deleteInstance(self, objID: str):
        dst = os.path.join(self.dir_instances, objID)
        try:
            rmtree([dst], ignore_errors=False)
        except (AssertionError, FileNotFoundError):
            msg = 'Could not delete objID <{}>'.format(objID)
            return RetVal(False, msg, None)
        return RetVal(True, None, None)
        
    def addTemplate(self, tt):
        """
        # fixme: docstring
        # fixme: document method
        """
        model_dir = os.path.join(self.dir_templates, tt.name)
        model_url = os.path.join(config.url_template, tt.name)
        try:
            os.makedirs(model_dir, exist_ok=False)
        except FileExistsError:
            msg = 'Template <{}> already exists'.format(tt.name)
            print(msg)
            return RetVal(False, msg, None)

        # Store all fragment models for this template.
        aabb = 0
        frag_names = {}
        for frag in tt.fragments:
            frag_dir = os.path.join(model_dir, frag.name)

            # Create the directory for this fragment:
            # eg. "some_url/template_name/fragment_name"
            try:
                os.makedirs(frag_dir, exist_ok=False)
            except FileExistsError:
                # Famous last words: this error is impossible --> handle it
                # anyway and remove the entire template directory.
                msg = 'Frag dir <{}> already exists'.format(frag_dir)
                rmtree([model_dir])
                return RetVal(False, msg, None)

            # Save the model data to disk.
            ret = saveModel(frag_dir, frag)
            if not ret.ok:
                rmtree([model_dir])
                return ret
            frag_names[frag.name] = frag.type
            tmp = json.dumps({'fragments': frag_names}).encode('utf8')
            open(os.path.join(model_dir, 'meta.json'), 'wb').write(tmp)
            del tmp

            aabb = np.amax((ret.data, aabb))

        # Return message 
        return RetVal(True, None, {'aabb': aabb, 'url': model_url})

