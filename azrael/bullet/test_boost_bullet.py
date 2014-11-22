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
import azrael.bullet.boost_bullet
import azrael.bullet.btInterface as btInterface
import azrael.bullet.bullet_data as bullet_data

import numpy as np


ipshell = IPython.embed


def test_getset_object():
    """
    Send/retrieve object to/from Bullet and verify the integrity.
    """
    # Create an object and serialise it.
    obj_a = bullet_data.BulletData(
        radius=2.5,
        scale=3.5,
        imass=4.5,
        restitution=5.5,
        orientation=np.array([0, 1, 0, 0], np.float64),
        position=np.array([0.2, 0.4, 0.6], np.float64),
        velocityLin=np.array([0.8, 1.0, 1.2], np.float64),
        velocityRot=np.array([1.4, 1.6, 1.8], np.float64))
    obj_a.cshape[0] = 3

    # Instantiate Bullet engine.
    bullet = azrael.bullet.boost_bullet.PyBulletPhys(1)

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


def test_update_object():
    """
    Add an object to Bullet, then change its parameters.
    """
    # Create an object and serialise it.
    obj_a = bullet_data.BulletData(
        radius=2.5,
        scale=3.5,
        imass=4.5,
        restitution=5.5,
        orientation=np.array([0, 1, 0, 0], np.float64),
        position=np.array([0.2, 0.4, 0.6], np.float64),
        velocityLin=np.array([0.8, 1.0, 1.2], np.float64),
        velocityRot=np.array([1.4, 1.6, 1.8], np.float64))
    obj_a.cshape[0] = 3

    # Instantiate Bullet engine.
    bullet = azrael.bullet.boost_bullet.PyBulletPhys(1)

    # Send object to Bullet and request it back.
    bullet.setObjectData([0], obj_a)
    ok, obj_b = bullet.getObjectData([0])
    assert ok == 0
    assert obj_a == obj_b

    # Update the object.
    obj_a = bullet_data.BulletData(
        radius=5.5,
        scale=6.5,
        imass=7.5,
        restitution=8.5,
        orientation=np.array([0, 0, 1, 0], np.float64),
        position=np.array([1.2, 1.4, 1.6], np.float64),
        velocityLin=np.array([2.8, 2.0, 2.2], np.float64),
        velocityRot=np.array([2.4, 2.6, 2.8], np.float64))
    obj_a.cshape[0] = 3
    bullet.setObjectData([0], obj_a)
    ok, obj_b = bullet.getObjectData([0])
    assert ok == 0
    assert obj_a == obj_b

    print('Test passed')


@pytest.mark.parametrize('force_fun_id', ['applyForce', 'applyForceAndTorque'])
def test_apply_force(force_fun_id):
    """
    Create object, send it to Bullet, apply a force, progress the simulation,
    and verify the object moved correctly.
    """
    # Constants and paramters for this test.
    objID = 10
    force = np.array([0, 0, 1], np.float64)
    dt, maxsteps = 1.0, 60

    # Create an object and overwrite the CShape data to obtain a sphere.
    obj_a = bullet_data.BulletData()
    obj_a.cshape[0] = 3

    # Instantiate Bullet engine.
    bullet = azrael.bullet.boost_bullet.PyBulletPhys(1)

    # Send object to Bullet and progress the simulation by one second.
    # The objects must not move because no forces are at play.
    bullet.setObjectData([objID], obj_a)
    bullet.compute([objID], dt, maxsteps)
    ok, obj_b = bullet.getObjectData([objID])
    assert ok == 0
    assert obj_a == obj_b

    # Now apply a central force of one Newton in z-direction.
    if force_fun_id == 'applyForce':
        applyForceFun = bullet.applyForce
    elif force_fun_id == 'applyForceAndTorque':
        applyForceFun = bullet.applyForceAndTorque
    else:
        assert False
    applyForceFun(objID, force, np.zeros(3, np.float64))

    # Nothing must have happened because the simulation has not progressed.
    ok, obj_b = bullet.getObjectData([objID])
    assert ok == 0
    assert obj_a == obj_b

    # Progress the simulation by another 'dt' seconds.
    bullet.compute([objID], dt, maxsteps)
    ok, obj_b = bullet.getObjectData([objID])
    assert ok == 0

    # The object must have accelerated and reached the linear velocity
    #   v = a * t                  (1)
    # where the acceleration $a$ follows from
    #   F = m * a --> a = F / m    (2)
    # Substitue (2) into (1) to obtain
    #   v = t * F / m
    # or in terms of the inverse mass:
    #   v = t * F * imass
    assert np.allclose(obj_b.velocityLin, dt * force * 1, atol=1E-2)

    print('Test passed')


