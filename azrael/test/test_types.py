import numpy as np
import azrael.types as types


def test_booster():
    orig = types.booster(1)
    a = types.booster_tostring(orig)
    assert isinstance(a, bytes)
    new = types.booster_fromstring(a)
    for ii in range(len(orig)):
        assert np.array_equal(orig[ii], new[ii])

    print('Test passed')


def test_factory():
    orig = types.factory(1)
    a = types.factory_tostring(orig)
    assert isinstance(a, bytes)
    new = types.factory_fromstring(a)
    for ii in range(len(orig)):
        assert np.array_equal(orig[ii], new[ii])

    print('Test passed')


if __name__ == '__main__':
    test_booster()
    test_factory()
