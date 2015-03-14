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
import sys
import time
import pymongo
import subprocess
import multiprocessing


def isMongoLive():
    """
    Return *True* if MongoDB is now online.
    """
    try:
        client = pymongo.MongoClient()
    except pymongo.errors.ConnectionFailure:
        return False
    return True


def ensureMongoIsLive():
    """
    Start MongoDB if it is not already live.
    """
    def startMongo():
        mdir = '/demo/azrael/volume/mongodb'
        os.makedirs(mdir, exist_ok=True)
        cmd_mongo = ('/usr/bin/mongod --smallfiles --dbpath {}'.format(mdir))
        subprocess.call(cmd_mongo, shell=True, stdout=subprocess.DEVNULL)

    # Start MongoDB and wait until it is live.
    proc = None
    if not isMongoLive():
        # Start MongoDB.
        print('Launching MongoDB ', end='', flush=True)
        proc = multiprocessing.Process(target=startMongo)
        proc.start()

        # Give MongoDB at most 2 minutes to start up.
        for ii in range(120):
            if isMongoLive():
                # Yep, it is live.
                break

            # 120 seconds have expired.
            if ii >= 60:
                print(' error. Could not connect to MongoDB -- Abort')
                sys.exit(1)

            # Print status to terminal.
            print('.', end='', flush=True)
            time.sleep(2)
        print(' success')

    print('MongoDB now live. Azrael ready to launch.')


# Start MongoDB if we are running inside a Docker container.
if 'INSIDEDOCKER' in os.environ:
    ensureMongoIsLive()
