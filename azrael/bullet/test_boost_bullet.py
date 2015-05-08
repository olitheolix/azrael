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
import cytoolz
import azrael.bullet.boost_bullet
import azrael.physics_interface as physAPI
import azrael.bullet.bullet_data as bullet_data

import numpy as np

from azrael.types import _MotionState
from IPython import embed as ipshell

MotionState = bullet_data.MotionState


def isEqualBD(bd1: _MotionState, bd2: _MotionState):
    """
    Return *True* if the content of ``bd1`` is (roughly) equal to ``bd2``.

    This is a convenience function only.
    """
    for f in _MotionState._fields:
        if not np.allclose(getattr(bd1, f), getattr(bd2, f), atol=1E-9):
            return False
    return True


def test_getset_object():
    """
    Send/retrieve object to/from Bullet and verify the integrity.
    """
    # Create an object and serialise it.
    obj_a = bullet_data.MotionState(
        scale=3.5,
        imass=4.5,
        cshape=[3, 1, 1, 1],
        restitution=5.5,
        orientation=np.array([0, 1, 0, 0], np.float64),
        position=np.array([0.2, 0.4, 0.6], np.float64),
        velocityLin=np.array([0.8, 1.0, 1.2], np.float64),
        velocityRot=np.array([1.4, 1.6, 1.8], np.float64))

    # Instantiate Bullet engine.
    bullet = azrael.bullet.boost_bullet.PyBulletPhys(1)

    # Request an invalid object ID.
    ret = bullet.getObjectData([0])
    assert not ret.ok

    # Send object to Bullet and request it back.
    bullet.setObjectData(0, obj_a)
    ret = bullet.getObjectData([0])
    assert ret.ok

    # De-serialise the data and verify it is identical (small rounding errors
    # are admissible because Bullet uses float32 types).
    assert isEqualBD(obj_a, ret.data)
    print('Test passed')


def test_update_object():
    """
    Add an object to Bullet, then change its parameters.
    """
    # Create an object and serialise it.
    obj_a = bullet_data.MotionState(
        scale=3.5,
        imass=4.5,
        cshape=[3, 1, 1, 1],
        restitution=5.5,
        orientation=np.array([0, 1, 0, 0], np.float64),
        position=np.array([0.2, 0.4, 0.6], np.float64),
        velocityLin=np.array([0.8, 1.0, 1.2], np.float64),
        velocityRot=np.array([1.4, 1.6, 1.8], np.float64))

    # Instantiate Bullet engine.
    bullet = azrael.bullet.boost_bullet.PyBulletPhys(1)

    # Send object to Bullet and request it back.
    bullet.setObjectData(0, obj_a)
    ret = bullet.getObjectData([0])
    assert ret.ok
    assert isEqualBD(ret.data, obj_a)

    # Update the object.
    obj_a = bullet_data.MotionState(
        scale=6.5,
        imass=7.5,
        cshape=[3, 1, 1, 1],
        restitution=8.5,
        orientation=np.array([0, 0, 1, 0], np.float64),
        position=np.array([1.2, 1.4, 1.6], np.float64),
        velocityLin=np.array([2.8, 2.0, 2.2], np.float64),
        velocityRot=np.array([2.4, 2.6, 2.8], np.float64))
    bullet.setObjectData(0, obj_a)
    ret = bullet.getObjectData([0])
    assert ret.ok
    assert isEqualBD(ret.data, obj_a)

    print('Test passed')


@pytest.mark.parametrize('force_fun_id', ['applyForce', 'applyForceAndTorque'])
def test_apply_force(force_fun_id):
    """
    Create object, send it to Bullet, apply a force, progress the simulation,
    and verify the object moved correctly.
    """
    # Constants and parameters for this test.
    objID = 10
    force = np.array([0, 0, 1], np.float64)
    dt, maxsteps = 1.0, 60

    # Create an object and overwrite the CShape data to obtain a sphere.
    obj_a = bullet_data.MotionState()

    # Instantiate Bullet engine.
    bullet = azrael.bullet.boost_bullet.PyBulletPhys(1)

    # Send object to Bullet and progress the simulation by one second.
    # The objects must not move because no forces are at play.
    bullet.setObjectData(objID, obj_a)
    bullet.compute([objID], dt, maxsteps)
    ret = bullet.getObjectData([objID])
    assert ret.ok
    assert isEqualBD(ret.data, obj_a)

    # Now apply a central force of one Newton in z-direction.
    if force_fun_id == 'applyForce':
        applyForceFun = bullet.applyForce
    elif force_fun_id == 'applyForceAndTorque':
        applyForceFun = bullet.applyForceAndTorque
    else:
        assert False
    applyForceFun(objID, force, np.zeros(3, np.float64))

    # Nothing must have happened because the simulation has not progressed.
    ret = bullet.getObjectData([objID])
    assert ret.ok
    assert isEqualBD(ret.data, obj_a)

    # Progress the simulation by another 'dt' seconds.
    bullet.compute([objID], dt, maxsteps)
    ret = bullet.getObjectData([objID])
    assert ret.ok

    # The object must have accelerated and reached the linear velocity
    #   v = a * t                  (1)
    # where the acceleration $a$ follows from
    #   F = m * a --> a = F / m    (2)
    # Substitue (2) into (1) to obtain
    #   v = t * F / m
    # or in terms of the inverse mass:
    #   v = t * F * imass
    assert np.allclose(ret.data.velocityLin, dt * force * 1, atol=1E-2)

    print('Test passed')


