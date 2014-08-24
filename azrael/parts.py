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
from collections import namedtuple as NT


Booster = NT('Booster', 'bid pos orient max_force')
Factory = NT('Factory', 'fid pos orient speed')

CmdBooster = NT('CmdBooster', 'unitID force_mag')
CmdFactory = NT('CmdFactory', 'unitID')

def controlBooster(unitID, force: float):
    unitID = np.int64(unitID)
    force = np.float64(force)
    return CmdBooster(unitID, force)


def booster(bid, pos=np.zeros(3), orient=[0, 0, 1], max_force=0.5):
    """
    Define a Booster unit.

    The unit is located at ``pos`` relative to the parent's center of mass. The
    Booster points into the direction ``orient``. Note: ``orient`` is *not* a
    Quaternion, but merely a unit vector that points in the direction of how
    a force is applied.
    """
    bid = np.int64(bid)

    pos = np.array(pos, np.float64)
    assert len(pos) == 3

    orient = np.array(orient, np.float64)
    assert len(orient) == 3

    # Normalise the direction vector.
    assert np.sum(orient) > 1E-5
    orient = orient / np.sqrt(np.dot(orient, orient))

    assert isinstance(max_force, (int, float))
    max_force = np.float64(max_force)
    
    return Booster(bid, pos, orient, max_force)


def factory(fid, pos=np.zeros(3), orient=[0, 0, 1], speed=[0.1, 0.5]):
    fid = np.int64(fid)

    pos = np.array(pos, np.float64)
    assert len(pos) == 3

    orient = np.array(orient, np.float64)
    assert len(orient) == 3

    # Normalise the direction vector.
    assert np.sum(orient) > 1E-5
    orient = orient / np.sqrt(np.dot(orient, orient))

    speed = np.array(speed, np.float64)
    assert len(speed) == 2

    return Factory(fid, pos, orient, speed)


def booster_tostring(b: Booster):
    out = b''.join([_.tostring() for _ in b])
    return out


def booster_fromstring(b: bytes):
    _ = np.fromstring
    return Booster(_(b[0:8], np.int64)[0],
                   _(b[8:32]),
                   _(b[32:56]),
                   _(b[56:64])[0])


def factory_tostring(f: Factory):
    out = b''.join([_.tostring() for _ in f])
    return out


def factory_fromstring(f: bytes):
    _ = np.fromstring
    return Factory(_(f[0:8], np.int64)[0],
                   _(f[8:32]),
                   _(f[32:56]),
                   _(f[56:72]))
