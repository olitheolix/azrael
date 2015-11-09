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
import pytest
import azrael.dibbler

import azrael.config as config
from IPython import embed as ipshell
from azrael.test.test import getTemplate, getFragRaw, getFragDae


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

        # Send invalid data format.
        assert not dibbler.put({'xy': 'str_instead_of_bytes'}).ok

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
