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

fixme

docu
"""
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
        ops = {'1': {'exists': False, 'data': {'key': 'value'}}}
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
            '1': {'exists': False, 'data': {'key1': 'value1'}},
            '2': {'exists': False, 'data': {'key2': 'value2'}},
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
        Test all four possible cases when inserting documents, depending on the
        'exists' parameter and whether or not the corresponding document is
        already in the database.
        """
        db = clsDatabase(name=('test1', 'test2'))

        # ---------------------------------------------------------------------
        # Empty database: unconditonal put must succeed.
        # ---------------------------------------------------------------------
        
        # Put unconditionally. Must always succeed.
        assert db.reset().ok and db.count().data == 0
        ops = {'1': {'exists': False, 'data': {'key1': 'value1'}}}
        assert db.put(ops) == (True, None, {'1': True})
        assert db.getOne('1') == (True, None, {'key1': 'value1'})

        # ---------------------------------------------------------------------
        # Empty database: conditional put must fail.
        # ---------------------------------------------------------------------

        # Overwrite if exists. Do nothing otherwise. Since the database is
        # empty nothing must happen.
        assert db.reset().ok and db.count().data == 0
        ops = {'1': {'exists': True, 'data': {'key1': 'value1'}}}
        assert db.put(ops) == (True, None, {'1': False})
        assert db.getOne('1') == (False, None, None)

        # ---------------------------------------------------------------------
        # Non-empty database. Our command specifies that the document must not
        # yet exist. Since it alrady does the update must fail and the original
        # document must prevail.
        # ---------------------------------------------------------------------

        # Put one document into database.
        assert db.reset().ok and db.count().data == 0
        ops = {'1': {'exists': False, 'data': {'key1': 'value1'}}}
        assert db.put(ops) == (True, None, {'1': True})
        assert db.getOne('1') == (True, None, {'key1': 'value1'})

        # Put unconditionally. Must always succeed and replace the current one.
        ops = {'1': {'exists': False, 'data': {'key2': 'value2'}}}
        assert db.put(ops) == (True, None, {'1': False})
        assert db.getOne('1') == (True, None, {'key1': 'value1'})

        # ---------------------------------------------------------------------
        # Non-empty database. Our command specifies that the document must
        # already exist. Since it does the update must proceed and overwrite
        # the original document.
        # ---------------------------------------------------------------------

        # Put one document into database.
        assert db.reset().ok and db.count().data == 0
        ops = {'1': {'exists': False, 'data': {'key1': 'value1'}}}
        assert db.put(ops) == (True, None, {'1': True})
        assert db.getOne('1') == (True, None, {'key1': 'value1'})

        # Conditional 'put'. Must not overwrite the document.
        ops = {'1': {'exists': True, 'data': {'key2': 'value2'}}}
        assert db.put(ops) == (True, None, {'1': True})
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

        # Empty database: unconditonal put must succeed.
        assert db.reset().ok and db.count().data == 0
        ops = {'1': {'exists': False, 'data': {'key1': 'value1'}}}
        ret = db.put(ops)
        assert ret.ok is True
        assert ret.msg is None
        assert ret.data['1'] is True

        # Empty database: conditional put must fail.
        assert db.reset().ok and db.count().data == 0
        ops = {'1': {'exists': True, 'data': {'key1': 'value1'}}}
        ret = db.put(ops)
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
            '1': {'exists': False, 'data': {'key1': 'value1'}},
            '2': {'exists': False, 'data': {'key2': 'value2'}},
            '3': {'exists': False, 'data': {'key3': 'value3'}},
            '4': {'exists': False, 'data': {'key4': 'value4'}},
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
        ops = {'1': {'exists': False, 'data': doc}}
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
        ops = {'1': {'exists': False, 'data': doc}}
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
