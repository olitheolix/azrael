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
import time
import json
import gridfs
import shutil
import base64
import pytest
import pickle
import binascii
import subprocess
import tornado.web
import tornado.ioloop
import tornado.testing
import multiprocessing
import urllib.request
import azrael.config as config

import numpy as np

from IPython import embed as ipshell
from azrael.types import typecheck, Template, RetVal
from azrael.types import FragDae, FragRaw, MetaFragment


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


class Dibbler:
    """
    fixme: docu
    fixme: rename to just 'Dibbler' after the current 'Dibbler' was removed.
    """
    def __init__(self):
        # Connect to GridFS.
        self.db = config.getMongoClient()['AzraelGridDB']
        self.fs = gridfs.GridFS(self.db)

    def reset(self):
        """
        Flush the entire database content.
        """
        for _ in self.fs.find():
            self.fs.delete(_._id)
        return RetVal(True, None, None)

    def getNumFiles(self):
        """
        Return the number of files in GridFS.
        """
        return RetVal(True, None, self.fs.find().count())

    def saveModelDae(self, frag_dir, model):
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

        # Save the dae file to "templates/model_name/frag_name/name.dae".
        self.fs.put(data.dae, filename=os.path.join(frag_dir, model.name))

        # Save the textures. These are stored as dictionaries with the texture
        # file name as key and the data as a binary stream, eg,
        # {'house.jpg': b'abc', 'tree.png': b'def', ...}
        for name, rgb in data.rgb.items():
            self.fs.put(rgb, filename=os.path.join(frag_dir, name))

        return RetVal(True, None, 1.0)

    def saveModelRaw(self, frag_dir, model):
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
        self.fs.put(json.dumps(data._asdict()).encode('utf8'),
                    filename=os.path.join(frag_dir, 'model.json'))

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
    def saveModel(self, model_dir, fragments, update=False):
        """
        Save the ``model`` to ``dirname`` and return the success.

        This function is merely a wrapper around dedicated methods to save
        individual file formats like Collada (dae) or Raw (for testing) files.

        :param str dirname: the destination directory.
        :param model: Container for the respective file format.
        :return: success.
        """
        if update:
            ret = self.fs.find_one({'filename': {'$regex': '^' + model_dir + '/'}})
            if ret is None:
                return RetVal(False, 'Model does not exist', None)

        # Store all fragment models for this template.
        aabb = -1
        frag_names = {}
        for frag in fragments:
            # Fragment directory, eg .../instances/mymodel/frag1
            frag_dir = os.path.join(model_dir, frag.name)

            # Save the fragment.
            if frag.type == 'raw':
                # Raw.
                ret = self.saveModelRaw(frag_dir, frag)
            elif frag.type == 'dae':
                # Collada.
                ret = self.saveModelDae(frag_dir, frag)
            else:
                # Unknown model format.
                msg = 'Unknown type <{}>'.format(frag.type)
                ret = RetVal(False, msg, None)

            # Delete the fragment directory if something went wrong and proceed to
            # the next fragment.
            if not ret.ok:
                fs.delete({'filename': {'$regex': '^{}/.*'.format(frag_dir)}})
                continue

            # Update the 'meta.json': it contains a dictionary with all fragment
            # names and their model type, eg. {'foo': 'raw', 'bar': 'dae', ...}
            frag_names[frag.name] = frag.type
            self.fs.put(json.dumps({'fragments': frag_names}).encode('utf8'),
                        filename=os.path.join(model_dir, 'meta.json'))

            # Find the largest AABB.
            aabb = float(np.amax((ret.data, aabb)))

        # Sanity check: if the AABB was negative then not a single fragment was
        # valid. This is an error.
        if aabb < 0:
            msg = 'Model contains no valid fragments'
            return RetVal(False, msg, None)
        return RetVal(True, None, aabb)

    def getTemplateDir(self, name: str):
        return os.path.join('/', 'templates', name)

    def getInstanceDir(self, objID: str):
        return os.path.join('/', 'instances', objID)

    def addTemplate(self, tt):
        model_dir = self.getTemplateDir(tt.name)
        model_url = os.path.join(config.url_template, tt.name)

        ret = self.saveModel(model_dir, tt.fragments)
        if not ret.ok:
            return ret

        # Return message.
        return RetVal(True, None, {'aabb': ret.data, 'url': model_url})

    def getFile(self, name):
        try:
            ret = self.fs.get_last_version(name)
        except gridfs.errors.NoFile as err:
            return RetVal(False, repr(err), None)
        except gridfs.errors.GridFSError as err:
            # All other GridFS errors.
            return RetVal(False, None, None)

        if ret is None:
            return RetVal(False, 'File not found', None)
        else:
            return RetVal(True, None, ret.read())
    
    def spawnTemplate(self, name: str, objID: str):
        try:
            # 'objID', albeit a string, must correspond a valid integer.
            int(objID)
        except (TypeError, ValueError):
            msg = 'Invalid parameters in spawn command'
            return RetVal(False, msg, None)

        # Copy the model from the template- to the instance directory.
        src = self.getTemplateDir(name)
        dst = self.getInstanceDir(objID)

        query = {'filename': {'$regex': '^{}/.*'.format(src)}}
        cnt = 0
        for f in self.fs.find(query):
            # Modify the original file name from
            # '/templates/temp_name/*' to '/instances/objID/*'.
            name = f.filename.replace(src, dst)

            # Copy the last version of the file.
            src_data = self.fs.get_last_version(f.filename)
            self.fs.put(src_data, filename=name)

            # Increment the file counter.
            cnt += 1

        if cnt == 0:
            # Did not find any template files.
            msg = 'Could not find template <{}>'.format(name)
            return RetVal(False, msg, None)
        else:
            # Found at least one template file to copy.
            url = config.url_instance + '/{}'.format(objID)
            return RetVal(True, None, {'url': url})

    def updateFragments(self, objID: str, frags: list):
        try:
            for _ in frags:
                assert isinstance(_, MetaFragment)
            # 'objID', albeit a string, must correspond a valid integer.
            int(objID)
        except (TypeError, ValueError):
            msg = 'Invalid parameters in updateFragments command'
            return RetVal(False, msg, None)

        # Ensure that ``objID`` exists.
        model_dir = self.getInstanceDir(objID)

        # Overwrite the model for instance with ``objID``.
        return self.saveModel(model_dir, frags, update=True)

    @typecheck
    def removeTemplate(self, name: str):
        """
        fixme: docu
        """
        query = {'filename': {'$regex': '^/templates/{}/.*'.format(name)}}
        cnt = 0
        for f in self.fs.find(query):
            self.fs.delete(f._id)
            cnt += 1
        return RetVal(True, None, cnt)

    @typecheck
    def removeInstance(self, objID: str):
        """
        fixme: docu
        """
        query = {'filename': {'$regex': '^/instances/{}/.*'.format(objID)}}
        cnt = 0
        for f in self.fs.find(query):
            self.fs.delete(f._id)
            cnt += 1
        return RetVal(True, None, cnt)
