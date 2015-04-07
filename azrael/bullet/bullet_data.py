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
import numpy as np
import azrael.util
import azrael.config as config

from collections import namedtuple
from IPython import embed as ipshell
from azrael.types import typecheck

# All relevant physics data.
_BulletData = namedtuple('_BulletData',
                         'scale imass restitution orientation '
                         'position velocityLin velocityRot cshape '
                         'axesLockLin axesLockRot lastChanged')


@typecheck
def BulletData(scale: (int, float)=1,
               imass: (int, float)=1,
               restitution: (int, float)=0.9,
               orientation: (list, np.ndarray)=[0, 0, 0, 1],
               position: (list, np.ndarray)=[0, 0, 0],
               velocityLin: (list, np.ndarray)=[0, 0, 0],
               velocityRot: (list, np.ndarray)=[0, 0, 0],
               cshape: (list, np.ndarray)=[0, 1, 1, 1],
               axesLockLin: (list, np.ndarray)=[1, 1, 1],
               axesLockRot: (list, np.ndarray)=[1, 1, 1],
               lastChanged: int=0):
    """
    Return a ``_BulletData`` object.

    Without any arguments this function will return a valid ``BulletData``
    specimen with sensible defaults.
    """

    # Convert arguments to NumPy types where necessary.
    position = np.array(position, np.float64).tolist()
    orientation = np.array(orientation, np.float64).tolist()
    velocityLin = np.array(velocityLin, np.float64).tolist()
    velocityRot = np.array(velocityRot, np.float64).tolist()
    cshape = np.array(cshape, np.float64).tolist()
    axesLockLin = np.array(axesLockLin, np.float64).tolist()
    axesLockRot = np.array(axesLockRot, np.float64).tolist()

    # Sanity checks.
    try:
        assert len(axesLockLin) == len(axesLockRot) == 3
        assert len(orientation) == len(cshape) == 4
        assert len(position) == len(velocityLin) == len(velocityRot) == 3
        assert lastChanged >= 0
    except (AssertionError, TypeError) as err:
        return None

    # Build the actual named tuple.
    return _BulletData(
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
        lastChanged=lastChanged)


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
        kwargs_all = {f: None for f in _BulletData._fields}

        # Overwrite those keys for which we actually have a value. Note that we
        # will not use the valued supplied to this function directly but use
        # the ones from the temporary BulletData object because this ensures
        # the data types were correctly converted (mosty lists to NumPy
        # arrays).
        for key in kwargs:
            kwargs_all[key] = getattr(sv, key)

        # Create the ``_BulletData`` named tuple.
        return super().__new__(cls, **kwargs_all)
