# Copyright 2015, Oliver Nagy <olitheolix@gmail.com>
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
import numpy as np
from IPython import embed as ipshell

import azrael.bullet.azBullet
from azrael.bullet.azBullet import Vec3, Quaternion
from azrael.bullet.azBullet import BoxShape, StaticPlaneShape, SphereShape, EmptyShape
from azrael.bullet.azBullet import Transform, MotionState, DefaultMotionState, RigidBody


class TestVector3:
    @classmethod
    def setup_class(cls):
        pass

    @classmethod
    def teardown_class(cls):
        pass

    def test_comparison(self):
        v1 = Vec3(1, -2.5, 3000.1234)
        v2 = Vec3(2, -2.5, 3000.1234)

        # Equality.
        assert v1 == v1
        assert v2 == v2

        # Inequality.
        assert v1 != v2
        assert v2 != v1

        # Equality with a different object that has same values.
        assert v1 == Vec3(1, -2.5, 3000.1234)
        assert v2 == Vec3(2, -2.5, 3000.1234)

    def test_arithmetic(self):
        v1 = Vec3(1, 2, 3)
        v2 = Vec3(.5, .6, .7)

        # Addition.
        assert v1 + v2 == Vec3(1.5, 2.6, 3.7)

        # Subtraction.
        assert v1 - v2 == Vec3(0.5, 1.4, 2.3)

        # Negation.
        assert -v1 == Vec3(-1, -2, -3)


