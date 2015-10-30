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
Dibbler stores and provides all geometry files.

Dibbler itself is a stateless service to store and retrieve model files. For
that purpose it provides dedicated methods to store- and sanity check the
various model types supported in Azrael. Furthermore, it provides a simple
`getFile` method to fetch the latest version of any file, if it exists.

Internally, Dibbler uses Mongo's GridFS to actually store the files.

By design, Dibbler will be useful to Clerk instances to add/remove models, and
WebServer to serve them up via HTTP. Its stateless design makes it possible to
create as many instances as necessary.

.. note:: Dibbler sanity checks models but has hardly any safe guards against
          overwriting existing files or concurrent access. Unless
          GridFS provides them itself. This is deliberate, partially because
          GridFS makes this considerably harder than plain MongoDB, and mostly
          because the Clerks already take care of it with the meta data they
          store in MongoDB. After all, Dibbler is merely the storage engine for
          large files.
"""
import os
import json
import base64
import gridfs

import azrael.config as config

from IPython import embed as ipshell
from azrael.aztypes import typecheck, Template, RetVal
from azrael.aztypes import FragDae, FragRaw, FragMeta


class Dibbler:
    """
    Stateless storage backend for Azrael's models.
    """
    def __init__(self):
        # Create a GridFS handle.
        db = config.getMongoClient()['AzraelGridDB']
        self.fs = gridfs.GridFS(db)

    def reset(self):
        """
        Flush all models.

        :return: Success
        """
        # Find all versions of all files and delete everything.
        for _ in self.fs.find():
            self.fs.delete(_._id)
        return RetVal(True, None, None)

    def getNumFiles(self):
        """
        Return the number of distinct files in GridFS.

        ..note:: There may be more files in Dibbler because old versions of the
                 same files are not deleted. However, the returned corresponds
                 to the number of files with distinct file names.

        :return: Number of files in storage.
        """
        return RetVal(True, None, len(self.fs.list()))

    @typecheck
    def saveModelDae(self, location: str, aid: str, model: FragMeta):
        """
        Save the Collada ``model`` to ``location``.

        This will create the necessary files under ``location`` to store all
        the attached information.

        The "directory" structure will contain the Collada file named after the
        model (without the .dae extension), plus any texture files. For
        instance:

        * location/model_name/model_name
        * location/model_name/pic1.png
        * location/model_name/pic2.jpg
        * location/model_name/blah.jpg

        .. note:: ``location`` will usually look like a path and file name (eg.
                  '/instances/1/') but as far as the storage is
                  concerned, it is merely a prefix string (hopefully) unique to
                  this ``model``.

        :param str location: location where to store the ``model``.
        :param FragMeta model: the Collada model itself.
        :return: success
        """
        # Convenience.
        b64dec = base64.b64decode

        # Verify the data is valid and undo the Base64 encoding.
        try:
            # Sanity check: construct the Collada fragment.
            tmp = FragDae(*model.fragdata)

            # Undo the Base64 encoding ('dae' and 'rgb' will be Bytes).
            dae = b64dec(tmp.dae.encode('utf8'))
            rgb = {k: b64dec(v.encode('utf8')) for k, v in tmp.rgb.items()}
        except TypeError:
            msg = 'Could not save Collada fragments'
            return RetVal(False, msg, None)

        # Save the dae file to "location/model_name/model_name".
        self.fs.put(dae, filename=os.path.join(location, aid))

        # Save the textures. These are stored as dictionaries with the texture
        # file name as key and the data as a binary stream, eg,
        # {'house.jpg': b'abc', 'tree.png': b'def', ...}
        for name, rgb in rgb.items():
            self.fs.put(rgb, filename=os.path.join(location, name))

        return RetVal(True, None, 1.0)

    @typecheck
    def saveModelRaw(self, location: str, aid: str, model: FragMeta):
        """
        Save the Raw ``model`` to ``location``.

        This will create the necessary files under ``location`` to store all
        the attached information.

        The "directory" structure will contain only a single entry:
          location/model_name/model.json

        :param str location: directory where to store ``model``.
        :param FragMeta model: the Raw model itself.
        :return: success
        """
        # Sanity checks.
        try:
            data = FragRaw(*model.fragdata)
            data = json.dumps(data._asdict()).encode('utf8')
        except (AssertionError, TypeError):
            msg = 'Invalid data types for Raw fragments'
            return RetVal(False, msg, None)

        # Save the fragments as JSON data to eg "location/model_name/model.json".
        self.fs.put(data, filename=os.path.join(location, 'model.json'))
        return RetVal(True, None, None)

    @typecheck
    def _deleteSubLocation(self, url: str):
        """
        Delete all files under ``url``.

        This function is the equivalent of 'rm -rf url/*'. It always succeeds
        and returns the number of deleted files.

        ..note:: It is well possible that multiple versions of a single file
            exist in GridFS. However, this method only returns the number of
            unique files deleted, irrespective of how many version of
            particular files were deleted along the way.

        :param str url: location (eg. '/instances/blah/')
        :return: number of deleted files
       """
        query = {'filename': {'$regex': '^{}/.*'.format(url)}}
        fnames = set()
        for _ in self.fs.find(query):
            fnames.add(_.filename)
            self.fs.delete(_._id)
        return RetVal(True, None, len(fnames))

    @typecheck
    def saveModel(self, location: str, fragments: dict, update: bool=False):
        """
        Save the ``model`` to ``location`` and return the success status.

        This function is merely a wrapper around dedicated methods to save
        individual fragment (eg Collada or Raw). It will store all
        ``fragments`` under the same ``location`` prefix and create a
        `meta.json` file to list all fragments, their names, and types.

        If ``update`` is *True* then 'location/meta.json' must already exist.

        .. note:: The ``update`` flag does not guarantee that meta.json still
                  exists when the files are written because another Dibbler
                  from another process may delete it at the same time. It is
                  the responsibility of the caller (usually Clerk) to ensure
                  this does not happen.

        For instance, if location='/foo' the "directory" structure in the
        model database will look like this:

        * /foo/meta.json
        * /foo/frag_name_1/...
        * /foo/frag_name_2/...

        The "meta.json" file contains a dictionary with the fragment names
        (keys) and their types (values), eg. {'foo': 'raw', 'bar': 'dae'}.

        :param str location: the common location prefix used for all
                             ``fragments``.
        :param dict[str: ``FragMeta``] fragments: new fragments.
        :param bool update: if *True* then the ``location`` prefix must already
                             exist.
        :return: success.
        """
        # The 'update' flag is merely a sanity check to verify an object even
        # exists. This is prone to a race condition but good enough for now,
        # especially because the race condition is harmless.
        if update:
            query = {'filename': {'$regex': '^' + location + '/meta.json'}}
            ret = self.fs.find_one(query)
            if ret is None:
                return RetVal(False, 'Model does not exist', None)

        # Save the meta JSON file. That file contains meta information about
        # the fragments, most notably which fragments exist. This file we be
        # overwritten in the loop below, but it is nevertheless important to
        # add save it right now as well because the loop below will not execute
        # at all if an object has no fragments (unusual, but perfectly valid).
        self.fs.put(json.dumps({'fragments': {}}).encode('utf8'),
                    filename=os.path.join(location, 'meta.json'))

        # Store all fragment models for this template.
        frag_names = {}
        for aid, frag in fragments.items():
            # Fragment directory as '.../instances/aid/', for instance
            # '/instances/20/'.
            frag_dir = os.path.join(location, aid)

            ftype = frag.fragtype.upper()
            # Delete the current fragments and save the new ones.
            if ftype == 'RAW':
                self._deleteSubLocation(frag_dir)
                ret = self.saveModelRaw(frag_dir, aid, frag)
            elif ftype == 'DAE':
                self._deleteSubLocation(frag_dir)
                ret = self.saveModelDae(frag_dir, aid, frag)
            elif ftype == '_DEL_':
                # Dummy fragment that tells us to remove it.
                ret = RetVal(False, None, None)
            else:
                # Unknown model format.
                msg = 'Unknown type <{}>'.format(ftype)
                ret = RetVal(False, msg, None)

            # Delete the fragment directory if something went wrong and proceed
            # to the next fragment.
            if not ret.ok:
                self._deleteSubLocation(frag_dir)
                continue

            # Update the 'meta.json': it contains a dictionary with all
            # fragment names and their type, for instance:
            # {'foo': 'raw', 'bar': # 'dae', ...}
            frag_names[aid] = frag.fragtype
            self.fs.put(json.dumps({'fragments': frag_names}).encode('utf8'),
                        filename=os.path.join(location, 'meta.json'))

        return RetVal(True, None, None)

    @typecheck
    def getTemplateDir(self, template_name: str):
        """
        Return the location of ``template_name``.

        This is a convenience method only to avoid code duplication. All it
        does is prefix ``template_name`` with the ``config.url_templates``
        value.

        :param str template_name: name of template (eg. 'foo')
        :return: location string (eg /templates/foo/').
        """
        return os.path.join(config.url_templates, template_name)

    @typecheck
    def getInstanceDir(self, objID: int):
        """
        Return the location of the object with ``objID``.

        This is a convenience method only to avoid code duplication. All it
        does is prefix ``template_name`` with the ``config.url_instances``
        value.

        :param int objID: object ID (eg. 8)
        :return: location string (eg /instances/8/').
        """
        return os.path.join(config.url_instances, str(objID))

    @typecheck
    def getFile(self, location: str):
        """
        Return the latest version of ``location``.

        If ``location`` does not exist then return an error.

        :param str location: the location to retrieve (eg.
                             '/instances/8/meta.json').
        :return: content of ``location`` (or *None* if an error occurred).
        :rtype: bytes
        """
        try:
            ret = self.fs.get_last_version(location)
        except gridfs.errors.NoFile as err:
            return RetVal(False, repr(err), None)
        except gridfs.errors.GridFSError as err:
            # All other GridFS errors.
            return RetVal(False, None, None)

        if ret is None:
            return RetVal(False, 'File not found', None)
        else:
            try:
                return RetVal(True, None, ret.read())
            except gridfs.errors.CorruptGridFile:
                return RetVal(False, 'File not found', None)

    @typecheck
    def addTemplate(self, template: Template):
        """
        Add the geometry from ``template`` to the database.

        :param Template template: new template.
        :return: success
        """
        location = self.getTemplateDir(template.aid)
        ret = self.saveModel(location, template.fragments)
        if not ret.ok:
            return ret
        else:
            return RetVal(True, None, {'url_frag': location})

    @typecheck
    def spawnTemplate(self, objID: int, name: str):
        """
        .. note:: It is the caller's responsibility to ensure that ``objID`` is
                  unique. Dibbler will happily overwrite existing data.

        :param int objID: the object ID
        :param str name: the name of the template to spawn.
        :return: number of files copied.
        """
        # Copy the model from the template- to the instance directory.
        src = self.getTemplateDir(name)
        dst = self.getInstanceDir(objID)

        # Copy every fragment from the template location to the instance
        # location.
        cnt = 0
        query = {'filename': {'$regex': '^{}/.*'.format(src)}}
        for f in self.fs.find(query):
            # Modify the original file name from eg
            # '/templates/temp_name/*' to '/instances/objID/*'.
            name = f.filename.replace(src, dst)

            # Copy the last version of the file from the template- to the
            # instance location.
            src_data = self.fs.get_last_version(f.filename)
            self.fs.put(src_data, filename=name)

            # Increment the file counter.
            cnt += 1

        if cnt == 0:
            # Did not copy any files.
            msg = 'Could not find template <{}>'.format(name)
            return RetVal(False, msg, None)
        else:
            # Found at least one template file to copy.
            url = config.url_instances + '/{}'.format(objID)
            return RetVal(True, None, {'url_frag': url})

    @typecheck
    def updateFragments(self, objID: int, fragments: dict):
        """
        Overwrite all ``fragments`` for ``objID``.

        This function will overwrite (or add) all specified ``fragments`` unless
        their type is *_del_*. If the type is *_del_* then this method will
        delete the respective fragment and update the `meta.json` file
        accordingly.

        :param int objID: the object for which to update the ``fragments``.
        :param dict[str: ``FragMeta``] fragments: new fragments.
        :return: see :func:`saveModel`
        """
        try:
            # Sanity check the fragments.
            fragments = {k: FragMeta(*v) for (k, v) in fragments.items()}
        except (TypeError, ValueError):
            msg = 'Invalid parameters in <updateFragments> command'
            return RetVal(False, msg, None)

        # Overwrite all fragments for the instance with with ``objID``.
        location = self.getInstanceDir(objID)
        return self.saveModel(location, fragments, update=True)

    @typecheck
    def deleteTemplate(self, name: str):
        """
        Delete the template ``name``.

        This function always succeeds but returns the number of actually
        deleted files.

        :param str name: the name of the template to delete.
        :return: number of (unique) files deleted.
        """
        location = self.getTemplateDir(name)
        return self._deleteSubLocation(location)

    @typecheck
    def deleteInstance(self, objID: int):
        """
        Delete the all files belonging to the instance with ``objID``.

        This function always succeeds but returns the number of actually
        deleted files.

        :param int objID: ID of object delete.
        :return: number of files deleted.
        """
        location = self.getInstanceDir(objID)
        return self._deleteSubLocation(location)
