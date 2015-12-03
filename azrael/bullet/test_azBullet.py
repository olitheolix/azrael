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

import azBullet
from azBullet import Vec3, Quaternion
from azBullet import BoxShape, StaticPlaneShape
from azBullet import SphereShape, EmptyShape
from azBullet import Transform, MotionState
from azBullet import DefaultMotionState, RigidBody
from azBullet import CompoundShape
from azBullet import Point2PointConstraint, BulletBase
from azBullet import RigidBodyConstructionInfo
from azBullet import Generic6DofConstraint
from azBullet import Generic6DofSpringConstraint, Generic6DofSpring2Constraint


def getRB(pos=Vec3(0, 0, 0),
          cshape=SphereShape(1),
          mass=1,
          inertia=(1, 1, 1),
          bodyID=0):
    """
    Return a Rigid Body plus auxiliary information (do *not* delete; see
    note below).

    .. note:: Do not delete the tuple until the end of the test
    because it may lead to memory access violations. The reason is that a
    rigid body requires several indepenent structures that need to remain
    in memory.
    """
    t = Transform(Quaternion(0, 0, 0, 1), pos)
    ms = DefaultMotionState(t)

    # Build construction info and instantiate the rigid body.
    ci = RigidBodyConstructionInfo(mass, ms, cshape, Vec3(*inertia))
    rb = RigidBody(ci, bodyID)

    # Ensure the body remains activated.
    rb.forceActivationState(4)
    return rb


class TestVector3:
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
        v1 = Vec3(1, 2, 4)
        v2 = Vec3(.5, .6, .7)

        # Addition.
        assert v1 + v2 == Vec3(1.5, 2.6, 4.7)

        # Subtraction.
        assert v1 - v2 == Vec3(0.5, 1.4, 3.3)

        # Negation.
        assert -v1 == Vec3(-1, -2, -4)

        # Multiplication (only right-multiplication is supported).
        assert v1 * 2 == Vec3(2, 4, 8)

        # Division.
        assert v1 / 2 == Vec3(0.5, 1, 2)


class TestQuaternion:
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

    def test_comparison(self):
        q1 = Quaternion(0, 0, 0, 1)
        q2 = Quaternion(0, 0, 1, 0)

        # Equality.
        assert q1 == q1
        assert q2 == q2

        # Inequality.
        assert q1 != q2
        assert q2 != q1

        # Equality with a different Quaternion that has the same values.
        assert q1 == Quaternion(0, 0, 0, 1)
        assert q2 == Quaternion(0, 0, 1, 0)

    def test_normalize(self):
        """
        Create an unnormalised Quaternion. Verify that it is unnormalise, then
        normalise it, and verify that its length is now unity.
        """
        # Verify length of Quaternion.
        q = Quaternion(1, 2, 3, 4)
        assert abs(q.length2() - np.dot(q.topy(), q.topy())) < 1E-5

        # Normalise the Quaternion and verify it now has unit length. Note that
        # the 'normalize' method normalised the Quaternion inplace.
        q.normalize()
        assert abs(q.length2() - 1.0) < 1E-5

        # Similar to before, but this time we use the 'normalized' method (note
        # the trailing 'd' in the method name). This must return a new
        # Quaternion that is normalised and leave the original one intact.
        q1 = Quaternion(1, 2, 3, 4).normalized()
        len_q1 = q1.length2()

        q2 = q1.normalized()
        assert q1.length2() == len_q1
        assert abs(q2.length2() - 1.0) < 1E-5

    def test_mult_inverse(self):
        """
        Create an unnormalised Quaternion. Verify that the product of Q and its
        inverse commute. Verify further that the product of the normalised
        version of Q and its inverse results in a neutral Quaternion.
        """
        # Unnormalised Quaternion.
        q = Quaternion(1, 2, 3, 4)

        # Quaternion products do not normally commute, however the product of a
        # Quaternion with its inverse must.
        a = q * q.inverse()
        b = q.inverse() * q
        assert np.allclose(a.topy(), b.topy())
        del a, b

        # Normalise the Quaternion. Then compute its product with its own
        # inverse. This must be neutral Quaternion.
        q.normalize()
        assert np.allclose((q * q.inverse()).topy(), [0, 0, 0, 1])


