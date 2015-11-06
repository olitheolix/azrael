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
Dibbler is a database for files (think of it a an Amazon S3 for the poor).

Dibbler exists because it can store files of any size. It provides methods to
put, get, copy and delete files. The storage system is flat and each file has
exactly one associated name. This name can contain the '/' character and the
application is free to interpret this as directory boundaries.

Storing files in Dibbler comes at the cost of atomicity because the files
should (probably) be stored alongside the state information.  However, those
databases often restrict the size of their documents.

Loss of atomicity is bearable (for now) because files tend to change
infrequently. They usually contain only geometric models and textures.

This version of Dibbler uses Mongo's GridFS to store the files.
"""
import os
import json
import base64
import gridfs
import logging

import azrael.config as config

from IPython import embed as ipshell
from azrael.aztypes import typecheck, Template, RetVal
from azrael.aztypes import FragMeta


class Dibbler:
    """
    Stateless storage backend for Azrael's models.
    """
    def __init__(self):
        # Create a GridFS handle.
        db = config.getMongoClient()['AzraelGridDB']
        self.fs = gridfs.GridFS(db)

        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

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
    def getFile(self, location: str):
        """
        Return the latest version of ``location``.

        If ``location`` does not exist then return an error.

        fixme: utilise 'self.get' to the work here.

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

    def isValidFileName(self, fname):
        """
        fixme: docu
        """
        # Compile the set of admissible characters.
        ref = 'abcdefghijklmnopqrstuvwxyz'
        ref += ref.upper()
        ref += '0123456789_/.'
        ref = set(ref)

        try:
            assert isinstance(fname, str)
            assert set(fname).issubset(ref)
        except AssertionError:
            return False
        return True

    @typecheck
    def put(self, files: dict):
        """
        Fixme: docu
        """
        # Sanity check input files.
        try:
            for fname, fdata in files.items():
                assert isinstance(fdata, bytes)
                assert self.isValidFileName(fname)
        except AssertionError as e:
            msg = 'Invalid file name or data format for <{}>'
            msg = msg.format(fname)
            self.logit.info(msg)
            return RetVal(False, msg, None)

        # Write the files to disk.
        for fname, fdata in files.items():
            try:
                self.fs.put(fdata, filename=fname)
            except gridfs.errors.GridFSError as err:
                # fixme: what is the expected return value here?
                self.logit.error('GridFS error')
                pass
        return RetVal(True, None, None)

    @typecheck
    def get(self, fnames: (tuple, list)):
        """
        fixme: docu
        """
        out = {}
        for fname in fnames:
            try:
                out[fname] = self.fs.get_last_version(fname).read()
            except gridfs.errors.NoFile as err:
                pass
            except gridfs.errors.GridFSError as err:
                # All other GridFS errors.
                pass
        return RetVal(True, None, out)

    @typecheck
    def copy(self, srcdst: dict):
        """
        fixme: docu

        :param dict srcdst: eg {'src1': 'dst1', 'src2': 'dst2', ...}
        """
        # Verify that all targets are unique.
        dst = list(srcdst.values())
        if sorted(dst) != sorted(list(set(dst))):
            return RetVal(False, 'Not all targets are unique', None)

        num_copied = 0
        for src, dst in srcdst.items():
            try:
                ret = self.get([src])
                assert ret.ok and src in ret.data
                assert self.put({dst: ret.data[src]}).ok
                num_copied += 1
            except AssertionError:
                continue
        return RetVal(True, None, num_copied)

    @typecheck
    def remove(self, fnames: (tuple, list)):
        """
        Fixme docu.
        """
        num_deleted = 0
        for fname in fnames:
            try:
                found_at_least_one = False
                for mid in self.fs.find({'filename': fname}):
                    ret = self.fs.delete(mid._id)
                    found_at_least_one = True
                if found_at_least_one:
                    num_deleted += 1
            except gridfs.errors.NoFile as err:
                pass
            except gridfs.errors.GridFSError as err:
                # All other GridFS errors.
                pass
        return RetVal(True, None, num_deleted)

    @typecheck
    def removeDirs(self, dirnames: (tuple, list)):
        """
        Fixme docu.
        Fixme: merge _deleteSubLocation
        """
        try:
            for idx, name in enumerate(dirnames):
                assert isinstance(name, str)
                dirnames[idx] = name if name[-1] != '/' else name[:-1]
        except AssertionError:
            return RetVal(False, 'Invalid arguments', None)

        num_deleted = 0
        for name in dirnames:
            ret = self._deleteSubLocation(name)
            if ret.ok:
                num_deleted += ret.data
        return RetVal(True, None, num_deleted)

        num_deleted = 0
        for fname in dirnames:
            try:
                found_at_least_one = False
                for mid in self.fs.find({'filename': fname}):
                    ret = self.fs.delete(mid._id)
                    found_at_least_one = True
                if found_at_least_one:
                    num_deleted += 1
            except gridfs.errors.NoFile as err:
                pass
            except gridfs.errors.GridFSError as err:
                # All other GridFS errors.
                pass
        return RetVal(True, None, num_deleted)
