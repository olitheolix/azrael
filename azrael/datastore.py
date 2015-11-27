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
import pymongo
import logging

import azrael.config as config
from IPython import embed as ipshell
from azrael.aztypes import typecheck, RetVal

# Global database handles.
logit = logging.getLogger('azrael.' + __name__)

dbHandles = {}

def init(flush):
    """
    Create all data stores and reset their content.

    This method will update the global dbHandles dictionary. Its keys are
    handles to subclasses of `DatastoreBase` instances.
    """
    global dbHandles

    # Create all the data stores.
    names = ('Commands', 'Constraints', 'Counters', 'ObjInstances', 'Templates')
    try:
        dbHandles = {name: DatabaseMongo(('azrael', name)) for name in names}
    except IOError:
        return RetVal(False, 'Could not initialise Datastore', None)

    # Reset each data store.
    if flush:
        for name in names:
            dbHandles[name].reset()
    return RetVal(True, 'Could not initialise Datastore', None)


@typecheck
def getUniqueObjectIDs(numIDs: int):
    """
    Return ``numIDs`` unique object IDs as a tuple.

    If ``numIDs`` is Zero then return a scalar with the current value.

    If ``numIDs`` is positive then return a tuple with ``numIDs`` entries,
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
    db = dbHandles['Counters']
    ret = db.incrementCounter('objcnt', numIDs)
    if not ret.ok:
        return ret

    # Return either the current value or the range of new IDs.
    cnt = ret.data
    if numIDs == 0:
        return RetVal(True, None, cnt)
    else:
        newIDs = tuple(range(cnt - numIDs + 1, cnt + 1))
        return RetVal(True, None, newIDs)


def _checkGet(aids: (tuple, list), prj: list):
    """
    Return True if the ``aids`` and ``prj`` are valid inputs to the
    `get{One, Multi, All}` methods.

    Example:: _checkGet(['foo', 'bar'], [('a', 'b')])

    :param str AIDs: the object ID.
    :param list[list] prj: list of (nested) JSON keys.
    :return: bool
    """
    try:
        # Each AID must be a string.
        for aid in aids:
            assert isinstance(aid, str)

        # Prj can be None. If it is not then it must be a list of lists/tuples.
        # Each of these inner lists/tuples must denote a valid JSON key.
        if prj is not None:
            assert isinstance(prj, (list, tuple))
            for jsonkey in prj:
                assert _validJsonKey(jsonkey)
    except (KeyError, AssertionError, TypeError):
        return False
    return True


def _checkGetAll(prj: list):
    """
    Return True if ``prj`` is valid.

    A projection is valid iff all its constitents are valid JSON keys.

    Example:: _checkGetAll([('x', 'y')])

    :param list prj: list of projection keys.
    :return: bool
    """
    try:
        if prj is not None:
            assert isinstance(prj, (list, tuple))
            for jsonkey in prj:
                assert _validJsonKey(jsonkey)
    except (KeyError, AssertionError, TypeError):
        return False
    return True


def _checkPut(ops: dict):
    """
    Return True if ``ops`` is valid input for {'put', 'replace'}.

    All keys in the ``ops`` dictionary must be strings. All the values must be
    dictionaries.

    Example:: _checkPut({'1': {'data': {'foo': 1}}})

    :param dict ops: put/replace operations.
    :return: bool
    """
    try:
        for key, value in ops.items():
            assert isinstance(key, str)
            assert isinstance(value['data'], dict)
    except (KeyError, AssertionError):
        return False
    return True


def _checkMod(ops):
    """
    Return True if ``ops`` is valid input for 'mod'.

    All keys in the ``ops`` dictionary must be strings. All the values must be
    dictionaries with the folling keys: 'inc', 'set', 'unset', 'exists'.

    See unit tests for examples.

    :param dict ops: mod operations.
    :return: bool
    """
    try:
        for key, value in ops.items():
            # The key is the AID and must thus be a string.
            assert isinstance(key, str)

            # The 'inc' field must be a dictionary. Its keys must be valid JSON
            # keys and its values must be numbers only.
            assert isinstance(value['inc'], dict)
            for k_inc, v_inc in value['inc'].items():
                assert _validJsonKey(k_inc)
                assert isinstance(v_inc, (float, int))

            # The 'set' field must be a dictionary. All its keys must be valid
            # JSON keys.
            assert isinstance(value['set'], dict)
            for k_set, v_set in value['set'].items():
                assert _validJsonKey(k_set)

            # The 'unset' field must be a dictionary. All its keys must be
            # valid JSON keys.
            assert isinstance(value['unset'], (tuple, list))
            for v_unset in value['unset']:
                assert _validJsonKey(v_unset)

            # The 'exists' field must be a dictionary. All its keys must be
            # valid JSON keys and all its values must be Boolean.
            assert isinstance(value['exists'], dict)
            for k_exists, v_exists in value['exists'].items():
                assert _validJsonKey(k_exists)
                assert isinstance(v_exists, bool)
    except (KeyError, AssertionError) as err:
        return False
    return True


def _checkRemove(aids):
    """
    Return True if all ``aids`` are strings.

    Example:: _checkRemove(['foo', 'bar'])

    :param list aids: The AIDS to remove.
    :return: bool
    """
    try:
        for aid in aids:
            assert isinstance(aid, str)
    except AssertionError:
        return False
    return True


@typecheck
def _validJsonKey(name: (list, tuple)):
    """
    Return True if ``name`` constitutes a valid (nested) key.

    Datastores use nested JSON documents. To reach a key the nested
    hierarchy requires one valid key per nesting level. These keys must be
    strings and they must not contain the dot ('.') character.

    Valid example: ('foo', 'bar'). This is valid and references the element
             J['foo']['bar'].

    Invalid eample: ('fo.o', 'bar') is invalid because it contains a dot.

    :param list/tuple name: the (nested) field name to verify.
    :return: bool
    """
    try:
        assert isinstance(name, (tuple, list))
        for n in name:
            assert isinstance(n, str)
        assert '.' not in ''.join(name)
    except (AssertionError, TypeError):
        return False
    return True


class DatastoreBase:
    """
    Base class for all Datastores.

    This class merely specifies the API.

    :param tuple[str, str] name: (db_name, collection_name)
    """
    def __init__(self, name: tuple):
        # Sanity check name. Must be a tuple of two strings.
        assert len(name) == 2
        assert isinstance(name[0], str)
        assert isinstance(name[1], str)

        # Store the database/collection name (or whatever terminology the
        # database uses).
        self.dbname = name

        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

    def reset(self):
        """
        Flush the database.
        """
        raise NotImplementedError

    def count(self):
        """
        Return the number of documents currently in the data store.

        :return: int #documents in data store.
        """
        raise NotImplementedError

    def allKeys(self):
        """
        Return a list of all AIDs currently in the data store.

        :return: list[str] AIDs.
        """
        raise NotImplementedError

    def getOne(self, aid: str, prj=None):
        """
        Return the document with ``aid``, or None if it does not exist.

        :param str aid: AID of object.
        :param list prj: only return the fields specified in ``prj``.
        :return: document dictionary.
        """
        raise NotImplementedError

    def getMulti(self, aids: (list, tuple), prj=None):
        """
        Return the documents with ``aid``.

        Return the documents in a dictionary. The keys are the AIDs and the
        values the documents. If an AID does not exist the value is None.

        The `ok` flag indicates either malformed arguments or a database error.
        A query for non-existing objects will still return ok=True.

        :param str aid: AID of object.
        :param list prj: only return the fields specified in ``prj``.
        :return: document dictionary.
        """
        raise NotImplementedError

    def getAll(self, prj=None):
        """
        Return all documents in the database in a dictionary.

        The keys in the return dictionary correspond to the AIDs.

        The `ok` flag indicates either malformed arguments or a database error.

        :param list prj: only return the fields specified in ``prj``.
        :return: document dictionary.
        """
        raise NotImplementedError

    def put(self, ops: dict):
        """
        Insert a not yet existing document into the data store.

        This method does nothing to already existing documents in the database
        that have the same AID.

        The boolean values in the returned dictionary state whether the
        document was inserted or not.

        Example::

            doc = {'key1': 'value1'}
            db.put({'1': {'data': doc}}) == (True, None, {'1': True})

        :param dict ops: insert operations.
        :return: dict
        """
        raise NotImplementedError

    def replace(self, ops: dict):
        """
        Replace existing documents.

        If one of the documents specified in ``ops`` does not exist then it is
        ignored (ie not inserted).

        The boolean values in the returned dictionary state whether the
        document was replaced or not.

        Example::

            doc = {'key1': 'value1'}
            db.replace({'1': {'data': doc}}) == (True, None, {'1': True})

        :param dict ops: insert operations.
        :return: dict
        """
        raise NotImplementedError

    def modify(self, ops: dict):
        """
        Modify the documents specified in ``ops``.

        The returned boolean dictionary states which documents were modified
        (unmodified documents did not exist).

        Example::

            ops = {
                '1': {
                    'inc': {('foo', 'a'): 1, ('bar', 'c'): -1},
                    'set': {('foo', 'b'): 20},
                    'unset': [('bar', 'd')],
                    'exists': {('bar', 'd'): True},
                }
            }
            db.mod(ops) == (True, None, {'1': True})

        :param dict ops: document specific modifications.
        :return: dict of bools
        """
        raise NotImplementedError

    def remove(self, aids: (tuple, list)):
        """
        Remove the documents with the specified ``aids``.

        Return the number of actually removed documents.

        :param list aids: list of AID strings.
        :return: int number of actually removed objects.
        """
        raise NotImplementedError

    def setCounter(self, counter_name: str, value: int):
        """
        Set ``counter_name`` to ``value`` and return ``value``.

        If the counter variable does not yet exist it then create it.

        :param str counter_name: name of counter to set.
        :param int value: initial counter value.
        :return: the counter ``value`` upon success.
        """
        raise NotImplementedError
        
    def getCounter(self, counter_name: str):
        """
        Return value of ``counter_name``.

        Return None if ``counter_name`` does not exist.

        :param str counter_name: return the value for this counter.
        :return: current value of ``counter_name``.
        """
        raise NotImplementedError
        
    def incrementCounter(self, counter_name: str, value: int):
        """
        Increment ``counter_name`` by ``value`` and return the new value.

        If ``counter_name`` does not yet exist then create it and initialise
        its values with Zero.

        :param str counter_name: name of counter.
        :param int value: add this value to the current counter.
        :return: new counter value
        """
        raise NotImplementedError
        
    def deleteCounter(self, counter_name: str):
        """
        Delete the counter.

        This method always suceeds.
        
        :param str counter_name: return the value for this counter.
        :return: current value of ``counter_name``.
        """
        raise NotImplementedError
        


class DatabaseInMemory(DatastoreBase):
    """
    Implements the Datastore as a simple dictionary.

    This class is currently only useful for testing because different instances
    operate on their own copy of the database.

    The main purpose of this class is to (eventually) speed up the unit tests,
    and have a reference implementation for the ideal Datastore for Azrael.
    """
    @typecheck
    def __init__(self, name: tuple):
        super().__init__(name)

        # Setup the database dictionary.
        self.reset()

    # -------------------------------------------------------------------------
    #                             API methods.
    # -------------------------------------------------------------------------
    def reset(self):
        """
        See docu in ``DatastoreBase``.
        """
        self.content = {}
        self.counters = {}
        return RetVal(True, None, None)

    def count(self):
        """
        See docu in ``DatastoreBase``.
        """
        return RetVal(True, None, len(self.content))

    def allKeys(self):
        """
        See docu in ``DatastoreBase``.
        """
        keys = list(self.content.keys())
        return RetVal(True, None, keys)

    @typecheck
    def getOne(self, aid: str, prj=None):
        """
        See docu in ``DatastoreBase``.
        """
        if _checkGet([aid], prj) is False:
            self.logit.warning('Invalid GETONE argument')
            return RetVal(False, 'Argument error', None)

        doc = self.content.get(aid, None)
        if doc is None:
            return RetVal(False, None, None)
        else:
            if prj is not None:
                doc = self.project(doc, prj)
            return RetVal(True, None, doc)

    @typecheck
    def getMulti(self, aids: (list, tuple), prj=None):
        """
        See docu in ``DatastoreBase``.
        """
        # Sanity check the arguments.
        if _checkGet(aids, prj) is False:
            self.logit.warning('Invalid GETMULTI argument')
            return RetVal(False, 'Argument error', None)

        # Copy the requested documents into an output dictionary. If a document
        # does not exist set it to None in the output dictionary.
        cp = copy.deepcopy
        content = self.content
        docs = {aid: content[aid] if aid in content else None
                for aid in aids}

        # Apply the projection operator.
        if prj is not None:
            project = self.project
            docs = {aid: project(doc, prj) for aid, doc in docs.items()}

        return RetVal(True, None, docs)

    @typecheck
    def getAll(self, prj=None):
        """
        See docu in ``DatastoreBase``.
        """
        if _checkGetAll(prj) is False:
            self.logit.warning('Invalid GETALL argument')
            return RetVal(False, 'Argument error', None)

        docs = copy.deepcopy(self.content)
        if prj is not None:
            for doc in docs:
                docs[doc] = self.project(docs[doc], prj)

        return RetVal(True, None, docs)

    @typecheck
    def put(self, ops: dict):
        """
        See docu in ``DatastoreBase``.
        """
        if _checkPut(ops) is False:
            self.logit.warning('Invalid PUT argument')
            return RetVal(False, 'Argument error', None)

        ret = {}
        for aid, op in ops.items():
            data = op['data']
            if aid not in self.content:
                self.content[aid] = data
                ret[aid] = True
            else:
                ret[aid] = False
        return RetVal(True, None, ret)

    @typecheck
    def replace(self, ops: dict):
        """
        See docu in ``DatastoreBase``.
        """
        if _checkPut(ops) is False:
            self.logit.warning('Invalid REPLACE argument')
            return RetVal(False, 'Argument error', None)

        ret = {}
        for aid, op in ops.items():
            data = op['data']
            if aid in self.content:
                self.content[aid] = data
                ret[aid] = True
            else:
                ret[aid] = False
        return RetVal(True, None, ret)

    @typecheck
    def modify(self, ops: dict):
        """
        See docu in ``DatastoreBase``.
        """
        if _checkMod(ops) is False:
            self.logit.warning('Invalid MODIFY argument')
            return RetVal(False, 'Argument error', None)

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

    @typecheck
    def remove(self, aids: (tuple, list)):
        """
        See docu in ``DatastoreBase``.
        """
        if _checkRemove(aids) is False:
            return RetVal(False, 'Argument error', None)

        num_deleted = 0
        for aid in aids:
            try:
                del self.content[aid]
                num_deleted += 1
            except KeyError:
                pass
        return RetVal(True, None, num_deleted)

    # -------------------------------------------------------------------------
    #                         Counter Functionality
    # -------------------------------------------------------------------------
    @typecheck
    def setCounter(self, counter_name: str, value: int):
        """
        See docu in ``DatastoreBase``.
        """
        self.counters[counter_name] = value
        return RetVal(True, None, value)

    @typecheck
    def getCounter(self, counter_name: str):
        """
        See docu in ``DatastoreBase``.
        """
        value = self.counters.get(counter_name)
        return RetVal(True, None, value)

    @typecheck
    def incrementCounter(self, counter_name: str, value: int):
        """
        See docu in ``DatastoreBase``.
        """
        try:
            self.counters[counter_name] += value
        except KeyError:
            self.counters[counter_name] = value

        return RetVal(True, None, self.counters[counter_name])

    @typecheck
    def deleteCounter(self, counter_name: str):
        """
        See docu in ``DatastoreBase``.
        """
        try:
            del self.counters[counter_name]
        except KeyError:
            pass
        return RetVal(True, None, None)


    # -------------------------------------------------------------------------
    #                           Utility methods.
    # -------------------------------------------------------------------------
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

    def project(self, doc, prj):
        doc = copy.deepcopy(doc)
        out = {}
        for p in prj:
            try:
                self.setKey(out, p, self.getKey(doc, p))
            except KeyError:
                continue
        return out


class DatabaseMongo(DatastoreBase):
    def __init__(self, name: tuple):
        super().__init__(name)

        self.name_db, self.name_col = name

        client = pymongo.MongoClient()
        self.db = client[self.name_db][self.name_col]

    # -------------------------------------------------------------------------
    #                             API methods.
    # -------------------------------------------------------------------------
    def reset(self):
        """
        See docu in ``DatastoreBase``.
        """
        self.db.drop()
        self.db.ensure_index(
            [('aid', pymongo.ASCENDING)],
            background=False,
            unique=True
        )
        return RetVal(True, None, None)

    def count(self):
        """
        See docu in ``DatastoreBase``.
        """
        return RetVal(True, None, self.db.count())

    def allKeys(self):
        """
        See docu in ``DatastoreBase``.
        """
        keys = self.db.distinct('aid')
        return RetVal(True, None, keys)

    @typecheck
    def getOne(self, aid: str, prj=None):
        """
        See docu in ``DatastoreBase``.
        """
        if _checkGet([aid], prj) is False:
            self.logit.warning('Invalid GETONE argument')
            return RetVal(False, 'Argument error', None)

        prj = self._compileProjectionOperator(prj)
        doc = self.db.find_one({'aid': aid}, prj)

        if doc is None:
            return RetVal(False, None, None)
        else:
            doc = self._removeAID([doc])[aid]
            return RetVal(True, None, doc)

    @typecheck
    def getMulti(self, aids: (list, tuple), prj=None):
        """
        See docu in ``DatastoreBase``.
        """
        if _checkGet(aids, prj) is False:
            self.logit.warning('Invalid GETMULTI argument')
            return RetVal(False, 'Argument error', None)

        prj = self._compileProjectionOperator(prj)
        cursor = self.db.find({'aid': {'$in': aids}}, prj)
        docs = self._removeAID(cursor)

        out = {_: None for _ in aids}
        out.update(docs)

        return RetVal(True, None, out)

    @typecheck
    def getAll(self, prj=None):
        """
        See docu in ``DatastoreBase``.
        """
        if _checkGetAll(prj) is False:
            self.logit.warning('Invalid GETALL argument')
            return RetVal(False, 'Argument error', None)

        prj = self._compileProjectionOperator(prj)
        cursor = self.db.find({}, prj)
        docs = self._removeAID(cursor)

        return RetVal(True, None, docs)

    @typecheck
    def put(self, ops: dict):
        """
        See docu in ``DatastoreBase``.
        """
        if _checkPut(ops) is False:
            self.logit.warning('Invalid PUT argument')
            return RetVal(False, 'Argument error', None)

        ret = {}
        for aid, op in ops.items():
            data = op['data']
            data = copy.deepcopy(data)
            data['aid'] = aid

            if True:
                r = self.db.update_one(
                    {'aid': aid},
                    {'$setOnInsert': data},
                    upsert=True
                )
                if r.upserted_id is None:
                    ret[aid] = False
                else:
                    ret[aid] = True
        return RetVal(True, None, ret)

    @typecheck
    def replace(self, ops: dict):
        """
        See docu in ``DatastoreBase``.
        """
        if _checkPut(ops) is False:
            self.logit.warning('Invalid REPLACE argument')
            return RetVal(False, 'Argument error', None)

        ret = {}
        for aid, op in ops.items():
            data = op['data']
            data = copy.deepcopy(data)
            data['aid'] = aid
            if True:
                r = self.db.replace_one({'aid': aid}, data, upsert=False)
                ret[aid] = (r.matched_count > 0)
        return RetVal(True, None, ret)

    @typecheck
    def modify(self, ops: dict):
        """
        See docu in ``DatastoreBase``.
        """
        if _checkMod(ops) is False:
            self.logit.warning('Invalid MOD argument')
            return RetVal(False, 'Argument error', None)

        ret = {}
        for aid, op_tmp in ops.items():
            query = {'.'.join(key): {'$exists': yes}
                     for key, yes in op_tmp['exists'].items()}
            query['aid'] = aid

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
            r = self.db.update_one(query, op, upsert=False)

            ret[aid] = (r.matched_count == 1)
        return RetVal(True, None, ret)

    @typecheck
    def remove(self, aids: (tuple, list)):
        """
        See docu in ``DatastoreBase``.
        """
        if _checkRemove(aids) is False:
            self.logit.warning('Invalid REMOVE argument')
            return RetVal(False, 'Argument error', None)

        ret = self.db.delete_many({'aid': {'$in': aids}})
        return RetVal(True, None, ret.deleted_count)

    # -------------------------------------------------------------------------
    #                         Counter Functionality
    # -------------------------------------------------------------------------

    @typecheck
    def setCounter(self, counter_name: str, value: int):
        """
        See docu in ``DatastoreBase``.
        """
        # Each counter has its own document that specifies the counter name and
        # its value. 
        fam = self.db.find_and_modify
        doc = fam(
            {'aid': counter_name},
            {'$set': {'aid': counter_name, 'value': value}},
            new=True, upsert=True,
        )

        if doc is None:
            # This should be impossible.
            msg = 'Could not create counter'
            self.logit.error(msg)
            return RetVal(False, msg, None)

        return RetVal(True, None, doc['value'])

    @typecheck
    def getCounter(self, counter_name: str):
        """
        See docu in ``DatastoreBase``.
        """
        doc = self.db.find_one({'aid': counter_name})
        if doc is None:
            value = None
        else:
            value = doc['value']
        return RetVal(True, None, value)

    @typecheck
    def incrementCounter(self, counter_name: str, value: int):
        """
        See docu in ``DatastoreBase``.
        """
        doc = self.db.find_one_and_update(
            {'aid': counter_name},
            {'$inc': {'value': value}},
            upsert=True,
            return_document=pymongo.ReturnDocument.AFTER
        )

        if doc is None:
            # This should be impossible.
            msg = 'Could not create counter'
            self.logit.error(msg)
            return RetVal(False, msg, None)

        return RetVal(True, None, doc['value'])

    @typecheck
    def deleteCounter(self, counter_name: str):
        """
        See docu in ``DatastoreBase``.
        """
        self.db.delete_one({'aid': counter_name})
        return RetVal(True, None, None)


    # -------------------------------------------------------------------------
    #                           Utility methods.
    # -------------------------------------------------------------------------
    def _removeAID(self, docs):
        docs = {doc['aid']: doc for doc in docs}
        for aid, doc in docs.items():
            del doc['aid']
        return docs

    def _compileProjectionOperator(self, prj):
        """
        Return a Mongo compatible projection operator.
        """
        if prj is None:
            prj = {}
        else:
            prj = {'.'.join(_): True for _ in prj}
            prj['aid'] = True
        prj['_id'] = False
        return prj
