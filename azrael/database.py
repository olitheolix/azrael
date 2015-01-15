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
Database abstractions.
"""
import pymongo
import IPython
import logging

import azrael.util
from azrael.typecheck import typecheck

ipshell = IPython.embed
RetVal = azrael.util.RetVal

# Global database handles.
dbHandles = {}


@typecheck
def reset(reset=False):
    """
    Connect to the State Variable database. Flush it if ``reset`` is **True**.

    fixme: merge this function with 'database.reset'.

    :param bool reset: flush the database.
    """
    global dbHandles
    client = pymongo.MongoClient()
    dbName = 'azrael'
    if reset:
        client.drop_database(dbName)

    dbHandles['SV'] = client[dbName]['sv']
    dbHandles['CmdSpawn'] = client[dbName]['CmdSpawn']
    dbHandles['CmdRemove'] = client[dbName]['CmdRemove']
    dbHandles['CmdModify'] = client[dbName]['CmdModify']
    dbHandles['CmdForce'] = client[dbName]['CmdForceAndTorque']
    dbHandles['Templates'] = client[dbName]['template']
    dbHandles['Counters'] = client[dbName]['Counters']
    dbHandles['WP'] = client[dbName]['WP']


def getNewWPID():
    """
    Return a new and unque WP ID.
    """
    db = dbHandles['Counters'].find_and_modify
    wpid = db({'name': 'wpcnt'},
              {'$inc': {'cnt': 1}},
              new=True, upsert=True)

    if wpid is None:
        return RetVal(False, 'Cannot fetch new WPID', None)
    else:
        return RetVal(True, None, wpid['cnt'])


def getNewObjectID():
    """
    Return a new and unique object ID.
    """
    db = dbHandles['Counters'].find_and_modify
    wpid = db({'name': 'objcnt'},
              {'$inc': {'cnt': 1}},
              new=True, upsert=True)

    if wpid is None:
        return RetVal(False, 'Cannot fetch new object ID', None)
    else:
        return RetVal(True, None, wpid['cnt'])