def test_apply_force_and_torque():
    """
    Create object, send it to Bullet, apply a force, progress the simulation,
    and verify the object moved correctly.
    """
    # Constants and paramters for this test.
    objID = 10
    force = np.array([0, 0, 1], np.float64)
    torque = np.array([0, 0, 1], np.float64)
    dt, maxsteps = 1.0, 60

    # Create a spherical object. Adjust the mass so that the sphere's inertia
    # is roughly unity.
    obj_a = bullet_data.BulletData(cshape=[3, 1, 1, 1], imass=2 / 5)
    obj_a.cshape[0] = 3

    # Instantiate Bullet engine.
    bullet = azrael.bullet.boost_bullet.PyBulletPhys(1)

    # Send object to Bullet and progress the simulation by one second.
    # The objects must not move because no forces are at play.
    bullet.setObjectData([objID], obj_a)
    bullet.compute([objID], dt, maxsteps)
    ok, obj_b = bullet.getObjectData([objID])
    assert ok == 0
    assert obj_a == obj_b

    # Now apply a central force of one Newton in z-direction and a torque of
    # two NewtonMeters.
    bullet.applyForceAndTorque(objID, force, torque)

    # Nothing must have happened because the simulation has not progressed.
    ok, obj_b = bullet.getObjectData([objID])
    assert ok == 0
    assert obj_a == obj_b

    # Progress the simulation for another second.
    bullet.compute([objID], dt, maxsteps)
    ok, obj_b = bullet.getObjectData([objID])
    assert ok == 0
    velLin, velRot = obj_b.velocityLin, obj_b.velocityRot

    # The object must have accelerated to the linear velocity
    #   v = a * t                  (1)
    # where the acceleration $a$ follows from
    #   F = m * a --> a = F / m    (2)
    # Substitue (2) into (1) to obtain
    #   v = t * F / m
    # or in terms of the inverse mass:
    #   v = t * F * imass
    assert np.allclose(velLin, dt * force * (2 / 5), atol=1E-2)

    # The object must have accelerated to the angular velocity omega
    #   omega = OMEGA * t                  (1)
    # where the torque $T$ follows from angular acceleration OMEGA
    #   T = I * OMEGA --> OMEGA = T / I    (2)
    # Substitue (2) into (1) to obtain
    #   omega = t * (T / I)
    # Our Inertia is roughly unity because we adjusted the sphere's mass
    # accordingly when we created it (ie. set it 5/2kg or 2/5 for the inverse
    # mass).
    assert np.allclose(velRot, dt * torque * 1, atol=1E-2)

    print('Test passed')


def test_get_pair_cache():
    """
    Test the pair cache with three objects. Two of the objects overlap.
    """
    # This test is currently disabled because the boost-wrappers do not support
    # it yet.
    return

    # Create a sphere.
    obj_a = bullet_data.BulletData()
    obj_a.cshape[0] = 3

    # Instantiate Bullet engine.
    bullet = azrael.bullet.boost_bullet.PyBulletPhys(1)
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
    bullet = azrael.bullet.boost_bullet.PyBulletPhys(1)

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
    test_update_object()
    test_getset_object()
    test_remove_object()
    test_apply_force_and_torque()
    test_apply_force('applyForceAndTorque')
    test_apply_force('applyForce')
    test_get_pair_cache()
