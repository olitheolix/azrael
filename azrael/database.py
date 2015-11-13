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
import logging

import azrael.config as config
from IPython import embed as ipshell
from azrael.aztypes import typecheck, RetVal

# Global database handles.
logit = logging.getLogger('azrael.' + __name__)

# Connect to MongoDB and store the relevant collection handles in the
# 'dbHandles' variables to avoid hard coded collection names in Azrael.
client = config.getMongoClient()
dbName = 'azrael'
dbHandles = {
    'RBS': client[dbName]['rbs'],
    'Commands': client[dbName]['Cmd'],
    'Templates': client[dbName]['template'],
    'ObjInstances': client[dbName]['objinstances'],
    'Counters': client[dbName]['Counters'],
    'Constraints': client[dbName]['Constraints'],
}


@typecheck
def init():
    """
    Flush the database.
    """
    # Delete the database.
    client.drop_database(dbName)
    dbHandles['ObjInstances'].ensure_index([('objID', 1)])


@typecheck
def getUniqueObjectIDs(numIDs: int):
    """
    Return ``numIDs`` unique object IDs as a tuple.

    If ``numIDs`` is Zero then return a scalar with the current value.

    The ``numIDs`` is positive then return a tuple with ``numIDs`` entries,
    each of which constitutes a unique ID.

    This function returns an error unless ``numIDs`` is non-negative.

    :param int numIDs: non-negative integer.
    :return tuple or scalar: object IDs (numIDs > 0) or last issued object ID
                            (numIDs = 0)
    """
    # Sanity check.
    if numIDs < 0:
        return RetVal(False, 'numIDs must be non-negative', None)

    # Increment the counter by ``numIDs``.
    fam = dbHandles['Counters'].find_and_modify
    doc = fam({'name': 'objcnt'},
              {'$inc': {'cnt': numIDs}},
              new=True, upsert=True)

    # Error check.
    if doc is None:
        return RetVal(False, 'Cannot determine new object IDs', None)

    # Extract the new counter value (after it was incremented).
    cnt = doc['cnt']

    # Return either the current value or the range of new IDs.
    if numIDs == 0:
        return RetVal(True, None, cnt)
    else:
        newIDs = tuple(range(cnt - numIDs + 1, cnt + 1))
        return RetVal(True, None, newIDs)


class DatabaseInMemory:
    def __init__(self, name: tuple):
        self.dbname = name
        self.reset()

    def reset(self):
        self.content = {}
        return RetVal(True, None, None)

    def count(self):
        return RetVal(True, None, len(self.content))

    def put(self, ops: dict, must_exists: bool=False):
        ret = {}
        for aid, op in ops.items():
            exists, data = op['exists'], op['data']
            if exists and aid in self.content:
                self.content[aid] = data
                ret[aid] = True
            elif not exists and aid not in self.content:
                self.content[aid] = data
                ret[aid] = True
            else:
                ret[aid] = False
        return RetVal(True, None, ret)


class DatabaseMongo:
    def __init__(self, name: tuple):
        import pymongo
        self.name_db, self.name_col = name
        client = pymongo.MongoClient()
        self.db = client[self.name_db][self.name_col]
        self.reset()

    def reset(self):
        self.db.drop()
        return RetVal(True, None, None)

    def count(self):
        return RetVal(True, None, self.db.count())

    def put(self, ops: dict, must_exists: bool=False):
        ret = {}
        for aid, op in ops.items():
            exists, data = op['exists'], op['data']
            if exists:
                r = self.db.update_one({'aid': aid}, {'$set': {aid: data}})
                if (r.matched_count == 1) and (r.modified_count == 1):
                    ret[aid] = True
                else:
                    ret[aid] = False
            else:
                r = self.db.update_one(
                    {'aid': aid},
                    {'$setOnInsert': {aid: data}},
                    upsert=True
                )
                if r.acknowledged:
                    ret[aid] = True
                else:
                    ret[aid] = False
        return RetVal(True, None, ret)