class TestRigidBody:
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

    def test_set_get_BodyID(self):
        """
        Set- and get the bodyID.
        """
        # Get RigidBody object.
        body = getRB()

        # The default ID is zero.
        assert body.azGetBodyID() == 0

        # Assign- and query the bodyID several times.
        for ii in range(5):
            body.azSetBodyID(ii)
            assert body.azGetBodyID() == ii

    def test_restitution(self):
        """
        Specify and query "Restitution".
        """
        # Get RigidBody object.
        body = getRB()

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
        body = getRB()

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
        body = getRB()

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
        body = getRB()

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
        body = getRB()

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
        body = getRB()

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
        body = getRB()

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
        body = getRB()

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
        body = getRB()

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
        body = getRB()

        # The default body has unit mass and unit inertia.
        assert body.getInvMass() == 1
        assert body.getInvInertiaDiagLocal() == Vec3(1, 1, 1)

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

    def test_set_get_gravity(self):
        # Create a simulation.
        sim = azBullet.BulletBase()

        # Set- and get gravity values.
        for ii in range(5):
            gravity = Vec3(ii, -ii, 2 * ii)
            sim.setGravity(gravity)
            assert sim.getGravity() == gravity

    def test_activation(self):
        """
        Create two bodies and make one active forever and the other the
        opposite. Then step the simulation and verify that only the active one
        falls (due to gravity).
        """
        # Create two RigidBody objects at distinct positions.
        ref_pos1 = Vec3(0, 0, 0)
        ref_pos2 = Vec3(10, 10, 10)
        body1 = getRB(pos=ref_pos1)
        body2 = getRB(pos=ref_pos2)

        # Active- and inactive forever.
        body1.forceActivationState(4)
        body2.forceActivationState(5)

        # Create a simulation and specify gravity.
        sim = azBullet.BulletBase()
        sim.setGravity(Vec3(0, -10, 0))

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

    def test_GetSet_CollisionShape(self):
        """
        Set, query, and replace a collision shape.
        """
        # Get RigidBody object.
        body = getRB()

        radius, extent = 1.5, Vec3(1, 2, 3)
        sphere = SphereShape(radius)
        box = BoxShape(extent)

        # Specify a Sphere shape.
        body.setCollisionShape(sphere)
        assert body.getCollisionShape().getName() == b'SPHERE'
        assert body.getCollisionShape().getRadius() == radius

        # Change to Box shape.
        body.setCollisionShape(box)
        assert body.getCollisionShape().getName() == b'Box'
        assert body.getCollisionShape().getHalfExtentsWithMargin() == extent

    def test_calculateLocalInertia(self):
        """
        Create a sphere and let Bullet compute its inertia via the
        'calculateLocalInertia' method. Verify that the result is correct.
        """
        # Compute the inertia of the sphere. The inertia for a sphere is
        # I = 2 / 5 * mass * (R ** 2)
        mass, radius = 2, 3
        sphere = SphereShape(radius)
        inertia = sphere.calculateLocalInertia(mass)
        ref = 2 / 5 * mass * radius ** 2
        assert np.allclose(inertia.topy(), ref * np.ones(3))

    def test_ConstructionInfo(self):
        """
        Create a RigidBodyConstructionInfo class and set/get some attributes.
        """
        mass = 1.5
        pos = Vec3(1, 2, 3)
        rot = Quaternion(0, 0, 0, 1)
        t = Transform(rot, pos)
        ms = DefaultMotionState(t)
        cs = EmptyShape()
        ci = RigidBodyConstructionInfo(mass, ms, cs)

        # Mass was specified in Ctor.
        assert ci.mass == mass
        ci.mass = 1.1
        assert ci.mass == 1.1
        ci.mass = 1.1
        assert ci.mass == 1.1

        # Local inertia was specified in Ctor.
        assert ci.localInertia == Vec3(1, 1, 1)
        inert = Vec3(1, 2, 10)
        ci.localInertia = inert
        assert ci.localInertia == inert
        inert = Vec3(1, 2, 20)
        ci.localInertia = inert
        assert ci.localInertia == inert

        # Verify the 'motionState' attribute.
        assert ci.motionState.getWorldTransform().getOrigin() == pos
        assert ci.motionState.getWorldTransform().getRotation() == rot

        # Verify the 'collisionShape' attribute.
        assert ci.collisionShape.getName() == b'Empty'

    def test_ConstructionInfo_to_RigidBody(self):
        """
        Verify that the initial motion state is transferred correctly to the
        RigidBody.
        """
        mass = 10
        pos = Vec3(1, 2, 3)
        rot = Quaternion(0, 1, 0, 0)
        t = Transform(rot, pos)
        ms = DefaultMotionState(t)
        cs = EmptyShape()
        inert = Vec3(1, 2, 4)

        # Compile the Rigid Body parameters.
        ci = RigidBodyConstructionInfo(mass, ms, cs, Vec3(2, 4, 6))
        assert ci.localInertia == Vec3(2, 4, 6)
        ci.localInertia = inert
        assert ci.localInertia == inert

        # Construct the rigid body and delete the construction info.
        body = RigidBody(ci)
        del ci

        # Verify that the object is at the correct position and has the correct
        # mass and inertia.
        t = body.getMotionState().getWorldTransform()
        assert t.getOrigin() == pos
        assert t.getRotation() == rot
        assert body.getInvMass() == 1 / mass
        assert body.getInvInertiaDiagLocal() == Vec3(1, 0.5, 0.25)


