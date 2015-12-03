# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""
Utility functions.
"""

import time

import pymongo
import numpy as np


# Global handle to the collection for timing metrics.
dbTiming = None


def resetTiming(host, port):
    """
    Flush existing timing metrics and create a new capped collection.
    """
    global dbTiming

    # Drop existing collection.
    client = pymongo.MongoClient(host=host, port=port)
    col = client['timing']
    col.drop_collection('timing')

    # Create a new capped collection and update the dbTiming variable.
    col.create_collection(name='timing', size=100000000, capped=True)
    dbTiming = col['timing']


def logMetricQty(metric, value, ts=None):
    """
    Log a Quantity ``metric`` and its integer ``value``.

    The time stamp ``ts`` is optional and defaults to the time when this
    function is called.

    :param str metric: name of metric
    :param int value: value
    :param float value: unix time stamp as supplied by eg. time.time()
    """
    if dbTiming is None:
        return

    if ts is None:
        ts = time.time()

    if not isinstance(metric, str):
        return
    if not isinstance(value, int):
        return
    if not isinstance(value, float) and (value > 1413435882):
        return

    doc = {'Timestamp': ts,
           'Metric': metric,
           'Value': value,
           'Type': 'Quantity'}
    dbTiming.insert(doc, j=False)


class Timeit(object):
    """
    Context manager to measure execution time.

    The elapsed time will automatically be added to the timing database.
    """
    def __init__(self, name, show=False):
        self.name = name
        self.show = show
        self.cpCnt = 0

    def __enter__(self):
        self.start = time.time()
        self.last_tick = time.time()
        return self

    def tick(self, suffix=''):
        """
        Save an intermediate timinig result.

        The name of this tick is the concatenation of the original name (passed
        to constructore) plus ``suffix``.
        """
        elapsed = time.time() - self.last_tick
        name = self.name + suffix
        self.save(name, elapsed)
        self.last_tick = time.time()

    def save(self, name, elapsed):
        """
        Write the measurement to the DB.
        """
        if dbTiming is None:
            return

        doc = {'Timestamp': self.start,
               'Metric': name,
               'Value': elapsed,
               'Type': 'Time'}
        dbTiming.insert(doc, j=False)

        if self.show:
            # Print the value to screen.
            print('-- TIMING {}: {:,}ms'.format(name, int(1000 * elapsed)))

    def __exit__(self, *args):
        self.save(self.name, time.time() - self.start)


def timefunc(func):
    """
    Profile execution time of entire function.
    """
    def wrapper(*args, **kwargs):
        with Timeit(func.__name__, False):
            res = func(*args, **kwargs)
        return res

    # Return a new function that wrapped the original with a Timeit instance.
    return wrapper


class Quaternion:
    """
    A Quaternion class.

    This class implements a sub-set of the available Quaternion
    algebra. The operations should suffice for most 3D related tasks.
    """
    def __init__(self, x, y, z, w):
        """
        Construct Quaternion with scalar ``w`` and vector ``v``.
        """
        # Store 'w' and 'v' as Numpy types in the class.
        self.w = np.float64(w)
        self.v = np.array([x, y, z], dtype=np.float64)

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
            arg = v.tolist() + [float(w)]
            return Quaternion(*arg)
        elif isinstance(q, (int, float)):
            # Q * S:
            arg = (q * v).tolist() + [q * float(self.w)]
            return Quaternion(*arg)
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

    def length(self):
        """
        Return length of Quaternion.
        """
        return np.sqrt(self.w ** 2 + np.inner(self.v, self.v))

    def normalise(self):
        """
        Return normalised version of this Quaternion.
        """
        l = self.length()
        w = self.w / l
        v = self.v / l

        arg = v.tolist() + [float(w)]
        return Quaternion(*arg)

    def toMatrix(self):
        """
        Return the corresponding rotation matrix for this Quaternion.
        """
        # Shorthands.
        x, y, z = self.v
        w = self.w

        # Elements of the Rotation Matrix based on the Quaternion elements.
        a11 = 1 - 2 * y * y - 2 * z * z
        a12 = 2 * x * y - 2 * z * w
        a13 = 2 * x * z + 2 * y * w
        a21 = 2 * x * y + 2 * z * w
        a22 = 1 - 2 * x * x - 2 * z * z
        a23 = 2 * y * z - 2 * x * w
        a31 = 2 * x * z - 2 * y * w
        a32 = 2 * y * z + 2 * x * w
        a33 = 1 - 2 * x * x - 2 * y * y

        # Arrange- and return in matrix form.
        return np.array([
            [a11, a12, a13, 0],
            [a21, a22, a23, 0],
            [a31, a32, a33, 0],
            [0, 0, 0, 1]], np.float32)
