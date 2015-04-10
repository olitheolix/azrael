import pytest
import azrael.database as database


def test_increment_WPCounter():
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

    print('Test passed')


if __name__ == '__main__':
    test_increment_WPCounter()
