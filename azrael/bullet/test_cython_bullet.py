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

import sys
import pytest
import IPython
import cytoolz
import azrael.bullet.cython_bullet
import azrael.bullet.btInterface as btInterface
import azrael.bullet.bullet_data as bullet_data

import numpy as np


ipshell = IPython.embed


def test_getset_object():
    """
    Send/retrieve object to/from Bullet and verify the integrity.
    """
    # Create an object and serialise it.
    obj_a = bullet_data.BulletData()
    obj_a.cshape[0] = 3

    # Instantiate Bullet engine.
    bullet = azrael.bullet.cython_bullet.PyBulletPhys(1, 0)

    # Request an invalid object ID.
    ok, ret_buf = bullet.getObjectData([0])
    assert ok == 1

    # Send object to Bullet and request it back.
    bullet.setObjectData([0], obj_a)
    ok, obj_b = bullet.getObjectData([0])
    assert ok == 0

    # De-serialise the data and verify it is identical (small rounding errors
    # are admissible because Bullet uses float32 types). The only field that
    # need not match is the collision shape since I still have not decided how
    # to handle it.
    assert obj_a == obj_b
    print('Test passed')


def test_apply_force():
    """
    Create object, send it to Bullet, apply a force, progress the simulation,
    and verify the object moved correctly.
    """
    # Create an object and overwrite the CShape data to obtain a sphere.
    obj_a = bullet_data.BulletData()
    obj_a.cshape[0] = 3

    # Instantiate Bullet engine.
    bullet = azrael.bullet.cython_bullet.PyBulletPhys(1, 0)

    # Send object to Bullet and progress the simulation by one second.
    # The objects must not move because no forces are at play.
    bullet.setObjectData([0], obj_a)
    bullet.compute([0], 1.0, 60)
    ok, obj_b = bullet.getObjectData([0])
    assert ok == 0
    assert obj_a == obj_b

    # Now apply a central force of one Newton in z-direction, run the
    # simulation again. The object must have moved roughly 0.5m in z-direction
    # because s = 0.5 * a * t^2.
    force = np.array([0, 0, 1], np.float64)
    bullet.applyForce(0, force, np.zeros(3, np.float64))

    # Nothing must have happened because the simulation has not progressed.
    ok, obj_b = bullet.getObjectData([0])
    assert ok == 0
    assert obj_a == obj_b

    # Progress the simulation again. The object must have moved in z-direction
    # by (roughly) 0.5 meters.
    bullet.compute([0], 1.0, 60)
    ok, obj_b = bullet.getObjectData([0])
    assert ok == 0
    assert np.allclose(obj_b.position, [0, 0, 0.5], atol=1E-2)

    print('Test passed')


def test_get_pair_cache():
    """
    Test the pair cache with three objects. Two of the objects overlap.
    """
    # Create a sphere.
    obj_a = bullet_data.BulletData()
    obj_a.cshape[0] = 3

    # Instantiate Bullet engine.
    bullet = azrael.bullet.cython_bullet.PyBulletPhys(1, 1)
    ok, pairs = bullet.getPairCache()
    assert ok

    # Create two more spheres (both identical).
    obj_a = bullet_data.BulletData(cshape=[3, 0, 0, 0], position=[10, 10, 10])
    obj_b = bullet_data.BulletData(cshape=[3, 0, 0, 0], position=[10, 10, 10])

    # Send object to Bullet and progress the simulation by one second.
    # The objects must not have moved because no forces are at play.
    bullet.setObjectData([0], obj_a)
    bullet.setObjectData([1], obj_a)
    bullet.setObjectData([2], obj_b)
    bullet.compute([0, 1], 1.0, 60)

    # The first two objects must "touch" each other and thus be in the pair
    # cache, whereas the third object is nowhere near them and thus not part of
    # any pair. Note: many identical pairs may be returned because Bullet runs
    # the broadphase algorithm several times.
    ok, pairs = bullet.getPairCache()
    assert ok
    for pair in cytoolz.partition(2, pairs):
        assert set(pair) == set([0, 1])


def test_remove_object():
    """
    Remove an object from the Bullet cache.
    """
    # Create a spherical object.
    obj_a = bullet_data.BulletData()
    obj_a.cshape[0] = 3

    # Instantiate Bullet engine.
    bullet = azrael.bullet.cython_bullet.PyBulletPhys(1, 0)

    # Request an invalid object ID.
    ok, obj_b = bullet.getObjectData([0])
    assert ok == 1

    # Send object to Bullet and request it back.
    bullet.setObjectData([0], obj_a)
    ok, obj_b = bullet.getObjectData([0])
    assert ok == 0
    assert obj_a == obj_b

    # Delete the object. The attempt to request it afterwards must fail.
    assert bullet.removeObject([0]) == 1
    ok, obj_b = bullet.getObjectData([0])
    assert ok == 1

    print('Test passed')


if __name__ == '__main__':
    test_remove_object()
    test_get_pair_cache()
    test_apply_force()
    test_getset_object()
