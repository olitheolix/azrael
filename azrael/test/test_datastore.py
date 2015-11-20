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
import copy
import pytest
import azrael.datastore as datastore

from IPython import embed as ipshell


class TestAtomicCounter:
    @classmethod
    def setup_class(cls):
        pass

    @classmethod
    def teardown_class(cls):
        pass

    def setup_method(self, method):
        pass

    def teardown_method(self, method):
        pass

    def test_increment_WPCounter(self):
        """
        Reset the Counter DB and fetch a few counter values.
        """
        # Reset Azrael.
        datastore.init()
        ret = datastore.getUniqueObjectIDs(0)
        assert ret.ok and ret.data == 0

        ret = datastore.getUniqueObjectIDs(1)
        assert ret.ok and ret.data == (1, )

        # Ask for new counter values.
        for ii in range(5):
            ret = datastore.getUniqueObjectIDs(1)
            assert ret.ok
            assert ret.data == (ii + 2, )

        # Reset Azrael again and verify that all counters start at '1' again.
        datastore.init()
        ret = datastore.getUniqueObjectIDs(0)
        assert ret.ok and ret.data == 0

        ret = datastore.getUniqueObjectIDs(3)
        assert ret.ok
        assert ret.data == (1, 2, 3)

        # Increment the counter by a different values.
        datastore.init()
        ret = datastore.getUniqueObjectIDs(0)
        assert ret.ok and ret.data == 0

        ret = datastore.getUniqueObjectIDs(2)
        assert ret.ok and ret.data == (1, 2)

        ret = datastore.getUniqueObjectIDs(3)
        assert ret.ok and ret.data == (3, 4, 5)

        ret = datastore.getUniqueObjectIDs(4)
        assert ret.ok and ret.data == (6, 7, 8, 9)

        # Run invalid queries.
        assert not datastore.getUniqueObjectIDs(-1).ok


