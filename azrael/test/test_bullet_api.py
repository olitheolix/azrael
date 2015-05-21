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

import pytest
import azrael.bullet_api
import azrael.bullet_data as bullet_data
import numpy as np

from IPython import embed as ipshell
from azrael.types import _MotionState
from azrael.types import CollShapeMeta, CollShapeEmpty, CollShapeSphere
from azrael.types import CollShapeBox


def isEqualBD(bd1: _MotionState, bd2: _MotionState):
    """
    Return *True* if the content of ``bd1`` is (roughly) equal to ``bd2``.

    This is a convenience function only.
    """
    for f in _MotionState._fields:
        a, b = getattr(bd1, f), getattr(bd2, f)
        try:
            if f == 'cshape':
                assert isinstance(bd1, (tuple, list))
                assert isinstance(bd2, (tuple, list))
                for csm_a, csm_b in zip(a, b):
                    tmp_a = CollShapeMeta(*csm_a)
                    tmp_b = CollShapeMeta(*csm_b)
                    tmp_a = tmp_a._replace(cs=list(tmp_a.cs))
                    tmp_b = tmp_b._replace(cs=list(tmp_b.cs))
                    tmp_a = tmp_a._replace(pos=list(tmp_a.pos))
                    tmp_b = tmp_b._replace(pos=list(tmp_b.pos))
                    tmp_a = tmp_a._replace(rot=list(tmp_a.rot))
                    tmp_b = tmp_b._replace(rot=list(tmp_b.rot))
                    tmp_a = list(tmp_a)
                    tmp_b = list(tmp_b)
                    assert tmp_a == tmp_b
            else:
                assert np.allclose(a, b, atol=1E-9)
        except (AssertionError, ValueError):
            return False
    return True