class TestRigidBody:
    @classmethod
    def setup_class(cls):
        pass

    @classmethod
    def teardown_class(cls):
        pass

    def getRB(self, pos=Vec3(0, 0, 0)):
        """
        Return a Rigid Body tuple.

        .. note:: Do not delete the tuple until the end of the test
        because it may lead to memory access violations. The reason is that a
        rigid body requires several indepenent structures that need to remain
        in memory.
        """
        cs = SphereShape(1)
        t = Transform(Quaternion(0, 0, 0, 1), pos)
        ms = DefaultMotionState(t)
        mass = 1
        inertia = Vec3(0, 0, 0)
        b = RigidBody(mass, ms, cs, inertia)
        return b, (cs, ms)

    def test_restitution(self):
        """
        Specify and query "Restitution".
        """
        # Get RigidBody object.
        body, _ = self.getRB()

        # Set restitution coefficient and verify it is correct.
        rest_ref = 2.4
        body.setRestitution(rest_ref)
        rest_out = body.getRestitution()
        assert np.allclose(rest_ref, rest_out, atol=1E-14, rtol=0)

        # Repeat with a different value.
        rest_ref = 5
        body.setRestitution(rest_ref)
        rest_out = body.getRestitution()
        assert rest_ref == rest_out

    def test_linearfactor(self):
        """
        Specify and query the "LinearFactor".

        The linear factor specifies a translational damping factor. A
        value of zero means the object cannot move in that direction at all.
        """
        # Get RigidBody object.
        body, _ = self.getRB()

        # Set the linear factor and verify it is correct.
        lf = Vec3(-1, 2, 2.5)
        body.setLinearFactor(lf)
        rest_out = body.getLinearFactor()
        assert lf == rest_out

        # Repeat with a different value.
        lf = Vec3(10.12345, -2.0, 20000.5)
        body.setLinearFactor(lf)
        rest_out = body.getLinearFactor()
        assert lf == rest_out

    def test_angularfactor(self):
        """
        Specify and query the "AngularFactor".

        The angular factor specifies a angular damping factor. A
        value of zero means the object cannot rotate along that axis.
        """
        # Get RigidBody object.
        body, _ = self.getRB()

        # Set the angular factor and verify it is correct.
        lf = Vec3(-1, 2, 2.5)
        body.setAngularFactor(lf)
        rest_out = body.getAngularFactor()
        assert lf == rest_out

        # Repeat with a different value.
        lf = Vec3(10.12345, -2.0, 20000.5)
        body.setAngularFactor(lf)
        rest_out = body.getAngularFactor()
        assert lf == rest_out

    def test_linearvelocity(self):
        """
        Specify and query the "LinearVelocity".
        """
        # Get RigidBody object.
        body, _ = self.getRB()

        # Set the linear velocity and verify it is correct.
        lf = Vec3(-1, 2, 2.5)
        body.setLinearVelocity(lf)
        rest_out = body.getLinearVelocity()
        assert lf == rest_out

        # Repeat with a different value.
        lf = Vec3(10.12345, -2.0, 20000.5)
        body.setLinearVelocity(lf)
        rest_out = body.getLinearVelocity()
        assert lf == rest_out

    def test_angularvelocity(self):
        """
        Specify and query the "AngularVelocity".
        """
        # Get RigidBody object.
        body, _ = self.getRB()

        # Set the angular velocity and verify it is correct.
        lf = Vec3(-1, 2, 2.5)
        body.setAngularVelocity(lf)
        rest_out = body.getAngularVelocity()
        assert lf == rest_out

        # Repeat with a different value.
        lf = Vec3(10.12345, -2.0, 20000.5)
        body.setAngularVelocity(lf)
        rest_out = body.getAngularVelocity()
        assert lf == rest_out

    def test_sleepingthreshold(self):
        """
        Set/get the {linear,angular} sleeping threshold.
        """
        # Get RigidBody object.
        body, _ = self.getRB()

        # Set the threshold (must both be set at the same time).
        th_lin, th_ang = 1.2, 3.4
        body.setSleepingThresholds(th_lin, th_ang)

        # The thresholds must be queried individually.
        assert body.getLinearSleepingThreshold() == th_lin
        assert body.getAngularSleepingThreshold() == th_ang

        # Repeat with a different value.
        th_lin, th_ang = 10.0, 1000.1234
        body.setSleepingThresholds(th_lin, th_ang)
        assert body.getLinearSleepingThreshold() == th_lin
        assert body.getAngularSleepingThreshold() == th_ang

    def test_applyForces(self):
        """
        Apply and query forces in various ways.
        """
        # Get RigidBody object.
        body, _ = self.getRB()

        # Clear all forces.
        body.clearForces()
        assert body.getTotalForce() == Vec3(0, 0, 0)
        assert body.getTotalTorque() == Vec3(0, 0, 0)

        # Apply central force and verify it was set correctly.
        force = Vec3(1, 2, -3.5)
        body.applyCentralForce(force)
        body.applyTorque(-force)
        assert body.getTotalForce() == force
        assert body.getTotalTorque() == -force

        # Verify that clearForces works.
        body.clearForces()
        assert body.getTotalForce() == Vec3(0, 0, 0)
        assert body.getTotalTorque() == Vec3(0, 0, 0)

        # Apply a non-central force.
        force = Vec3(3.5, -4.12, 5.345)
        pos = Vec3(1, 1, 1)
        body.applyForce(force, pos)
        assert body.getTotalForce() == force
        
        # Add more force and torque.
        inc = Vec3(1, 2, 3)
        body.applyCentralForce(inc)
        body.applyTorque(inc)
        assert body.getTotalForce() == force + inc

    def test_damping(self):
        """
        Set/get damping factors.
        """
        # Get RigidBody object.
        body, _ = self.getRB()

        # Set the linear- and angular damping factors (must be in [0, 1] each).
        damp_lin, damp_ang = 0.2, 0.4
        body.setDamping(damp_lin, damp_ang)

        # The damping factors must be queried individually.
        assert body.getLinearDamping() == damp_lin
        assert body.getAngularDamping() == damp_ang

        # Repeat with a different value.
        damp_lin, damp_ang = 0.3, 0.5
        body.setDamping(damp_lin, damp_ang)
        assert body.getLinearDamping() == damp_lin
        assert body.getAngularDamping() == damp_ang

        # Repeat once more but specify values outside the range of [0, 1].
        # Bullet must clamp them.
        damp_lin, damp_ang = -0.3, 1.5
        body.setDamping(damp_lin, damp_ang)
        assert body.getLinearDamping() == 0
        assert body.getAngularDamping() == 1

    def test_friction(self):
        """
        Set/get friction coefficients.
        """
        # Get RigidBody object.
        body, _ = self.getRB()

        # Set the linear- and angular friction coefficients.
        friction = 1.8
        body.setFriction(friction)
        assert body.getFriction() == friction

        # Repeat with a different value.
        friction = 2.2
        body.setFriction(friction)
        assert body.getFriction() == friction

    def test_mass_inertia(self):
        """
        Set/get mass- and inertia.
        """
        # Get RigidBody object.
        body, _ = self.getRB()

        # The default body has unit mass and no inertia.
        assert body.getInvMass() == 1
        assert body.getInvInertiaDiagLocal() == Vec3(0, 0, 0)

        # Set the linear- and angular friction coefficients.
        mass, inertia = 2, Vec3(1, 10, 100)
        body.setMassProps(mass, inertia)
        assert body.getInvMass() == 1 / mass
        assert body.getInvInertiaDiagLocal() == Vec3(1, 0.1, 0.01)

        # Repeat with a different set of values.
        mass, inertia = 5, Vec3(10, 1, 1000)
        body.setMassProps(mass, inertia)
        assert body.getInvMass() == 1 / mass
        assert body.getInvInertiaDiagLocal() == Vec3(0.1, 1, 0.001)

    def test_activation(self):
        """
        Create two bodies and make one active forever and the other the
        opposite. Then step the simulation and verify that only the active one
        falls (due to gravity).
        """
        # Create two RigidBody objects at distinct positions.
        ref_pos1 = Vec3(0, 0, 0)
        ref_pos2 = Vec3(10, 10, 10)
        body1, _1 = self.getRB(pos=ref_pos1)
        body2, _2 = self.getRB(pos=ref_pos2)

        # Active- and inactive forever.
        body1.forceActivationState(4)
        body2.forceActivationState(5)

        # Creat a simulation and specify gravity.
        sim = azrael.bullet.azBullet.BulletBase()
        sim.setGravity(0, -10, 0)

        # Add the bodies.
        sim.addRigidBody(body1)
        sim.addRigidBody(body2)

        pos1 = body1.getMotionState().getWorldTransform().getOrigin()
        pos2 = body2.getMotionState().getWorldTransform().getOrigin()
        assert pos1 == ref_pos1
        assert pos2 == ref_pos2

        # Step the simulation.
        sim.stepSimulation(1.0, 60)

        # Verify that only the first object fell (by roughly .5m according to
        # the '1/2 * a * t**2' law.
        pos1 = body1.getMotionState().getWorldTransform().getOrigin()
        pos2 = body2.getMotionState().getWorldTransform().getOrigin()
        assert pos1 != ref_pos1
        assert pos2 == ref_pos2

    def test_transform(self):
        """
        Test the Transform class.
        """
        t = Transform()
        t.setIdentity()

        # Set the position and orientation.
        pos = Vec3(1, 2, 3.5)
        rot = Quaternion(0, 1, 0, 0)
        t.setOrigin(pos)
        t.setRotation(rot)
        assert t.getOrigin() == pos
        assert t.getRotation().tolist() == rot.tolist()

        # Repeat with different values.
        pos = Vec3(-1, 2.5, 3.5)
        rot = Quaternion(0, 0, 0, 1)
        t.setOrigin(pos)
        t.setRotation(rot)
        assert t.getOrigin() == pos
        assert t.getRotation().tolist() == rot.tolist()

    def test_motionstate(self):
        """
        Set and get a motion state.
        """
        # Get RigidBody object.
        body, _ = self.getRB()

        # Create a new Transform.
        pos = Vec3(1, 2, 3.5)
        rot = Quaternion(0, 1, 0, 0)
        t = Transform()
        t.setOrigin(pos)
        t.setRotation(rot)

        # Create a MotionState and apply the new transform.
        ms_ref = DefaultMotionState()
        ms_ref.setWorldTransform(t)

        # Verify the MotionState does not yet match ours.
        ms_out = body.getMotionState()
        assert ms_out.getWorldTransform().getOrigin() != pos
        assert ms_out.getWorldTransform().getRotation().tolist() != rot.tolist()

        # Apply- and query the MotionState.
        body.setMotionState(ms_ref)
        ms_out = body.getMotionState()

        # Verify the MotionState is correct.
        assert ms_out.getWorldTransform().getOrigin() == pos
        assert ms_out.getWorldTransform().getRotation().tolist() == rot.tolist()

    def test_centerOfMassTransform(self):
        """
        Get/set the centerOfMassTransform.
        """
        # Get RigidBody object.
        body, _ = self.getRB()

        # Create a new Transform.
        pos = Vec3(1, 2, 3.5)
        rot = Quaternion(0, 1, 0, 0)
        t1 = Transform()
        t1.setOrigin(pos)
        t1.setRotation(rot)

        # Apply the Transform to the body.
        body.setCenterOfMassTransform(t1)
        t2 = body.getCenterOfMassTransform()

        # Verify the result.
        assert t1.getOrigin() == t2.getOrigin()
        assert t1.getRotation().tolist() == t2.getRotation().tolist()

    def test_GetSet_CollisionShape(self):
        """
        Set, query, and replace a collision shape.
        """
        # Get RigidBody object.
        body, _ = self.getRB()

        sphere = SphereShape(1.5)
        box = BoxShape(Vec3(1, 2, 3))

        # Specify a sphere shape.
        body.setCollisionShape(sphere)
        assert body.getCollisionShape().getName() == b'SPHERE'

        # Change to box shape.
        body.setCollisionShape(box)
        assert body.getCollisionShape().getName() == b'Box'


class TestCollisionShapes:
    @classmethod
    def setup_class(cls):
        pass

    @classmethod
    def teardown_class(cls):
        pass

    def test_StaticPlaneShape(self):
        # Create a Static Plane and change its scaling.
        cs = StaticPlaneShape(Vec3(0, 1, 2), 3)
        scale = Vec3(1.5, 2.5, 3.5)
        cs.setLocalScaling(scale)
        assert cs.getLocalScaling() == scale

        # Create a Sphere and change its scaling.
        cs = SphereShape(3)
        scale = Vec3(1.5, 2.5, 3.5)
        cs.setLocalScaling(scale)
        assert cs.getLocalScaling() == scale

        # Create a Box and change its scaling.
        cs = BoxShape(Vec3(1, 2, 3))
        scale = Vec3(1.5, 2.5, 3.5)
        cs.setLocalScaling(scale)
        assert cs.getLocalScaling() == scale

        # Create an Empty shape and change its scaling.
        cs = EmptyShape()
        scale = Vec3(1.5, 2.5, 3.5)
        cs.setLocalScaling(scale)
        assert cs.getLocalScaling() == scale
