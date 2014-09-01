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

from collections import namedtuple as NT
from azrael.typecheck import typecheck
from azrael.protocol_json import loads, dumps


@typecheck
def fromstring(data: bytes):
    """
    Decode the part of command in ``data``.

    If the content in ``data`` is invalid then ``ValueError`` will be raised.

    :param bytes data: input data to de-serialise.
    :return: (ok, decoded-data)
    :rtype: (bool, part)
    :raises: None
    """
    # Decode JSON.
    try:
        d = loads(data)
    except ValueError:
        return False, 'JSON decoding error'

    # Sanity check.
    if not isinstance(d, dict):
        return False, 'Corrupt part description.'

    # The 'part' field must be present.
    if 'part' not in d:
        return False, 'Corrupt part data'

    # Identify what we want to decode.
    if d['part'] == 'Booster':
        args = [d[_] for _ in Booster._fields]
        return Booster(*args)
    elif d['part'] == 'Factory':
        args = [d[_] for _ in Factory._fields]
        return Factory(*args)
    elif d['part'] == 'CmdBooster':
        args = [d[_] for _ in CmdBooster._fields]
        return CmdBooster(*args)
    else:
        return False, 'Unknown part <{}>'.format(d['part'])


# -----------------------------------------------------------------------------
# Booster
#
# Boosters exert a force on an object. Boosters have an ID (user can specify
# it), a position relative to the object's centre of mass, a force direction
# relative to the object's overall orientation, and a maximum force. Note that
# the force is a scalar not a vector.
# -----------------------------------------------------------------------------

# Define named tuples to describe a Booster and the commands it can receive.
_Booster = NT('Booster', 'partID pos direction max_force')
_CmdBooster = NT('CmdBooster', 'partID force_mag')


class Booster(_Booster):
    """
    Return a ``Booster`` instance.

    The unit is located at ``pos`` relative to the parent's centre of mass. The
    Booster points into ``direction``.

    .. note::
       ``direction`` is *not* a Quaternion but merely a unit vector that points
       in the direction of the force.

    :param int partID: Booster ID (arbitrary)
    :param ndarray pos: position vector (3-elements)
    :param ndarray direction: force direction (3-elements)
    :param float max_force: maximum force this Booster can generate.
    :return Booster: compiled booster description.
    """
    @typecheck
    def __new__(
            cls, partID: int, pos=[0, 0, 0], direction=[0, 0, 1], max_force=0.5):
        # Convert the booster ID and force threshold to NumPy types.
        partID = np.int64(partID)
        max_force = np.float64(max_force)

        # Position must be a 3-element vector.
        pos = np.array(pos, np.float64)
        assert len(pos) == 3

        # Direction must be a 3-element vector.
        direction = np.array(direction, np.float64)
        assert len(direction) == 3

        # Normalise the direction vector or raise an error if invalid.
        assert np.dot(direction, direction) > 1E-5
        direction = direction / np.sqrt(np.dot(direction, direction))
        self = super().__new__(cls, partID, pos, direction, max_force)
        return self

    def __eq__(self, ref):
        # Sanity check.
        if not isinstance(ref, type(self)):
            return False

        # Test if all fields are essentially identical.
        for f in self._fields:
            if not np.allclose(getattr(self, f), getattr(ref, f), atol=1E-9):
                return False
        return True

    def __ne__(self, ref):
        return not self.__eq__(ref)

    def tostring(self):
        d = {'part': 'Booster'}
        for f in self._fields:
            d[f] = getattr(self, f)
        return dumps(d)


class CmdBooster(_CmdBooster):
    """
    Return Booster command wrapped into a ``CmdBooster`` instance.

    This wrapper only ensures the provided data is sane.

    :param int partID: Booster ID (arbitrary)
    :param float force: magnitude of force (a scalar!)
    :return Booster: compiled description of booster command.
    """
    @typecheck
    def __new__(cls, partID: int, force: (int, float, np.float64)):
        partID = np.int64(partID)
        force = np.float64(force)

        self = super().__new__(cls, partID, force)
        return self

    def __eq__(self, ref):
        # Sanity check.
        if not isinstance(ref, type(self)):
            return False

        # Test if all fields are essentially identical.
        for f in self._fields:
            if not np.allclose(getattr(self, f), getattr(ref, f), atol=1E-9):
                return False
        return True

    def __ne__(self, ref):
        return not self.__eq__(ref)

    def tostring(self):
        d = {'part': 'CmdBooster'}
        for f in self._fields:
            d[f] = getattr(self, f)
        return dumps(d)


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
CmdFactory = NT('CmdFactory', 'partID exit_speed')


class Factory(_Factory):
    @typecheck
    def __new__(cls, partID, pos, direction, templateID, exit_speed):
        """
        Return a ``Factory`` instance.

        The unit is located at ``pos`` relative to the parent's centre of
        mass. The initial velocity of the spawned objects is constrained by the
        ``exit_speed`` variable.

        .. note::
           ``direction`` is *not* a Quaternion but merely a unit vector that
           points in the nozzle direction of the factory (it the direction in
           which new objects will be spawned).

        :param int partID: factory ID (arbitrary)
        :param ndarray pos: position vector (3-elements)
        :param ndarray direction: exit direction of new objects (3-elements)
        :param ndarray exit_speed: min/max exit speed of spawned object.
        :return Factory: compiled factory description.
        """
        # Factory ID.
        partID = np.int64(partID)

        if isinstance(templateID, (tuple, list)):
            templateID = bytes(templateID)
            
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

        # Return a valid Factory instance based on the arguments.
        self = super().__new__(
            cls, partID, pos, direction, templateID, exit_speed)
        return self

    def __eq__(self, ref):
        if not isinstance(ref, type(self)):
            return False

        for f in self._fields:
            a, b = getattr(self, f), getattr(ref, f)
            if isinstance(a, np.ndarray):
                if not np.allclose(a, b, 1E-9):
                    return False
            else:
                if a != b:
                    return False
        return True

    def tostring(self):
        d = {'part': 'Factory'}
        for f in self._fields:
            d[f] = getattr(self, f)
        return dumps(d)
