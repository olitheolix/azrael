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

import json
import numpy as np

from collections import namedtuple as NT
from azrael.typecheck import typecheck

class AzraelEncoder(json.JSONEncoder):
    """
    Augment default JSON encoder to handle bytes and NumPy arrays.
    """
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, bytes):
            return list(obj)
        if isinstance(obj, np.int64):
            return int(obj)
        if isinstance(obj, np.float64):
            return float(obj)
        return json.JSONEncoder.default(self, obj)

def dumps(data):
    # Convenience function for encoding ``data`` with custom JSON encoder.
    return json.dumps(data, cls=AzraelEncoder)

def loads(data: bytes):
    # Convenience function for decoding ``data``.
    return json.loads(data.decode('utf8'))


# ----------------------------------------------------------------------
# Define available parts.
# ----------------------------------------------------------------------

# Booster exert a force on an ojbect.
# Boosters have an ID (user can specify it), a position relative to the
# object's centre of mass, an orientation relative to the object's overall
# orientation, and a maximum force. Note that the force is a scalar not a
# vector. The direction of the force is governed by the orientation of the
# Booster.
Booster = NT('Booster', 'bid pos orient max_force')

# Factories can spawn objects. Like Boosters, they have custom ID, and a
# position and  orientation relative to the object they are attached
# to. Furthermore, they can only spawn a particular template and provide it
# with an initial speed along its orientation.
Factory = NT('Factory', 'fid pos orient speed')

# ----------------------------------------------------------------------
# Define available commands to parts.
# ----------------------------------------------------------------------

CmdBooster = NT('CmdBooster', 'unitID force_mag')
CmdFactory = NT('CmdFactory', 'unitID')


@typecheck
def controlBooster(unitID: int, force: (int, float, np.float64)):
    """
    Return a ``CmdBooster`` instance.

    This wrapper only ensures that the provided data types are sane.

    :param int unitID: custom ID of this booster.
    :param float force: force magnitude to apply.
    """
    unitID = np.int64(unitID)
    force = np.float64(force)
    return CmdBooster(unitID, force)


@typecheck
def booster(bid: int, pos=np.zeros(3), orient=[0, 0, 1], max_force=0.5):
    """
    Return a ``Booster`` instance.

    The unit is located at ``pos`` relative to the parent's center of mass. The
    Booster points into the direction ``orient``.

    .. note::
       ``orient`` is *not* a Quaternion but merely a unit vector that points
       in the direction of the force.

    :param int bid: Booster ID (arbitrary)
    :param ndarray pos: position vector (3-elements)
    :param ndarray orient: orientation (3-elements)
    :param float max_force: maximum force this Booster can generate.
    :return Booster: compiled booster description.
    """
    # Convert the booster ID and force threshold to NumPy types.
    bid = np.int64(bid)
    max_force = np.float64(max_force)

    # Position must be a 3-element vector.
    pos = np.array(pos, np.float64)
    assert len(pos) == 3

    # Orientation must be a 3-element vector.
    orient = np.array(orient, np.float64)
    assert len(orient) == 3

    # Normalise the direction vector or raise an error if invalid.
    assert np.sum(orient) > 1E-5
    orient = orient / np.sqrt(np.dot(orient, orient))

    # Return a valid Booster instance based on the arguments.
    return Booster(bid, pos, orient, max_force)


def factory(fid, pos=np.zeros(3), orient=[0, 0, 1], speed=[0.1, 0.5]):
    """
    Return a ``Factory`` instance.

    The unit is located at ``pos`` relative to the parent's center of
    mass. The objects it spawns can exit the factory at any speed specified by
    the ``speed`` interval.

    .. note::
       ``orient`` is *not* a Quaternion but merely a unit vector that points
       in the nozzle direction of the factory (it the direction in which new
       objects will be spawned).

    :param int fid: factory ID (arbitrary)
    :param ndarray pos: position vector (3-elements)
    :param ndarray orient: orientation (3-elements)
    :param ndarray speed: min/max exit speed of spawned object.
    :return Factory: compiled factory description.
    """
    # Factory ID.
    fid = np.int64(fid)

    # Position must be a 3-element vector.
    pos = np.array(pos, np.float64)
    assert len(pos) == 3

    # Orientation must be a 3-element vector.
    orient = np.array(orient, np.float64)
    assert len(orient) == 3

    # Normalise the direction vector or raise an error if invalid.
    assert np.sum(orient) > 1E-5
    orient = orient / np.sqrt(np.dot(orient, orient))

    # This defines exit speed range of the spawned object.
    speed = np.array(speed, np.float64)
    assert len(speed) == 2

    # Return a valid Factory instance based on the arguments.
    return Factory(fid, pos, orient, speed)


def booster_tostring(b: Booster):
    return dumps(b).encode('utf8')


def booster_fromstring(b: bytes):
    return booster(*(loads(b)))


def factory_tostring(f: Factory):
    return dumps(f).encode('utf8')


def factory_fromstring(f: bytes):
    return factory(*(loads(f)))
