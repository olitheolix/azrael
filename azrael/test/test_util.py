import pytest
import numpy as np

import azrael.util as util
import azrael.config as config


def test_id2int():
    for ii in range(1, 10):
        tmp = util.int2id(ii)
        assert util.id2int(tmp) == ii

    with pytest.raises(AssertionError):
        util.int2id(-1)

    with pytest.raises(AssertionError):
        util.id2int(b'\x05' * (config.LEN_ID + 1))

    if config.LEN_ID > 1:
        with pytest.raises(AssertionError):
            util.id2int(b'\x05' * (config.LEN_ID - 1))

    print('Test passed')


if __name__ == '__main__':
    test_id2int()