def test_apply_force_and_torque():
    """
    Create object, send it to Bullet, apply a force, progress the simulation,
    and verify the object moved correctly.
    """
    # Constants and parameters for this test.
    objID = 10
    force = np.array([0, 0, 1], np.float64)
    torque = np.array([0, 0, 1], np.float64)
    dt, maxsteps = 1.0, 60

    # Create a spherical object. Adjust the mass so that the sphere's inertia
    # is roughly unity.
    obj_a = bullet_data.MotionState(cshape=[3, 1, 1, 1], imass=2 / 5)

    # Instantiate Bullet engine.
    bullet = azrael.bullet.boost_bullet.PyBulletPhys(1)

    # Send object to Bullet and progress the simulation by one second.
    # The objects must not move because no forces are at play.
    bullet.setObjectData(objID, obj_a)
    bullet.compute([objID], dt, maxsteps)
    ret = bullet.getObjectData([objID])
    assert ret.ok
    assert isEqualBD(ret.data, obj_a)

    # Now apply a central force of one Newton in z-direction and a torque of
    # two NewtonMeters.
    bullet.applyForceAndTorque(objID, force, torque)

    # Nothing must have happened because the simulation has not progressed.
    ret = bullet.getObjectData([objID])
    assert ret.ok
    assert isEqualBD(ret.data, obj_a)

    # Progress the simulation for another second.
    bullet.compute([objID], dt, maxsteps)
    ret = bullet.getObjectData([objID])
    assert ret.ok
    velLin, velRot = ret.data.velocityLin, ret.data.velocityRot

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


def test_remove_object():
    """
    Remove an object from the Bullet cache.
    """
    # Create a spherical object.
    obj_a = bullet_data.MotionState()

    # Instantiate Bullet engine.
    bullet = azrael.bullet.boost_bullet.PyBulletPhys(1)

    # Request an invalid object ID.
    ret = bullet.getObjectData([0])
    assert not ret.ok

    # Send object to Bullet and request it back.
    bullet.setObjectData(0, obj_a)
    ret = bullet.getObjectData([0])
    assert ret.ok
    assert isEqualBD(ret.data, obj_a)

    # Delete the object. The attempt to request it afterwards must fail.
    assert bullet.removeObject([0]).ok
    assert not bullet.getObjectData([0]).ok

    print('Test passed')


def test_modify_mass():
    """
    Create two identical spheres, double the mass of one, and apply the same
    force to both. The heavier sphere must have moved only half as far.
    """
    # Constants and parameters for this test.
    objID_a, objID_b = 10, 20
    pos_a = [+5, 0, 0]
    pos_b = [-5, 0, 0]
    cshape = [3, 1, 1, 1]
    force = np.array([0, 1, 0], np.float64)
    torque = np.array([0, 0, 0], np.float64)

    # Create two identical spheres, one left, one right (x-axis).
    obj_a = bullet_data.MotionState(position=pos_a, cshape=cshape, imass=1)
    obj_b = bullet_data.MotionState(position=pos_b, cshape=cshape, imass=1)

    # Instantiate Bullet engine.
    bullet = azrael.bullet.boost_bullet.PyBulletPhys(1)

    # Send object to Bullet and progress the simulation by one second.
    # The objects must not move because no forces are at play.
    bullet.setObjectData(objID_a, obj_a)
    bullet.setObjectData(objID_b, obj_b)

    # Progress the simulation for one second. Nothing must happen.
    bullet.compute([objID_a, objID_b], 1.0, 60)

    # Update the mass of the second object.
    obj_b = obj_b._replace(imass=0.5 * obj_b.imass)
    bullet.setObjectData(objID_b, obj_b)

    # Apply the same central force that pulls both spheres forward (y-axis).
    bullet.applyForceAndTorque(objID_a, force, torque)
    bullet.applyForceAndTorque(objID_b, force, torque)

    # Progress the simulation for another second.
    bullet.compute([objID_a, objID_b], 1.0, 60)

    # The lighter sphere must have moved pretty exactly twice as far in
    # y-direction.
    ret_a = bullet.getObjectData([objID_a])
    assert ret_a.ok
    ret_b = bullet.getObjectData([objID_b])
    assert ret_b.ok
    assert abs(ret_a.data.position[1] - 2 * ret_b.data.position[1]) < 1E-5

    print('Test passed')


