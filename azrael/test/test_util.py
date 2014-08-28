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

import pytest
import numpy as np

import azrael.util as util
import azrael.config as config


def test_id2int():
    """
    Test conversion from integer to binary object ID and back.
    """
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