class TestCollisionShapes:
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

    def test_BasicShapes(self):
        """
        Create the basic shapes and verify their names. Furthermore, verify
        that scaling them works.
        """
        # Create the Collision Shape instances.
        cs_p = StaticPlaneShape(Vec3(0, 1, 2), 3)
        cs_s = SphereShape(3)
        cs_b = BoxShape(Vec3(1, 2, 3))
        cs_e = EmptyShape()

        # Verify the dimensions of the sphere and the box.
        assert cs_s.getRadius() == 3
        assert cs_b.getHalfExtentsWithMargin() == Vec3(1, 2, 3)

        # Put the collision shapes into a dictionary where the key is the
        # expected name.
        shapes = {b'STATICPLANE': cs_p,
                  b'SPHERE': cs_s,
                  b'Box': cs_b,
                  b'Empty': cs_e}

        # Verify the name of each shape and modify its scale.
        scale = Vec3(1.5, 2.5, 3.5)
        for name, cs in shapes.items():
            cs.setLocalScaling(scale)
            assert cs.getLocalScaling() == scale
            assert cs.getName() == name

    def test_CompoundShapes(self):
        """
        Create a compound shape, then add- and remove objects in it.
        """
        # Create some shapes.
        cs_p = StaticPlaneShape(Vec3(0, 1, 2), 3)
        cs_s = SphereShape(3)
        cs_b = BoxShape(Vec3(1, 2, 3))
        cs_e = EmptyShape()

        # Create a compound shape and verify it is empty.
        comp = CompoundShape()
        assert comp.getNumChildShapes() == 0

        # Add a plane with a default Transform.
        comp.addChildShape(Transform(), cs_p)
        assert comp.getNumChildShapes() == 1

        # Add sphere with a default Transform.
        comp.addChildShape(Transform(), cs_s)
        assert comp.getNumChildShapes() == 2

        # Add box with a default Transform.
        comp.addChildShape(Transform(), cs_b)
        assert comp.getNumChildShapes() == 3

        # Verify the collision shapes.
        assert comp.getChildShape(0).getName() == b'STATICPLANE'
        assert isinstance(comp.getChildShape(0), StaticPlaneShape)
        assert comp.getChildShape(1).getName() == b'SPHERE'
        assert isinstance(comp.getChildShape(1), SphereShape)
        assert comp.getChildShape(2).getName() == b'Box'
        assert isinstance(comp.getChildShape(2), BoxShape)

        # Remove the sphere. This must reduce the number of shapes to 2.
        comp.removeChildShape(cs_s)
        assert comp.getNumChildShapes() == 2
        assert comp.getChildShape(0).getName() == b'STATICPLANE'
        assert comp.getChildShape(1).getName() == b'Box'

        # Attempt to access a non-existing index.
        assert comp.getChildShape(-1) is None
        assert comp.getChildShape(2) is None

        # Test iterator support.
        assert [_.getName() for _ in comp] == [b'STATICPLANE', b'Box']

        # Test iterator support.
        comp.addChildShape(Transform(), cs_s)
        comp.addChildShape(Transform(), cs_e)
        tmp = [_.getName() for _ in comp]
        assert tmp == [b'STATICPLANE', b'Box', b'SPHERE', b'Empty']

    def test_CompoundShapes_calculatePrincipalAxisTransform_basic(self):
        """
        Test edge cases of calculatePrincipalAxisTransform.
        """
        # Create a compound- and sphere shape.
        cs = CompoundShape()
        sphere = SphereShape(1)

        # Inertia of empty compound shape must be zero.
        inertia, principal = cs.calculatePrincipalAxisTransform([])
        center_of_mass = principal.getOrigin().topy()
        paxis = principal.getRotation().topy()
        assert np.allclose(center_of_mass, [0, 0, 0])
        assert np.allclose(paxis, [0, 0, 0, 1])
        assert np.allclose(inertia.topy(), [0, 0, 0])

        # Add a sphere to the compund shape.
        t = Transform(Quaternion(0, 0, 0, 1), Vec3(0, 0, 0))
        cs.addChildShape(t, sphere)

        # Passing more or less masses to CPAT than there are child shapes must
        # result in an error.
        mass = 1
        with pytest.raises(AssertionError):
            cs.calculatePrincipalAxisTransform([])
        with pytest.raises(AssertionError):
            cs.calculatePrincipalAxisTransform([mass, mass])

    def test_CompoundShapes_calculatePrincipalAxisTransform_single(self):
        """
        Create a compound shape with one sphere at different positions. Then
        verify its inertia and center of mass.
        """
        # ---------------------------------------------------------------------
        # Inertia of compound shape with one sphere at the center must match
        # the inertia of the single sphere.
        # ---------------------------------------------------------------------
        mass = 1
        cs = CompoundShape()
        sphere = SphereShape(1)

        # Add the sphere to the center of the compound shape.
        pos = [0, 0, 0]
        t = Transform(Quaternion(0, 0, 0, 1), Vec3(*pos))
        cs.addChildShape(t, sphere)

        # Ask Bullet for the Inertia of the compound shape.
        inertia, principal = cs.calculatePrincipalAxisTransform([mass])
        center_of_mass = principal.getOrigin().topy()
        paxis = principal.getRotation().topy()
        inertia_sphere = sphere.calculateLocalInertia(mass)

        # The center of mass must coincide with 'pos' because the compound
        # contains only one sphere. Similarly, the principal axis must be
        # neutral and the inertia must match that of the sphere.
        assert np.allclose(center_of_mass, pos)
        assert np.allclose(paxis, [0, 0, 0, 1])
        assert np.allclose(inertia.topy(), inertia_sphere.topy())

        del pos, t, inertia, principal, center_of_mass, paxis, inertia_sphere
        del cs, sphere

        # ---------------------------------------------------------------------
        # Create a compound shape with one sphere _not_ at the center. The
        # principal axis and Inertia must still be that of the sphere, but the
        # center of mass must match the position of the sphere in the compound
        # shape.
        # ---------------------------------------------------------------------
        mass = 1
        cs = CompoundShape()
        sphere = SphereShape(1)

        # Add the sphere at position `pos` to the compound shape.
        pos = [1, 2, 3]
        t = Transform(Quaternion(0, 0, 0, 1), Vec3(*pos))
        cs.addChildShape(t, sphere)

        # The center of mass must coincide with 'pos' because the compound
        # contains only one sphere. Similarly, the principal axis must be
        # neutral and the inertia must match that of the sphere.
        inertia, principal = cs.calculatePrincipalAxisTransform([mass])
        center_of_mass = principal.getOrigin().topy()
        paxis = principal.getRotation().topy()
        inertia_sphere = sphere.calculateLocalInertia(mass)

        assert np.allclose(center_of_mass, pos)
        assert np.allclose(paxis, [0, 0, 0, 1])
        assert np.allclose(inertia.topy(), inertia_sphere.topy())

    def test_CompoundShapes_calculatePrincipalAxisTransform_multi(self):
        """
        Create a compound shape with two spheres at different positions. Then
        verify its inertia and center of mass.
        """
        # Create compound- and sphere shape.
        cs = CompoundShape()
        sphere = SphereShape(1)

        # Add two sphere shapes to the compound.
        pos1 = [-2, 2, 0]
        pos2 = [1, -1, 0]
        t1 = Transform(Quaternion(0, 0, 0, 1), Vec3(*pos1))
        t2 = Transform(Quaternion(0, 0, 0, 1), Vec3(*pos2))
        cs.addChildShape(t1, sphere)
        cs.addChildShape(t2, sphere)

        # Specify the mass of the spheres and manually compute the weighted
        # center of mass.
        masses = [1, 2]
        ref = np.array(pos1) * masses[0] + np.array(pos2) * masses[1]
        ref = ref / sum(masses)

        # Ask Bullet for the Inertia and princiapl axis. The center of mass
        # must match our manually compute one.
        inertia, principal = cs.calculatePrincipalAxisTransform(masses)
        assert np.allclose(principal.getOrigin().topy(), ref)

    def test_CompoundShape_get_and_update_childTransforms(self):
        """
        Create a compound shape with two elements. Then query their transforms,
        update one of them, and verify they were udpated correctly.
        """
        # Create compound- and sphere shape.
        cs = CompoundShape()
        sphere_1, sphere_2 = SphereShape(1), SphereShape(2)

        # Create two distinct transforms.
        rot1, pos1 = (0, 0, 0, 1), (1, 2, 3)
        rot2, pos2 = (1, 0, 0, 0), (4, 5, 6)
        t1 = Transform(Quaternion(*rot1), Vec3(*pos1))
        t2 = Transform(Quaternion(*rot2), Vec3(*pos2))

        # Add both spheres with the _same_ transform.
        cs.addChildShape(t1, sphere_1)
        cs.addChildShape(t1, sphere_2)

        # Verify the children have the specified transforms.
        for childIdx in range(2):
            child_transform = cs.getChildTransform(childIdx)
            assert np.allclose(pos1, child_transform.getOrigin().topy())
            assert np.allclose(rot1, child_transform.getRotation().topy())

        # Update the local transform of the first child. Leave the second child
        # alone.
        cs.updateChildTransform(0, t2)

        # Verify that the first child has the new transform values and the
        # second one still the original ones.
        assert np.allclose(pos2, cs.getChildTransform(0).getOrigin().topy())
        assert np.allclose(rot2, cs.getChildTransform(0).getRotation().topy())
        assert np.allclose(pos1, cs.getChildTransform(1).getOrigin().topy())
        assert np.allclose(rot1, cs.getChildTransform(1).getRotation().topy())


