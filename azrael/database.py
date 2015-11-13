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
import copy
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

    def put(self, ops: dict):
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

    def hasKey(self, d, key_hierarchy):
        try:
            tmp = d
            for key in key_hierarchy:
                tmp = tmp[key]
                
        except (KeyError, TypeError):
            return False
        return True
        
    def setKey(self, d, key_hierarchy, value):
        tmp = d
        for key in key_hierarchy[:-1]:
            if key not in tmp:
                tmp[key] = {}
            tmp = tmp[key]
        tmp[key_hierarchy[-1]] = value
        return True

    def incKey(self, d, key_hierarchy, value):
        tmp = d
        for key in key_hierarchy[:-1]:
            if key not in tmp:
                tmp[key] = {}
            tmp = tmp[key]

        try:
            tmp[key_hierarchy[-1]] += value
        except TypeError:
            return False
        return True

    def delKey(self, d, key_hierarchy):
        try:
            tmp = d
            for key in key_hierarchy[:-1]:
                tmp = tmp[key]
            del tmp[key_hierarchy[-1]]
        except (KeyError, TypeError):
            return False
        return True

    def getKey(self, d, key_hierarchy):
        tmp = d
        for key in key_hierarchy:
            tmp = tmp[key]
        return tmp

    def mod(self, ops):
        ret = {}
        for aid, op in ops.items():
            # Verify the specified items exist.
            try:
                c = self.content[aid]
                for key, yes in op['exists'].items():
                    assert self.hasKey(c, key) is yes

                for key_hierarchy in op['inc']:
                    tmp = c
                    for key in key_hierarchy:
                        tmp = tmp[key]
                    assert isinstance(tmp, (float, int))
                ret[aid] = True
            except (AssertionError, KeyError):
                ret[aid] = False
                continue

            for key, val in op['inc'].items():
                self.incKey(self.content[aid], key, val)

            for key in op['unset']:
                self.delKey(self.content[aid], key)

            for key, val in op['set'].items():
                self.setKey(self.content[aid], key, val)

        return RetVal(True, None, ret)
        

    def project(self, doc, prj):
        doc = copy.deepcopy(doc)
        out = {}
        for p in prj:
            try:
                self.setKey(out, p, self.getKey(doc, p))
            except KeyError:
                continue
        return out
        
    def getOne(self, aid, prj=[]):
        doc = self.content.get(aid, None)
        if doc is None:
            return RetVal(False, None, None)
        else:
            if len(prj) > 0:
                doc = self.project(doc, prj)
            return RetVal(True, None, doc)

    def getMulti(self, aids, prj=[]):
        docs = {aid: self.content[aid] for aid in aids if aid in self.content}
        if len(prj) > 0:
            for doc in docs:
                docs[doc] = self.project(docs[doc], prj)

        return RetVal(True, None, docs)

    def getAll(self, prj=[]):
        docs = copy.deepcopy(self.content)
        if len(prj) > 0:
            for doc in docs:
                docs[doc] = self.project(docs[doc], prj)

        return RetVal(True, None, docs)


class DatabaseMongo:
    def __init__(self, name: tuple):
        import pymongo
        self.name_db, self.name_col = name
        client = pymongo.MongoClient()
        self.db = client[self.name_db][self.name_col]
        print(self.db)
        print(self.db.count())

    def reset(self):
        self.db.drop()
        return RetVal(True, None, None)

    def count(self):
        return RetVal(True, None, self.db.count())

    def put(self, ops: dict):
        ret = {}
        for aid, op in ops.items():
            exists, data = op['exists'], op['data']
            data = copy.deepcopy(data)
            data['objID'] = aid
            if exists:
                r = self.db.update({'objID': aid}, data, upsert=False)
                if r['updatedExisting']:
                    ret[aid] = True
                else:
                    ret[aid] = False
            else:
                r = self.db.update_one(
                    {'objID': aid},
                    {'$setOnInsert': data},
                    upsert=True
                )
                if r.upserted_id is None:
                    ret[aid] = False
                else:
                    ret[aid] = True
        return RetVal(True, None, ret)

    def mod(self, ops):
        ret = {}
        for aid, op_tmp in ops.items():
            query = {'.'.join(key): {'$exists': yes} for key, yes in op_tmp['exists'].items()}
            query['objID'] = aid

            # Update operations.
            op = {
                '$inc': {'.'.join(key): val for key, val in op_tmp['inc'].items()},
                '$set': {'.'.join(key): val for key, val in op_tmp['set'].items()},
                '$unset': {'.'.join(key): True for key in op_tmp['unset']},
            }
            # Prune update operations.
            op = {k: v for k, v in op.items() if len(v) > 0}

            # If no updates are necessary then skip this object.
            if len(op) == 0:
                continue

            # Issue the database query.
            print('\nQuery:', query)
            print('Op:', op)
            r = self.db.update_one(query, op, upsert=False)
            ret[aid] = r.acknowledged
        return RetVal(True, None, ret)
        
    def _removeAID(self, docs):
        docs = {doc['objID']: doc for doc in docs}
        for aid, doc in docs.items():
            del doc['objID']
        return docs

    def getOne(self, aid, prj=[]):
        prj = {'.'.join(_): True for _ in prj}
        prj['_id'] = False

        doc = self.db.find_one({'objID': aid}, prj)
        try:
            del doc['objID']
        except (KeyError, TypeError):
            pass

        if doc is None:
            return RetVal(False, None, None)
        else:
            return RetVal(True, None, doc)

    def getMulti(self, aids, prj=[]):
        prj = {'.'.join(_): True for _ in prj}
        if len(prj) > 0:
            prj['objID'] = True
        prj['_id'] = False
        cursor = self.db.find({'objID': {'$in': aids}}, prj)
        docs = self._removeAID(cursor)
        return RetVal(True, None, docs)

    def getAll(self, prj=[]):
        prj = {'.'.join(_): True for _ in prj}
        if len(prj) > 0:
            prj['objID'] = True
        prj['_id'] = False
        cursor = self.db.find({}, prj)
        docs = self._removeAID(cursor)
        return RetVal(True, None, docs)
