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
Wrapper around `RigidBodyState` structure.

This structure encapsulates all the data associated with the Rigid Body portion
of the object.
"""

import sys
import numpy as np
import azrael.config as config

from IPython import embed as ipshell
from azrael.types import typecheck, _RigidBodyState
from azrael.types import CollShapeMeta, CollShapeEmpty

# Default argument for RigidBodyState below (purely for visual appeal, not because
# anyone would/should use it).
_CSDefault = CollShapeMeta(
    'Empty', '', (0, 0, 0), (0, 0, 0, 1), CollShapeEmpty()
)


@typecheck
def RigidBodyState(scale: (int, float)=1,
                imass: (int, float)=1,
                restitution: (int, float)=0.9,
                orientation: (tuple, list, np.ndarray)=[0, 0, 0, 1],
                position: (tuple, list, np.ndarray)=[0, 0, 0],
                velocityLin: (tuple, list, np.ndarray)=[0, 0, 0],
                velocityRot: (tuple, list, np.ndarray)=[0, 0, 0],
                cshapes: (tuple, list)=[_CSDefault],
                axesLockLin: (tuple, list, np.ndarray)=[1, 1, 1],
                axesLockRot: (tuple, list, np.ndarray)=[1, 1, 1],
                lastChanged: int=0):
    """
    Return a ``_RigidBodyState`` object.

    Without any arguments this function will return a valid ``RigidBodyState``
    specimen with sensible defaults.
    """
    # Convert arguments to NumPy types where necessary.
    position = np.array(position, np.float64).tolist()
    orientation = np.array(orientation, np.float64).tolist()
    velocityLin = np.array(velocityLin, np.float64).tolist()
    velocityRot = np.array(velocityRot, np.float64).tolist()
    axesLockLin = np.array(axesLockLin, np.float64).tolist()
    axesLockRot = np.array(axesLockRot, np.float64).tolist()

    # Sanity checks.
    try:
        assert len(axesLockLin) == len(axesLockRot) == 3
        assert len(orientation) == 4
        assert len(position) == len(velocityLin) == len(velocityRot) == 3
        assert lastChanged >= 0
        cshapes = [CollShapeMeta(*_) for _ in cshapes]
        for cs in cshapes:
            assert isinstance(cs.type, str)
            assert isinstance(cs.name, str)
            assert isinstance(cs.pos, (tuple, list, np.ndarray))
            assert isinstance(cs.rot, (tuple, list, np.ndarray))
            assert len(np.array(cs.pos)) == 3
            assert len(np.array(cs.rot)) == 4
            assert cs.type.lower() in ('empty', 'sphere', 'box')

            # fixme: do I need additional sanity checks for the various
            # Collision shapes, or is the protocol module going to handle it?
    except (AssertionError, TypeError) as err:
        return None

    # Build- and return the actual named tuple.
    return _RigidBodyState(
        scale=scale,
        imass=imass,
        restitution=restitution,
        orientation=orientation,
        position=position,
        velocityLin=velocityLin,
        velocityRot=velocityRot,
        cshapes=cshapes,
        axesLockLin=axesLockLin,
        axesLockRot=axesLockRot,
        lastChanged=lastChanged)


class RigidBodyStateOverride(_RigidBodyState):
    """
    Create a ``_RigidBodyState`` named tuple.

    The only difference between this class and ``rb_state.RigidBodyState`` is
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
        kwargs_tmp = dict(zip(_RigidBodyState._fields, args))

        # ... Step 2: Remove all keys where the value is None...
        kwargs_tmp = {k: v for (k, v) in kwargs_tmp.items() if v is not None}

        # ... Step 3: add the original keyword arguments that are not None.
        for key, value in kwargs.items():
            if value is not None:
                kwargs_tmp[key] = value
        kwargs = kwargs_tmp
        del args, kwargs_tmp

        # Create a RigidBodyState instance. Return an error if this fails.
        try:
            sv = RigidBodyState(**kwargs)
        except TypeError:
            sv = None
        if sv is None:
            return None

        # Create keyword arguments for all fields and populate them all
        # with *None*.
        kwargs_all = {f: None for f in _RigidBodyState._fields}

        # Overwrite those keys for which we actually have a value. Note that we
        # will not use the valued supplied to this function directly but use
        # the ones from the temporary RigidBodyState object because this ensures
        # the data types were correctly converted (mosty lists to NumPy
        # arrays).
        for key in kwargs:
            kwargs_all[key] = getattr(sv, key)

        # Create the ``_RigidBodyState`` named tuple.
        return super().__new__(cls, **kwargs_all)