class TestTransform:
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

    def test_transform(self):
        """
        Test the Transform class.
        """
        pos = Vec3(1, 2, 3.5)
        rot = Quaternion(0, 1, 0, 0)
        t = Transform(rot, pos)
        assert t.getOrigin() == pos
        assert t.getRotation() == rot

        # Set to identity.
        t.setIdentity()
        assert t.getOrigin() == Vec3(0, 0, 0)
        assert t.getRotation() == Quaternion(0, 0, 0, 1)

        # Set the position and rotation.
        pos = Vec3(1, 2, 3.5)
        rot = Quaternion(0, 1, 0, 0)
        t.setOrigin(pos)
        t.setRotation(rot)
        assert t.getOrigin() == pos
        assert t.getRotation() == rot

        # Repeat with different values.
        pos = Vec3(-1, 2.5, 3.5)
        rot = Quaternion(0, 0, 0, 1)
        t.setOrigin(pos)
        t.setRotation(rot)
        assert t.getOrigin() == pos
        assert t.getRotation() == rot

    def test_mult(self):
        """
        Multiply two transforms. There are two ways to do this: overloaded '*'
        operator and dedicated `mult` method of `Transform` class.
        """
        # Create two Transforms. Their Quaternions are deliberately not
        # normalised. The Transform class must normalise them automatically.
        t1 = Transform(Quaternion(1, 2, 3, 4), Vec3(1, 4, 8))
        t2 = Transform(Quaternion(4, 3, 2, 1), Vec3(16, 32, 64))

        # To use the 'mult' method we need a Transform to hold the result.
        t3 = Transform()
        t3.mult(t1, t2)

        # Use the overloaded '*' operator.
        t4 = t1 * t2

        # Verify that both operations yielded the same result.
        assert np.allclose(t3.getOrigin().topy(), t4.getOrigin().topy())
        assert np.allclose(t3.getRotation().topy(), t4.getRotation().topy())

        # Verify that the transforms normalised their Quaternions.
        assert abs(t3.getRotation().length2() - 1) < 1E-5
        assert abs(t4.getRotation().length2() - 1) < 1E-5
        del t1, t2, t3, t4

        # Verify the translation value manually. This is only a very basic test
        # because we are basically relying on Bullet to correctly compute it.
        t1 = Transform(Quaternion(0, 0, 0, 1), Vec3(0, 1, 2))
        t2 = Transform(Quaternion(0, 0, 0, 1), Vec3(3, 2, 1))
        t3 = t1 * t2
        assert np.allclose(t3.getOrigin().topy(), [3, 3, 3])

    def test_inverse_mult(self):
        """
        Create a transform and verify that its multiplication with its inverse
        is a neutral transform.
        """
        # Create a Transform. The Quaternion is deliberately not normalised.
        t1 = Transform(Quaternion(1, 2, 3, 4), Vec3(1, 4, 8))

        # To use the 'mult' method we need a Transform to hold the result.
        t2 = Transform()
        t2.mult(t1, t1.inverse())

        # Verify that t2 is indeed the neutral transform.
        pos = t2.getOrigin().topy()
        rot = t2.getRotation().topy()
        assert np.allclose(pos, [0, 0, 0])
        assert np.allclose(rot, [0, 0, 0, 1])


class TestMotionState:
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

    def test_motionstate(self):
        """
        Set and get a motion state.
        """
        # Get RigidBody object.
        body = getRB()

        # Create a new Transform.
        pos = Vec3(1, 2, 3.5)
        rot = Quaternion(0, 1, 0, 0)
        t = Transform()
        t.setOrigin(pos)
        t.setRotation(rot)

        # It must be impossible to instantiate 'MotionState' directly.
        with pytest.raises(NotImplementedError):
            MotionState()

        # Create a MotionState and apply the new transform.
        ms_ref = DefaultMotionState()
        ms_ref.setWorldTransform(t)

        # Verify the MotionState does not yet match ours.
        ms = body.getMotionState()
        assert ms.getWorldTransform().getOrigin() != pos
        assert ms.getWorldTransform().getRotation() != rot

        # Apply- and query the MotionState.
        body.setMotionState(ms_ref)
        ms = body.getMotionState()

        # Verify the MotionState is correct.
        assert ms.getWorldTransform().getOrigin() == pos
        assert ms.getWorldTransform().getRotation() == rot

    def test_centerOfMassTransform(self):
        """
        Get/set the centerOfMassTransform.
        """
        # Get RigidBody object.
        body = getRB()

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
        assert t1.getRotation() == t2.getRotation()


