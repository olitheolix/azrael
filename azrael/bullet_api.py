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
"""
Provide classes to create-, modify- and query dynamic simulations. The classes
abstract away the particular physics engine (currently Bullet) used underneath.

This module is the *one and only* module that actually imports the Bullet
engine (ie the wrapper called `azBullet`). This will make it easier to swap out
Bullet for another engine at some point, should the need arise.
"""
import logging
import numpy as np

# Attempt to import the locally compiled version of azBullet first. If it does
# not exist (typically the case inside a Docker container) then import the
# system wide one.
try:
    import azrael.bullet.azBullet as azBullet
except ImportError:
    import azBullet

from IPython import embed as ipshell
from azrael.aztypes import typecheck, RetVal, _RigidBodyData, RbStateUpdate
from azrael.aztypes import ConstraintMeta, ConstraintP2P, Constraint6DofSpring2
from azrael.aztypes import CollShapeMeta, CollShapeSphere, CollShapeBox, CollShapePlane

# Convenience.
Vec3 = azBullet.Vec3
Quaternion = azBullet.Quaternion
Transform = azBullet.Transform


class PyRigidBody(azBullet.RigidBody):
    """
    Wrapper around RigidBody class.

    The original azBullet.RigidBody class cannot be extended since it is a
    compiled module. However, by subclassing it we get the convenience of
    a pure Python class (eg adding attributes at runtime). This is transparent
    to the end user.
    """
    def __init__(self, ci):
        super().__init__(ci)


def bullet2azrael(bt_pos: Vec3, bt_rot: Quaternion, com_ofs: list):
    """
    Return the Azrael object position for the compound shape.

    pos_new = bt_pos - bt_rot * com_ofs
    """
    # Use Bullet's Transform class to apply the Quaternion bt_rot.
    rot = Transform(bt_rot, Vec3(0, 0, 0))
    bt_pos = bt_pos - rot * Vec3(*com_ofs)
    return bt_pos.topy(), bt_rot.topy()


def azrael2bullet(az_pos: list, az_rot: list, com_ofs: list):
    """
    Return the compound shape transform for the Azrael object.

    pos_new = az_pos + az_rot * com_ofs
    """
    # Use Bullet's Transform class to apply the Quaternion bt_rot.
    az_rot = Quaternion(*az_rot)
    rot = Transform(az_rot, Vec3(0, 0, 0))
    az_pos = Vec3(*az_pos) + rot * Vec3(*com_ofs)
    return az_pos, az_rot


