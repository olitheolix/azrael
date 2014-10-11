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

"""
Utility functions.
"""

import time
import pymongo
import numpy as np
import azrael.config as config

from azrael.typecheck import typecheck


dbTiming = pymongo.MongoClient()['timing']['timing']

def resetTiming():
    dbTiming.drop()


class Timeit(object):
    def __init__(self, name):
        self.name = name

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, *args):
        doc = {'start': self.start,
               'elapsed': time.time() - self.start,
               'name': self.name}
        dbTiming.insert(doc, j=0, w=0)


@typecheck
def int2id(objID: int):
    """
    Convert an integer to the binary object ID.

    :param int objID: object ID as integer.
    """
    assert 0 <= objID < 2 ** 63
    return np.int64(objID).tostring()


@typecheck
def id2int(objID: bytes):
    """
    Convert an binary object ID to the corresponding integer.

    .. note::
       This function should not be called as it only serves debugging purposes.
       Azrael does not know or care about what the binary object ID means.
    """
    assert len(objID) == config.LEN_ID
    return int(np.fromstring(objID, np.int64)[0])


class Quaternion:
    """
    A Quaternion class.

    This class implements a sub-set of the available Quaternion
    algebra. The operations should suffice for most 3D related tasks.
    """
    def __init__(self, w=None, v=None):
        """
        Construct Quaternion with scalar ``w`` and vector ``v``.
        """
        # Sanity checks. 'w' must be a scalar, and 'v' a 3D vector.
        assert isinstance(w, float)
        assert isinstance(v, np.ndarray)
        assert len(v) == 3

        # Store 'w' and 'v' as Numpy types in the class.
        self.w = np.float64(w)
        self.v = np.array(v, dtype=np.float64)

    def __mul__(self, q):
        """
        Multiplication.

        The following combination of (Q)uaternions, (V)ectors, and (S)calars
        are supported:

        * Q * S
        * Q * V
        * Q * Q2

        Note that V * Q and S * Q are *not* supported.
        """
        if isinstance(q, Quaternion):
            # Q * Q2:
            w = self.w * q.w - np.inner(self.v, q.v)
            v = self.w * q.v + q.w * self.v + np.cross(self.v, q.v)
            return Quaternion(w, v)
        elif isinstance(q, (int, float)):
            # Q * S:
            return Quaternion(q * self.w, q * self.v)
        elif isinstance(q, (np.ndarray, tuple, list)):
            # Q * V: convert Quaternion to 4x4 matrix and multiply it
            # with the input vector.
            assert len(q) == 3
            tmp = np.zeros(4, dtype=np.float64)
            tmp[:3] = np.array(q)
            res = np.inner(self.toMatrix(), tmp)
            return res[:3]
        else:
            print('Unsupported Quaternion product.')
            return None

    def __repr__(self):
        """
        Represent Quaternion as a vector with 4 elements.
        """
        tmp = np.zeros(4, dtype=np.float64)
        tmp[:3] = self.v
        tmp[3] = self.w
        return str(tmp)

    def norm(self):
        """
        Norm of Quaternion.
        """
        return np.sqrt(self.w ** 2 + np.inner(self.v, self.v))

    def toMatrix(self):
        """
        Return the corresponding rotation matrix for this Quaternion.
        """
        # Shorthands.
        x, y, z = self.v
        w = self.w

        # Standard formula.
        mat = np.array([
            [1 - 2*y*y - 2*z*z, 2*x*y - 2*z*w, 2*x*z + 2*y*w, 0],
            [2*x*y + 2*z*w, 1 - 2*x*x - 2*z*z, 2*y*z - 2*x*w, 0],
            [2*x*z - 2*y*w, 2*y*z + 2*x*w, 1 - 2*x*x - 2*y*y, 0],
            [0, 0, 0, 1]])
        return mat.astype(np.float32)