class TestConstraints:
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

    def test_typedObject(self):
        """
        Bullet uses TypedObjects as a "rudimentary" base class for all
        constraints. This is the equally rudimentary test for it, most notably
        that it cannot be instantiated directly.
        """
        with pytest.raises(NotImplementedError):
            # Requires an integer argument; not sure what it really means.
            azBullet.TypedObject(1)

    def test_Point2Point(self):
        """
        Create-, set, and query various Point2Point constraint attributes.
        """
        # Create two rigid bodies side by side (they *do* touch, but just).
        cs_a = SphereShape(1)
        cs_b = BoxShape(Vec3(1, 2, 3))
        pos_a = Vec3(-1, 0, 0)
        pos_b = Vec3(1, 0, 0)
        rb_a = getRB(pos=pos_a, cshape=cs_a)
        rb_b = getRB(pos=pos_b, cshape=cs_b)

        # Connect the two rigid bodies at their left/right boundary.
        pivot_a, pivot_b = pos_b, pos_a
        p2p = Point2PointConstraint(rb_a, rb_b, pivot_a, pivot_b)

        # Verify that their pivot is at the specified position.
        assert p2p.getPivotInA() == pivot_a
        assert p2p.getPivotInB() == pivot_b

        # Swap the pivot points.
        p2p.setPivotA(pivot_b)
        p2p.setPivotB(pivot_a)

        # Verify that their pivot is as specified.
        assert p2p.getPivotInA() == pivot_b
        assert p2p.getPivotInB() == pivot_a

        # Query the two objects and verify they have the correct type.
        assert p2p.getRigidBodyA().getCollisionShape().getName() == b'SPHERE'
        assert p2p.getRigidBodyB().getCollisionShape().getName() == b'Box'

        # Enable- and disable the constraint.
        assert p2p.isEnabled() == True
        p2p.setEnabled(False)
        assert p2p.isEnabled() == False
        p2p.setEnabled(True)
        assert p2p.isEnabled() == True

        # Query the object type; not sure what this is, but if it does not
        # segfault it works :)
        p2p.getObjectType()

    def test_Point2Point_sim(self):
        """
        Test the Point2Point constraint in a Bullet simulation.
        """
        # Create two rigid bodies side by side (they *do* touch, but just).
        pos_a = Vec3(-1, 0, 0)
        pos_b = Vec3(1, 0, 0)
        rb_a = getRB(pos=pos_a, cshape=SphereShape(1))
        rb_b = getRB(pos=pos_b, cshape=BoxShape(Vec3(1, 2, 3)))

        # Connect the two rigid bodies at their left/right boundary.
        pivot_a, pivot_b = pos_b, pos_a
        p2p = Point2PointConstraint(rb_a, rb_b, pivot_a, pivot_b)

        # Add both rigid bodies into a simulation.
        bb = BulletBase()
        bb.setGravity(Vec3(0, 0, 0))
        bb.addRigidBody(rb_a)
        bb.addRigidBody(rb_b)

        # Tell the simulation about the constraint.
        bb.addConstraint(p2p)

        # Verify that the objects are at x-position +/-1, and thus 2 Meters
        # apart.
        p_a = rb_a.getCenterOfMassTransform().getOrigin().topy()
        p_b = rb_b.getCenterOfMassTransform().getOrigin().topy()
        init_pos = (p_a[0], p_b[0])
        fixed_dist = p_a[0] - p_b[0]
        assert init_pos == (-1, 1)

        # Apply opposing forces to both objects, step the simulation a few
        # times, and verify at each step that *both* objects move in the *same*
        # direction due to the constraint.
        rb_a.applyCentralForce(Vec3(10, 0, 0))
        rb_b.applyCentralForce(Vec3(-1, 0, 0))
        for ii in range(3):
            # Step simulation.
            bb.stepSimulation(10 / 60, 60)

            # Query the position of the objects.
            p_a = rb_a.getCenterOfMassTransform().getOrigin().topy()
            p_b = rb_b.getCenterOfMassTransform().getOrigin().topy()

            # Verify that both objects continue to move to right, yet maintain
            # their initial distance.
            assert p_a[0] > init_pos[0]
            assert p_b[0] > init_pos[1]
            assert abs((p_a[0] - p_b[0]) - fixed_dist) < 0.1
            init_pos = (p_a[0], p_b[0])

    @pytest.mark.parametrize('clsDof6', [Generic6DofConstraint,
                                         Generic6DofSpringConstraint,
                                         Generic6DofSpring2Constraint,
                                         ])
    def test_Generic6DofConstraint(self, clsDof6):
        """
        Create-, set, and query various `Generic6DofConstraint` attributes.
        """
        # Create two rigid bodies side by side (they *do* touch, but just).
        cs_a = SphereShape(1)
        cs_b = BoxShape(Vec3(1, 2, 3))
        pos_a = Vec3(-1, 0, 0)
        pos_b = Vec3(1, 0, 0)
        rb_a = getRB(pos=pos_a, cshape=cs_a)
        rb_b = getRB(pos=pos_b, cshape=cs_b)

        # Create the 6DOF constraint between the two bodies.
        frameInA = Transform()
        frameInB = Transform()
        frameInA.setIdentity()
        frameInB.setIdentity()
        refIsA = True
        dof = clsDof6(rb_a, rb_b, frameInA, frameInB, refIsA)

        # We are now emulating a slider constraint with this 6DOF constraint.
        # For this purpose we need to specify the linear/angular limits.
        sliderLimitLo = Vec3(-10, 0, 0)
        sliderLimitHi = Vec3(10, 0, 0)
        angularLimitLo = Vec3(-1.5, 0, 0)
        angularLimitHi = Vec3(1.5, 0, 0)

        # Apply the linear/angular limits.
        dof.setLinearLowerLimit(sliderLimitLo)
        dof.setLinearUpperLimit(sliderLimitHi)
        dof.setAngularLowerLimit(angularLimitLo)
        dof.setAngularUpperLimit(angularLimitHi)

        # Verify the linear/angular limits were applied correctly.
        assert dof.getLinearLowerLimit() == sliderLimitLo
        assert dof.getLinearUpperLimit() == sliderLimitHi
        assert dof.getAngularLowerLimit() == angularLimitLo
        assert dof.getAngularUpperLimit() == angularLimitHi

        # Query the object type; not sure what this is, but if it does not
        # segfault it works :)
        dof.getObjectType()

    @pytest.mark.parametrize('clsDof6', [Generic6DofConstraint,
                                         Generic6DofSpringConstraint,
                                         Generic6DofSpring2Constraint,
                                         ])
    def test_Generic6DofConstraint_emulateP2P_sim(self, clsDof6):
        """
        Test the Generic6Dof constraint in a Bullet simulation.

        The 6DOF constraint in this test emulates a Point2Point constraint
        because the default values for linear/angular motion are not modified.
        The test code is therefore mostly identical to that for a Point2Point
        constraint.
        """
        # Create two rigid bodies side by side (they *do* touch, but just) and
        # lock their Inertia (ie the bodies cannot rotate).
        pos_a = Vec3(-1, 0, 0)
        pos_b = Vec3(1, 0, 0)
        rb_a = getRB(pos=pos_a, cshape=SphereShape(1), inertia=(0, 0, 0))
        rb_b = getRB(pos=pos_b, cshape=BoxShape(Vec3(1, 2, 3)), inertia=(0, 0, 0))

        # Create the constraint between the two bodies.
        frameInA = Transform()
        frameInB = Transform()
        frameInA.setIdentity()
        frameInB.setIdentity()
        refIsA = True
        dof = clsDof6(rb_a, rb_b, frameInA, frameInB, refIsA)

        # Add both rigid bodies into a simulation.
        bb = BulletBase()
        bb.setGravity(Vec3(0, 0, 0))
        bb.addRigidBody(rb_a)
        bb.addRigidBody(rb_b)

        # Add constraint to Bullet simulation.
        bb.addConstraint(dof)

        # Verify that the objects are at x=+/-1 respectively.
        p_a = rb_a.getCenterOfMassTransform().getOrigin().topy()
        p_b = rb_b.getCenterOfMassTransform().getOrigin().topy()
        init_pos = (p_a[0], p_b[0])
        fixed_dist = p_a[0] - p_b[0]
        assert init_pos == (-1, 1)

        # Apply opposing forces to both objects and step the simulation a few
        # times. Verify that *both* objects move in the *same* direction
        # due to the constraint.
        rb_a.applyCentralForce(Vec3(10, 0, 0))
        rb_b.applyCentralForce(Vec3(10, 0, 0))
        for ii in range(3):
            # Step simulation.
            bb.stepSimulation(10 / 60, 60)

            # Query the position of the objects.
            p_a = rb_a.getCenterOfMassTransform().getOrigin().topy()
            p_b = rb_b.getCenterOfMassTransform().getOrigin().topy()

            # Verify that both objects a) continue to move right and b)
            # to (roughly) maintain their initial distance. The distance will
            # not be maintained exactly due to the implementation of the
            # constraint inside Bullet itself.
            assert p_a[0] > init_pos[0]
            assert p_b[0] > init_pos[1]
            assert abs((p_a[0] - p_b[0]) - fixed_dist) < 0.1
            init_pos = (p_a[0], p_b[0])

    @pytest.mark.parametrize('clsDof6', [Generic6DofConstraint,
                                         Generic6DofSpringConstraint])
    def test_Generic6DofConstraint_emulateSlider_pivot_sim(self, clsDof6):
        """
        Same as test_Generic6DofConstraint_emulateP2P_pivot_sim except
        that the pivot does not coincide with the center of mass and the
        constraint is setup such that it mimicks a slider.
        """
        # Create two rigid bodies side by side (they *do* touch, but just).
        pos_a = Vec3(-1, 0, 0)
        pos_b = Vec3(1, 0, 0)
        rb_a = getRB(pos=pos_a, cshape=SphereShape(1))
        rb_b = getRB(pos=pos_b, cshape=BoxShape(Vec3(1, 2, 3)))

        # Create the constraint between the two bodies. The constraint applies
        # at (0, 0, 0) in world coordinates.
        frameInA = Transform(Quaternion(0, 0, 0, 1), pos_b)
        frameInB = Transform(Quaternion(0, 0, 0, 1), pos_a)
        refIsA = True
        dof = clsDof6(rb_a, rb_b, frameInA, frameInB, refIsA)

        # We are now emulating a slider constraint with this 6DOF constraint.
        # For this purpose we need to specify the linear/angular limits.
        sliderLimitLo = -1
        sliderLimitHi = 1

        # Apply the linear/angular limits.
        dof.setLinearLowerLimit(Vec3(sliderLimitLo, 0, 0))
        dof.setLinearUpperLimit(Vec3(sliderLimitHi, 0, 0))

        # Add both rigid bodies and the constraint to the Bullet simulation.
        bb = BulletBase()
        bb.setGravity(Vec3(0, 0, 0))
        bb.addRigidBody(rb_a)
        bb.addRigidBody(rb_b)
        bb.addConstraint(dof)

        # Verify that the objects are at x-position +/-1, and thus 2 Meters
        # apart.
        p_a = rb_a.getCenterOfMassTransform().getOrigin().topy()
        p_b = rb_b.getCenterOfMassTransform().getOrigin().topy()
        init_pos = (p_a[0], p_b[0])
        assert init_pos == (-1, 1)

        # Pull the right object to the right. Initially this must not affect
        # the object on the left until the slider is fully extended, at which
        # point the left object must begin to move as well.
        for ii in range(5):
            # Apply the force and step the simulation.
            rb_b.applyCentralForce(Vec3(10, 0, 0))
            bb.stepSimulation(10 / 60, 60)

            # Query the position of the objects.
            p_a = rb_a.getCenterOfMassTransform().getOrigin().topy()
            p_b = rb_b.getCenterOfMassTransform().getOrigin().topy()

            # If the right object has not moved far enough to fully extend the
            # (emulated) slider constraint then the left object must remain
            # where it is, otherwise it must move to the right.
            if p_b[0] <= (init_pos[1] + sliderLimitHi):
                assert p_a[0] == init_pos[0]
            else:
                assert p_a[0] > init_pos[0]

        # Verify that the above loop really pulled the right object far enought
        # to exhaust the maximum translation allowance.
        assert p_b[0] > (init_pos[1] + sliderLimitHi)

    def test_Generic6DofSpring2Constraint_emulateSlider_pivot_sim(self):
        """
        The '6DofSpring2Constraint' (note the '2' in the name) behave slight
        differently than the '6DofSpringConstraint' (no '2' in the name). For
        this reason it has a dedicated test.

        The differences are subtle and, as usual with Bullet, not really
        documented. However, the '2' version is (apparently) more stable and I
        know that the damping coefficient works (unlike in the version without
        '2' where it has no effect).

        One of the main difference, and also the reason why the previous slider
        test would fail with the '2' version is that the slider does not have
        to extend fully before the second object experiences a force. This is
        rather plausible for all realistic slider constraints but hard to test
        rigorously. However, this test attempts to verify this basic feature
        nevertheless even though the limits are somewhat empirical.
        """
        # Create two rigid bodies side by side (they *do* touch, but just).
        pos_a = Vec3(-1, 0, 0)
        pos_b = Vec3(1, 0, 0)
        rb_a = getRB(pos=pos_a, cshape=SphereShape(1))
        rb_b = getRB(pos=pos_b, cshape=BoxShape(Vec3(1, 2, 3)))

        # Create the constraint between the two bodies. The constraint applies
        # at (0, 0, 0) in world coordinates.
        frameInA = Transform(Quaternion(0, 0, 0, 1), pos_b)
        frameInB = Transform(Quaternion(0, 0, 0, 1), pos_a)
        clsDof6 = Generic6DofSpring2Constraint
        dof = clsDof6(rb_a, rb_b, frameInA, frameInB)

        # We are now emulating a slider constraint with this 6DOF constraint.
        # For this purpose we need to specify the linear/angular limits.
        sliderLimitLo = -1
        sliderLimitHi = -sliderLimitLo

        # Apply the linear/angular limits.
        dof.setLinearLowerLimit(Vec3(sliderLimitLo, 0, 0))
        dof.setLinearUpperLimit(Vec3(sliderLimitHi, 0, 0))

        # Add both rigid bodies and the constraint to the Bullet simulation.
        bb = BulletBase()
        bb.setGravity(Vec3(0, 0, 0))
        bb.addRigidBody(rb_a)
        bb.addRigidBody(rb_b)
        bb.addConstraint(dof)

        # Verify that the objects are at x-position +/-1, and thus 2 Meters
        # apart.
        p_a = rb_a.getCenterOfMassTransform().getOrigin().topy()
        p_b = rb_b.getCenterOfMassTransform().getOrigin().topy()
        init_pos = (p_a[0], p_b[0])
        assert init_pos == (-1, 1)

        # The ...Spring2... (notice the '2') behaves slightly differently (and
        # more correctly) than the Dof without the '2' in the name. In
        # particular, once the slider constraint extends to ~1/sqrt(2) of the
        # full distance it starts to dampen the motion. For this purpose we
        # define three regions: half extended, between half- and fully extend,
        # and fully extended. The two threshold values below specify the two
        # boundary regions.
        thresh_1 = init_pos[1] + sliderLimitHi / 2
        thresh_2 = init_pos[1] + sliderLimitHi

        # Pull the right object to the right. Initially this must not affect
        # the object on the left until the slider is fully extended, at which
        # point the left object must begin to move as well.
        for ii in range(50):
            # Apply the force and step the simulation.
            rb_b.applyCentralForce(Vec3(10, 0, 0))
            bb.stepSimulation(1 / 60, 60)

            # Query the position of the objects.
            p_a = rb_a.getCenterOfMassTransform().getOrigin().topy()
            p_b = rb_b.getCenterOfMassTransform().getOrigin().topy()

            # If the right object has not moved far enough to extend the slider
            # by at least half then the left object must remain still. If it is
            # in the region between half- and full extend then the object will
            # eventually start to move (but we do not know exactly when). When
            # the right object has moved enough to fully extend the slider the
            # left object must definitively have moved by then.
            if p_b[0] < thresh_1:
                assert p_a[0] == init_pos[0]
            elif thresh_1 <= p_b[0] < thresh_2:
                assert p_a[0] >= init_pos[0]
            else:
                assert p_a[0] > init_pos[0]

        # Verify that the above loop really pulled the right object far enought
        # to exhaust the maximum translation allowance.
        assert p_b[0] > (init_pos[1] + sliderLimitHi)

    def test_add_get_remove_iterate(self):
        """
        Test the various functions
        """
        # Create two rigid bodies side by side (they *do* touch, but just).
        pos_a = Vec3(-3, 0, 0)
        pos_b = Vec3(-1, 0, 0)
        pos_c = Vec3(1, 0, 0)
        pos_d = Vec3(3, 0, 0)
        rb_a = getRB(pos=pos_a, cshape=SphereShape(1))
        rb_b = getRB(pos=pos_b, cshape=BoxShape(Vec3(1, 2, 3)))
        rb_c = getRB(pos=pos_c, cshape=SphereShape(1))
        rb_d = getRB(pos=pos_d, cshape=BoxShape(Vec3(1, 2, 3)))

        frameInA = Transform(Quaternion(0, 0, 0, 1), pos_b)
        frameInB = Transform(Quaternion(0, 0, 0, 1), pos_a)

        # Connect the two rigid bodies at their left/right boundary.
        pivot_a, pivot_b, pivot_c, pivot_d = pos_a, pos_b, pos_c, pos_d
        p2p_ab = Point2PointConstraint(rb_a, rb_b, pivot_a, pivot_b)
        dof_bc = Generic6DofSpring2Constraint(rb_b, rb_c, frameInA, frameInB)
        p2p_cd = Point2PointConstraint(rb_c, rb_d, pivot_c, pivot_d)

        # Add both rigid bodies into a simulation.
        bb = BulletBase()
        bb.addRigidBody(rb_a)
        bb.addRigidBody(rb_b)

        # So far we have not added any constraints.
        assert bb.getNumConstraints() == 0
        assert bb.getConstraint(0) == None
        assert bb.getConstraint(10) == None

        # Add the first constraint.
        bb.addConstraint(p2p_ab)
        assert bb.getNumConstraints() == 1
        assert bb.getConstraint(0) == p2p_ab
        assert bb.getConstraint(1) == None
        assert list(bb.iterateConstraints()) == [p2p_ab]

        # Add the first constraint a second time. The function call must suceed
        # but the constraint must not have been added again.
        bb.addConstraint(p2p_ab)
        assert bb.getNumConstraints() == 1
        assert bb.getConstraint(0) == p2p_ab
        assert bb.getConstraint(1) == None
        assert list(bb.iterateConstraints()) == [p2p_ab]

        # Add the second and third constraint.
        bb.addConstraint(dof_bc)
        assert bb.getNumConstraints() == 2
        assert list(bb.iterateConstraints()) == [p2p_ab, dof_bc]
        bb.addConstraint(p2p_cd)
        assert bb.getNumConstraints() == 3
        assert bb.getConstraint(0) == p2p_ab
        assert bb.getConstraint(1) == dof_bc
        assert bb.getConstraint(2) == p2p_cd
        assert list(bb.iterateConstraints()) == [p2p_ab, dof_bc, p2p_cd]

        # Remove the middle constraint twice.
        p2p_none = Point2PointConstraint(rb_a, rb_d, pivot_b, pivot_c)
        for ii in range(2):
            bb.removeConstraint(dof_bc)
            assert bb.getNumConstraints() == 2
            assert bb.getConstraint(0) == p2p_ab
            assert bb.getConstraint(1) == p2p_cd
            assert bb.getConstraint(2) == None

            # Remove non-existing constraint.
            bb.removeConstraint(p2p_none)


