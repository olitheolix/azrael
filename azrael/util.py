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


import numpy as np
import azrael.config as config


class Timer(object):
    def __init__(self, verbose=False, msg='Elapsed Time: '):
        self.verbose = verbose
        self.prefix = msg

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, *args):
        self.end = time.time()
        self.elapsed = self.end - self.start
        self.secs = int(self.elapsed)
        self.msecs = int(self.elapsed * 1E3)
        self.usecs = int(self.elapsed * 1E6)

        if self.verbose:
            print(self.prefix + '{}'.format(self.format(self.elapsed)))

    def format(self, elapsed):
        return '{0:,}us'.format(int(elapsed * 1E6))


def int2id(id_int: int):
    """
    Convert an integer to the corresponding object ID.

    This function will raise an `OverflowError` if ``id_int`` is too large for
    the available number of bytes.
    """
    assert isinstance(id_int, int)
    assert id_int >= 0
    assert id_int < 2 ** (8 * config.LEN_ID)
    return (id_int).to_bytes(config.LEN_ID, 'little')


def id2int(id_bytes: int):
    """
    Convert an object ID to the corresponding integer.
    """
    assert isinstance(id_bytes, bytes)
    assert len(id_bytes) == config.LEN_ID
    return int.from_bytes(id_bytes, 'little')
