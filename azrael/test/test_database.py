import pytest
import IPython

import azrael.database as database

allCounterFunctions = [database.getNewWPID,
                       database.getNewObjectID]


@pytest.mark.parametrize('fun', allCounterFunctions)
def test_increment_WPCounter(fun):
    """
    Reset the Counter DB and fetch a few counter values.
    """
    # Reset Azrael.
    database.init(reset=True)

    # Ask for new counter values.
    for ii in range(5):
        ret = fun()
        assert ret.ok
        assert ret.data == ii + 1

    # Reset Azrael again and verify that all counters start at '1' again.
    database.init(reset=True)
    ret = fun()
    assert ret.ok
    assert ret.data == 1

    print('Test passed')


if __name__ == '__main__':
    for _fun in allCounterFunctions:
        test_increment_WPCounter(_fun)