class TestBroadphase:
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

    def test_broadphase_collection(self):
        def moveBody(rb, pos):
            trans = Transform()
            trans.setOrigin(pos)
            ms = DefaultMotionState()
            ms.setWorldTransform(trans)
            rb.setMotionState(ms)

        # Create two rigid bodies side by side (they *do* touch, but just).
        pos_a = Vec3(-3, 0, 0)
        pos_b = Vec3(-1, 0, 0)
        pos_c = Vec3(1, 0, 0)
        pos_d = Vec3(3, 0, 0)
        rb_a = getRB(pos=pos_a, cshape=SphereShape(1), bodyID=1)
        rb_b = getRB(pos=pos_b, cshape=SphereShape(1), bodyID=2)
        rb_c = getRB(pos=pos_c, cshape=SphereShape(1), bodyID=3)
        rb_d = getRB(pos=pos_d, cshape=SphereShape(1), bodyID=4)

        # Create a simulation, install the Broadphase Pair Cache Builder, and
        # add bodies A, B, D. The first two are touching, the last one is
        # considerably away from the others. The bodies are arranged like this:
        # "AB D"
        sim = BulletBase()
        sim.installBroadphaseCallback()
        sim.addRigidBody(rb_a)
        sim.addRigidBody(rb_b)
        sim.addRigidBody(rb_d)

        # Step the simulation and fetch the collision pairs.
        sim.azResetPairCache()
        assert sim.azReturnPairCache() == set([])
        sim.stepSimulation(1, 1)
        assert sim.azReturnPairCache() == set([(1, 2)])

        # Move the middle body towards the right.  Step the simulation again
        # (this will re-populate the broadphase cache) and verify that the
        # broadphase now returns the two objects on the right: "A  BD"
        moveBody(rb_b, pos_c)
        sim.azResetPairCache()
        sim.stepSimulation(1, 1)
        assert sim.azReturnPairCache() == set([(2, 4)])

        # Move the middle body towards the far right so that none of the bodies
        # overlap: "A D        B"
        moveBody(rb_b, Vec3(30, 0, 0))
        sim.azResetPairCache()
        sim.stepSimulation(1, 1)
        assert sim.azReturnPairCache() == set([])

        # Move the middle body back to its original position and insert the
        # fourth body. Now all bodies touch their immediate neighbours:
        # "ABCD"
        moveBody(rb_b, pos_b)
        sim.addRigidBody(rb_c)
        sim.azResetPairCache()
        sim.stepSimulation(1, 1)
        assert sim.azReturnPairCache() == set([(1, 2), (2, 3), (3, 4)])

    def test_broadphase_no_collision(self):
        """
        When the pair cache broadphase solve is active then objects must not
        collide. To test this, create a dynamic sphere above a static ground
        plane. Add both to a simulation with gravity, run the simulation, and
        verify that the sphere falls right through the ground plane.
        """
        def runSimulation(sim):
            # Create the collision shapes for the ball and ground.
            cs_ball = SphereShape(1)
            cs_ground = StaticPlaneShape(Vec3(0, 1, 0), 1)

            # Create a Rigid Body for the static (ie mass=0) Ground.
            q0 = Quaternion(0, 0, 0, 1)
            ms = DefaultMotionState(Transform(q0, Vec3(0, -1, 0)))
            ci = RigidBodyConstructionInfo(0, ms, cs_ground)
            rb_ground = RigidBody(ci, bodyID=1)
            del ms, ci

            # Create a Rigid body for the dynamic (ie mass > 0) Ball.
            ms = DefaultMotionState(Transform(q0, Vec3(0, 5, 0)))
            inertia = cs_ball.calculateLocalInertia(1)
            ci = RigidBodyConstructionInfo(1, ms, cs_ball, inertia)
            rb_ball = RigidBody(ci, bodyID=2)
            del ms, inertia, ci

            # Ensure that Bullet never deactivates the objects.
            rb_ground.forceActivationState(4)
            rb_ball.forceActivationState(4)

            # Add both bodies to the simulation.
            sim.addRigidBody(rb_ground)
            sim.addRigidBody(rb_ball)

            # Sanity check: the ball must be at position y=5
            pos = rb_ball.getMotionState().getWorldTransform().getOrigin()
            pos = pos.topy()
            assert pos[1] == 5

            # Step the simulation long enough for the ball to fall down and
            # come to rest on the plane.
            for ii in range(10):
                sim.stepSimulation(1, 100)

            # Verify that the y-position of the ball is such that the ball
            # rests on the plane.
            pos = rb_ball.getMotionState().getWorldTransform().getOrigin()
            return pos.topy()

        # Run the simulation and verify that the ball has come to rest on the
        # plane.
        sim = azBullet.BulletBase()
        sim.setGravity(Vec3(0, -10, 0))
        pos = runSimulation(sim)
        assert 0.99 < pos[1] < 1.01
        del sim, pos

        # Repeat the experiement. However, this time we will install the pair
        # cache broadphase callback which has the side effect that all
        # collisions are disabled and the ball must thus fall straight through
        # the plane.
        sim = azBullet.BulletBase()
        sim.setGravity(Vec3(0, -10, 0))
        sim.installBroadphaseCallback()
        pos = runSimulation(sim)
        assert pos[1] < -100


