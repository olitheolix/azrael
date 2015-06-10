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
from azrael.types import ConstraintMeta, ConstraintP2P, Constraint6DofSpring2


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


def getCSEmpty(name='csempty', pos=[0, 0, 0], rot=[0, 0, 0, 1]):
    """
    Convenience function to construct an Empty shape.
    """
    return CollShapeMeta('empty', name, pos, rot, CollShapeEmpty())


def getCSBox(name='csbox', pos=[0, 0, 0], rot=[0, 0, 0, 1], dim=[1, 1, 1]):
    """
    Convenience function to construct a Box shape.
    """
    return CollShapeMeta('box', name, pos, rot, CollShapeBox(*dim))


def getCSSphere(name='cssphere', pos=[0, 0, 0], rot=[0, 0, 0, 1], radius=1):
    """
    Convenience function to construct a Sphere shape.
    """
    return CollShapeMeta('sphere', name, pos, rot, CollShapeSphere(radius))


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
        cshape = [getCSEmpty('1', pos, rot), getCSSphere('2', pos, rot)]

        # Create an object and serialise it.
        obj_a = bullet_data.MotionState(
            scale=3.5,
            imass=4.5,
            cshape=cshape,
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
        obj_c = obj_a._replace(cshape=[getCSBox('2', pos, rot)])

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
        cshape_1 = getCSSphere('csfoo', pos, rot, radius=2)
        cshape_2 = cshape_1._replace(cs=list(cshape_1.cs))
        cshape_2 = list(cshape_2)
        obj_a1 = obj_a._replace(cshape=[cshape_1])
        obj_a2 = obj_a._replace(cshape=[cshape_2])

        assert isEqualBD(obj_a1, obj_a2)

    def test_getset_object(self):
        """
        Send/retrieve object to/from Bullet and verify the integrity.
        """
        # Define a set of collision shapes.
        pos = (0, 1, 2)
        rot = (0, 0, 0, 1)
        cshape = [getCSEmpty('1', pos, rot), getCSSphere('2', pos, rot)]
        del pos, rot

        # Create an object and serialise it.
        obj_a = bullet_data.MotionState(
            scale=3.5,
            imass=4.5,
            cshape=cshape,
            restitution=5.5,
            orientation=np.array([0, 1, 0, 0], np.float64),
            position=np.array([0.2, 0.4, 0.6], np.float64),
            velocityLin=np.array([0.8, 1.0, 1.2], np.float64),
            velocityRot=np.array([1.4, 1.6, 1.8], np.float64))
        assert obj_a is not None

        # Instantiate Bullet engine.
        bullet = azrael.bullet_api.PyBulletDynamicsWorld(1)

        # Request an invalid object ID.
        ret = bullet.getObjectData(0)
        assert not ret.ok

        # Send object to Bullet and request it back.
        bullet.setObjectData(0, obj_a)
        ret = bullet.getObjectData(0)
        assert ret.ok
        assert isEqualBD(obj_a, ret.data)

    def test_update_object(self):
        """
        Add an object to Bullet, then change its parameters.
        """
        cshape = [getCSSphere('foo')]

        # Create an object and serialise it.
        obj_a = bullet_data.MotionState(
            scale=3.5,
            imass=4.5,
            cshape=cshape,
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
        ret = bullet.getObjectData(0)
        assert ret.ok
        assert isEqualBD(ret.data, obj_a)

        # Update the object.
        obj_a = bullet_data.MotionState(
            scale=6.5,
            imass=7.5,
            cshape=cshape,
            restitution=8.5,
            orientation=np.array([0, 0, 1, 0], np.float64),
            position=np.array([1.2, 1.4, 1.6], np.float64),
            velocityLin=np.array([2.8, 2.0, 2.2], np.float64),
            velocityRot=np.array([2.4, 2.6, 2.8], np.float64))
        assert obj_a is not None
        bullet.setObjectData(0, obj_a)
        ret = bullet.getObjectData(0)
        assert ret.ok
        assert isEqualBD(ret.data, obj_a)

    @pytest.mark.parametrize('forceFun', ['applyForce', 'applyForceAndTorque'])
    def test_apply_force(self, forceFun):
        """
        Create object, send it to Bullet, apply a force, progress the
        simulation, and verify the object moved correctly.
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
        ret = bullet.getObjectData(objID)
        assert ret.ok
        assert isEqualBD(ret.data, obj_a)

        # Now apply a central force of one Newton in z-direction.
        if forceFun == 'applyForce':
            applyForceFun = bullet.applyForce
        elif forceFun == 'applyForceAndTorque':
            applyForceFun = bullet.applyForceAndTorque
        else:
            assert False
        applyForceFun(objID, force, np.zeros(3, np.float64))

        # Nothing must have happened because the simulation has not progressed.
        ret = bullet.getObjectData(objID)
        assert ret.ok
        assert isEqualBD(ret.data, obj_a)

        # Progress the simulation by another 'dt' seconds.
        bullet.compute([objID], dt, maxsteps)
        ret = bullet.getObjectData(objID)
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
        ret = bullet.getObjectData(objID)
        assert ret.ok
        assert isEqualBD(ret.data, obj_a)

        # Call 'compute' again with one (in)valid object.
        assert not bullet.compute([objID, 100], dt, maxsteps).ok
        assert not bullet.compute([100, objID], dt, maxsteps).ok

    def test_apply_force_and_torque(self):
        """
        Create object, send it to Bullet, apply a force, progress the
        simulation, and verify the object moved correctly.
        """
        # Constants and parameters for this test.
        objID = 10
        force = np.array([0, 0, 1], np.float64)
        torque = np.array([0, 0, 1], np.float64)
        dt, maxsteps = 1.0, 60

        # Create a spherical object. Adjust the mass so that the sphere's
        # inertia is roughly unity.
        cshape = [getCSSphere('foo')]
        obj_a = bullet_data.MotionState(cshape=cshape, imass=2 / 5)

        # Instantiate Bullet engine.
        bullet = azrael.bullet_api.PyBulletDynamicsWorld(1)

        # Send object to Bullet and progress the simulation by one second.
        # The objects must not move because no forces are at play.
        bullet.setObjectData(objID, obj_a)
        bullet.compute([objID], dt, maxsteps)
        ret = bullet.getObjectData(objID)
        assert ret.ok
        assert isEqualBD(ret.data, obj_a)

        # Now apply a central force of one Newton in z-direction and a torque
        # of two NewtonMeters.
        bullet.applyForceAndTorque(objID, force, torque)

        # Nothing must have happened because the simulation has not progressed.
        ret = bullet.getObjectData(objID)
        assert ret.ok
        assert isEqualBD(ret.data, obj_a)

        # Progress the simulation for another second.
        bullet.compute([objID], dt, maxsteps)
        ret = bullet.getObjectData(objID)
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
        #
        # where the torque $T$ follows from angular acceleration OMEGA
        #   T = I * OMEGA --> OMEGA = T / I    (2)
        #
        # Substitue (2) into (1) to obtain
        #   omega = t * (T / I)
        #
        # Our Inertia is roughly unity because we adjusted the sphere's mass
        # accordingly when we created it (ie. set it 5/2kg or 2/5 for the
        # inverse mass).
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
        ret = bullet.getObjectData(0)
        assert not ret.ok

        # Send object to Bullet and request it back.
        bullet.setObjectData(0, obj_a)
        ret = bullet.getObjectData(0)
        assert ret.ok
        assert isEqualBD(ret.data, obj_a)

        # Delete the object. The attempt to request it afterwards must fail.
        assert bullet.removeObject([0]).ok
        assert not bullet.getObjectData(0).ok

    def test_modify_mass(self):
        """
        Create two identical spheres, double the mass of one, and apply the
        same force to both. The heavier sphere must have moved only half as
        far.
        """
        # Constants and parameters for this test.
        objID_a, objID_b = 10, 20
        pos_a = [+5, 0, 0]
        pos_b = [-5, 0, 0]
        force = np.array([0, 1, 0], np.float64)
        torque = np.array([0, 0, 0], np.float64)
        cshape = [getCSSphere('foo')]

        # Create two identical spheres, one left, one right (x-axis).
        obj_a = bullet_data.MotionState(position=pos_a, cshape=cshape, imass=1)
        obj_b = bullet_data.MotionState(position=pos_b, cshape=cshape, imass=1)
        del pos_a, pos_b, cshape

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

        # Apply the same central force that pulls both spheres forward
        # (y-axis).
        bullet.applyForceAndTorque(objID_a, force, torque)
        bullet.applyForceAndTorque(objID_b, force, torque)

        # Progress the simulation for another second.
        bullet.compute([objID_a, objID_b], 1.0, 60)

        # The lighter sphere must have moved pretty exactly twice as far in
        # y-direction.
        ret_a = bullet.getObjectData(objID_a)
        assert ret_a.ok
        ret_b = bullet.getObjectData(objID_b)
        assert ret_b.ok
        assert abs(ret_a.data.position[1] - 2 * ret_b.data.position[1]) < 1E-5

    def test_modify_size(self):
        """
        Change the size of the collision shape. This is more intricate than
        changing the mass (see previous test) because this time the entire
        collision shape must be swapped out underneath.

        To test this we create two spheres that do not touch, which means
        nothing must happen during a physics update. Then we enlarge one sphere
        so that it touchs the other. This time Bullet must pick up on the
        interpenetration and modify the sphere's position somehow (we do not
        really care how).
        """
        # Constants and parameters for this test.
        objID_a, objID_b = 10, 20
        pos_a = [0, 0, 0]
        pos_b = [3, 0, 0]

        # Create two identical spheres, one left, one right (x-axis).
        radius = 2
        cs_a = [getCSSphere('csfoo', radius=radius)]
        cs_b = [getCSSphere('csbar', radius=radius)]
        obj_a = bullet_data.MotionState(position=pos_a, cshape=cs_a)
        obj_b = bullet_data.MotionState(position=pos_b, cshape=cs_b)
        del cs_a, cs_b, pos_a, pos_b

        # Instantiate Bullet engine.
        bullet = azrael.bullet_api.PyBulletDynamicsWorld(1)

        # Send objects to Bullet and progress the simulation. The sole point of
        # progressing the simulation is to make sure Bullet actually accesses
        # the objects; we do not actually care if/how the objects moved.
        bullet.setObjectData(objID_a, obj_a)
        bullet.setObjectData(objID_b, obj_b)
        bullet.compute([objID_a, objID_b], 1.0, 60)

        # Request the object back and inspect the collision shapes.
        ret_a = bullet.getObjectData(objID_a)
        ret_b = bullet.getObjectData(objID_b)
        assert ret_a.ok and ret_b.ok
        assert ret_a.data.cshape[0].name.upper() == 'CSFOO'
        assert ret_b.data.cshape[0].name.upper() == 'CSBAR'
        tmp_cs = bullet.rigidBodies[objID_a].getCollisionShape()
        assert tmp_cs.getChildShape(0).getRadius() == radius
        tmp_cs = bullet.rigidBodies[objID_b].getCollisionShape()
        assert tmp_cs.getChildShape(0).getRadius() == radius

        # Enlarge the second object so that the spheres do not overlap.
        obj_b = obj_b._replace(scale=2.5)
        bullet.setObjectData(objID_b, obj_b)
        ret = bullet.getObjectData(objID_b)
        assert ret.ok
        tmp_cs = bullet.rigidBodies[objID_b].getCollisionShape()
        assert tmp_cs.getChildShape(0).getRadius() == 2.5 * radius

        # Then step the simulation again to ensure Bullet accesses each object
        # and nothing bad happens (eg a segfault).
        bullet.compute([objID_a, objID_b], 1.0, 60)

    def test_modify_cshape(self):
        """
        Change the collision shape type. This is more intricate than
        changing the mass (see previous test) because this time the entire
        collision shape must be swapped out underneath.

        To test this we create two spheres that (just) do not touch. They are
        offset along the x/y axis. Once we change the spheres to cubes the
        their edges will interpenetrate and Bullet will move them apart. We can
        identify this movement.
        """
        # Constants and parameters for this test.
        objID_a, objID_b = 10, 20
        pos_a = [-0.8, -0.8, 0]
        pos_b = [0.8, 0.8, 0]
        p, q = (0, 0, 0), (0, 0, 0, 1)
        cshape_box = [getCSBox('csbox', p, q)]
        cshape_sph = [getCSSphere('cssphere', p, q)]
        del p, q

        # Create two identical unit spheres, offset along the x/y axis.
        obj_a = bullet_data.MotionState(position=pos_a, cshape=cshape_sph)
        obj_b = bullet_data.MotionState(position=pos_b, cshape=cshape_sph)

        # Instantiate Bullet engine.
        bullet = azrael.bullet_api.PyBulletDynamicsWorld(1)

        # Send objects to Bullet and progress the simulation. The sole point of
        # progressing the simulation is to make sure Bullet actually accesses
        # the objects; we do not actually care if/how the objects moved.
        bullet.setObjectData(objID_a, obj_a)
        bullet.setObjectData(objID_b, obj_b)
        bullet.compute([objID_a, objID_b], 1.0, 60)

        # Verify the collision shapes are as expected.
        ret = bullet.getObjectData(objID_a)
        assert ret.ok
        assert ret.data.cshape[0].name.upper() == 'CSSPHERE'
        ret = bullet.getObjectData(objID_b)
        assert ret.ok
        assert ret.data.cshape[0].name.upper() == 'CSSPHERE'

        # Change both collision shape to unit cubes. Then step the simulation
        # again to ensure Bullet accesses each object and nothing bad happens
        # (eg a segfault).
        obj_a = bullet_data.MotionState(position=pos_a, cshape=cshape_box)
        obj_b = bullet_data.MotionState(position=pos_b, cshape=cshape_box)
        bullet.setObjectData(objID_a, obj_a)
        bullet.setObjectData(objID_b, obj_b)
        bullet.compute([objID_a, objID_b], 1.0, 60)

        # Verify the collision shapes have been updated to boxes.
        ret = bullet.getObjectData(objID_a)
        assert ret.ok
        assert ret.data.cshape[0].name.upper() == 'CSBOX'
        ret = bullet.getObjectData(objID_b)
        assert ret.ok
        assert ret.data.cshape[0].name.upper() == 'CSBOX'

    def test_specify_P2P_constraint(self):
        """
        Use a P2P constraint to test the various methods to add- and remove
        constraints.
        """
        # Instantiate Bullet engine.
        bullet = azrael.bullet_api.PyBulletDynamicsWorld(1)

        # Create identical unit spheres at x=+/-1.
        id_a, id_b = 10, 20
        pos_a = (-1, 0, 0)
        pos_b = (1, 0, 0)
        obj_a = bullet_data.MotionState(position=pos_a, cshape=[getCSSphere()])
        obj_b = bullet_data.MotionState(position=pos_b, cshape=[getCSSphere()])

        # Load the objects into the physics engine.
        bullet.setObjectData(id_a, obj_a)
        bullet.setObjectData(id_b, obj_b)

        # Compile the constraint.
        pivot_a, pivot_b = pos_b, pos_a
        constraints = [
            ConstraintMeta('p2p', id_a, id_b, '',
                           ConstraintP2P(pivot_a, pivot_b)),
        ]

        # Load the constraints into the physics engine.
        assert bullet.setConstraints(constraints).ok

        # Step the simulation. Nothing must happen.
        bullet.compute([id_a, id_b], 1.0, 60)
        ret_a = bullet.getObjectData(id_a)
        ret_b = bullet.getObjectData(id_b)
        assert ret_a.ok and ret_b.ok
        assert np.allclose(ret_a.data.position, pos_a)
        assert np.allclose(ret_b.data.position, pos_b)

        # Apply a force that will pull the left object further to the left.
        bullet.applyForceAndTorque(id_a, (-10, 0, 0), (0, 0, 0))

        # Step the simulation. Both objects must have moved (almost) exactly
        # the same amount "delta".
        bullet.compute([id_a, id_b], 1.0, 60)
        ret_a = bullet.getObjectData(id_a)
        ret_b = bullet.getObjectData(id_b)
        assert ret_a.ok and ret_b.ok
        delta_a = np.array(ret_a.data.position) - np.array(pos_a)
        delta_b = np.array(ret_b.data.position) - np.array(pos_b)
        assert np.allclose(delta_a, delta_b)
        assert delta_a[1] == delta_a[2] == 0

        # Remove all constraints (do it twice to test the case when there are
        # no constraints).
        assert bullet.clearAllConstraints().ok
        assert bullet.clearAllConstraints().ok

        # Overwrite the objects with the default data (ie put them back into
        # the original position and set their velocity to zero).
        bullet.setObjectData(id_a, obj_a)
        bullet.setObjectData(id_b, obj_b)
        bullet.compute([id_a, id_b], 1.0, 60)
        ret_a = bullet.getObjectData(id_a)
        ret_b = bullet.getObjectData(id_b)
        assert ret_a.ok and ret_b.ok
        assert np.allclose(ret_a.data.position, pos_a)
        assert np.allclose(ret_b.data.position, pos_b)

        # Apply a force that will pull the left object further to the left.
        # However, now *only* the left one must move because there are not
        # constraint anymore.
        bullet.applyForceAndTorque(id_a, (-10, 0, 0), (0, 0, 0))
        bullet.compute([id_a, id_b], 1.0, 60)
        ret_a = bullet.getObjectData(id_a)
        ret_b = bullet.getObjectData(id_b)
        assert ret_a.ok and ret_b.ok
        assert not np.allclose(ret_a.data.position, pos_a)
        assert np.allclose(ret_b.data.position, pos_b)

    def test_specify_6DofSpring2_constraint(self):
        """
        Create two objects and linke them with a 6DOF constraint. The
        constraint mimicks a spring-loaded slider that will pull the objects
        together.
        """
        # Create physics simulation.
        sim = azrael.bullet_api.PyBulletDynamicsWorld(1)

        # Create identical unit spheres 10 meters apart.
        id_a, id_b = 10, 20
        pos_a = (-5, 0, 0)
        pos_b = (5, 0, 0)
        obj_a = bullet_data.MotionState(position=pos_a, cshape=[getCSSphere()])
        obj_b = bullet_data.MotionState(position=pos_b, cshape=[getCSSphere()])

        # Load the objects into the physics engine.
        sim.setObjectData(id_a, obj_a)
        sim.setObjectData(id_b, obj_b)

        # Compile the 6DOF constraint.
        c = Constraint6DofSpring2(
            frameInA=(0, 0, 0, 0, 0, 0, 1),
            frameInB=(0, 0, 0, 0, 0, 0, 1),
            stiffness=(1, 2, 3, 4, 5.5, 6),
            damping=(2, 3.5, 4, 5, 6.5, 7),
            equilibrium=(-1, -1, -1, 0, 0, 0),
            linLimitLo=(-10.5, -10.5, -10.5),
            linLimitHi=(10.5, 10.5, 10.5),
            rotLimitLo=(-0.1, -0.2, -0.3),
            rotLimitHi=(0.1, 0.2, 0.3),
            bounce=(1, 1.5, 2),
            enableSpring=(True, False, False, False, False, False))
        constraints = [ConstraintMeta('6DofSpring2', id_a, id_b, '', c)]
        del c

        # Step the simulation. Nothing must happen because no forces or
        # constraints act upon the objects.
        sim.compute([id_a, id_b], 1.0, 60)
        ret_a = sim.getObjectData(id_a)
        ret_b = sim.getObjectData(id_b)
        assert ret_a.ok and ret_b.ok
        assert np.allclose(ret_a.data.position, pos_a)
        assert np.allclose(ret_b.data.position, pos_b)

        # Load the constraints into the physics engine and step the simulation
        # again. This time the objects must move closer together.
        assert sim.setConstraints(constraints).ok

        # Step the simulation --> the objects must move closer together.
        sim.compute([id_a, id_b], 1.0, 60)
        ret_a = sim.getObjectData(id_a)
        ret_b = sim.getObjectData(id_b)
        assert ret_a.ok and ret_b.ok
        assert ret_a.data.position[0] > pos_a[0]
        assert ret_b.data.position[0] < pos_b[0]

    def test_specify_constraints_invalid(self):
        """
        Call the constraint- related methods with invalid data and verify that
        nothing breaks.
        """
        # Instantiate Bullet engine.
        bullet = azrael.bullet_api.PyBulletDynamicsWorld(1)

        # Create to spheres.
        id_a, id_b = 10, 20
        obj_a = bullet_data.MotionState(cshape=[getCSSphere()])
        obj_b = bullet_data.MotionState(cshape=[getCSSphere()])

        # An empty list is valid, albeit nothing will happen.
        assert bullet.setConstraints([]).ok

        # Invalid constraint types.
        assert not bullet.setConstraints([1]).ok

        # Compile the constraint.
        pivot_a, pivot_b = (0, 0, 0), (1, 1, 1)
        P2P = ConstraintP2P
        constraints = [
            ConstraintMeta('p2p', id_a, id_b, '', P2P(pivot_a, pivot_b)),
        ]

        # Constraint is valid but the objects do not exist.
        assert not bullet.setConstraints([constraints]).ok

        # Add one sphere to the world.
        bullet.setObjectData(id_a, obj_a)

        # Load the constraints into the physics engine.
        assert not bullet.setConstraints(constraints).ok

        # Load the second sphere and apply the constraint. This time it must
        # have worked.
        bullet.setObjectData(id_b, obj_b)
        assert bullet.setConstraints(constraints).ok

        # Clear all constraints
        assert bullet.clearAllConstraints().ok

        # Compile a P2P constraint with an invalid pivot.
        pivot_a, pivot_b = (0, 0, 0), (1, 1, 1, 1, 1)
        constraints = [
            ConstraintMeta('p2p', id_a, id_b, '', P2P(pivot_a, pivot_b)),
        ]
        assert not bullet.setConstraints(constraints).ok

        # Another invalid pivot.
        pivot_a, pivot_b = (0, 0, 0), (1, 1, 's')
        constraints = [
            ConstraintMeta('p2p', id_a, id_b, '', P2P(pivot_a, pivot_b)),
        ]
        assert not bullet.setConstraints(constraints).ok
