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

import time
import pymongo
import multiprocessing
import azrael.config as config

# Use 'fork' system call to create new processes.
multiprocessing.set_start_method('fork')


def waitForDatabase(timeout=60):
    """
    Raise `ImportError` if we cannot reach MongoDB within ``timeout`` seconds.

    Azrael crucially relies on MongoDB. The main purpose of this function is to
    ensure it is ready. However, MongoDB may need time to start up because it
    eg runs in a different container, started slower than Azrael, ...
    """
    def isMongoLive():
        """
        Return *True* if connecting to MongoDB is possible.
        """
        try:
            config.getMongoClient()
        except pymongo.errors.ConnectionFailure:
            return False
        return True

    # Attempt to reach MongoDB for `timeout` seconds before giving up.
    t0 = time.time()
    print('Connecting to MongoDB: ', flush=True, end='')
    while not isMongoLive():
        if time.time() - t0 > timeout:
            # A minute has passed - abort with an error.
            print('failed!')
            print('Could not connect to MongoDB -- Abort')
            raise ImportError('Could not connect to MongoDB')
        time.sleep(1)
        print('.', end='', flush=True)
    print('success!')


# Do not proceed with Azrael until MongoDB is accessible.
waitForDatabase(timeout=60)
