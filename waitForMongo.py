#!/usr/bin/python3
# Copyright 2014, Oliver Nagy <olitheolix@gmail.com>
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
Auxiliary script that blocks until Mongo can be contacted.

The main purpose of this function is to avoid problems when running from a
Docker container because MongoDB takes a while (up to 1min) to actually
start up and accept connections.
"""
import time
import pymongo


def waitForMongo():
    """
    Block until MongoDB can be contacted.
    """
    print('Waiting for MongoDB to come online', end='', flush=True)
    t0 = time.time()
    while True:
        try:
            client = pymongo.MongoClient()
            break
        except pymongo.errors.ConnectionFailure:
            print('.', end='', flush=True)
            time.sleep(1)
    print('. Done ({}s)'.format(int(time.time() - t0)))


if __name__ == '__main__':
    waitForMongo()
