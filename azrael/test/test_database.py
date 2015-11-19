"""
Todo: tests for
invalid arguments to any of the methods

put:
 * verify return values for different combinations of exist
 * repeat, but use multiple objects and check the boolean return dict

put/mod must verify that none of the keys contains a dot ('.').

setInc

several corner cases for when a variable to increment does not exist, or if
it does exist but has the wrong type.

rename 'objID' to 'aid' in Mongo driver (only after all of Azrael uses it)

move all Database specific tests into a separate classs and keep one class
that features all the database agnostic tests.

search for all print in clerk/database/test_database

instead of db.update use db.replace_one

don't use a list default argument (eg getAll)

implement getDistinct() method and use in clerk.getAllObjectIDs

go over clerk and eliminate all database calls inside loops.

fixme:
  - rename allEngines to all_engines


docu
"""
import copy
import pytest
import azrael.database as database

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
        database.init()
        ret = database.getUniqueObjectIDs(0)
        assert ret.ok and ret.data == 0

        ret = database.getUniqueObjectIDs(1)
        assert ret.ok and ret.data == (1, )

        # Ask for new counter values.
        for ii in range(5):
            ret = database.getUniqueObjectIDs(1)
            assert ret.ok
            assert ret.data == (ii + 2, )

        # Reset Azrael again and verify that all counters start at '1' again.
        database.init()
        ret = database.getUniqueObjectIDs(0)
        assert ret.ok and ret.data == 0

        ret = database.getUniqueObjectIDs(3)
        assert ret.ok
        assert ret.data == (1, 2, 3)

        # Increment the counter by a different values.
        database.init()
        ret = database.getUniqueObjectIDs(0)
        assert ret.ok and ret.data == 0

        ret = database.getUniqueObjectIDs(2)
        assert ret.ok and ret.data == (1, 2)

        ret = database.getUniqueObjectIDs(3)
        assert ret.ok and ret.data == (3, 4, 5)

        ret = database.getUniqueObjectIDs(4)
        assert ret.ok and ret.data == (6, 7, 8, 9)

        # Run invalid queries.
        assert not database.getUniqueObjectIDs(-1).ok


allEngines = [
    database.DatabaseInMemory,
    database.DatabaseMongo,
]