class TestAllDatastoreBackends:
    """
    The tests here are valid for every storage backend listed in all_engines.
    """
    # Used in the py.test decorator to apply every test each backend.
    all_engines = [
        datastore.DatabaseInMemory,
        datastore.DatabaseMongo,
    ]

    @classmethod
    def setup_class(cls):
        pass

    @classmethod
    def teardown_class(cls):
        pass

    def setup_method(self, method):
        pass

    def teardown_method(self, method):
        pass

    @pytest.mark.parametrize('clsDatabase', all_engines)
    def test_reset_add(self, clsDatabase):
        """
        Add data and verify that 'reset' flushes it.
        """
        db = clsDatabase(name=('test1', 'test2'))

        # Reset the database and verify that it is empty.
        assert db.reset().ok
        assert db.count() == (True, None, 0)

        # Insert one document and verify the document count is now at 1.
        ops = {'1': {'data': {'key': 'value'}}}
        assert db.put(ops) == (True, None, {'1': True})
        assert db.count() == (True, None, 1)

        # Reset the database and verfify that it is empty again.
        assert db.reset() == (True, None, None)
        assert db.count() == (True, None, 0)

    @pytest.mark.parametrize('clsDatabase', all_engines)
    def test_add_get(self, clsDatabase):
        """
        Add data and verify that 'reset' flushes it.
        """
        db = clsDatabase(name=('test1', 'test2'))

        # Reset the database and verify that it is empty.
        assert db.reset().ok and db.count().data == 0

        # Insert two documents and verify the document count.
        ops = {
            '1': {'data': {'key1': 'value1'}},
            '2': {'data': {'key2': 'value2'}},
        }
        assert db.put(ops) == (True, None, {'1': True, '2': True})
        assert db.count() == (True, None, 2)

        # Fetch the content via three different methods.

        # getOne:
        assert db.getOne('1') == (True, None, ops['1']['data'])
        assert db.getOne('2') == (True, None, ops['2']['data'])

        # getMulti:
        tmp = {'1': ops['1']['data'], '2': ops['2']['data']}
        assert db.getMulti(['1', '2']) == (True, None, tmp)

        # getAll:
        assert db.getMulti(['1', '2']) == db.getAll()

        assert db.reset().ok and (db.count().data == 0)

    @pytest.mark.parametrize('clsDatabase', all_engines)
    def test_put(self, clsDatabase):
        """
        Attempt to insert new documents. This must succeed when the database
        does not yet contain an object with the same AID. Otherwise the
        database content must not be modified.
        """
        db = clsDatabase(name=('test1', 'test2'))

        # ---------------------------------------------------------------------
        # Put must succeed when no document with the same ID exists in datastore.
        # ---------------------------------------------------------------------

        assert db.reset().ok and db.count().data == 0
        ops = {'1': {'data': {'key1': 'value1'}}}
        assert db.put(ops) == (True, None, {'1': True})
        assert db.getOne('1') == (True, None, {'key1': 'value1'})

        # ---------------------------------------------------------------------
        # Put must fail when no document with the same ID exists in datastore.
        # ---------------------------------------------------------------------

        # Pre-fill database with one document.
        assert db.reset().ok and db.count().data == 0
        ops = {'1': {'data': {'key1': 'value1'}}}
        assert db.put(ops) == (True, None, {'1': True})
        assert db.getOne('1') == (True, None, {'key1': 'value1'})

        # Put must not return an error but also not modify the document.
        ops = {'1': {'data': {'key2': 'value2'}}}
        assert db.put(ops) == (True, None, {'1': False})
        assert db.getOne('1') == (True, None, {'key1': 'value1'})

        # ---------------------------------------------------------------------
        # Attempt to insert two new documents, one of which already exists.
        # ---------------------------------------------------------------------
        ops = {
            '1': {'data': {'key3': 'value3'}},
            '2': {'data': {'key4': 'value4'}},
        }
        assert db.put(ops) == (True, None, {'1': False, '2': True})
        assert db.count() == (True, None, 2)

        # Query both documents. Both must exist.
        ret = db.getMulti(['1', '2'])
        assert ret.ok
        assert ret.data == {'1': {'key1': 'value1'}, '2': {'key4': 'value4'}}

    @pytest.mark.parametrize('clsDatabase', all_engines)
    def test_replace(self, clsDatabase):
        """
        Attempt to replace existing and non-existing documents.
        """
        db = clsDatabase(name=('test1', 'test2'))

        # ---------------------------------------------------------------------
        # Replacing a non-existing document must do nothing.
        # ---------------------------------------------------------------------

        # Overwrite if exists. Do nothing otherwise. Since the database is
        # empty nothing must happen.
        assert db.reset().ok and db.count().data == 0
        ops = {'1': {'data': {'key1': 'value1'}}}
        assert db.replace(ops) == (True, None, {'1': False})
        assert db.getOne('1') == (False, None, None)

        # ---------------------------------------------------------------------
        # Replacing an existing document must succeed.
        # ---------------------------------------------------------------------

        # Pre-fill database with one document.
        assert db.reset().ok and db.count().data == 0
        ops = {'1': {'data': {'key1': 'value1'}}}
        assert db.put(ops) == (True, None, {'1': True})
        assert db.getOne('1') == (True, None, {'key1': 'value1'})

        # Replace the existing document with a new one.
        ops = {'1': {'data': {'key2': 'value2'}}}
        assert db.replace(ops) == (True, None, {'1': True})
        assert db.getOne('1') == (True, None, {'key2': 'value2'})

        # ---------------------------------------------------------------------
        # Attempt to replace two documents, only one of which already exists.
        # ---------------------------------------------------------------------
        ops = {
            '1': {'data': {'key3': 'value3'}},
            '2': {'data': {'key4': 'value4'}},
        }
        assert db.replace(ops) == (True, None, {'1': True, '2': False})
        assert db.count() == (True, None, 1)

        # Query both documents albeit only one exists. The value for the
        # non-existing one must be None.
        ret = db.getMulti(['1', '2'])
        assert ret.ok
        assert ret.data == {'1': {'key3': 'value3'}, '2': None}

    @pytest.mark.parametrize('clsDatabase', all_engines)
    def test_put_boolean_return(self, clsDatabase):
        """
        In Python `1 == 1 == True` and `0 == 0 == False`. The API
        specifies that the return value for the `put` operations are bools,
        However, most tests in this harness just use the `==' to check. This is
        usually alright and yet the problem did arise. This test will therefore
        explicity verify that the return values are bools not integers.
        """
        db = clsDatabase(name=('test1', 'test2'))

        # Empty database: put must insert a new document.
        assert db.reset().ok and db.count().data == 0
        ops = {'1': {'data': {'key1': 'value1'}}}
        ret = db.put(ops)
        assert ret.ok is True
        assert ret.msg is None
        assert ret.data['1'] is True

        # Empty database: replace must not return an error but also not insert
        # a new document.
        assert db.reset().ok and db.count().data == 0
        ops = {'1': {'data': {'key1': 'value1'}}}
        ret = db.replace(ops)
        assert ret.ok is True
        assert ret.msg is None
        assert ret.data['1'] is False

    @pytest.mark.parametrize('clsDatabase', all_engines)
    def test_getMulti_getAll(self, clsDatabase):
        """
        Insert some documents. Then query them in batches.
        """
        db = clsDatabase(name=('test1', 'test2'))

        # Empty database: unconditonal put must succeed.
        assert db.reset().ok and db.count().data == 0
        ops = {
            '1': {'data': {'key1': 'value1'}},
            '2': {'data': {'key2': 'value2'}},
            '3': {'data': {'key3': 'value3'}},
            '4': {'data': {'key4': 'value4'}},
        }
        assert db.put(ops) == (True, None, {str(_): True for _ in range(1, 5)})
        assert db.count() == (True, None, 4)

        # If the query is empty then no documents must be returned.
        assert db.getMulti([]) == (True, None, {})

        # A query for non-existing documents must return a None for each AID.
        ret = db.getMulti(['5', '6'])
        assert ret == (True, None, {'5': None, '6': None})

        # Query two existing documents.
        ret = db.getMulti(['1', '4'])
        assert ret.ok
        assert ret.data == {'1': {'key1': 'value1'}, '4': {'key4': 'value4'}}

        # Query two documents. Only one exists. This must return the document
        # for the existing one, and None for the not-existing one.
        ret = db.getMulti(['2', '5'])
        assert ret.ok
        assert ret.data == {'2': {'key2': 'value2'}, '5': None}

        # getAll and getMulti must return the exact same data when getMulti was
        # asked for all documents.
        assert db.getAll() == db.getMulti(['1', '2', '3', '4'])

    @pytest.mark.parametrize('clsDatabase', all_engines)
    def test_remove(self, clsDatabase):
        """
        Insert some documents. Then delete them.
        """
        db = clsDatabase(name=('test1', 'test2'))

        # Empty database: unconditonal put must succeed.
        assert db.reset().ok and db.count().data == 0
        ops = {
            '1': {'data': {'key1': 'value1'}},
            '2': {'data': {'key2': 'value2'}},
            '3': {'data': {'key3': 'value3'}},
            '4': {'data': {'key4': 'value4'}},
        }
        assert db.put(ops) == (True, None, {str(_): True for _ in range(1, 5)})
        assert db.count() == (True, None, 4)

        # Attempt to delete a non-existing document. This must not return
        # error, yet the database must remain unchanged.
        assert db.remove(['5']) == (True, None, 0)
        assert db.count() == (True, None, 4)

        # Delete one document.
        assert db.remove(['2']) == (True, None, 1)
        assert db.count() == (True, None, 3)

        # Delete two documents.
        assert db.remove(['1', '3']) == (True, None, 2)
        assert db.count() == (True, None, 1)

        # Delete two documents, only of which exists.
        assert db.remove(['1', '4']) == (True, None, 1)
        assert db.count() == (True, None, 0)

    @pytest.mark.parametrize('clsDatabase', all_engines)
    def test_allKeys(self, clsDatabase):
        """
        Verify the allKeys method.
        """
        db = clsDatabase(name=('test1', 'test2'))

        # Empty database: unconditonal put must succeed.
        assert db.reset().ok and db.count().data == 0
        ops = {
            '1': {'data': {'key1': 'value1'}},
            '2': {'data': {'key2': 'value2'}},
            '3': {'data': {'key3': 'value3'}},
            '4': {'data': {'key4': 'value4'}},
        }
        assert db.put(ops) == (True, None, {str(_): True for _ in range(1, 5)})
        assert db.count() == (True, None, 4)
        ret = db.allKeys()
        assert ret.ok
        assert sorted(ret.data) == ['1', '2', '3', '4']

        # Delete two documents.
        assert db.remove(['1', '3']) == (True, None, 2)
        assert db.count() == (True, None, 2)
        ret = db.allKeys()
        assert ret.ok
        assert sorted(ret.data) == ['2', '4']

    @pytest.mark.parametrize('clsDatabase', all_engines)
    def test_get_with_projections(self, clsDatabase):
        """
        Add data and verify that 'reset' flushes it.
        """
        db = clsDatabase(name=('test1', 'test2'))

        # Reset the database and verify that it is empty.
        assert db.reset().ok and db.count().data == 0

        # Insert two documents and verify the document count.
        doc = {
            'foo': {'x': {'y0': 0, 'y1': 1}},
            'bar': {'a': {'b0': 2, 'b1': 3}},
        }
        ops = {'1': {'data': doc}}
        assert db.put(ops) == (True, None, {'1': True})
        assert db.count() == (True, None, 1)

        # ---------------------------------------------------------------------
        # Fetch the content via getOne.
        # ---------------------------------------------------------------------

        assert db.getOne('1', [['blah']]) == (True, None, {})

        ret = db.getOne('1', [['foo', 'x']])
        assert ret.ok
        assert ret.data == {'foo': {'x': {'y0': 0, 'y1': 1}}}

        ret = db.getOne('1', [['foo', 'x', 'y0']])
        assert ret.ok
        assert ret.data == {'foo': {'x': {'y0': 0}}}

        # ---------------------------------------------------------------------
        # Fetch the content via getMulti.
        # ---------------------------------------------------------------------

        assert db.getMulti(['1'], [['blah']]) == (True, None, {'1': {}})

        ret = db.getMulti(['1'], [['foo', 'x']])
        assert ret.ok
        assert ret.data == {'1': {'foo': {'x': {'y0': 0, 'y1': 1}}}}

        ret = db.getMulti(['1'], [['foo', 'x', 'y0']])
        assert ret.ok
        assert ret.data == {'1': {'foo': {'x': {'y0': 0}}}}

        # ---------------------------------------------------------------------
        # Fetch the content via getAll. For simplicity, just verify that the
        # output matched that of getMult since we just tested that that one
        # worked.
        # ---------------------------------------------------------------------
        projections = [
            [['blah']], [['foo', 'x']], [['foo', 'x', 'y0']]
        ]
        for prj in projections:
            assert db.getMulti(['1'], prj) == db.getAll(prj)

    @pytest.mark.parametrize('clsDatabase', all_engines)
    def test_modify_single(self, clsDatabase):
        """
        Insert a single document and modify it.
        """
        db = clsDatabase(name=('test1', 'test2'))

        # Reset the database and verify that it is empty.
        assert db.reset().ok and db.count().data == 0

        # Insert one document.
        doc = {
            'foo': {'a': 1, 'b': 2},
            'bar': {'c': 3, 'd': 2},
        }
        ops = {'1': {'data': doc}}
        assert db.put(ops) == (True, None, {'1': True})

        # Modify that document.
        ops = {
            '1': {
                'inc': {('foo', 'a'): 1, ('bar', 'c'): -1},
                'set': {('foo', 'b'): 20},
                'unset': [('bar', 'd')],
                'exists': {('bar', 'd'): True},
            }
        }
        ret = db.modify(ops)
        assert ret.ok
        assert ret.data == {'1': True}
        assert ret.data['1'] is True

        # Verify the document was modified correctly.
        ret = db.getOne('1')
        assert ret.ok
        ref = {
            'foo': {'a': 2, 'b': 20},
            'bar': {'c': 2},
        }
        assert ret.data == ref


