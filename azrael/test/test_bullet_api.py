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
import azutils
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

        # Create a test object.
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
        imass = 2
        force = np.array([1, 2, 3], np.float64)
        dt, maxsteps = 1.0, 60

        # Create an object and overwrite the CShape data to obtain a sphere.
        obj_a = getRigidBody(imass=imass)

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
        applyForceFun(objID, force, [0, 0, 0])

        # Nothing must have happened because the simulation has not progressed.
        ret = sim.getRigidBodyData(objID)
        assert ret.ok and self.isBulletRbsEqual(ret.data, obj_a)

        # Progress the simulation by another 'dt' seconds.
        sim.compute([objID], dt, maxsteps)
        ret = sim.getRigidBodyData(objID)
        assert ret.ok

        # The object must have accelerated to the linear velocity
        #   v = a * t                  (1)
        # where the acceleration $a$ follows from
        #   F = m * a --> a = F / m    (2)
        # Substitute (2) into (1) to obtain
        #   v = t * F / m
        # or in terms of the inverse mass:
        #   v = t * F * imass
        assert np.allclose(ret.data.vLin, dt * force * imass, atol=1E-1)

    def test_apply_torque_diagonal(self):
        """
        Create a body with neutral principal axis (ie aligned with the world
        coordinate system). Then apply a torque vector. The object must spin at
        the respective velocities in each direction.
        """
        # Constants and parameters for this test.
        objID = '10'
        inertia = [1, 2, 3]
        torque = np.array([2, 3, 1])

        # Bullet simulation step. This *must* happen in a *single* step to
        # produce the anticipated outcome. The reason is subtle: Bullet always
        # applies the torque in world coordinates yet the body progressively
        # rotate in each sub-step. Unless the moments of inertia are all equal
        # this means the induced rotation will change its axis a bit at each
        # step.
        dt, maxsteps = 1.0, 1

        # Create an object and overwrite the CShape data to obtain a sphere.
        obj_a = getRigidBody(inertia=inertia)

        # Instantiate Bullet engine.
        sim = azrael.bullet_api.PyBulletDynamicsWorld(1)

        # Send object to Bullet and progress the simulation by one second.
        # The objects must not move because no forces are at play.
        sim.setRigidBodyData(objID, obj_a)
        sim.compute([objID], dt, maxsteps)
        ret = sim.getRigidBodyData(objID)
        assert ret.ok and self.isBulletRbsEqual(ret.data, obj_a)

        # Apply the torque.
        sim.applyForceAndTorque(objID, [0, 0, 0], torque)

        # Nothing must have happened because the simulation has not progressed.
        ret = sim.getRigidBodyData(objID)
        assert ret.ok and self.isBulletRbsEqual(ret.data, obj_a)

        # Progress the simulation by another 'dt' seconds.
        sim.compute([objID], dt, maxsteps)
        ret = sim.getRigidBodyData(objID)
        assert ret.ok

        # The object must have accelerated to the angular velocity
        #   v = a * t                  (1)
        # The (angular) acceleration $a$ follows from
        #   T = I * a --> a = T / I    (2)
        # based on (T)orque and (I)nertia. In this test, the torque and
        # principal axis coincide and T and I are thus diagonal (the "division"
        # of matrices above is thus justified in this special case). Now
        # substitute (2) into (1) to obtain the angular velocity v as
        #   v = t * T / I
        assert np.allclose(ret.data.vRot, dt * torque / inertia, atol=1E-1)

    def test_apply_torque_not_diagonal(self):
        """
        Verify the angular velocity for a general torque vector and a body with
        a dense 3x3 inertia matrix (ie all 9 elements are nonzero).

        The setup is annoyingly fickle. For more information about why this
        test does what it does refer to the docstring of
        'bullet_api._compileCollisionShape'.

        We will use a general 3x3 inertia tensor and apply a torque. Then we
        will use Newton's second law and the 3x3 Inertia tensor to predict the
        angular velocity. If Azrael set up the bodies correctly then this must
        match the values returned by Bullet.

        There is another catch: specifying the 3x3 Inertia tensor is easy, but
        expressing its principal axis (ie. the rotation defined by its
        eigenvectors) is not always (numerically) straightforward. To avoid
        this problem I will therfore start with a general Quaternion, convert
        it to a rotation matrix (always stable), and then use this as the
        eigenspace of the Inertia matrix. This still allows me to construct a
        general inertia matrix, specify the diagonal inertias directly, and
        have the principal axis Quaternion handy for Bullet.

        In case you wonder: no, none of this is self evident. At least we will
        not have to manually compute the eigenvectors.
        """
        # Constants and parameters for this test.
        objID = '10'

        # Specify the torque and moments of inertia.
        torque = [1, -2, 3]
        inertia_diag = [1, 2, 3]

        # Construct an inertia matrix Step 1/2: start with a general
        # Quaternion, convert it to a rotation matrix, and then pretend this is
        # the eigenspace of the inertia tensor.
        paxis = [1, -2, 3, 0]
        q = azutils.Quaternion(*paxis).normalise()
        U = np.around(q.toMatrix()[:3, :3], 3)

        # Construct an inertia matrix Step 2/2: given the orthonormal matrix U
        # and the moments of inertia, we can can compute the total inertia
        # matrix as I = U * diag(inertia_diag) * U^{-1]
        inertia_mat = U.dot(np.diag(inertia_diag).dot(U.T))
        del q, U

        # Let's be certain that our inertia matrix is really dense, ie does not
        # contain any zeros.
        assert np.amin(np.abs(inertia_mat)) > 0.1

        # Specify the Bullet simulation step. Ther *must* be only a *single*
        # step. The reason is subtle: Bullet always applies the torque in world
        # coordinates. If it splits up the physis update into several sub-steps
        # then the body will progressively rotate yet Bullet does not rotate
        # the torque with it. Unless the moments of inertia are symmetric this
        # will induce more and more "wobble" in each step. If Bullet is not
        # allowed to compute sub-steps then only one update is applied (at the
        # expense of numerical accuracy for which we do not care in this test).
        dt, maxsteps = 1.0, 1

        # Create an object and overwrite the CShape data to obtain a sphere.
        obj_a = getRigidBody(inertia=inertia_diag, paxis=paxis)

        # Instantiate Bullet engine, add the body, and apply the torque.
        sim = azrael.bullet_api.PyBulletDynamicsWorld(1)
        sim.setRigidBodyData(objID, obj_a)
        sim.applyForceAndTorque(objID, [0, 0, 0], torque)

        # Progress the simulation by 'dt' seconds.
        sim.compute([objID], dt, maxsteps)
        ret = sim.getRigidBodyData(objID)
        assert ret.ok

        # Newton's second law relates the (angular) (a)cceleration (3-Vec) to
        # the (I)nertia matrix (3x3) and (T)orque (3-Vec):
        #
        #   T = I * a    -->     a = I^{-1} * T
        #
        # Integrating both sides by $t$ yields the angular velocity:
        #
        #   \int{a dt} = \int{I^{-1} * T dt}
        #            v = I^{-1} * T * t
        #
        # This velocity must match the one returned by Bullet if all the
        # collisions were aligned properly.
        acceleration = np.linalg.inv(inertia_mat).dot(torque)
        assert np.allclose(ret.data.vRot, dt * acceleration, atol=1E-1)

    @pytest.mark.parametrize('forceFun', ['applyForce', 'applyForceAndTorque'])
    def test_apply_force_on_noncentred_body(self, forceFun):
        """
        Create two non-touching bodies. The centre of mass of the first
        coincides with its position. The center of mass for the second has an
        offset in y-direction.

        Then apply a force in z-direction at position of the rigid body and
        query them via the `bullet_api`. The first object must have moved
        *only* along the z-direction (we do not really care how much here). The
        second object must have moved only a bit in z *and* negative y
        direction (because it starts to rotate around the centre of mass which
        is at a negative y-position).
        """
        # Constants and parameters for this test.
        id_a, id_b = '10', '11'
        force = [0, 0, 1]
        pos_a, pos_b = [-5, 0, 0], [5, 0, 0]
        dt, maxsteps = 1.0, 60

        # Create two bodies. They do not touch and have different centres of
        # mass.
        obj_a = getRigidBody(position=pos_a, com=[0, 0, 0])
        obj_b = getRigidBody(position=pos_b, com=[0, -1, 0])

        # Instantiate a Bullet engine, load the objects, and apply the same
        # force to both with respect to the position in Azrael (not with
        # respect to their centre of mass!).
        sim = azrael.bullet_api.PyBulletDynamicsWorld(1)
        sim.setRigidBodyData(id_a, obj_a)
        sim.setRigidBodyData(id_b, obj_b)
        sim.applyForce(id_a, force, [0, 0, 0])
        sim.applyForce(id_b, force, [0, 0, 0])

        # Progress the simulation and query the objects.
        sim.compute([id_a, id_b], dt, maxsteps)
        ret_a = sim.getRigidBodyData(id_a)
        ret_b = sim.getRigidBodyData(id_b)
        assert ret_a.ok and ret_b.ok

        # Verify that the centred body only moved in z-direction. Then verify
        # that the second object moved along the positive 'z' and negative 'y'
        # axis because it must have started to spin.
        rpos_a = ret_a.data.position
        rpos_b = ret_b.data.position
        assert (rpos_a[0] == pos_a[0]) and (rpos_a[1] == pos_a[1])
        assert rpos_a[2] > 0.1
        assert rpos_b[0] == pos_b[0]
        assert (rpos_b[1] < 0.1) and (rpos_b[2] > 0.1)

    @pytest.mark.parametrize('forceFun', ['applyForce', 'applyForceAndTorque'])
    def test_apply_angular_velocity_to_noncentred_body(self, forceFun):
        """
        Create a body at position (0, 0, 0). Its centre of mass is at (1, 0, 0). The
        apply an angular velocity of pi rad/s along the z-axis and step the
        simulation for one second. This must have rotated the body by 180
        degrees, which means the body's position must have gone from (0, 0, 0)
        to (2, 0, 0).
        """
        # Constants and parameters for this test.
        id_a = '10'

        # Create a rigid body that spins with pi rad/s around the z-axis.
        pi = float(np.pi)
        pos = (1, 2, 3)
        com = (4, 5, 0)
        obj_a = getRigidBody(position=pos, com=com, velocityRot=(0, 0, pi))

        # Instantiate a Bullet engine and load the object.
        sim = azrael.bullet_api.PyBulletDynamicsWorld(1)
        sim.setRigidBodyData(id_a, obj_a)

        # Query the object back immediately and verify that it is intact
        # (despite the centre of mass not being zero in this test).
        ret_a = sim.getRigidBodyData(id_a)
        assert self.isBulletRbsEqual(ret_a.data, obj_a)

        # Progress the simulation by one second. Use many small steps to ensure
        # the numerical errors stay small and the object does indeed rotate
        # ~180 degrees around the z-axis (recall that we specified an angular
        # velocity of ~Pi rad/s).
        sim.compute([id_a], 1, 60)

        # Query the object back.
        ret_a = sim.getRigidBodyData(id_a)
        assert ret_a.ok

        # Extract the position. The object position must have rotated 180
        # degrees around the centre of mass (around the z-axis).
        assert np.allclose(2 * np.array(com) + pos, ret_a.data.position, 0.1)

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
        changing the mass in test_modify_mass. The reason is that, internally,
        the entire collision shape must be replaced.

        For this test we create two non-touching spheres. Nothing must
        therefore happen during a physics update. Then we enlarge one sphere
        to ensure they interpenetrate. This time Bullet must pick up on the
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

        # Request the object back and inspect the radius of the spherical
        # collision shapes.
        ret_a = sim.getRigidBodyData(objID_a)
        ret_b = sim.getRigidBodyData(objID_b)
        assert ret_a.ok and ret_b.ok
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
        Replace the entire collision shape.

        Place two spheres diagonally along the x/y axis. Their distance is such
        that they do not touch, but only just. Then replace them with boxes and
        step the simulation again. Ideally, nothing happens, in particular no
        segfault because we swapped out C-pointers under the hood.
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

        # Verify the collision shapes are spheres.
        ret_a = sim.getRigidBodyData(objID_a)
        ret_b = sim.getRigidBodyData(objID_b)
        assert ret_a.ok and ret_b.ok
        cs_a = sim.rigidBodies[objID_a].getCollisionShape().getChildShape(0)
        cs_b = sim.rigidBodies[objID_a].getCollisionShape().getChildShape(0)
        assert cs_a.getName() == cs_b.getName() == b'SPHERE'
        del ret_a, ret_b, cs_a, cs_b

        # Replace the collision spheres with collision cubes. Then step the
        # simulation again to ensure Bullet touches the shapes without
        # segfaulting.
        obj_a = getRigidBody(position=pos_a, cshapes=cshape_box)
        obj_b = getRigidBody(position=pos_b, cshapes=cshape_box)
        sim.setRigidBodyData(objID_a, obj_a)
        sim.setRigidBodyData(objID_b, obj_b)
        sim.compute([objID_a, objID_b], 1.0, 60)

        # Verify the collision shapes are now boxes.
        ret_a = sim.getRigidBodyData(objID_a)
        ret_b = sim.getRigidBodyData(objID_b)
        assert ret_a.ok and ret_b.ok
        cs_a = sim.rigidBodies[objID_a].getCollisionShape().getChildShape(0)
        cs_b = sim.rigidBodies[objID_a].getCollisionShape().getChildShape(0)
        assert cs_a.getName() == cs_b.getName() == b'Box'
        del ret_a, ret_b, cs_a, cs_b

    def test_needNewCollisionShapes(self):
        """
        Verify the conditions under which 'bullet_api' must throw out its
        current compound shape and compile a new one from scratch.

        Specifically, create a new compound shape only if:
          * type of at least one collision shape changed,
          * size of at least one collision shape changed,
          * centre of mass position changed,
          * principal axs of inertia changed.

        To clarify, there is no need to recompile the compound shape if only
        mass, moments of inertia (without a change in principal axis),
        position, rotation, etc changed.
        """
        id_a = '1'
        p, q = (0, 0, 0), (0, 0, 0, 1)
        csdefault = {'foo': getCSSphere(p, q, radius=1)}

        # Create test body with spherical collision shape.
        obj_a = getRigidBody(cshapes=csdefault)
        sim = azrael.bullet_api.PyBulletDynamicsWorld(1)
        sim.setRigidBodyData(id_a, obj_a)

        # Same object: do not rebuild.
        obj_new = getRigidBody(cshapes=csdefault)
        assert sim.needNewCollisionShape(id_a, obj_new) is False

        # Different position and rotation: do not rebuild.
        obj_new = getRigidBody(
            position=[0, 1, 2],
            rotation=[0, 1, 0, 1],
            cshapes=csdefault,
        )
        assert sim.needNewCollisionShape(id_a, obj_new) is False

        # New collision shape name: rebuild CS (Azrael cannot know if the old
        # one was just renamed or if it was removed and replaced by a new one
        # that just happens to have the same properties).
        obj_new = getRigidBody(cshapes={'bar': getCSSphere(p, q, radius=1)})
        assert sim.needNewCollisionShape(id_a, obj_new) is True

        # New collision shape parameter (radius):
        obj_new = getRigidBody(cshapes={'foo': getCSSphere(p, q, radius=2)})
        assert sim.needNewCollisionShape(id_a, obj_new) is True

        # Changed collision shape type (box):
        obj_new = getRigidBody(cshapes={'foo': getCSBox(p, q)})
        assert sim.needNewCollisionShape(id_a, obj_new) is True

        # Additional collision shape: rebuild.
        obj_new = getRigidBody(
            cshapes={
                'foo': getCSSphere(p, q),
                'bar': getCSBox(p, q),
            }
        )
        assert sim.needNewCollisionShape(id_a, obj_new) is True

        # New center of mass: rebuild.
        obj_new = getRigidBody(cshapes=csdefault, com=[1, 2, 3])
        assert sim.needNewCollisionShape(id_a, obj_new) is True

        # New principal axis of inertia: rebuild.
        obj_new = getRigidBody(cshapes=csdefault, paxis=[1, 2, 3, 4])
        assert sim.needNewCollisionShape(id_a, obj_new) is True

        # New inertia (but same principal axis): do not rebuild.
        obj_new = getRigidBody(cshapes=csdefault, inertia=[1, 2, 3])
        assert sim.needNewCollisionShape(id_a, obj_new) is False

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

    @pytest.mark.parametrize('num_sub_steps', [1, 60])
    def test_get_contacts(self, num_sub_steps):
        """
        Verify that every call to 'compute' also creates collision contacts.

        This test runs twice, once with a single sub-step and once with
        multiple sub-steps. The reason is due to a changed collision callback
        in Bullet. The original method could only gather contacts from the last
        sub-step, which means the number of sub-steps had to be set to 1. Now
        there is a better version which is independent of the number of
        sub-steps. However, just to be sure, I am testing both here.
        """
        # Create a test object.
        cshapes = {'1': getCSSphere((0, 0, 0), (0, 0, 0, 1))}
        obj_a = getRigidBody(
            scale=1,
            imass=1,
            cshapes=cshapes,
            restitution=1,
            rotation=(0, 1, 0, 0),
            position=(0, 0, 0),
            velocityLin=(0, 0, 0),
            velocityRot=(0, 0, 0)
        )

        # Instantiate Bullet engine.
        sim = azrael.bullet_api.PyBulletDynamicsWorld(1)

        # Verify there are no collision contacts, and that a simulation for
        # unknown objects does not produce any.
        assert sim.getLastContacts() == (True, None, [])
        assert not sim.compute(['0'], 1, num_sub_steps).ok
        assert sim.getLastContacts() == (True, None, [])

        # Add the object and verify again that there are still no collisions (a
        # single object cannot collide with anything).
        sim.setRigidBodyData('0', obj_a)
        assert sim.getLastContacts() == (True, None, [])
        assert sim.compute(['0'], 1, num_sub_steps).ok
        assert sim.getLastContacts() == (True, None, [])

        # Add another body with the same attributes as the first. This ensures
        # they touch and must create a collision *after* the 'compute'
        # method was called.
        sim.setRigidBodyData('1', obj_a)
        assert sim.getLastContacts() == (True, None, [])

        assert sim.compute(['0', '1'], 1, num_sub_steps).ok

        # Query the collision contacts produced by both methods.
        ret = sim.getLastContacts()

        # Verify the returned contacts from both methods.
        assert ret.ok

        # The collision informaiton must be provided in the form (aidA, aidB,
        # [colPosA_0, colPosB_0, colPosA_1, colPosB_2, ...]). In this test
        # exactly one collision must have been created. The next few lines
        # disassemble this result and verify it is correct. We will also verify
        # that all types are native to Python.
        assert len(ret.data) == 1
        data = ret.data[0]

        # Unpack the constituents.
        aidA, aidB, colPositions = data
        assert aidA == '0' and aidB == '1'

        # The collision points must be a list of 3-tuples. There must be
        # exactly two such 3-tuple if we only simulated a single sub-step:
        # one for the collision contact on object A and B, respectively. If we
        # did multiple sub-steps, then Bullet will probably have generated
        # contacts in several sub-steps until it was resolved. How many exactly
        # is difficult to predict however.
        if num_sub_steps == 1:
            assert isinstance(colPositions, list) and len(colPositions) == 2
        else:
            assert isinstance(colPositions, list) and len(colPositions) >= 2
        assert len(colPositions) % 2 == 0
        for colPosA, colPosB in zip(colPositions[0::2], colPositions[1::2]):
            assert isinstance(colPosA, tuple) and len(colPosA) == 3
            assert isinstance(colPosB, tuple) and len(colPosB) == 3

        # The 'compute' method must clear the contacts every time. To test
        # this, call it with an empty list of objects. This must do nothing in
        # terms of physics, but the contacts data must still be erased.
        assert sim.compute([], 1, num_sub_steps).ok
        assert sim.getLastContacts() == (True, None, [])
