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
    def getFile(self, location: str):
        """
        Return the latest version of ``location``.

        If ``location`` does not exist then return an error.

        :param str location: the location to retrieve (eg.
                             '/instances/8/meta.json').
        :return: content of ``location`` (or *None* if an error occurred).
        :rtype: bytes
        """
        ret = self.get([location])
        if ret.ok and location in ret.data:
            return RetVal(True, None, ret.data[location])
        else:
            return RetVal(False, ret.msg, None)

    def isValidFileName(self, fname):
        """
        Return True if ``fname`` is admissible.

        This is a convenience method to ensure that all file names are sane.

        :param str fname: the file name
        :return: bool
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
        Save all ``files`` to Dibbler and return the number of succesful writes.

        The ``files`` argument is a simple {file_name: file_content_in_bytes}
        dictionary. For instance, `files = {'todo.txt': b'foobar'}.

        Errors with the underlying storage are silently ignored. However, the
        return value states how many files were successfully written.

        :param dict files: {fname: content}
        :return: dict (eg. {'written': 3})
        """
        # Sanity checks. File names must be valid. File content must be Bytes.
        try:
            for fname, fdata in files.items():
                assert isinstance(fdata, bytes)
                assert self.isValidFileName(fname)
        except AssertionError as e:
            msg = 'Invalid file name or data format for <{}>'
            msg = msg.format(fname)
            self.logit.info(msg)
            return RetVal(False, msg, None)

        # Save each file.
        num_written = 0
        for fname, fdata in files.items():
            try:
                self.fs.put(fdata, filename=fname)
                num_written += 1
            except gridfs.errors.GridFSError as err:
                self.logit.error('GridFS error')
        return RetVal(True, None, {'written': num_written})

    @typecheck
    def get(self, fnames: (tuple, list)):
        """
        Return the files specified in ``fnames``.

        :param list[str] fname: the file names to retrieve.
        :return: dict[file_name: file_content]
        """
        out = {}
        for fname in fnames:
            try:
                out[fname] = self.fs.get_last_version(fname).read()
            except gridfs.errors.NoFile as err:
                msg = 'GridFS URL <{}> not found'.format(fname)
                self.logit.info(msg)
            except gridfs.errors.CorruptGridFile:
                msg = 'Corrupt GridFS for URL <{}>'.format(fname)
                return RetVal(False, msg, None)
            except gridfs.errors.GridFSError as err:
                # All other GridFS errors.
                return RetVal(False, None, None)

        return RetVal(True, None, out)

    @typecheck
    def copy(self, srcdst: dict):
        """
        Copy the files in ``srcdst``.

        This method only copies individual files. It does not recursivley copy
        directories.

        All destination names must be unique. If they are not then this method
        will return immediately with an error.

        :param dict[src:dst] srcdst: src/dst pairs.
        :return: int num_copied
        """
        # Verify that all targets are unique.
        dst = list(srcdst.values())
        if sorted(dst) != sorted(list(set(dst))):
            return RetVal(False, 'Not all targets are unique', None)

        # Copy each file from src to dst.
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
        Remove all files specified in ``fnames``.

        :param list[str] fname: the file names to retrieve.
        :return: number of deleted files.
        """
        # Iterate over each file and delete it.
        num_deleted = 0
        for fname in fnames:
            try:
                # File names are unique. However, multiple versions of the same
                # file may exist (an implicit GridFS feature).
                found_at_least_one = False
                for mid in self.fs.find({'filename': fname}):
                    self.fs.delete(mid._id)
                    found_at_least_one = True

                # Increment the counter by at most one, no matter how many
                # versions we found.
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
        Recursively delete all directories specified in ``dirnames``.

        This function is the equivalent of 'rm -rf path/*'. It always succeeds
        and returns the number of deleted files.

        :param list[str] fname: the file names to retrieve.
        :return: number of deleted directories.
        """
        # Sanity check: all entries must be strings. If a named does not end
        # with a slash ('/') then add it to avoid ambiguous queries.
        try:
            for idx, name in enumerate(dirnames):
                assert isinstance(name, str)
                dirnames[idx] = name if name[-1] != '/' else name[:-1]
        except AssertionError:
            return RetVal(False, 'Invalid arguments', None)

        # Delete the directories.
        num_deleted = 0
        for dirname in dirnames:
            # Find all filenames that begin with 'dirname' and delete them.
            query = {'filename': {'$regex': '^{}/.*'.format(dirname)}}
            fnames = set()
            for doc in self.fs.find(query):
                fnames.add(doc.filename)
                self.fs.delete(doc._id)

            # Aggregate the total number of deleted files (we do not count
            # multiple versions of the same file.).
            num_deleted += len(fnames)
        return RetVal(True, None, num_deleted)