class TestDatabaseInMemory:
    """
    The tests here pertain to various helper functions defined in the datastore
    module (eg. various argument checks).
    """
    @classmethod
    def setup_class(cls):
        pass

    @classmethod
    def teardown_class(cls):
        pass

    def setup_method(self, method):
        self.db = datastore.DatabaseInMemory(name=('test1', 'test2'))

    def teardown_method(self, method):
        pass

    def test_projection(self):
        """
        The projection operator must only return the specified subset of
        fields. The fields can specify a key in a nested JSON hierarchy.
        """
        src = {'x': 1, 'a': {'b0': 2, 'b1': 3}, 'c': {'d': {'e': 3}}}
        assert self.db.project(src, [['z']]) == {}
        assert self.db.project(src, [['x']]) == {'x': 1}
        assert self.db.project(src, [['x'], ['a']]) == {'x': 1, 'a': {'b0': 2, 'b1': 3}}
        assert self.db.project(src, [['x'], ['a', 'b0']]) == {'x': 1, 'a': {'b0': 2}}
        assert self.db.project(src, [['x'], ['a', 'b5']]) == {'x': 1}
        assert self.db.project(src, [['c']]) == {'c': {'d': {'e': 3}}}
        assert self.db.project(src, [['c', 'd']]) == {'c': {'d': {'e': 3}}}
        assert self.db.project(src, [['c', 'd', 'e']]) == {'c': {'d': {'e': 3}}}
        assert self.db.project(src, [['c', 'd', 'blah']]) == {}

    def test_hasKey(self):
        """
        'delKey' is a helper function in the InMemory data store. It returns
        True if a (possibly) nested key exists in the document structure.
        """
        src = {'x': 1, 'a': {'b': 2}, 'c': {'d': {'e': 3}}}
        assert not self.db.hasKey(src, ['z'])
        assert not self.db.hasKey(src, ['x', 'a'])
        assert not self.db.hasKey(src, ['a', 'x'])
        assert self.db.hasKey(src, ['x'])
        assert self.db.hasKey(src, ['a'])
        assert self.db.hasKey(src, ['c'])
        assert self.db.hasKey(src, ['a', 'b'])
        assert self.db.hasKey(src, ['c', 'd'])
        assert self.db.hasKey(src, ['c', 'd', 'e'])

    def test_delKey(self):
        """
        'delKey' is a helper function in the InMemory data store. It must
        remove the specified key if it exists, and do nothing if not.
        """
        src = {'x': 1, 'a': {'b': 2}, 'c': {'d': {'e': 3}}}

        self.db.delKey(src, ['z'])
        assert src == {'x': 1, 'a': {'b': 2}, 'c': {'d': {'e': 3}}}

        self.db.delKey(src, ['x'])
        assert src == {'a': {'b': 2}, 'c': {'d': {'e': 3}}}

        self.db.delKey(src, ['a'])
        assert src == {'c': {'d': {'e': 3}}}

        self.db.delKey(src, ['c', 'd'])
        assert src == {'c': {}}

        self.db.delKey(src, ['c'])
        assert src == {}

    def test_setKey(self):
        """
        'setKey' is a helper function in the InMemory data store. It must
        create/overwrite the specified key in the (nested) JSON document.
        """
        src = {'x': 1, 'a': {'b': 2}, 'c': {'d': {'e': 3}}}

        self.db.setKey(src, ['z'], -1)
        assert src == {'x': 1, 'a': {'b': 2}, 'c': {'d': {'e': 3}}, 'z': -1}

        self.db.setKey(src, ['x'], -1)
        assert src == {'x': -1, 'a': {'b': 2}, 'c': {'d': {'e': 3}}, 'z': -1}

        self.db.setKey(src, ['a'], -1)
        assert src == {'x': -1, 'a': -1, 'c': {'d': {'e': 3}}, 'z': -1}

        self.db.setKey(src, ['a'], {'b': -2})
        assert src == {'x': -1, 'a': {'b': -2}, 'c': {'d': {'e': 3}}, 'z': -1}

        self.db.setKey(src, ['c', 'd', 'e'], -2)
        assert src == {'x': -1, 'a': {'b': -2}, 'c': {'d': {'e': -2}}, 'z': -1}


