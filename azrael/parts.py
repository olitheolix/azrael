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
Defines object parts like Boosters and their commands.
"""
import numpy as np

from azrael.types import typecheck
from IPython import embed as ipshell
from collections import namedtuple as NT


# -----------------------------------------------------------------------------
# Booster
#
# Boosters exert a force on an object. Boosters have an ID (user can specify
# it), a position relative to the object's centre of mass, a force direction
# relative to the object's overall orientation, and a maximum force. Note that
# the force is a scalar not a vector.
# -----------------------------------------------------------------------------

# Define named tuples to describe a Booster and the commands it can receive.
_Booster = NT('Booster', 'partID pos direction maxval minval force ')
_CmdBooster = NT('CmdBooster', 'partID force_mag')


class Booster(_Booster):
    """
    Return a ``Booster`` instance.

    The unit is located at ``pos`` relative to the parent's centre of mass. The
    Booster points into ``direction``.

    .. note::
       ``direction`` is *not* a Quaternion but merely a unit vector that points
       in the direction of the force.

    :param str partID: Booster ID (arbitrary)
    :param ndarray pos: position vector (3-elements)
    :param ndarray direction: force direction (3-elements)
    :param float minval: minimum force this Booster can generate.
    :param float maxval: maximum force this Booster can generate.
    :param float force: force value this booster currently exerts on object.
    :return Booster: compiled booster description.
    """
    @typecheck
    def __new__(cls, partID: str, pos: (list, np.ndarray),
                direction: (list, np.ndarray), minval: (int, float),
                maxval: (int, float), force: (int, float)):
        try:
            # Position must be a 3-element vector.
            pos = np.array(pos, np.float64)
            assert len(pos) == 3

            # Direction must be a 3-element vector.
            direction = np.array(direction, np.float64)
            assert len(direction) == 3

            # Normalise the direction vector or raise an error if invalid.
            assert np.dot(direction, direction) > 1E-5
            direction = direction / np.sqrt(np.dot(direction, direction))

            # Only store native Python types to make them compatible with
            # MongoDB.
            pos = pos.tolist()
            direction = direction.tolist()
        except (TypeError, AssertionError):
            raise TypeError

        self = super().__new__(cls, partID, pos, direction,
                               minval, maxval, force)

        return self

    def __eq__(self, ref):
        # Sanity check.
        if not isinstance(ref, type(self)):
            return False

        # Test if all fields are essentially identical. All fields except
        # partID must be numeric arrays (Python lists or NumPy arrays).
        for f in self._fields:
            a, b = getattr(self, f), getattr(ref, f)
            if isinstance(a, (tuple, list, np.ndarray)):
                if not np.allclose(a, b, atol=1E-9):
                    return False
            else:
                if a != b:
                    return False
        return True

    def __ne__(self, ref):
        return not self.__eq__(ref)


class CmdBooster(_CmdBooster):
    """
    Return Booster command wrapped into a ``CmdBooster`` instance.

    This wrapper only ensures the provided data is sane.

    :param str partID: Booster ID (arbitrary)
    :param float force: magnitude of force (a scalar!)
    :return Booster: compiled description of booster command.
    """
    @typecheck
    def __new__(cls, partID: str, force: (int, float, np.float64)):
        force = float(force)
        self = super().__new__(cls, partID, force)
        return self

    def __eq__(self, ref):
        # Sanity check.
        if not isinstance(ref, type(self)):
            return False

        # Test if all fields are essentially identical. All fields except
        # partID must be numeric arrays (Python lists or NumPy arrays).
        for f in self._fields:
            a, b = getattr(self, f), getattr(ref, f)
            if isinstance(a, (tuple, list, np.ndarray)):
                if not np.allclose(a, b, atol=1E-9):
                    return False
            else:
                if a != b:
                    return False
        return True

    def __ne__(self, ref):
        return not self.__eq__(ref)


# -----------------------------------------------------------------------------
# Factory
#
# Factories can spawn objects. Like Boosters, they have a custom ID, position,
# direction (both relative to the object). Furthermore, they can only spawn a
# particular template. The newly spawned object can exit with the specified
# speed along the factory direction.
# -----------------------------------------------------------------------------

# Define named tuples to describe a Factory and the commands it can receive.
_Factory = NT('Factory', 'partID pos direction templateID exit_speed')
_CmdFactory = NT('CmdFactory', 'partID exit_speed')


class Factory(_Factory):
    @typecheck
    def __new__(cls, partID: str, pos: (list, np.ndarray),
                direction: (list, np.ndarray), templateID: str,
                exit_speed: (list, np.ndarray)):
        """
        Return a ``Factory`` instance.

        The unit is located at ``pos`` relative to the parent's centre of
        mass. The initial velocity of the spawned objects is constrained by the
        ``exit_speed`` variable.

        .. note::
           ``direction`` is *not* a Quaternion but merely a unit vector that
           points in the nozzle direction of the factory (it the direction in
           which new objects will be spawned).

        :param str partID: factory ID (arbitrary).
        :param ndarray pos: position vector (3-elements).
        :param ndarray direction: exit direction of new objects (3-elements).
        :param str templateID: name of template spawned by this factory.
        :param ndarray exit_speed: [min, max] exit speed of spawned object.
        :return Factory: compiled factory description.
        """
        try:
            # Position must be a 3-element vector.
            pos = np.array(pos, np.float64)
            assert len(pos) == 3

            # Direction must be a 3-element vector.
            direction = np.array(direction, np.float64)
            assert len(direction) == 3

            # Normalise the direction vector or raise an error if invalid.
            assert np.dot(direction, direction) > 1E-5
            direction = direction / np.sqrt(np.dot(direction, direction))

            # This defines exit speed range of the spawned object.
            exit_speed = np.array(exit_speed, np.float64)
            assert len(exit_speed) == 2

            # Only store native Python types to make them compatible with MongoDB.
            pos = pos.tolist()
            direction = direction.tolist()
            exit_speed = exit_speed.tolist()
        except (TypeError, AssertionError):
            raise TypeError

        # Return a valid Factory instance based on the arguments.
        self = super().__new__(
            cls, partID, pos, direction, templateID, exit_speed)
        return self

    def __eq__(self, ref):
        if not isinstance(ref, type(self)):
            return False

        for f in self._fields:
            a, b = getattr(self, f), getattr(ref, f)
            if isinstance(a, (tuple, list, np.ndarray)):
                if not np.allclose(a, b, 1E-9):
                    return False
            else:
                if a != b:
                    return False
        return True


class CmdFactory(_CmdFactory):
    """
    Return Factory command wrapped into a ``CmdFactory`` instance.

    This wrapper only ensures the provided data is sane.

    :param str partID: Factory ID (arbitrary)
    :param float force: magnitude of force (a scalar!)
    :return Factory: compiled description of factory command.
    """
    @typecheck
    def __new__(cls, partID: str, exit_speed: (int, float, np.float64)):
        exit_speed = float(exit_speed)
        self = super().__new__(cls, partID, exit_speed)
        return self

    def __eq__(self, ref):
        # Sanity check.
        if not isinstance(ref, type(self)):
            return False

        # Test if all fields are essentially identical.
        for f in self._fields:
            a, b = getattr(self, f), getattr(ref, f)
            if isinstance(a, (tuple, list, np.ndarray)):
                if not np.allclose(a, b, 1E-9):
                    return False
            else:
                if a != b:
                    return False
        return True

    def __ne__(self, ref):
        return not self.__eq__(ref)
