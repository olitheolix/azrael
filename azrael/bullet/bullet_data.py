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
Define the State Variables structure and its cencoding.

The state variables are encapsulated by the named tuple ``BulletData``. This
module contains the necessary conversions to/from binary, as well as a
conversion to NumPy. The NumPy conversion was necessary for the Cython
wrapper to Bullet. This has become redundant and will be cleaned up at some
point.
"""

import sys
import logging
import pymongo
import IPython
import numpy as np
import azrael.util
import azrael.config as config

from collections import namedtuple
from azrael.typecheck import typecheck
from azrael.protocol_json import loads, dumps

ipshell = IPython.embed

# All relevant physics data.
_BulletData = namedtuple('BulletData',
                         'scale imass restitution orientation '
                         'position velocityLin velocityRot cshape '
                         'axesLockLin axesLockRot checksumGeometry')


class BulletData(_BulletData):
    """
    Return a ``BulletData`` object.

    Without any arguments this function will return a valid ``BulletData``
    specimen with sensible defaults.
    """
    @typecheck
    def __new__(cls,
                scale: (int, float)=1,
                imass: (int, float)=1,
                restitution: (int, float)=0.9,
                orientation: (list, np.ndarray)=[0, 0, 0, 1],
                position: (list, np.ndarray)=[0, 0, 0],
                velocityLin: (list, np.ndarray)=[0, 0, 0],
                velocityRot: (list, np.ndarray)=[0, 0, 0],
                cshape: (list, np.ndarray)=[0, 1, 1, 1],
                axesLockLin: (list, np.ndarray)=[1, 1, 1],
                axesLockRot: (list, np.ndarray)=[1, 1, 1],
                checksumGeometry: int=0,
                ):

        # Convert arguments to NumPy types where necessary.
        position = np.array(position, np.float64)
        orientation = np.array(orientation, np.float64)
        velocityLin = np.array(velocityLin, np.float64)
        velocityRot = np.array(velocityRot, np.float64)
        cshape = np.array(cshape, np.float64)
        axesLockLin = np.array(axesLockLin, np.float64)
        axesLockRot = np.array(axesLockRot, np.float64)

        # Sanity checks.
        try:
            assert len(axesLockLin) == len(axesLockRot) == 3
            assert len(orientation) == len(cshape) == 4
            assert len(position) == len(velocityLin) == len(velocityRot) == 3
            assert checksumGeometry >= 0
        except (AssertionError, TypeError) as err:
            return None

        # Build the actual named tuple.
        return super().__new__(
            cls,
            scale=scale,
            imass=imass,
            restitution=restitution,
            orientation=orientation,
            position=position,
            velocityLin=velocityLin,
            velocityRot=velocityRot,
            cshape=cshape,
            axesLockLin=axesLockLin,
            axesLockRot=axesLockRot,
            checksumGeometry=checksumGeometry)

    def __eq__(self, ref):
        """
        Two ``BulletData`` instances are considered equal their content matches
        well.

        Small rounding errors are possible, especially when Bullet is involved
        since it uses 32Bit data types internally.
        """
        # Sanity check.
        if not isinstance(ref, type(self)):
            return False

        # Test all fields except cshape.
        for f in self._fields:
            if f == 'cshape':
                continue
            if not np.allclose(getattr(self, f), getattr(ref, f), atol=1E-9):
                return False
        return True

    def __ne__(self, ref):
        return not self.__eq__(ref)

    def toJsonDict(self):
        """
        Convert ``BulletData`` to JSON encodeable dictionary.
        """
        d = {'part': 'BulletData'}
        for f in self._fields:
            d[f] = getattr(self, f)

        # The dictionary 'd' is alreay what we want. However, it still contains
        # some NumPy arrays which JSON cannot serialise. To avoid manually
        # converting all of them to lists we simply use our own JSON encoder
        # which does that automatically, and then decode it again. The result
        # is the same.
        return loads(dumps(d))


class BulletDataOverride(_BulletData):
    """
    Create a ``_BulletData`` named tuple.

    The only difference between this class and ``bullet_data.BulletData`` is
    that this class permits *None* values.
    """
    @typecheck
    def __new__(cls, *args, **kwargs):
        """
        This method merely uses a default value of *None* for every unspecified
        field in the named tuple.
        """
        # Convert all positional- and keyword arguments that are not None to a
        # dictionary of keyword arguments. Step 1: convert the positional
        # arguments to a dictionary...
        kwargs_tmp = dict(zip(_BulletData._fields, args))

        # ... Step 2: Remove all keys where the value is None...
        kwargs_tmp = {k: v for (k, v) in kwargs_tmp.items() if v is not None}

        # ... Step 3: add the original keyword arguments that are not None.
        for key, value in kwargs.items():
            if value is not None:
                kwargs_tmp[key] = value
        kwargs = kwargs_tmp
        del args, kwargs_tmp

        # Create a BulletData instance. Return an error if this fails.
        try:
            sv = BulletData(**kwargs)
        except TypeError:
            sv = None
        if sv is None:
            return None

        # Create keyword arguments for all fields and populate them all
        # with *None*.
        kwargs_all = {f: None for f in BulletData._fields}

        # Overwrite those keys for which we actually have a value. Note that we
        # will not use the valued supplied to this function directly but use
        # the ones from the temporary BulletData object because this ensures
        # the data types were correctly converted (mosty lists to NumPy
        # arrays).
        for key in kwargs:
            kwargs_all[key] = getattr(sv, key)

        # Create the ``_BulletData`` named tuple.
        return super().__new__(cls, **kwargs_all)


@typecheck
def fromJsonDict(data):
    """
    Unpack the JSON encoded ``BulletData`` in ``data``.
    """
    args = [data[_] for _ in BulletData._fields]
    return BulletData(*args)
