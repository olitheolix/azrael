import numpy as np
import azrael.parts as parts


def test_booster():
    orig = parts.booster(1)
    a = parts.booster_tostring(orig)
    assert isinstance(a, bytes)
    new = parts.booster_fromstring(a)
    for ii in range(len(orig)):
        assert np.array_equal(orig[ii], new[ii])

    print('Test passed')


def test_factory():
    orig = parts.factory(1)
    a = parts.factory_tostring(orig)
    assert isinstance(a, bytes)
    new = parts.factory_fromstring(a)
    for ii in range(len(orig)):
        assert np.array_equal(orig[ii], new[ii])

    print('Test passed')


if __name__ == '__main__':
    test_booster()
    test_factory()
