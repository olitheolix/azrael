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

import numpy as np

from IPython import embed as ipshell
from azrael.test.test import getP2P, get6DofSpring2, getRigidBody
from azrael.test.test import getCSEmpty, getCSBox, getCSSphere, getCSPlane


class TestBulletAPI:
    @classmethod
    def setup_class(cls):
        pass

    @classmethod
    def teardown_class(cls):
        pass

    def setup_method(self, method):
        pass

    def teardown_method(self, method):
        pass

    def isBulletRbsEqual(self, ret_bullet, ref):
        tmp = (ref.position, ref.rotation, ref.velocityLin, ref.velocityRot)
        ac = np.allclose
        try:
            assert ac(ret_bullet.position, ref.position)
            assert ac(ret_bullet.rotation, ref.rotation)
            assert ac(ret_bullet.vLin, ref.velocityLin)
            assert ac(ret_bullet.vRot, ref.velocityRot)
        except AssertionError:
            return False
        return True

    def test_convert_bullet2azrael(self):
        """
        Azrael uses the same coordinate system for fragment and collisions
        shapes positions. However, collision shapes must be specified relative
        to their center of mass to produce the correct physics. The position in
        Azrael and the position of the compound shape used in the physics
        engine there do not coincide unless the center of mass is (0, 0, 0).

        This test verifies that the utility functions that convert between the
        Azrael object position and the Bullet compound shape position work
        correctly.
        """
        # Convenience.
        bullet2azrael = azrael.bullet_api.bullet2azrael
        azrael2bullet = azrael.bullet_api.azrael2bullet
        Vec3 = azrael.bullet_api.Vec3
        Quaternion = azrael.bullet_api.Quaternion

        # Center of mass offset relative to the object position in Azrael (the
        # user specifies this value in the template).
        com_ofs = [2, 2, 0]

        # After a physics update Bullet gives us the following position and rotation
        # for the compound shape.
        bt_pos = Vec3(*[6, 2, 0])
        bt_rot = Quaternion(*[0, 0, 1, 0])

        # Convert this to an object position in Azrael. The rotatation of rigid
        # bodies and Azrael objects are always identical; only the position
        # differs due to the center of mass offset.
        az_pos, az_rot = bullet2azrael(bt_pos, bt_rot, com_ofs)
        assert np.allclose(az_pos, [8, 4, 0])
        assert np.allclose(az_rot, bt_rot.topy())

        # Convert the Azrael object position to a Bullet rigid body position.
        # Verify that this produces the original value.
        bt_pos_new, bt_rot_new = azrael2bullet(az_pos, az_rot, com_ofs)
        assert isinstance(bt_pos_new, Vec3)
        assert isinstance(bt_rot_new, Quaternion)
        assert np.allclose(bt_pos_new.topy(), bt_pos.topy())
        assert np.allclose(bt_rot_new.topy(), bt_rot.topy())

    def test_getset_object(self):
        """
        Send/retrieve object to/from Bullet and verify the integrity.
        """
        aid = '0'

        # Define a set of collision shapes.
        pos = (0, 1, 2)
        rot = (0, 0, 0, 1)
        cshapes = {'1': getCSEmpty(pos, rot), '2': getCSSphere(pos, rot)}
        del pos, rot

        # Create an object and serialise it.
        obj_a = getRigidBody(
            scale=3.5,
            imass=4.5,
            cshapes=cshapes,
            restitution=5.5,
            rotation=(0, 1, 0, 0),
            position=(0.2, 0.4, 0.6),
            velocityLin=(0.8, 1.0, 1.2),
            velocityRot=(1.4, 1.6, 1.8))
        assert obj_a is not None

        # Instantiate Bullet engine.
        sim = azrael.bullet_api.PyBulletDynamicsWorld(1)

        # Request an invalid object ID.
        ret = sim.getRigidBodyData(0)
        assert not ret.ok

        # Send object to Bullet and request it back.
        sim.setRigidBodyData(aid, obj_a)
        ret = sim.getRigidBodyData(aid)
        assert ret.ok and self.isBulletRbsEqual(ret.data, obj_a)

    def test_update_object(self):
        """
        Add an object to Bullet, then change its parameters.
        """
        aid = '0'
        cshapes = {'foo': getCSSphere()}

        # Create an object and serialise it.
        obj_a = getRigidBody(
            scale=3.5,
            imass=4.5,
            cshapes=cshapes,
            restitution=5.5,
            rotation=(0, 1, 0, 0),
            position=(0.2, 0.4, 0.6),
            velocityLin=(0.8, 1.0, 1.2),
            velocityRot=(1.4, 1.6, 1.8))
        assert obj_a is not None

        # Instantiate Bullet engine.
        sim = azrael.bullet_api.PyBulletDynamicsWorld(1)

        # Send object to Bullet and request it back.
        sim.setRigidBodyData(aid, obj_a)
        ret = sim.getRigidBodyData(aid)
        assert ret.ok and self.isBulletRbsEqual(ret.data, obj_a)

        # Update the object.
        obj_a = getRigidBody(
            scale=6.5,
            imass=7.5,
            cshapes=cshapes,
            restitution=8.5,
            rotation=(0, 0, 1, 0),
            position=(1.2, 1.4, 1.6),
            velocityLin=(2.8, 2.0, 2.2),
            velocityRot=(2.4, 2.6, 2.8))
        assert obj_a is not None
        sim.setRigidBodyData(aid, obj_a)
        ret = sim.getRigidBodyData(aid)
        assert ret.ok and self.isBulletRbsEqual(ret.data, obj_a)

    @pytest.mark.parametrize('forceFun', ['applyForce', 'applyForceAndTorque'])
    def test_apply_force(self, forceFun):
        """
        Create object, send it to Bullet, apply a force, progress the
        simulation, and verify the object moved correctly.
        """
        # Constants and parameters for this test.
        objID = '10'
        force = np.array([0, 0, 1], np.float64)
        dt, maxsteps = 1.0, 60

        # Create an object and overwrite the CShape data to obtain a sphere.
        obj_a = getRigidBody()

        # Instantiate Bullet engine.
        sim = azrael.bullet_api.PyBulletDynamicsWorld(1)

        # Send object to Bullet and progress the simulation by one second.
        # The objects must not move because no forces are at play.
        sim.setRigidBodyData(objID, obj_a)
        sim.compute([objID], dt, maxsteps)
        ret = sim.getRigidBodyData(objID)
        assert ret.ok and self.isBulletRbsEqual(ret.data, obj_a)

        # Now apply a central force of one Newton in z-direction.
        if forceFun == 'applyForce':
            applyForceFun = sim.applyForce
        elif forceFun == 'applyForceAndTorque':
            applyForceFun = sim.applyForceAndTorque
        else:
            assert False
        applyForceFun(objID, force, np.zeros(3, np.float64))

        # Nothing must have happened because the simulation has not progressed.
        ret = sim.getRigidBodyData(objID)
        assert ret.ok and self.isBulletRbsEqual(ret.data, obj_a)

        # Progress the simulation by another 'dt' seconds.
        sim.compute([objID], dt, maxsteps)
        ret = sim.getRigidBodyData(objID)
        assert ret.ok

        # The object must have accelerated and reached the linear velocity
        #   v = a * t                  (1)
        # where the acceleration $a$ follows from
        #   F = m * a --> a = F / m    (2)
        # Substitue (2) into (1) to obtain
        #   v = t * F / m
        # or in terms of the inverse mass:
        #   v = t * F * imass
        assert np.allclose(ret.data.vLin, dt * force * 1, atol=1E-2)

    def test_compute_invalid(self):
        """
        Call 'compute' method for non-existing object IDs.
        """
        # Constants and parameters for this test.
        objID = '10'
        dt, maxsteps = 1.0, 60

        # Create an object and overwrite the CShape data to obtain a sphere.
        obj_a = getRigidBody()

        # Instantiate Bullet engine.
        sim = azrael.bullet_api.PyBulletDynamicsWorld(1)

        # Call 'compute' on non-existing object.
        assert not sim.compute([objID], dt, maxsteps).ok

        # Send object to Bullet and progress the simulation by one second.
        # The objects must not move because no forces are at play.
        sim.setRigidBodyData(objID, obj_a)
        assert sim.compute([objID], dt, maxsteps).ok
        ret = sim.getRigidBodyData(objID)
        assert ret.ok and self.isBulletRbsEqual(ret.data, obj_a)

        # Call 'compute' again with one (in)valid object.
        assert not sim.compute([objID, 100], dt, maxsteps).ok
        assert not sim.compute([100, objID], dt, maxsteps).ok

    def test_apply_force_and_torque(self):
        """
        Create object, send it to Bullet, apply a force, progress the
        simulation, and verify the object moved correctly.
        """
        # Constants and parameters for this test.
        objID = '10'
        force = np.array([0, 0, 1], np.float64)
        torque = np.array([0, 0, 1], np.float64)
        dt, maxsteps = 1.0, 60

        # Create a spherical object. Adjust the mass so that the sphere's
        # inertia is roughly unity.
        cshapes = {'foo': getCSSphere()}
        obj_a = getRigidBody(cshapes=cshapes, imass=2 / 5)

        # Instantiate Bullet engine.
        sim = azrael.bullet_api.PyBulletDynamicsWorld(1)

        # Send object to Bullet and progress the simulation by one second.
        # The objects must not move because no forces are at play.
        sim.setRigidBodyData(objID, obj_a)
        sim.compute([objID], dt, maxsteps)
        ret = sim.getRigidBodyData(objID)
        assert ret.ok and self.isBulletRbsEqual(ret.data, obj_a)

        # Now apply a central force of one Newton in z-direction and a torque
        # of two NewtonMeters.
        sim.applyForceAndTorque(objID, force, torque)

        # Nothing must have happened because the simulation has not progressed.
        ret = sim.getRigidBodyData(objID)
        assert ret.ok and self.isBulletRbsEqual(ret.data, obj_a)

        # Progress the simulation for another second.
        sim.compute([objID], dt, maxsteps)
        ret = sim.getRigidBodyData(objID)
        assert ret.ok

        # The object must have accelerated to the linear velocity
        #   v = a * t                  (1)
        # where the acceleration $a$ follows from
        #   F = m * a --> a = F / m    (2)
        # Substitue (2) into (1) to obtain
        #   v = t * F / m
        # or in terms of the inverse mass:
        #   v = t * F * imass
        assert np.allclose(ret.data.vLin, dt * force * (2 / 5), atol=1E-2)

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
        assert np.allclose(ret.data.vRot, dt * torque * 1, atol=1E-2)

    def test_remove_object(self):
        """
        Remove an object from the Bullet cache.
        """
        aid = '0'

        # Create a spherical object.
        obj_a = getRigidBody()

        # Instantiate Bullet engine.
        sim = azrael.bullet_api.PyBulletDynamicsWorld(1)

        # Request an invalid object ID.
        ret = sim.getRigidBodyData(aid)
        assert not ret.ok

        # Send object to Bullet and request it back.
        sim.setRigidBodyData(aid, obj_a)
        ret = sim.getRigidBodyData(aid)
        assert ret.ok and self.isBulletRbsEqual(ret.data, obj_a)

        # Delete the object. The attempt to request it afterwards must fail.
        assert sim.removeRigidBody([aid]).ok
        assert not sim.getRigidBodyData(aid).ok

    def test_modify_mass(self):
        """
        Create two identical spheres, double the mass of one, and apply the
        same force to both. The heavier sphere must have moved only half as
        far.
        """
        # Constants and parameters for this test.
        objID_a, objID_b = '10', '20'
        pos_a = [+5, 0, 0]
        pos_b = [-5, 0, 0]
        force = np.array([0, 1, 0], np.float64)
        torque = np.array([0, 0, 0], np.float64)
        cshapes = {'foo': getCSSphere()}

        # Create two identical spheres, one left, one right (x-axis).
        obj_a = getRigidBody(position=pos_a, cshapes=cshapes, imass=1)
        obj_b = getRigidBody(position=pos_b, cshapes=cshapes, imass=1)
        del pos_a, pos_b, cshapes

        # Instantiate Bullet engine.
        sim = azrael.bullet_api.PyBulletDynamicsWorld(1)

        # Send object to Bullet and progress the simulation by one second.
        # The objects must not move because no forces are at play.
        sim.setRigidBodyData(objID_a, obj_a)
        sim.setRigidBodyData(objID_b, obj_b)

        # Progress the simulation for one second. Nothing must happen.
        sim.compute([objID_a, objID_b], 1.0, 60)

        # Update the mass of the second object.
        obj_b = obj_b._replace(imass=0.5 * obj_b.imass)
        sim.setRigidBodyData(objID_b, obj_b)

        # Apply the same central force that pulls both spheres forward
        # (y-axis).
        sim.applyForceAndTorque(objID_a, force, torque)
        sim.applyForceAndTorque(objID_b, force, torque)

        # Progress the simulation for another second.
        sim.compute([objID_a, objID_b], 1.0, 60)

        # The lighter sphere must have moved pretty exactly twice as far in
        # y-direction.
        ret_a = sim.getRigidBodyData(objID_a)
        assert ret_a.ok
        ret_b = sim.getRigidBodyData(objID_b)
        assert ret_b.ok
        assert abs(ret_a.data.position[1] - 2 * ret_b.data.position[1]) < 1E-5

    def test_modify_size(self):
        """
        Change the size of the collision shape. This is more intricate than
        changing the mass (see previous test) because this time the entire
        collision shape must be swapped out underneath.

        To test this we create two spheres that do not touch. Nothing must
        therefore happen during a physics update. Then we enlarge one sphere
        until it touches the other. This time Bullet must pick up on the
        interpenetration and modify the sphere's position somehow (we do not
        really care how).
        """
        # Constants and parameters for this test.
        objID_a, objID_b = '10', '20'
        pos_a = [0, 0, 0]
        pos_b = [3, 0, 0]

        # Create two identical spheres. Place one left and one right (x-axis).
        radius = 2
        cs_a = {'csfoo': getCSSphere(radius=radius)}
        cs_b = {'csbar': getCSSphere(radius=radius)}
        obj_a = getRigidBody(position=pos_a, cshapes=cs_a)
        obj_b = getRigidBody(position=pos_b, cshapes=cs_b)
        del cs_a, cs_b, pos_a, pos_b

        # Instantiate Bullet engine.
        sim = azrael.bullet_api.PyBulletDynamicsWorld(1)

        # Send objects to Bullet and progress the simulation. Nothing must
        # happen because the bodies do not touch and no forces are active.
        sim.setRigidBodyData(objID_a, obj_a)
        sim.setRigidBodyData(objID_b, obj_b)
        sim.compute([objID_a, objID_b], 1.0, 60)

        # Request the object back and inspect the collision shapes.
        ret_a = sim.getRigidBodyData(objID_a)
        ret_b = sim.getRigidBodyData(objID_b)
        assert ret_a.ok and ret_b.ok
        assert list(ret_a.data.cshapes.keys()) == ['csfoo']
        assert list(ret_b.data.cshapes.keys()) == ['csbar']
        tmp_cs = sim.rigidBodies[objID_a].getCollisionShape()
        assert tmp_cs.getChildShape(0).getRadius() == radius
        tmp_cs = sim.rigidBodies[objID_b].getCollisionShape()
        assert tmp_cs.getChildShape(0).getRadius() == radius

        # Enlarge the second object until it overlaps with the first.
        obj_b = obj_b._replace(scale=2.5)
        sim.setRigidBodyData(objID_b, obj_b)
        ret = sim.getRigidBodyData(objID_b)
        assert ret.ok
        tmp_cs = sim.rigidBodies[objID_b].getCollisionShape()
        assert tmp_cs.getChildShape(0).getRadius() == 2.5 * radius

        # Step the simulation. This ensures that Bullet accesses each
        # object without segfaulting despite swapping out C-pointers
        # underneath the hood.
        sim.compute([objID_a, objID_b], 1.0, 60)

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
        objID_a, objID_b = '10', '20'
        pos_a = [-0.8, -0.8, 0]
        pos_b = [0.8, 0.8, 0]
        p, q = (0, 0, 0), (0, 0, 0, 1)
        cshape_box = {'csbox': getCSBox(p, q)}
        cshape_sph = {'cssphere': getCSSphere(p, q)}
        del p, q

        # Create two identical unit spheres at different positions.
        obj_a = getRigidBody(position=pos_a, cshapes=cshape_sph)
        obj_b = getRigidBody(position=pos_b, cshapes=cshape_sph)

        # Instantiate Bullet engine.
        sim = azrael.bullet_api.PyBulletDynamicsWorld(1)

        # Send objects to Bullet and progress the simulation. The sole point of
        # progressing the simulation is to make sure Bullet actually accesses
        # the objects; we do not actually care if/how the objects moved.
        sim.setRigidBodyData(objID_a, obj_a)
        sim.setRigidBodyData(objID_b, obj_b)
        sim.compute([objID_a, objID_b], 1.0, 60)

        # Verify the collision shapes are as expected.
        ret = sim.getRigidBodyData(objID_a)
        assert ret.ok
        assert ret.data.cshapes == cshape_sph
        ret = sim.getRigidBodyData(objID_b)
        assert ret.ok
        assert ret.data.cshapes == cshape_sph

        # Change both collision shape to unit cubes. Then step the simulation
        # again to ensure Bullet accesses each object and nothing bad happens
        # (eg a segfault).
        obj_a = getRigidBody(position=pos_a, cshapes=cshape_box)
        obj_b = getRigidBody(position=pos_b, cshapes=cshape_box)
        sim.setRigidBodyData(objID_a, obj_a)
        sim.setRigidBodyData(objID_b, obj_b)
        sim.compute([objID_a, objID_b], 1.0, 60)

        # Verify the collision shapes have been updated to boxes.
        ret = sim.getRigidBodyData(objID_a)
        assert ret.ok
        assert ret.data.cshapes == cshape_box
        ret = sim.getRigidBodyData(objID_b)
        assert ret.ok
        assert ret.data.cshapes == cshape_box

    def test_specify_P2P_constraint(self):
        """
        Use a P2P constraint to test the various methods to add- and remove
        constraints.
        """
        # Instantiate Bullet engine.
        sim = azrael.bullet_api.PyBulletDynamicsWorld(1)

        # Create identical unit spheres at x=+/-1.
        id_a, id_b = '10', '20'
        pos_a = (-1, 0, 0)
        pos_b = (1, 0, 0)
        obj_a = getRigidBody(position=pos_a, cshapes={'cssphere': getCSSphere()})
        obj_b = getRigidBody(position=pos_b, cshapes={'cssphere': getCSSphere()})

        # Load the objects into the physics engine.
        sim.setRigidBodyData(id_a, obj_a)
        sim.setRigidBodyData(id_b, obj_b)

        # Compile the constraint.
        pivot_a, pivot_b = pos_b, pos_a
        con = [getP2P(rb_a=id_a, rb_b=id_b, pivot_a=pivot_a, pivot_b=pivot_b)]

        # Load the constraints into the physics engine.
        assert sim.setConstraints(con).ok

        # Step the simulation. Both objects must stay put.
        sim.compute([id_a, id_b], 1.0, 60)
        ret_a = sim.getRigidBodyData(id_a)
        ret_b = sim.getRigidBodyData(id_b)
        assert ret_a.ok and ret_b.ok
        assert np.allclose(ret_a.data.position, pos_a)
        assert np.allclose(ret_b.data.position, pos_b)

        # Apply a force that will pull the left object further to the left.
        sim.applyForceAndTorque(id_a, (-10, 0, 0), (0, 0, 0))

        # Step the simulation. Both objects must have moved (almost) exactly
        # the same amount "delta".
        sim.compute([id_a, id_b], 1.0, 60)
        ret_a = sim.getRigidBodyData(id_a)
        ret_b = sim.getRigidBodyData(id_b)
        assert ret_a.ok and ret_b.ok
        delta_a = np.array(ret_a.data.position) - np.array(pos_a)
        delta_b = np.array(ret_b.data.position) - np.array(pos_b)
        assert np.allclose(delta_a, delta_b)
        assert delta_a[1] == delta_a[2] == 0

        # Remove all constraints (do it twice to test the case when there are
        # no constraints).
        assert sim.clearAllConstraints().ok
        assert sim.clearAllConstraints().ok

        # Overwrite the objects with the default data (ie put them back into
        # the original position and set their velocity to zero).
        sim.setRigidBodyData(id_a, obj_a)
        sim.setRigidBodyData(id_b, obj_b)
        sim.compute([id_a, id_b], 1.0, 60)
        ret_a = sim.getRigidBodyData(id_a)
        ret_b = sim.getRigidBodyData(id_b)
        assert ret_a.ok and ret_b.ok
        assert np.allclose(ret_a.data.position, pos_a)
        assert np.allclose(ret_b.data.position, pos_b)

        # Apply a force that will pull the left object further to the left.
        # However, now *only* the left one must move because there are not
        # constraint anymore.
        sim.applyForceAndTorque(id_a, (-10, 0, 0), (0, 0, 0))
        sim.compute([id_a, id_b], 1.0, 60)
        ret_a = sim.getRigidBodyData(id_a)
        ret_b = sim.getRigidBodyData(id_b)
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
        id_a, id_b = '10', '20'
        pos_a = (-5, 0, 0)
        pos_b = (5, 0, 0)
        obj_a = getRigidBody(position=pos_a, cshapes={'cssphere': getCSSphere()})
        obj_b = getRigidBody(position=pos_b, cshapes={'cssphere': getCSSphere()})

        # Load the objects into the physics engine.
        sim.setRigidBodyData(id_a, obj_a)
        sim.setRigidBodyData(id_b, obj_b)

        # Compile the 6DOF constraint.
        constraints = [get6DofSpring2(rb_a=id_a, rb_b=id_b)]

        # Step the simulation. Nothing must happen because no forces or
        # constraints act upon the objects.
        sim.compute([id_a, id_b], 1.0, 60)
        ret_a = sim.getRigidBodyData(id_a)
        ret_b = sim.getRigidBodyData(id_b)
        assert ret_a.ok and ret_b.ok
        assert np.allclose(ret_a.data.position, pos_a)
        assert np.allclose(ret_b.data.position, pos_b)

        # Load the constraints into the physics engine and step the simulation
        # again. This time the objects must move closer together.
        assert sim.setConstraints(constraints).ok

        # Step the simulation --> the objects must move closer together.
        sim.compute([id_a, id_b], 1.0, 60)
        ret_a = sim.getRigidBodyData(id_a)
        ret_b = sim.getRigidBodyData(id_b)
        assert ret_a.ok and ret_b.ok
        assert ret_a.data.position[0] > pos_a[0]
        assert ret_b.data.position[0] < pos_b[0]

    def test_specify_constraints_invalid(self):
        """
        Call the constraint- related methods with invalid data and verify that
        nothing breaks.
        """
        # Instantiate Bullet engine.
        sim = azrael.bullet_api.PyBulletDynamicsWorld(1)

        # Create to spheres.
        id_a, id_b = '10', '20'
        obj_a = getRigidBody(cshapes={'cssphere': getCSSphere()})
        obj_b = getRigidBody(cshapes={'cssphere': getCSSphere()})

        # An empty list is valid, albeit nothing will happen.
        assert sim.setConstraints([]).ok

        # Invalid constraint types.
        assert not sim.setConstraints([1]).ok

        # Compile the constraint.
        pivot_a, pivot_b = (0, 0, 0), (1, 1, 1)
        con = [getP2P(rb_a=id_a, rb_b=id_b, pivot_a=pivot_a, pivot_b=pivot_b)]

        # Constraint is valid but the objects do not exist.
        assert not sim.setConstraints([con]).ok

        # Add one sphere to the world.
        sim.setRigidBodyData(id_a, obj_a)

        # Load the constraints into the physics engine.
        assert not sim.setConstraints(con).ok

        # Load the second sphere and apply the constraint. This time it must
        # have worked.
        sim.setRigidBodyData(id_b, obj_b)
        assert sim.setConstraints(con).ok

        # Clear all constraints
        assert sim.clearAllConstraints().ok

    def test_box_on_plane(self):
        """
        Create a simulation with gravity. Place a box above a plane and verify
        that after a long time the box will have come to rest on the infinitely
        large plane.
        """
        aid_1, aid_2 = '1', '2'

        # Instantiate Bullet engine and activate gravity.
        sim = azrael.bullet_api.PyBulletDynamicsWorld(1)
        sim.setGravity((0, 0, -10))

        # Create a box above a static plane. The ground plane is at z=-1.
        cs_plane = getCSPlane(normal=(0, 0, 1), ofs=-1)
        cs_box = getCSBox()
        b_plane = getRigidBody(imass=0, cshapes={'csplane': cs_plane})
        b_box = getRigidBody(position=(0, 0, 5), cshapes={'csbox': cs_box})
        assert b_box is not None
        assert b_plane is not None

        # Add the objects to the simulation and verify their positions.
        sim.setRigidBodyData(aid_1, b_plane)
        sim.setRigidBodyData(aid_2, b_box)
        ret_plane = sim.getRigidBodyData(aid_1)
        ret_box = sim.getRigidBodyData(aid_2)
        assert (ret_plane.ok is True) and (ret_box.ok is True)
        assert ret_plane.data.position[2] == 0
        assert ret_box.data.position[2] == 5

        # Step the simulation often enough for the box to fall down and come to
        # rest on the surface.
        dt, maxsteps = 1.0, 60
        for ii in range(10):
            sim.compute([aid_1, aid_2], dt, maxsteps)

        # Verify that the plane has not moved (because it is static) and that
        # the box has come to rest atop. The position of the box rigid body
        # must be approximately zero, because the plane is at position z=-1,
        # and the half length of the box is 1 Meters.
        ret_plane = sim.getRigidBodyData(aid_1)
        ret_box = sim.getRigidBodyData(aid_2)
        assert (ret_plane.ok is True) and (ret_box.ok is True)
        assert ret_plane.data.position[2] == 0
        assert abs(ret_box.data.position[2]) < 1E-5

    def test_cshape_with_offset(self):
        """
        Same as above except that the collision shape has a different position
        relative to the rigid body.

        This test is to establish that the relative positions of the collision
        shapes are correctly passed to Bullet and taken into account in a
        simulation.

        Setup: place a box above a plane and verify that after a long time the
        box will have come to rest on the infinitely large plane.
        """
        aid_1, aid_2 = '1', '2'

        # Instantiate Bullet engine and activate gravity.
        sim = azrael.bullet_api.PyBulletDynamicsWorld(1)
        sim.setGravity((0, 0, -10))

        # Create a box above a static plane. The ground plane is at z=-1. The
        # rigid body for the box is initially at z = 5, however, the collision
        # shape for that rigid body is actually z = 5 + ofs_z.
        ofs_z = 10
        cs_plane = getCSPlane(normal=(0, 0, 1), ofs=-1)
        cs_box = getCSBox(pos=(0, 0, ofs_z))
        b_plane = getRigidBody(imass=0, cshapes={'csplane': cs_plane})
        b_box = getRigidBody(position=(0, 0, 5), cshapes={'csbox': cs_box})
        assert b_box is not None
        assert b_plane is not None

        # Add the objects to the simulation and verify their positions.
        sim.setRigidBodyData(aid_1, b_plane)
        sim.setRigidBodyData(aid_2, b_box)
        ret_plane = sim.getRigidBodyData(aid_1)
        ret_box = sim.getRigidBodyData(aid_2)
        assert (ret_plane.ok is True) and (ret_box.ok is True)
        assert ret_plane.data.position[2] == 0
        assert ret_box.data.position[2] == 5

        # Step the simulation often enough for the box to fall down and come to
        # rest on the surface.
        dt, maxsteps = 1.0, 60
        for ii in range(10):
            sim.compute([aid_1, aid_2], dt, maxsteps)

        # Verify that the plane has not moved (because it is static). If the
        # position of the box' collision shape were at the origin of the body,
        # then the body's position should be approximately zero. However, since
        # the collisions shape is at 'ofs_z' higher, the final resting position
        # of the body must be 'ofs_z' lower, ie rb_position + ofs_z must now be
        # approximately zero.
        ret_plane = sim.getRigidBodyData(aid_1)
        ret_box = sim.getRigidBodyData(aid_2)
        assert (ret_plane.ok is True) and (ret_box.ok is True)
        assert ret_plane.data.position[2] == 0
        assert abs(ret_box.data.position[2] + ofs_z) < 1E-3
