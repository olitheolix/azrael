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


if __name__ == '__main__':
    test_increment_WPCounter()