class TestBulletAPI:
    @classmethod
    def setup_class(cls):
        pass

    @classmethod
    def teardown_class(cls):
        pass

    def test_isEqualBD(self):
        """
        Verify that the auxiliary `isEqualBD` function works as expected.
        """
        # Define a set of collision shapes.
        pos = (0, 1, 2)
        rot = (0, 0, 0, 1)
        cs2 = [
            CollShapeMeta('1', pos, rot, CollShapeEmpty()),
            CollShapeMeta('2', pos, rot, CollShapeSphere(radius=1))
        ]

        # Create an object and serialise it.
        obj_a = bullet_data.MotionState(
            scale=3.5,
            imass=4.5,
            cshape=cs2,
            restitution=5.5,
            orientation=np.array([0, 1, 0, 0], np.float64),
            position=np.array([0.2, 0.4, 0.6], np.float64),
            velocityLin=np.array([0.8, 1.0, 1.2], np.float64),
            velocityRot=np.array([1.4, 1.6, 1.8], np.float64))
        assert obj_a is not None

        obj_b = bullet_data.MotionState(
            scale=3.5,
            imass=4.5,
            restitution=5.5,
            orientation=np.array([0, 1, 0, 0], np.float64),
            position=np.array([0.2, 0.4, 0.6], np.float64),
            velocityLin=np.array([0.8, 1.0, 1.2], np.float64),
            velocityRot=np.array([1.4, 1.6, 1.8], np.float64))
        assert obj_b is not None

        # Swap out the Collision shape.
        obj_c = obj_a._replace(
            cshape=[CollShapeMeta('2', pos, rot, CollShapeBox(1, 1, 1))])

        # Verify that the original objects are all identical to themselves but
        # distinct from each other.
        assert obj_a is not None
        assert obj_b is not None
        assert obj_c is not None
        assert isEqualBD(obj_a, obj_a)
        assert isEqualBD(obj_b, obj_b)
        assert isEqualBD(obj_c, obj_c)
        assert not isEqualBD(obj_a, obj_b)
        assert not isEqualBD(obj_a, obj_c)
        assert not isEqualBD(obj_b, obj_c)

        # Replace a scalar value and verify that 'isEqualBD' picks it up.
        assert isEqualBD(obj_a, obj_a._replace(scale=3.5))
        assert not isEqualBD(obj_a, obj_a._replace(scale=1))

        # Replace a vector value with various combinations of being a tuple,
        # list, or NumPy array.
        pos_old = np.array([0.2, 0.4, 0.6])
        pos_new = 2 * pos_old
        assert isEqualBD(obj_a, obj_a._replace(position=tuple(pos_old)))
        assert isEqualBD(obj_a, obj_a._replace(position=list(pos_old)))
        assert isEqualBD(obj_a, obj_a._replace(position=pos_old))
        assert not isEqualBD(obj_a, obj_a._replace(position=tuple(pos_new)))
        assert not isEqualBD(obj_a, obj_a._replace(position=list(pos_new)))
        assert not isEqualBD(obj_a, obj_a._replace(position=pos_new))

        # Try to replace a 3-vector with a 4-vector.
        pos_old = np.array([0.2, 0.4, 0.6])
        pos_new = np.array([0.2, 0.4, 0.6, 0.8])
        assert isEqualBD(obj_a, obj_a._replace(position=pos_old))
        assert not isEqualBD(obj_a, obj_a._replace(position=pos_new))

        # Replace the CollShape named tuple with just a list.
        p, q = (0, 0, 0), (0, 0, 0, 1)
        cs2_1 = CollShapeMeta('csfoo', p, q, CollShapeSphere(2))
        cs2_2 = list(CollShapeMeta('csfoo', p, q, list(CollShapeSphere(2))))
        obj_a1 = obj_a._replace(cshape=[cs2_1])
        obj_a2 = obj_a._replace(cshape=[cs2_2])

        assert isEqualBD(obj_a1, obj_a2)

    def test_getset_object(self):
        """
        Send/retrieve object to/from Bullet and verify the integrity.
        """
        # Define a set of collision shapes.
        pos = (0, 1, 2)
        rot = (0, 0, 0, 1)
        cs2 = [
            CollShapeMeta('1', pos, rot, CollShapeEmpty()),
            CollShapeMeta('2', pos, rot, CollShapeSphere(radius=1))
        ]

        # Create an object and serialise it.
        obj_a = bullet_data.MotionState(
            scale=3.5,
            imass=4.5,
            cshape=cs2,
            restitution=5.5,
            orientation=np.array([0, 1, 0, 0], np.float64),
            position=np.array([0.2, 0.4, 0.6], np.float64),
            velocityLin=np.array([0.8, 1.0, 1.2], np.float64),
            velocityRot=np.array([1.4, 1.6, 1.8], np.float64))
        assert obj_a is not None

        # Instantiate Bullet engine.
        bullet = azrael.bullet_api.PyBulletDynamicsWorld(1)

        # Request an invalid object ID.
        ret = bullet.getObjectData([0])
        assert not ret.ok

        # Send object to Bullet and request it back.
        bullet.setObjectData(0, obj_a)
        ret = bullet.getObjectData([0])
        assert ret.ok
        assert isEqualBD(obj_a, ret.data)

    def test_update_object(self):
        """
        Add an object to Bullet, then change its parameters.
        """
        cs2 = [CollShapeMeta('foo', (0, 0, 0), (0, 0, 0, 1), CollShapeSphere(1))]

        # Create an object and serialise it.
        obj_a = bullet_data.MotionState(
            scale=3.5,
            imass=4.5,
            cshape=cs2,
            restitution=5.5,
            orientation=np.array([0, 1, 0, 0], np.float64),
            position=np.array([0.2, 0.4, 0.6], np.float64),
            velocityLin=np.array([0.8, 1.0, 1.2], np.float64),
            velocityRot=np.array([1.4, 1.6, 1.8], np.float64))
        assert obj_a is not None

        # Instantiate Bullet engine.
        bullet = azrael.bullet_api.PyBulletDynamicsWorld(1)

        # Send object to Bullet and request it back.
        bullet.setObjectData(0, obj_a)
        ret = bullet.getObjectData([0])
        assert ret.ok
        assert isEqualBD(ret.data, obj_a)

        # Update the object.
        obj_a = bullet_data.MotionState(
            scale=6.5,
            imass=7.5,
            cshape=cs2,
            restitution=8.5,
            orientation=np.array([0, 0, 1, 0], np.float64),
            position=np.array([1.2, 1.4, 1.6], np.float64),
            velocityLin=np.array([2.8, 2.0, 2.2], np.float64),
            velocityRot=np.array([2.4, 2.6, 2.8], np.float64))
        assert obj_a is not None
        bullet.setObjectData(0, obj_a)
        ret = bullet.getObjectData([0])
        assert ret.ok
        assert isEqualBD(ret.data, obj_a)

    @pytest.mark.parametrize('force_fun_id', ['applyForce', 'applyForceAndTorque'])
    def test_apply_force(self, force_fun_id):
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
        bullet = azrael.bullet_api.PyBulletDynamicsWorld(1)

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

    def test_compute_invalid(self):
        """
        Call 'compute' method for non-existing object IDs.
        """
        # Constants and parameters for this test.
        objID = 10
        dt, maxsteps = 1.0, 60

        # Create an object and overwrite the CShape data to obtain a sphere.
        obj_a = bullet_data.MotionState()

        # Instantiate Bullet engine.
        bullet = azrael.bullet_api.PyBulletDynamicsWorld(1)

        # Call 'compute' on non-existing object.
        assert not bullet.compute([objID], dt, maxsteps).ok

        # Send object to Bullet and progress the simulation by one second.
        # The objects must not move because no forces are at play.
        bullet.setObjectData(objID, obj_a)
        assert bullet.compute([objID], dt, maxsteps).ok
        ret = bullet.getObjectData([objID])
        assert ret.ok
        assert isEqualBD(ret.data, obj_a)

        # Call 'compute' again with one (in)valid object.
        assert not bullet.compute([objID, 100], dt, maxsteps).ok
        assert not bullet.compute([100, objID], dt, maxsteps).ok

    def test_apply_force_and_torque(self):
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
        cs2 = [CollShapeMeta('foo', (0, 0, 0), (0, 0, 0, 1), CollShapeSphere(1))]
        obj_a = bullet_data.MotionState(cshape=cs2, imass=2 / 5)

        # Instantiate Bullet engine.
        bullet = azrael.bullet_api.PyBulletDynamicsWorld(1)

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

    def test_remove_object(self):
        """
        Remove an object from the Bullet cache.
        """
        # Create a spherical object.
        obj_a = bullet_data.MotionState()

        # Instantiate Bullet engine.
        bullet = azrael.bullet_api.PyBulletDynamicsWorld(1)

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

    def test_modify_mass(self):
        """
        Create two identical spheres, double the mass of one, and apply the same
        force to both. The heavier sphere must have moved only half as far.
        """
        # Constants and parameters for this test.
        objID_a, objID_b = 10, 20
        pos_a = [+5, 0, 0]
        pos_b = [-5, 0, 0]
        force = np.array([0, 1, 0], np.float64)
        torque = np.array([0, 0, 0], np.float64)
        cshape = [CollShapeMeta('foo', (0, 0, 0), (0, 0, 0, 1), CollShapeSphere(1))]

        # Create two identical spheres, one left, one right (x-axis).
        obj_a = bullet_data.MotionState(position=pos_a, cshape=cshape, imass=1)
        obj_b = bullet_data.MotionState(position=pos_b, cshape=cshape, imass=1)

        # Instantiate Bullet engine.
        bullet = azrael.bullet_api.PyBulletDynamicsWorld(1)

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

    def test_modify_size(self):
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
        force = np.array([0, 1, 0], np.float64)
        torque = np.array([0, 0, 0], np.float64)

        # Create two identical spheres, one left, one right (x-axis).
        cs_a = [CollShapeMeta('csfoo', (0, 0, 0), (0, 0, 0, 1), CollShapeSphere(1))]
        cs_b = [CollShapeMeta('csbar', (0, 0, 0), (0, 0, 0, 1), CollShapeSphere(1))]
        obj_a = bullet_data.MotionState(position=pos_a, cshape=cs_a)
        obj_b = bullet_data.MotionState(position=pos_b, cshape=cs_b)
        del cs_a, cs_b

        # Instantiate Bullet engine.
        bullet = azrael.bullet_api.PyBulletDynamicsWorld(1)

        # Send objects to Bullet and progress the simulation. The sole point of
        # progressing the simulation is to make sure Bullet actually accesses the
        # objects; we do not actually care if/how the objects moved.
        bullet.setObjectData(objID_a, obj_a)
        bullet.setObjectData(objID_b, obj_b)
        bullet.compute([objID_a, objID_b], 1.0, 60)

        # Verify that the collision shapes are as expected.
        ret = bullet.getObjectData([objID_a])
        assert ret.ok
        assert ret.data.cshape[0].name.upper() == 'CSFOO'
        tmp_cs = bullet.rigidBodies[objID_a].getCollisionShape()
        assert tmp_cs.getLocalScaling().topy() == (1.0, 1.0, 1.0)

        ret = bullet.getObjectData([objID_b])
        assert ret.ok
        assert ret.data.cshape[0].name.upper() == 'CSBAR'
        tmp_cs = bullet.rigidBodies[objID_b].getCollisionShape()
        assert tmp_cs.getLocalScaling().topy() == (1.0, 1.0, 1.0)

        # Enlarge the second object so that the spheres do not overlap.  Then step
        # the simulation again to ensure Bullet accesses each object and nothing
        # bad happens (eg a segfault).
        obj_b = obj_b._replace(scale=2.5)
        bullet.setObjectData(objID_b, obj_b)
        bullet.compute([objID_a, objID_b], 1.0, 60)

        # Progress the simulation for one second. Bullet must move the objects away
        # from each other (in y-direction only).
        bullet.compute([objID_a, objID_b], 1.0, 60)
        ret = bullet.getObjectData([objID_a])
        assert ret.ok
        assert ret.data.cshape[0].name.upper() == 'CSFOO'
        tmp_cs = bullet.rigidBodies[objID_a].getCollisionShape()
        assert tmp_cs.getLocalScaling().topy() == (1.0, 1.0, 1.0)

        ret = bullet.getObjectData([objID_b])
        assert ret.ok
        assert ret.data.cshape[0].name.upper() == 'CSBAR'
        tmp_cs = bullet.rigidBodies[objID_b].getCollisionShape()
        assert tmp_cs.getLocalScaling().topy() == (2.5, 2.5, 2.5)

    def test_modify_cshape(self):
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
        p, q = (0, 0, 0), (0, 0, 0, 1)
        cs2_box = [CollShapeMeta('csbox', p, q, CollShapeBox(1, 1, 1))]
        cs2_sphere = [CollShapeMeta('cssphere', p, q, CollShapeSphere(1))]
        del p, q

        # Create two identical unit spheres, offset along the x/y axis.
        obj_a = bullet_data.MotionState(
            position=pos_a, cshape=cs2_sphere)
        obj_b = bullet_data.MotionState(
            position=pos_b, cshape=cs2_sphere)

        # Instantiate Bullet engine.
        bullet = azrael.bullet_api.PyBulletDynamicsWorld(1)

        # Send objects to Bullet and progress the simulation. The sole point of
        # progressing the simulation is to make sure Bullet actually accesses the
        # objects; we do not actually care if/how the objects moved.
        bullet.setObjectData(objID_a, obj_a)
        bullet.setObjectData(objID_b, obj_b)
        bullet.compute([objID_a, objID_b], 1.0, 60)

        # Verify the collision shapes are as expected.
        ret = bullet.getObjectData([objID_a])
        assert ret.ok
        assert ret.data.cshape[0].name.upper() == 'CSSPHERE'
        ret = bullet.getObjectData([objID_b])
        assert ret.ok
        assert ret.data.cshape[0].name.upper() == 'CSSPHERE'

        # Change both collision shape to unit cubes. Then step the simulation again
        # to ensure Bullet accesses each object and nothing bad happens (eg a
        # segfault).
        obj_a = bullet_data.MotionState(position=pos_a, cshape=cs2_box)
        obj_b = bullet_data.MotionState(position=pos_b, cshape=cs2_box)
        bullet.setObjectData(objID_a, obj_a)
        bullet.setObjectData(objID_b, obj_b)
        bullet.compute([objID_a, objID_b], 1.0, 60)

        # Verify the collision shapes have been updated to boxes.
        ret = bullet.getObjectData([objID_a])
        assert ret.ok
        assert ret.data.cshape[0].name.upper() == 'CSBOX'
        ret = bullet.getObjectData([objID_b])
        assert ret.ok
        assert ret.data.cshape[0].name.upper() == 'CSBOX'