class TestHelperFunctions:
    """
    The tests here pertain to various helper functions defined in the datastore
    module (eg. various argument checks).
    """
    @classmethod
    def setup_class(cls):
        pass

    @classmethod
    def teardown_class(cls):
        pass

    def setup_method(self, method):
        pass

    def teardown_method(self, method):
        pass

    def test_datastore_validJsonKey(self):
        """
        Verify that 'DatastoreBase.validJsonKey' only admits valid JSON
        hierarchy specifiers.
        """
        assert datastore._validJsonKey(('a', )) is True
        assert datastore._validJsonKey(('a', 'b')) is True
        assert datastore._validJsonKey(('a', 1)) is False
        assert datastore._validJsonKey(('a', 'b.c')) is False

    def test_invalid_args_getOne(self):
        """
        Create invalid arguments for 'getOne'.

        The 'get' methods expect two arguments: aid(s) (str) and an optional
        projection (list of lists). The projection must contain only strings,
        none of which must contain the dot ('.') character. That last
        restriction is necessary because the nested JSON hierarchies are
        usually traversed with dots, eg 'parent.child.grandchild'.
        """
        # Valid.
        assert datastore._checkGet(['1'], [('x', 'y')]) is True

        # AID is not a string.
        assert datastore._checkGet([1], [['blah']]) is False

        # Projection is not a list of lists.
        assert datastore._checkGet(['1'], {}) is False
        assert datastore._checkGet(['1'], [{}]) is False

        # Projection does not contain only strings.
        assert datastore._checkGet(['1'], [['a', 2]]) is False

        # Projection contains a string with a dot.
        assert datastore._checkGet(['1'], [['a', 'b.c']]) is False

    def test_invalid_args_getAll(self):
        """
        Create invalid arguments for 'getAll'.

        Almost identical to `test_invalid_args_getOne`.
        """
        # Valid.
        assert datastore._checkGetAll([('x', 'y')]) is True

        # Projection is not a list of lists.
        assert datastore._checkGetAll({}) is False
        assert datastore._checkGetAll([{}]) is False

        # Projection does not contain only strings.
        assert datastore._checkGetAll([['a', 2]]) is False

        # Projection contains a string with a dot.
        assert datastore._checkGetAll([['a', 'b.c']]) is False

    def test_invalid_args_put(self):
        """
        Create invalid arguments for 'put'.

        Put takes one argument called 'ops'. This must be a dictionary with a
        string key. The value is another dictionary and must contain two fields
        called 'exists' and 'data'. Their types are bool and dict,
        respectively.
        """
        # Valid.
        ops = {'1': {'data': {'foo': 1}}}
        assert datastore._checkPut(ops) is True

        # 'data' is not a dict.
        ops = {'1': {'data': 'foo'}}
        assert datastore._checkPut(ops) is False

        # AID is not a string.
        ops = {5: {'data': {}}}
        assert datastore._checkPut(ops) is False

    def test_invalid_args_remove(self):
        """
        Create invalid arguments for 'remove'.

        The 'remove' methods expect a list of aid strings.
        """
        # Not a list of strings.
        assert datastore._checkRemove([['blah']]) is False
        assert datastore._checkRemove(['blah', 1]) is False

    def test_invalid_args_mod(self):
        """
        Create invalid arguments for 'mod'.

        The 'mod' methods expect {aid: ops}, where 'ops' is itself a dictionary
        that must contain the keys 'exists', 'inc', 'set', and 'unset. Each of
        those keys hols another dictionary. The keys of those dictionaries must
        be another tuple of strings, none of which must contain the dot ('.')
        character.
        """
        ops_valid = {
            '1': {
                'inc': {('foo', 'a'): 1},
                'set': {('foo', 'a'): 20},
                'unset': [('foo', 'a')],
                'exists': {('foo', 'a'): True},
            }
        }

        assert datastore._checkMod(ops_valid) is True

        # AID is not a string.
        op = {1: {'inc': None, 'set': None, 'unset': None, 'exists': None}}
        assert datastore._checkMod(op) is False

        # Does not contain all keys.
        op = {'1': {}}
        assert datastore._checkMod(op) is False

        # Invalid JSON hierarchy in one of the keys.
        valid, invalid = ('foo', 'a'), ('foo.a', 'b')
        op = {'1': {'inc': {invalid: 1}, 'set': {valid: 20},
                    'unset': [valid], 'exists': {valid: True}}}
        assert datastore._checkMod(op) is False
        op = {'1': {'inc': {valid: 1}, 'set': {invalid: 20},
                    'unset': [valid], 'exists': {valid: True}}}
        assert datastore._checkMod(op) is False
        op = {'1': {'inc': {valid: 1}, 'set': {valid: 20},
                    'unset': [invalid], 'exists': {valid: True}}}
        assert datastore._checkMod(op) is False
        op = {'1': {'inc': {valid: 1}, 'set': {valid: 20},
                    'unset': [valid], 'exists': {invalid: True}}}
        assert datastore._checkMod(op) is False
        del op

        # 'inc' must specify a number.
        ops = copy.deepcopy(ops_valid)
        ops['1']['inc'][('foo', 'a')] = 'b'
        assert datastore._checkMod(ops) is False

        # 'exists' must specify bools.
        ops = copy.deepcopy(ops_valid)
        ops['1']['exists'][('foo', 'a')] = 5
        assert datastore._checkMod(ops) is False

        # 'unset' must be a list, not a dict like all the other fields.
        ops = copy.deepcopy(ops_valid)
        ops['1']['unset'] = {('foo', 'a'): 5}
        assert datastore._checkMod(ops) is False


if __name__ == '__main__':
    test_increment_WPCounter()