def test_modify_size():
    """
    Change the size of the collision shape. This is more intricate than
    changing the mass (see previous test) because this time the entire
    collision shape must be swapped out underneath.

    To test this we create two spheres that do not touch, which means nothing
    must happen during a physics update. Then we enlarge one sphere so that it
    touchs the other. This time Bullet must pick up on the interpenetration and
    modify the sphere's position (somehow).
    """
    # Constants and parameters for this test.
    objID_a, objID_b = 10, 20
    pos_a = [0, 0, 0]
    pos_b = [3, 0, 0]
    cshape = [3, 1, 1, 1]
    force = np.array([0, 1, 0], np.float64)
    torque = np.array([0, 0, 0], np.float64)

    # Create two identical spheres, one left, one right (x-axis).
    obj_a = bullet_data.MotionState(position=pos_a, cshape=cshape)
    obj_b = bullet_data.MotionState(position=pos_b, cshape=cshape)

    # Instantiate Bullet engine.
    bullet = azrael.bullet.boost_bullet.PyBulletPhys(1)

    # Send object to Bullet and progress the simulation by one second.
    # The objects must not move because no forces are at play.
    bullet.setObjectData(objID_a, obj_a)
    bullet.setObjectData(objID_b, obj_b)

    # Progress the simulation for one second. Nothing must happen.
    bullet.compute([objID_a, objID_b], 1.0, 60)

    ret = bullet.getObjectData([objID_a])
    assert ret.ok
    assert isEqualBD(ret.data, obj_a)
    ret = bullet.getObjectData([objID_b])
    assert ret.ok
    assert isEqualBD(ret.data, obj_b)

    # Enlarge the second object so that the spheres do not overlap.
    obj_b = obj_b._replace(scale=2.5)
    bullet.setObjectData(objID_b, obj_b)

    # Progress the simulation for one second. Bullet must move the spheres away
    # from each other.
    bullet.compute([objID_a, objID_b], 1.0, 60)

    # Apply the same central force that pulls both spheres forward (y-axis).
    bullet.applyForceAndTorque(objID_a, force, torque)
    bullet.applyForceAndTorque(objID_b, force, torque)

    # Progress the simulation for one second. Bullet must move the objects away
    # from each other (in y-direction only).
    bullet.compute([objID_a, objID_b], 1.0, 60)
    ret = bullet.getObjectData([objID_a])
    assert ret.data.position[1] > pos_a[1]
    ret = bullet.getObjectData([objID_b])
    assert ret.data.position[1] > pos_b[1]

    print('Test passed')


def test_modify_cshape():
    """
    Change the collision shape type. This is more intricate than
    changing the mass (see previous test) because this time the entire
    collision shape must be swapped out underneath.

    To test this we create two spheres that (just) do not touch. They are
    offset along the x/y axis. Once we change the spheres to cubes the their
    edges will interpenetrate and Bullet will move them apart. We can identify
    this movement.
    """
    # Constants and parameters for this test.
    objID_a, objID_b = 10, 20
    pos_a = [-0.8, -0.8, 0]
    pos_b = [0.8, 0.8, 0]
    cs_cube = [4, 2, 2, 2]
    cs_sphere = [3, 1, 1, 1]
    force = np.array([0, 1, 0], np.float64)
    torque = np.array([0, 0, 0], np.float64)

    # Create two identical unit spheres, offset along the x/y axis.
    obj_a = bullet_data.MotionState(position=pos_a, cshape=cs_sphere)
    obj_b = bullet_data.MotionState(position=pos_b, cshape=cs_sphere)

    # Instantiate Bullet engine.
    bullet = azrael.bullet.boost_bullet.PyBulletPhys(1)

    # Send objects to Bullet and progress the simulation by one second.
    # The objects must not move because no forces are at play and the spheres
    # do not touch.
    bullet.setObjectData(objID_a, obj_a)
    bullet.setObjectData(objID_b, obj_b)
    bullet.compute([objID_a, objID_b], 1.0, 60)
    ret = bullet.getObjectData([objID_a])
    assert ret.ok
    assert isEqualBD(ret.data, obj_a)
    ret = bullet.getObjectData([objID_b])
    assert ret.ok
    assert isEqualBD(ret.data, obj_b)

    # Change the collision shape of both objects to a unit cube.
    obj_a = bullet_data.MotionState(position=pos_a, cshape=cs_cube)
    obj_b = bullet_data.MotionState(position=pos_b, cshape=cs_cube)
    bullet.setObjectData(objID_a, obj_a)
    bullet.setObjectData(objID_b, obj_b)

    # Apply the same central force that pulls both spheres forward (y-axis).
    bullet.applyForceAndTorque(objID_a, force, torque)
    bullet.applyForceAndTorque(objID_b, force, torque)

    # Progress the simulation for one second. Bullet must move the objects away
    # from each other (in y-direction only).
    bullet.compute([objID_a, objID_b], 1.0, 60)
    ret = bullet.getObjectData([objID_a])
    assert ret.data.position[1] > pos_a[1]
    ret = bullet.getObjectData([objID_b])
    assert ret.data.position[1] > pos_b[1]

    print('Test passed')


if __name__ == '__main__':
    test_modify_cshape()
    test_modify_size()
    test_modify_mass()
    test_update_object()
    test_getset_object()
    test_remove_object()
    test_apply_force_and_torque()
    test_apply_force('applyForceAndTorque')
    test_apply_force('applyForce')