class TestContactGeneration:
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

    def test_getLatestContacts(self):
        def moveBody(rb, pos):
            trans = Transform()
            trans.setOrigin(pos)
            ms = DefaultMotionState()
            ms.setWorldTransform(trans)
            rb.setMotionState(ms)

        # Create two rigid bodies side by side (they *do* touch, but just).
        pos_a = Vec3(-3, 0, 0)
        pos_b = Vec3(-1, 0, 0)
        pos_c = Vec3(1, 0, 0)
        pos_d = Vec3(3, 0, 0)
        rb_a = getRB(pos=pos_a, cshape=SphereShape(1), bodyID=1)
        rb_b = getRB(pos=pos_b, cshape=SphereShape(1), bodyID=2)
        rb_c = getRB(pos=pos_c, cshape=SphereShape(1), bodyID=3)
        rb_d = getRB(pos=pos_d, cshape=SphereShape(1), bodyID=4)

        # Create a simulation and add three objects. The relative positions of
        # the objects is like this: "AB D", ie A & B are just touching, but D
        # is by itself.
        sim = BulletBase()
        sim.addRigidBody(rb_a)
        sim.addRigidBody(rb_b)
        sim.addRigidBody(rb_d)

        # Step the simulation and fetch the collision pairs.
        sim.stepSimulation(1, 1)
        ret = sim.azGetLastContacts()
        assert set(ret.keys()) == set([(1, 2)])

        # Move the middle body B towards the right so that touches D: "A  BD".
        moveBody(rb_a, pos_a)
        moveBody(rb_b, pos_c)
        moveBody(rb_d, pos_d)
        sim.stepSimulation(1, 1)
        ret = sim.azGetLastContacts()
        assert set(ret.keys()) == set([(2, 4)])

        # Move the B towards the far right so that it does not touch D at all:
        # "A  B    D".
        moveBody(rb_a, pos_a)
        moveBody(rb_b, Vec3(30, 0, 0))
        moveBody(rb_d, pos_d)
        sim.stepSimulation(1, 1)
        assert sim.azGetLastContacts() == {}

        # Move the middle body back to its original position and insert the
        # fourth body. Now all bodies touch their immediate neighbours:
        # "ABCD"
        sim.addRigidBody(rb_c)
        moveBody(rb_a, pos_a)
        moveBody(rb_b, pos_b)
        moveBody(rb_c, pos_c)
        moveBody(rb_d, pos_d)
        sim.stepSimulation(1, 1)
        ret = sim.azGetLastContacts()
        assert set(ret.keys()) == set([(1, 2), (2, 3), (3, 4)])