class PyBulletDynamicsWorld():
    """
    High level wrapper around the low level Bullet bindings.
    """
    def __init__(self, engineID: int):
        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

        # To distinguish engines.
        self.engineID = engineID

        # Create a standard Bullet Dynamics World.
        self.dynamicsWorld = azBullet.BulletBase()

        # Disable gravity.
        self.dynamicsWorld.setGravity(Vec3(0, 0, 0))

        # Dictionary of all bodies.
        self.rigidBodies = {}

    def setGravity(self, gravity: (tuple, list)):
        """
        Set the ``gravity`` in the simulation.
        """
        try:
            gravity = np.array(gravity, np.float64)
            assert gravity.ndim == 1
            assert len(gravity) == 3
        except (TypeError, ValueError, AssertionError):
            return RetVal(False, 'Invalid type', None)
        self.dynamicsWorld.setGravity(Vec3(*gravity))
        return RetVal(True, None, None)

    def removeRigidBody(self, bodyIDs: (list, tuple)):
        """
        Remove ``bodyIDs`` from Bullet and return the number of removed bodies.

        Non-existing bodies are not counted (and ignored).

        :param list bodyIDs: list of bodyIDs to remove.
        :return: number of actually removed bodies.
        :rtype: int
        """
        cnt = 0
        # Remove every body, skipping non-existing ones.
        for bodyID in bodyIDs:
            # Skip non-existing bodies.
            if bodyID not in self.rigidBodies:
                continue

            # Delete the body from all caches.
            del self.rigidBodies[bodyID]
            cnt += 1

        # Return the total number of removed bodies.
        return RetVal(True, None, cnt)

    def compute(self, bodyIDs: (tuple, list), dt: float, max_substeps: int):
        """
        Step the simulation for all ``bodyIDs`` by ``dt``.

        This method aborts immediately if one or more bodyIDs do not exist.

        The ``max_substeps`` parameter tells Bullet the maximum allowed
        granularity. Typiclal values for ``dt`` and ``max_substeps`` are
        (1, 60).

        :param list bodyIDs: list of bodyIDs for which to update the physics.
        :param float dt: time step in seconds
        :param int max_substeps: maximum number of sub-steps.
        :return: Success
        """
        # All specified bodies must exist. Abort otherwise.
        try:
            rigidBodies = [self.rigidBodies[_] for _ in bodyIDs]
        except KeyError as err:
            self.logit.warning('Body IDs {} do not exist'.format(err.args))
            return RetVal(False, None, None)

        # Add the body to the world and make sure it is activated, as
        # Bullet may otherwise decide to simply set its velocity to zero
        # and ignore the body.
        for body in rigidBodies:
            self.dynamicsWorld.addRigidBody(body)
            body.forceActivationState(4)

        # The max_substeps parameter instructs Bullet to subdivide the
        # specified timestep (dt) into at most max_substeps. For example, if
        # dt= 0.1 and max_substeps=10, then, internally, Bullet will simulate
        # no finer than dt / max_substeps = 0.01s.
        self.dynamicsWorld.stepSimulation(dt, max_substeps)

        # Remove all bodies from the simulation again.
        for body in rigidBodies:
            self.dynamicsWorld.removeRigidBody(body)
        return RetVal(True, None, None)

    def applyForceAndTorque(self, bodyID, force, torque):
        """
        Apply a ``force`` and ``torque`` to the center of mass of ``bodyID``.

        :param int bodyID: the ID of the body to update
        :param 3-array force: force applied directly to center of mass
        :param 3-array torque: torque around center of mass.
        :return: Success
        """
        # Sanity check.
        if bodyID not in self.rigidBodies:
            msg = 'Cannot set force of unknown body <{}>'.format(bodyID)
            self.logit.warning(msg)
            return RetVal(False, msg, None)

        # Convenience.
        body = self.rigidBodies[bodyID]

        # Convert the force and torque to Vec3.
        b_force = Vec3(*force)
        b_torque = Vec3(*torque)

        # Clear pending forces (should be cleared automatically by Bullet when
        # it steps the simulation) and apply the new ones.
        body.clearForces()
        body.applyCentralForce(b_force)
        body.applyTorque(b_torque)
        return RetVal(True, None, None)

    def applyForce(self, bodyID: str, force, rel_pos):
        """
        Apply a ``force`` at ``rel_pos`` to ``bodyID``.

        :param str bodyID: the ID of the body to update
        :param 3-array force: force applied directly to center of mass
        :param 3-array rel_pos: position of force relative to center of mass
        :return: Success
        """
        # Sanity check.
        if bodyID not in self.rigidBodies:
            msg = 'Cannot set force of unknown body <{}>'.format(bodyID)
            return RetVal(False, msg, None)

        # Convenience.
        body = self.rigidBodies[bodyID]

        # Convert the force and torque to Vec3.
        b_force = Vec3(*force)
        b_relpos = Vec3(*rel_pos)

        # Clear pending forces (should be cleared automatically by Bullet when
        # it steps the simulation) and apply the new ones.
        body.clearForces()
        body.applyForce(b_force, b_relpos)
        return RetVal(True, None, None)

    def setConstraints(self, constraints: (tuple, list)):
        """
        Apply the ``constraints`` to the specified bodies in the world.

        If one or more of the rigid bodies specified in any of the constraints
        do not exist then this method will abort. Similarly, it will also abort
        if one or more constraints could not be constructed for whatever
        reason (eg. unknown constraint name).

        In any case, this function will either apply all constraints or none.
        It is not possible that this function applies only some constraints.

        :param list constraints: list of `ConstraintMeta` instances.
        :return: Success
        """
        def _buildConstraint(c):
            """
            Compile the constraint `c` into the proper C-level Bullet body.
            """
            # Get handles to the two bodies. This will raise a KeyError unless
            # both bodies exist.
            rb_a = self.rigidBodies[c.rb_a]
            rb_b = self.rigidBodies[c.rb_b]

            # Construct the specified constraint type. Raise an error if the
            # constraint could not be constructed (eg the constraint name is
            # unknown).
            if c.contype.upper() == 'P2P':
                tmp = ConstraintP2P(*c.condata)
                out = azBullet.Point2PointConstraint(
                    rb_a, rb_b,
                    Vec3(*tmp.pivot_a),
                    Vec3(*tmp.pivot_b)
                )
            elif c.contype.upper() == '6DOFSPRING2':
                t = Constraint6DofSpring2(*c.condata)
                fa, fb = t.frameInA, t.frameInB
                frameInA = Transform(Quaternion(*fa[3:]), Vec3(*fa[:3]))
                frameInB = Transform(Quaternion(*fb[3:]), Vec3(*fb[:3]))
                out = azBullet.Generic6DofSpring2Constraint(
                    rb_a, rb_b, frameInA, frameInB
                )
                out.setLinearLowerLimit(Vec3(*t.linLimitLo))
                out.setLinearUpperLimit(Vec3(*t.linLimitHi))
                out.setAngularLowerLimit(Vec3(*t.rotLimitLo))
                out.setAngularUpperLimit(Vec3(*t.rotLimitHi))
                for ii in range(6):
                    if not t.enableSpring[ii]:
                        out.enableSpring(ii, False)
                        continue
                    out.enableSpring(ii, True)
                    out.setStiffness(ii, t.stiffness[ii])
                    out.setDamping(ii, t.damping[ii])
                    out.setEquilibriumPoint(ii, t.equilibrium[ii])

                for ii in range(3):
                    out.setBounce(ii, t.bounce[ii])
            else:
                assert False

            # Return the Bullet constraint body.
            return out

        # Compile a list of all Bullet constraints.
        try:
            constraints = [ConstraintMeta(*_) for _ in constraints]
            out = [_buildConstraint(_) for _ in constraints]
        except (TypeError, AttributeError, KeyError, AssertionError):
            return RetVal(False, 'Could not compile all Constraints.', None)

        # Apply the constraints.
        fun = self.dynamicsWorld.addConstraint
        for c in out:
            fun(c)

        # All went well.
        return RetVal(True, None, None)

    def clearAllConstraints(self):
        """
        Remove all constraints from the simulation.

        :return: success
        """
        # Convenience.
        world = self.dynamicsWorld

        # Return immediately if the world has no constraints to remove.
        if world.getNumConstraints() == 0:
            return RetVal(True, None, None)

        # Iterate over all constraints and remove them.
        for c in world.iterateConstraints():
            world.removeConstraint(c)

        # Verify that the number of constraints is now zero.
        if world.getNumConstraints() != 0:
            return RetVal(False, 'Bug: #constraints must now be zero', None)
        else:
            return RetVal(True, None, None)

    @typecheck
    def compileCollisionShape(self, rbState: _RigidBodyData):
        """
        Return the correct Bullet collision shape based on ``rbState``.

        The position of all collision shapes will be automatically corrected to
        be relative to the center of mass argument ``com_ofs``.

        This is a convenience method only.

        :param _RigidBodyData rbState: meta data to describe the body.
        :return: compound shape with all the individual shapes.
        :rtype: ``CompoundShape``
        """
        # Create the compound shape that will hold all other shapes.
        compound = azBullet.CompoundShape()

        # Compute the inverse COT.
        # fixme: quaternion should normalise automatically
        paxis = Quaternion(*rbState.paxis)
        paxis.normalize()
        cot = Transform(paxis, Vec3(*rbState.com))
        i_cot = cot.inverse()

        # Create the collision shapes one by one.
        scale = rbState.scale
        for cs in rbState.cshapes.values():
            # Convert the input data (usually a list of values) to a
            # proper CollShapeMeta tuple (sanity checks included).
            cs = CollShapeMeta(*cs)

            # Instantiate the specified collision shape.
            cstype = cs.cstype.upper()
            if cstype == 'SPHERE':
                sphere = CollShapeSphere(*cs.csdata)
                child = azBullet.SphereShape(scale * sphere.radius)
            elif cstype == 'BOX':
                box = CollShapeBox(*cs.csdata)
                hl = Vec3(scale * box.x, scale * box.y, scale * box.z)
                child = azBullet.BoxShape(hl)
            elif cstype == 'EMPTY':
                child = azBullet.EmptyShape()
            elif cstype == 'PLANE':
                # Planes are always static.
                rbState_mass = 0
                plane = CollShapePlane(*cs.csdata)
                normal = Vec3(*plane.normal)
                child = azBullet.StaticPlaneShape(normal, plane.ofs)
            else:
                child = azBullet.EmptyShape()
                msg = 'Unrecognised collision shape <{}>'.format(cstype)
                self.logit.warning(msg)

            # Determine the transform with respect to the center of mass. Then
            # pre-multiply it with the principal axis of inertia (the rigid
            # body will apply the inverse to undo the effect). This ensures the
            # applied torque will be properly aligned with the principal axis.
            # fixme: rename COT to something else, maybe aligned_center_of_mass
            # (ACOT)?
            t = Transform(Quaternion(*cs.rotation), Vec3(*cs.position))
            t = i_cot * t

            # Add the child with the correct transform.
            compound.addChildShape(t, child)

        return RetVal(True, None, compound)

    @typecheck
    def createRigidBody(self, bodyID: str, rbState: _RigidBodyData):
        """
        Return a new rigid body based on ``rbState`` with ``bodyID``.

        :param str bodyID: ID of new rigid body.
        :param _RigidBodyData rbState: State Variables of rigid body.
        :return: Success
        """
        # Bodies with virtually no mass will be converted to static bodies.
        # This is almost certainly not what the user wants but it is the only
        # safe option here. Note: it is the user's responsibility to ensure the
        # mass is reasonably large!
        if rbState.imass > 1E-4:
            mass = 1.0 / rbState.imass
        else:
            mass = 0

        # Warn about unreasonable inertia values.
        # fixme: what to do about this?
        if mass > 0:
            tmp = np.array(rbState.inertia)
            if not (1E-5 < np.sqrt(np.dot(tmp, tmp)) < 100):
                msg = 'Inertia = ({:.1E}, {:.1E}, {:.1E})'
                msg = msg.format(*tmp)
                self.logit.warning(msg)
                return RetVal(False, msg, None)

        # Build the collision shape.
        ret = self.compileCollisionShape(rbState)
        compound = ret.data

        # Instantiate the rigid body and specify its mass, motion state,
        # collision shapes, and inertia.
        # fixme: mention that all values are neutral; setRigidBody will
        # actually set them. Can I simplify this method further?
        ci = azBullet.RigidBodyConstructionInfo(
            mass,
            azBullet.DefaultMotionState(Transform()),
            compound,
            Vec3(*rbState.inertia)
        )
        body = PyRigidBody(ci)

        # Set additional parameters.
        body.setFriction(0.1)
        body.setDamping(0.02, 0.02)
        body.setSleepingThresholds(0.1, 0.1)

        # Attach my own admin structure to the body.
        body.azrael = {'rbState': rbState}

        # Return the new body.
        return RetVal(True, None, body)

    def getRigidBodyData(self, bodyID: str):
        """
        Return latest body state (pos, rot, vLin, vRot) of ``bodyID``.

        Return with an error if ``bodyID`` does not exist.

        :param str bodyID: the ID of body for which to return the state.
        :return: ``RbStateUpdate`` instances.
        """
        # Abort immediately if the ID is unknown.
        if bodyID not in self.rigidBodies:
            msg = 'Cannot find body with ID <{}>'.format(bodyID)
            return RetVal(False, msg, None)

        # Convenience.
        body = self.rigidBodies[bodyID]
        rbState = body.azrael['rbState']

        # Get the transform (ie. position and rotation) of the compound shape.
        t = body.getCenterOfMassTransform()
        rot, pos = t.getRotation(), t.getOrigin()

        # Undo the rotation that is purely due to the alignment with the ineria
        # axis so that Bullet can apply the moments of inertia directly.
        # fixme: Quaternions should automatically normalise
        paxis = Quaternion(*rbState.paxis)
        paxis.normalize()
        rot = paxis.inverse() * rot
        del t, paxis

        # The object position does not match the position of the rigid body
        # unless the center of mass is (0, 0, 0). Here we correct it.
        pos, rot = bullet2azrael(pos, rot, body.azrael['rbState'].com)

        # Determine linear and angular velocity.
        vLin = body.getLinearVelocity().topy()
        vRot = body.getAngularVelocity().topy()

        # Put the result into a named tuple and return it.
        out = RbStateUpdate(pos, rot, vLin, vRot)
        return RetVal(True, None, out)

    @typecheck
    def setRigidBodyData(self, bodyID: str, rbState: _RigidBodyData):
        """
        Update State Variables of ``bodyID`` to ``rbState``.

        Create a new body with ``bodyID`` if it does not yet exist.

        :param str bodyID: the IDs of all bodies to retrieve.
        :param ``_RigidBodyData`` rbState: body description.
        :return: Success
        """
        paxis = Quaternion(*rbState.paxis)
        paxis.normalize()
        cot = Transform(paxis, Vec3(*rbState.com))
        del paxis

        # Create the rigid body if it does not exist yet.
        if bodyID not in self.rigidBodies:
            ret = self.createRigidBody(bodyID, rbState)
            if ret.ok:
                self.rigidBodies[bodyID] = ret.data

        # Convenience.
        body = self.rigidBodies[bodyID]

        # Convert rotation and position to Vec3.
        # fixme: this is now void
        pos, rot = azrael2bullet(rbState.position, rbState.rotation, [0, 0, 0])

        # The shapes inside the compound have all been transformed with the
        # inverse COT. Here we undo this transformation by applying the COT
        # again. The net effect in terms of collision shape positions is zero.
        # However, by undoing the COT on every shape *inside* the compound it
        # has overall become aligned with the principal axis of all those
        # shapes. This, in turn, is what Bullet implicitly assumes when it
        # computes angular movement. This is also the reason why the inertia
        # Tensor has only 3 elements instead of being a 3x3 matrix. Yes, I know
        # this is confusing.
        t = Transform(rot, pos) * cot

        # Assign body properties.
        body.setCenterOfMassTransform(t)
        body.setLinearVelocity(Vec3(*rbState.velocityLin))
        body.setAngularVelocity(Vec3(*rbState.velocityRot))
        body.setRestitution(rbState.restitution)
        body.setLinearFactor(Vec3(*rbState.axesLockLin))
        body.setAngularFactor(Vec3(*rbState.axesLockRot))
        del t

        # Build and assign the new collision shape if they have changed.
        # fixme: also build a new compund if paxis has changed.
        old = body.azrael['rbState']
        new_cs = not np.array_equal(old.cshapes, rbState.cshapes)
        new_scale = (old.scale != rbState.scale)
        if new_cs or new_scale:
            # Create a new collision shape.
            ret = self.compileCollisionShape(rbState)

            # Replace the existing collision shape with the new one.
            body.setCollisionShape(ret.data)
        del old, new_cs, new_scale

        # Set mass and inertia.
        if rbState.imass < 1E-5:
            # Static body: mass and inertia are zero anyway.
            body.setMassProps(0, Vec3(0, 0, 0))
        else:
            imass = 1 / rbState.imass
            inertia = Vec3(*rbState.inertia)

            # Apply the new mass and inertia.
            body.setMassProps(imass, inertia)
            del imass, inertia

        # Attach a copy of the rbState structure to the rigid body.
        body.azrael = {'rbState': rbState}
        return RetVal(True, None, None)