class TestDatabaseAPI:
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

    @pytest.mark.parametrize('clsDatabase', allEngines)
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

    @pytest.mark.parametrize('clsDatabase', allEngines)
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

    @pytest.mark.parametrize('clsDatabase', allEngines)
    def test_put(self, clsDatabase):
        """
        Attempt to insert new documents. This must succeed when the database
        does not yet contain an object with the same AID. Otherwise the
        database content must not be modified.
        """
        db = clsDatabase(name=('test1', 'test2'))

        # ---------------------------------------------------------------------
        # Put must succeed when no document with the same ID exists in database.
        # ---------------------------------------------------------------------
        
        assert db.reset().ok and db.count().data == 0
        ops = {'1': {'data': {'key1': 'value1'}}}
        assert db.put(ops) == (True, None, {'1': True})
        assert db.getOne('1') == (True, None, {'key1': 'value1'})

        # ---------------------------------------------------------------------
        # Put must fail when no document with the same ID exists in database.
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

    @pytest.mark.parametrize('clsDatabase', allEngines)
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

    @pytest.mark.parametrize('clsDatabase', allEngines)
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

    @pytest.mark.parametrize('clsDatabase', allEngines)
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

    @pytest.mark.parametrize('clsDatabase', allEngines)
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

    def test_projection(self):
        db = database.DatabaseInMemory(name=('test1', 'test2'))

        src = {'x': 1, 'a': {'b0': 2, 'b1': 3}, 'c': {'d': {'e': 3}}}
        assert db.project(src, [['z']]) == {}
        assert db.project(src, [['x']]) == {'x': 1}
        assert db.project(src, [['x'], ['a']]) == {'x': 1, 'a': {'b0': 2, 'b1': 3}}
        assert db.project(src, [['x'], ['a', 'b0']]) == {'x': 1, 'a': {'b0': 2}}
        assert db.project(src, [['x'], ['a', 'b5']]) == {'x': 1}
        assert db.project(src, [['c']]) == {'c': {'d': {'e': 3}}}
        assert db.project(src, [['c', 'd']]) == {'c': {'d': {'e': 3}}}
        assert db.project(src, [['c', 'd', 'e']]) == {'c': {'d': {'e': 3}}}
        assert db.project(src, [['c', 'd', 'blah']]) == {}

    @pytest.mark.parametrize('clsDatabase', allEngines)
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
            
        # Fetch the content via getOne.

        assert db.getOne('1', [['blah']]) == (True, None, {})

        ret = db.getOne('1', [['foo', 'x']])
        assert ret.ok
        assert ret.data == {'foo': {'x': {'y0': 0, 'y1': 1}}}

        ret = db.getOne('1', [['foo', 'x', 'y0']])
        assert ret.ok
        assert ret.data == {'foo': {'x': {'y0': 0}}}

        # Fetch the content via getMulti.

        assert db.getMulti(['1'], [['blah']]) == (True, None, {'1': {}})

        ret = db.getMulti(['1'], [['foo', 'x']])
        assert ret.ok
        assert ret.data == {'1': {'foo': {'x': {'y0': 0, 'y1': 1}}}}

        ret = db.getMulti(['1'], [['foo', 'x', 'y0']])
        assert ret.ok
        assert ret.data == {'1': {'foo': {'x': {'y0': 0}}}}

        # Fetch the content via getAll. For simplicity, just verify that the
        # output matched that of getMult since we just tested that that one
        # worked.
        projections = [ [['blah']], [['foo', 'x']], [['foo', 'x', 'y0']] ]
        for prj in projections:
            assert db.getMulti(['1'], prj) == db.getAll(prj)

    def test_datastore_validJsonKey(self):
        """
        Verify that 'DatastoreBase.validJsonKey' only admits valid JSON
        hierarchy specifiers.
        """
        db = database

        assert db._validJsonKey(('a', )) is True
        assert db._validJsonKey(('a', 'b')) is True
        assert db._validJsonKey(('a', 1)) is False
        assert db._validJsonKey(('a', 'b.c')) is False

    def test_invalid_args_getOne(self):
        """
        Create invalid arguments for 'getOne'.

        The 'get' methods expect two arguments: aid(s) (str) and an optional
        projection (list of lists). The projection must contain only strings,
        none of which must contain the dot ('.') character. That last
        restriction is necessary because the nested JSON hierarchies are
        usually traversed with dots, eg 'parent.child.grandchild'.
        """
        db = database

        # Valid.
        assert db._checkGet('1', [('x', 'y')]) is True

        # AID is not a string.
        assert db._checkGet(1, [['blah']]) is False

        # Projection is not a list of lists.
        assert db._checkGet('1', {}) is False
        assert db._checkGet('1', [{}]) is False

        # Projection does not contain only strings.
        assert db._checkGet('1', [['a', 2]]) is False

        # Projection contains a string with a dot.
        assert db._checkGet('1', [['a', 'b.c']]) is False

    def test_invalid_args_getAll(self):
        """
        Create invalid arguments for 'getAll'.

        Almost identical to `test_invalid_args_getOne`.
        """
        db = database

        # Valid.
        assert db._checkGetAll([('x', 'y')]) is True

        # Projection is not a list of lists.
        assert db._checkGetAll({}) is False
        assert db._checkGetAll([{}]) is False

        # Projection does not contain only strings.
        assert db._checkGetAll([['a', 2]]) is False

        # Projection contains a string with a dot.
        assert db._checkGetAll([['a', 'b.c']]) is False

    def test_invalid_args_put(self):
        """
        Create invalid arguments for 'put'.

        Put takes one argument called 'ops'. This must be a dictionary with a
        string key. The value is another dictionary and must contain two fields
        called 'exists' and 'data'. Their types are bool and dict,
        respectively.
        """
        db = database

        # Valid.
        ops = {'1': {'data': {'foo': 1}}}
        assert db._checkPut(ops) is True

        # 'data' is not a dict.
        ops = {'1': {'data': 'foo'}}
        assert db._checkPut(ops) is False

        # AID is not a string.
        ops = {5: {'data': {}}}
        assert db._checkPut(ops) is False

    def test_invalid_args_remove(self):
        """
        Create invalid arguments for 'remove'.

        The 'remove' methods expect a list of aid strings.
        """
        db = database

        # Not a list of strings.
        assert db._checkRemove([['blah']]) is False
        assert db._checkRemove(['blah', 1]) is False

    def test_invalid_args_mod(self):
        """
        Create invalid arguments for 'mod'.

        The 'mod' methods expect {aid: ops}, where 'ops' is itself a dictionary
        that must contain the keys 'exists', 'inc', 'set', and 'unset. Each of
        those keys hols another dictionary. The keys of those dictionaries must
        be another tuple of strings, none of which must contain the dot ('.')
        character.
        """
        db = database

        ops_valid = {
            '1': {
                'inc': {('foo', 'a'): 1},
                'set': {('foo', 'a'): 20},
                'unset': [('foo', 'a')],
                'exists': {('foo', 'a'): True},
            }
        }

        assert db._checkMod(ops_valid) is True

        # AID is not a string.
        op = {1: {'inc': None, 'set': None, 'unset': None, 'exists': None}}
        assert db._checkMod(op) is False

        # Does not contain all keys.
        op = {'1': {}}
        assert db._checkMod(op) is False

        # Invalid JSON hierarchy in one of the keys.
        valid, invalid = ('foo', 'a'), ('foo.a', 'b')
        op = {'1': {'inc': {invalid: 1}, 'set': {valid: 20},
                    'unset': [valid], 'exists': {valid: True}}}
        assert db._checkMod(op) is False
        op = {'1': {'inc': {valid: 1}, 'set': {invalid: 20},
                    'unset': [valid], 'exists': {valid: True}}}
        assert db._checkMod(op) is False
        op = {'1': {'inc': {valid: 1}, 'set': {valid: 20},
                    'unset': [invalid], 'exists': {valid: True}}}
        assert db._checkMod(op) is False
        op = {'1': {'inc': {valid: 1}, 'set': {valid: 20},
                    'unset': [valid], 'exists': {invalid: True}}}
        assert db._checkMod(op) is False
        del op

        # 'inc' must specify a number.
        ops = copy.deepcopy(ops_valid)
        ops['1']['inc'][('foo', 'a')] = 'b'
        assert db._checkMod(ops) is False

        # 'exists' must specify bools.
        ops = copy.deepcopy(ops_valid)
        ops['1']['exists'][('foo', 'a')] = 5
        assert db._checkMod(ops) is False

        # 'unset' must be a list, not a dict like all the other fields.
        ops = copy.deepcopy(ops_valid)
        ops['1']['unset'] = {('foo', 'a'): 5}
        assert db._checkMod(ops) is False

    def test_hasKey(self):
        db = database.DatabaseInMemory(name=('test1', 'test2'))

        src = {'x': 1, 'a': {'b': 2}, 'c': {'d': {'e': 3}}}
        assert not db.hasKey(src, ['z'])
        assert not db.hasKey(src, ['x', 'a'])
        assert not db.hasKey(src, ['a', 'x'])
        assert db.hasKey(src, ['x'])
        assert db.hasKey(src, ['a'])
        assert db.hasKey(src, ['c'])
        assert db.hasKey(src, ['a', 'b'])
        assert db.hasKey(src, ['c', 'd'])
        assert db.hasKey(src, ['c', 'd', 'e'])

    def test_delKey(self):
        db = database.DatabaseInMemory(name=('test1', 'test2'))

        src = {'x': 1, 'a': {'b': 2}, 'c': {'d': {'e': 3}}}

        db.delKey(src, ['z'])
        assert src == {'x': 1, 'a': {'b': 2}, 'c': {'d': {'e': 3}}}

        db.delKey(src, ['x'])
        assert src == {'a': {'b': 2}, 'c': {'d': {'e': 3}}}

        db.delKey(src, ['a'])
        assert src == {'c': {'d': {'e': 3}}}

        db.delKey(src, ['c', 'd'])
        assert src == {'c': {}}

        db.delKey(src, ['c'])
        assert src == {}

    def test_setKey(self):
        db = database.DatabaseInMemory(name=('test1', 'test2'))

        src = {'x': 1, 'a': {'b': 2}, 'c': {'d': {'e': 3}}}

        db.setKey(src, ['z'], -1)
        assert src == {'x': 1, 'a': {'b': 2}, 'c': {'d': {'e': 3}}, 'z': -1}

        db.setKey(src, ['x'], -1)
        assert src == {'x': -1, 'a': {'b': 2}, 'c': {'d': {'e': 3}}, 'z': -1}

        db.setKey(src, ['a'], -1)
        assert src == {'x': -1, 'a': -1, 'c': {'d': {'e': 3}}, 'z': -1}

        db.setKey(src, ['a'], {'b': -2})
        assert src == {'x': -1, 'a': {'b': -2}, 'c': {'d': {'e': 3}}, 'z': -1}

        db.setKey(src, ['c', 'd', 'e'], -2)
        assert src == {'x': -1, 'a': {'b': -2}, 'c': {'d': {'e': -2}}, 'z': -1}

    @pytest.mark.parametrize('clsDatabase', allEngines)
    def test_modify_single(self, clsDatabase):
        """
        Insert a single document and modify it.
        """
        db = clsDatabase(name=('test1', 'test2'))

        # Reset the database and verify that it is empty.
        assert db.reset().ok and db.count().data == 0

        doc = {
            'foo': {'a': 1, 'b': 2},
            'bar': {'c': 3, 'd': 2},
        }
        ops = {'1': {'data': doc}}
        assert db.put(ops) == (True, None, {'1': True})

        ops = {
            '1': {
                'inc': {('foo', 'a'): 1, ('bar', 'c'): -1},
                'set': {('foo', 'b'): 20},
                'unset': [('bar', 'd')],
                'exists': {('bar', 'd'): True},
            }
        }
        ret = db.mod(ops)
        assert ret.ok
        assert ret.data == {'1': True}
        assert ret.data['1'] is True

        ret = db.getOne('1')
        assert ret.ok
        ref = {
            'foo': {'a': 2, 'b': 20},
            'bar': {'c': 2},
        }
        assert ret.data == ref


if __name__ == '__main__':
    test_increment_WPCounter()
