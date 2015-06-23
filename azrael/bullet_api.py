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
import sys
import logging
import azrael.util
import azrael.bullet.azBullet as azBullet

import numpy as np
import azrael.config as config
import azrael.rb_state as rb_state

from IPython import embed as ipshell
from azrael.types import typecheck, RetVal, _RigidBodyState
from azrael.types import CollShapeMeta, CollShapeEmpty, CollShapeSphere
from azrael.types import CollShapeBox, CollShapePlane
from azrael.types import ConstraintMeta, ConstraintP2P, Constraint6DofSpring2

# Convenience.
Vec3 = azBullet.Vec3
Quaternion = azBullet.Quaternion
Transform = azBullet.Transform

# Convenience.
RigidBodyState = rb_state.RigidBodyState


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

    def applyForce(self, bodyID: int, force, rel_pos):
        """
        Apply a ``force`` at ``rel_pos`` to ``bodyID``.

        :param int bodyID: the ID of the body to update
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

    def getRigidBodyData(self, bodyID: int):
        """
        Return Body State of ``bodyID``.

        This method aborts immediately if ``bodyID`` does not exists.

        :param int bodyID: the ID of body for which to return the state.
        :return: ``_RigidBodyState`` instances.
        """
        # Abort immediately if the ID is unknown.
        if bodyID not in self.rigidBodies:
            msg = 'Cannot find body with ID <{}>'.format(bodyID)
            return RetVal(False, msg, None)

        # Convenience.
        body = self.rigidBodies[bodyID]

        # Determine rotation and position.
        rot = body.getCenterOfMassTransform().getRotation().topy()
        pos = body.getCenterOfMassTransform().getOrigin().topy()

        # Determine linear and angular velocity.
        vLin = body.getLinearVelocity().topy()
        vRot = body.getAngularVelocity().topy()

        # Linear/angular damping factors.
        axesLockLin = body.getLinearFactor().topy()
        axesLockRot = body.getAngularFactor().topy()

        # Bullet does not support scaling collision shape (actually, it does,
        # but it is frought with problems). Therefore, we may thus copy the
        # 'scale' value from the body's meta data.
        scale = body.azrael[1].scale

        # Bullet will never modify the Collision shape. We may thus use the
        # information from the body's meta data.
        cshapes = body.azrael[1].cshapes

        # Construct a new _RigidBodyState structure and add it to the list
        # that will eventually be returned to the caller.
        csname = body.getCollisionShape().getChildShape(0).getName()
        out = _RigidBodyState(scale, body.getInvMass(),
                              body.getRestitution(), rot, pos, vLin, vRot,
                              cshapes, axesLockLin, axesLockRot, 0)
        return RetVal(True, None, out)

    @typecheck
    def setRigidBodyData(self, bodyID: int, rbState: _RigidBodyState):
        """
        Update State Variables of ``bodyID`` to ``rbState``.

        Create a new body with ``bodyID`` if it does not yet exist.

        :param int bodyID: the IDs of all bodies to retrieve.
        :param ``_RigidBodyState`` rbState: body description.
        :return: Success
        """
        # Create the Rigid Body if it does not exist yet.
        if bodyID not in self.rigidBodies:
            self.createRigidBody(bodyID, rbState)

        # Convenience.
        body = self.rigidBodies[bodyID]

        # Convert orientation and position to Vec3.
        rot = Quaternion(*rbState.orientation)
        pos = Vec3(*rbState.position)

        # Assign body properties.
        tmp = azBullet.Transform(rot, pos)
        body.setCenterOfMassTransform(tmp)
        body.setLinearVelocity(Vec3(*rbState.velocityLin))
        body.setAngularVelocity(Vec3(*rbState.velocityRot))
        body.setRestitution(rbState.restitution)
        body.setLinearFactor(Vec3(*rbState.axesLockLin))
        body.setAngularFactor(Vec3(*rbState.axesLockRot))

        # Build and assign the new collision shape, if necessary.
        old = body.azrael[1]
        if (old.scale != rbState.scale) or \
           not (np.array_equal(old.cshapes, rbState.cshapes)):
            # Create a new collision shape.
            tmp = self.compileCollisionShape(bodyID, rbState)
            mass, inertia, cshapes = tmp.data
            del mass, inertia, tmp

            # Replace the existing collision shape with the new one.
            body.setCollisionShape(cshapes)
        del old

        # Update the mass but leave the inertia intact. This is somewhat
        # awkward to implement because Bullet returns the inverse values yet
        # expects the non-inverted ones in 'set_mass_props'.
        if rbState.imass == 0:
            # Static body: mass and inertia are zero anyway.
            body.setMassProps(0, Vec3(0, 0, 0))
        else:
            m = rbState.imass
            x, y, z = body.getInvInertiaDiagLocal().topy()
            if (m < 1E-10) or (x < 1E-10) or (y < 1E-10) or (z < 1E-10):
                # Use safe values if either the inertia or the mass is too small
                # for inversion.
                m = x = y = z = 1
            else:
                # Inverse mass and inertia.
                x = 1 / x
                y = 1 / y
                z = 1 / z
                m = 1 / m

            # Apply the new mass and inertia.
            body.setMassProps(m, Vec3(x, y, z))

        # Overwrite the old RigidBodyState instance with the latest version.
        body.azrael = (bodyID, rbState)
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
    def compileCollisionShape(self, bodyID: int, rbState: _RigidBodyState):
        """
        Return the correct Bullet collision shape based on ``rbState``.

        This is a convenience method only.

        fixme: find out how to combine mass/inertia of multi body bodies.

        :param int bodyID: body ID.
        :param _RigidBodyState rbState: meta data to describe the body.
        :return: compound shape with all the individual shapes.
        :rtype: ``CompoundShape``
        """
        # Create the compound shape that will hold all other shapes.
        compound = azBullet.CompoundShape()

        # Aggregate the total mass and inertia.
        tot_mass = 0
        tot_inertia = Vec3(0, 0, 0)

        # Bodies with virtually no mass will be converted to static bodies.
        # This is almost certainly not what the user wants but it is the only
        # safe option here. Note: it is the user's responsibility to ensure the
        # mass is reasonably large!
        if rbState.imass > 1E-4:
            rbState_mass = 1.0 / rbState.imass
        else:
            rbState_mass = 0

        # Create the collision shapes one by one.
        scale = rbState.scale
        for cs in rbState.cshapes:
            # Convert the input data to a CollShapeMeta tuple. This is
            # necessary if the data passed to us here comes straight from the
            # database because then it it is merely a list of values, not (yet)
            # a named tuple.
            cs = CollShapeMeta(*cs)

            # Determine which CollisionShape to instantiate, scale it
            # accordingly, and apply create it in Bullet.
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

            # Let Bullet compute the local inertia of the body.
            inertia = child.calculateLocalInertia(rbState_mass)

            # Warn about unreasonable inertia values.
            if rbState_mass > 0:
                tmp = np.array(inertia.topy())
                if not (1E-5 < np.sqrt(np.dot(tmp, tmp)) < 100):
                    msg = 'Inertia = ({:.1E}, {:.1E}, {:.1E})'
                    self.logit.warning(msg.format(*inertia.topy()))
                del tmp

            # Add the collision shape at the respective position and
            # orientation relative to the parent.
            t = azBullet.Transform(Quaternion(*cs.rotation), Vec3(*cs.position))
            compound.addChildShape(t, child)
            tot_mass += rbState_mass
            tot_inertia += inertia

        return RetVal(True, None, (tot_mass, tot_inertia, compound))

    @typecheck
    def createRigidBody(self, bodyID: int, rbState: _RigidBodyState):
        """
        Create a new rigid body ``rbState`` with ``bodyID``.

        :param int bodyID: ID of new rigid body.
        :param _RigidBodyState rbState: State Variables of rigid body.
        :return: Success
        """
        # Convert orientation and position to Bullet types.
        rot = Quaternion(*rbState.orientation)
        pos = Vec3(*rbState.position)

        # Build the collision shape.
        ret = self.compileCollisionShape(bodyID, rbState)
        mass, inertia, cshapes = ret.data

        # Create a motion state for the initial orientation and position.
        ms = azBullet.DefaultMotionState(azBullet.Transform(rot, pos))

        # Instantiate the actual rigid body.
        ci = azBullet.RigidBodyConstructionInfo(mass, ms, cshapes, inertia)
        body = PyRigidBody(ci)

        # Set additional parameters.
        body.setFriction(1)
        body.setDamping(0.02, 0.02)
        body.setSleepingThresholds(0.1, 0.1)

        # Attach my own admin structure to the body.
        body.azrael = (bodyID, rbState)

        # Add the rigid body to the body cache.
        self.rigidBodies[bodyID] = body
        return RetVal(True, None, None)
