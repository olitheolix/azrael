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
Provide various classes that abstract away the fact that we are using Bullet.

This module is the *one and only* module that actually imports the Bullet
engine. This will make it possible (and easier) to swap out Bullet for another
engine, should the need arise.
"""
import sys
import logging
import azrael.util
import azrael.bullet.azBullet as azBullet

import numpy as np
import azrael.config as config
import azrael.bullet_data as bullet_data

from IPython import embed as ipshell
from azrael.types import typecheck, RetVal, _MotionState
from azrael.types import CollShapeMeta, CollShapeEmpty, CollShapeSphere
from azrael.types import CollShapeBox

# Convenience.
Vec3 = azBullet.Vec3
Quaternion = azBullet.Quaternion

# Convenience.
MotionState = bullet_data.MotionState


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
        self.dynamicsWorld.setGravity(0, 0, 0)

        # Dictionary of all bodies.
        self.rigidBodies = {}

    def removeObject(self, objIDs: (list, tuple)):
        """
        Remove ``objIDs`` from Bullet and return the number of removed objects.

        Non-existing objects are not counted (and ignored).

        :param list objIDs: list of objIDs to remove.
        :return: number of actually removed objects.
        :rtype: int
        """
        cnt = 0
        # Remove every object, skipping non-existing ones.
        for objID in objIDs:
            # Skip non-existing objects.
            if objID not in self.rigidBodies:
                continue

            # Delete the object from all caches.
            del self.rigidBodies[objID]
            cnt += 1

        # Return the total number of removed objects.
        return RetVal(True, None, cnt)

    def compute(self, objIDs: (tuple, list), dt: float, max_substeps: int):
        """
        Step the simulation for all ``objIDs`` by ``dt``.

        This method aborts immediately if one or more objIDs do not exist.

        The ``max_substeps`` parameter tells Bullet the maximum allowed
        granularity. Typiclal values for ``dt`` and ``max_substeps`` are
        (1, 60).

        :param list objIDs: list of objIDs for which to update the physics.
        :param float dt: time step in seconds
        :param int max_substeps: maximum number of sub-steps.
        :return: Success
        """
        # All specified objects must exist. Abort otherwise.
        try:
            rigidBodies = [self.rigidBodies[_] for _ in objIDs]
        except KeyError as err:
            self.logit.warning('Object IDs {} do not exist'.format(err.args))
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

    def applyForceAndTorque(self, objID, force, torque):
        """
        Apply a ``force`` and ``torque`` to the center of mass of ``objID``.

        :param int objID: the ID of the object to update
        :param 3-array force: force applied directly to center of mass
        :param 3-array torque: torque around center of mass.
        :return: Success
        """
        # Sanity check.
        if objID not in self.rigidBodies:
            msg = 'Cannot set force of unknown object <{}>'.format(objID)
            self.logit.warning(msg)
            return RetVal(False, msg, None)

        # Convenience.
        body = self.rigidBodies[objID]

        # Convert the force and torque to Vec3.
        b_force = Vec3(*force)
        b_torque = Vec3(*torque)

        # Clear pending forces (should be cleared automatically by Bullet when
        # it steps the simulation) and apply the new ones.
        body.clearForces()
        body.applyCentralForce(b_force)
        body.applyTorque(b_torque)
        return RetVal(True, None, None)

    def applyForce(self, objID: int, force, rel_pos):
        """
        Apply a ``force`` at ``rel_pos`` to ``objID``.

        :param int objID: the ID of the object to update
        :param 3-array force: force applied directly to center of mass
        :param 3-array rel_pos: position of force relative to center of mass
        :return: Success
        """
        # Sanity check.
        if objID not in self.rigidBodies:
            msg = 'Cannot set force of unknown object <{}>'.format(objID)
            return RetVal(False, msg, None)

        # Convenience.
        body = self.rigidBodies[objID]

        # Convert the force and torque to Vec3.
        b_force = Vec3(*force)
        b_relpos = Vec3(*rel_pos)

        # Clear pending forces (should be cleared automatically by Bullet when
        # it steps the simulation) and apply the new ones.
        body.clearForces()
        body.applyForce(b_force, b_relpos)
        return RetVal(True, None, None)

    def getObjectData(self, objID: int):
        """
        Return State Variables of all ``objIDs``.

        This method aborts immediately if one or more objects in ``objIDs`` do
        not exists.

        :param list objIDs: the IDs of all objects to retrieve.
        :return: list of ``_MotionState`` instances.
        :rtype: list
        """
        # Abort immediately if one or more objects don't exist.
        if objID not in self.rigidBodies:
            msg = 'Cannot find object with ID <{}>'.format(objID)
            return RetVal(False, msg, None)

        # Convenience.
        body = self.rigidBodies[objID]

        # fixme: must come from collision shape
        scale = body.azrael[1].scale

        # Determine rotation and position.
        rot = body.getCenterOfMassTransform().getRotation().topy()
        pos = body.getCenterOfMassTransform().getOrigin().topy()

        # Determine linear and angular velocity.
        vLin = body.getLinearVelocity().topy()
        vRot = body.getAngularVelocity().topy()

        # Dummy value for the collision shape.
        # fixme: this must be the JSON version of collisionShape
        #        description.
        cshape = body.azrael[1].cshape

        # Linear/angular damping factors.
        axesLockLin = body.getLinearFactor().topy()
        axesLockRot = body.getAngularFactor().topy()

        # Construct a new _MotionState structure and add it to the list
        # that will eventually be returned to the caller.
        # fixme: do not use azrael[1].scale but query the scale from the
        # collisionShape object
        csname = body.getCollisionShape().getChildShape(0).getName()
        out= _MotionState(body.azrael[1].scale, body.getInvMass(),
                         body.getRestitution(), rot, pos, vLin, vRot,
                         cshape, axesLockLin, axesLockRot, 0)
        return RetVal(True, None, out)

    @typecheck
    def setObjectData(self, objID: int, obj: _MotionState):
        """
        Update State Variables of ``objID`` to ``obj``.

        Create a new object with ``objID`` if it does not yet exist.

        :param int objID: the IDs of all objects to retrieve.
        :param ``_MotionState`` obj: object description.
        :return: Success
        """
        # Create the Rigid Body if it does not exist yet.
        if objID not in self.rigidBodies:
            self.createRigidBody(objID, obj)

        # Convenience.
        body = self.rigidBodies[objID]

        # Convert orientation and position to Vec3.
        rot = Quaternion(*obj.orientation)
        pos = Vec3(*obj.position)

        # Assign body properties.
        tmp = azBullet.Transform(rot, pos)
        body.setCenterOfMassTransform(tmp)
        body.setLinearVelocity(Vec3(*obj.velocityLin))
        body.setAngularVelocity(Vec3(*obj.velocityRot))
        body.setRestitution(obj.restitution)
        body.setLinearFactor(Vec3(*obj.axesLockLin))
        body.setAngularFactor(Vec3(*obj.axesLockRot))

        # Build and assign the new collision shape, if necessary.
        old = body.azrael[1]
        if (old.scale != obj.scale) or \
           not (np.array_equal(old.cshape, obj.cshape)):
            # Create a new collision shape.
            mass, inertia, cshape = self.compileCollisionShape(objID, obj).data

            # Replace the existing collision shape with the new one.
            body.setCollisionShape(cshape)
        del old

        # Update the mass but leave the inertia intact. This is somewhat
        # awkward to implement because Bullet returns the inverse values yet
        # expects the non-inverted ones in 'set_mass_props'.
        m = obj.imass
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

        # Overwrite the old MotionState instance with the latest version.
        body.azrael = (objID, obj)
        return RetVal(True, None, None)

    def setConstraints(self, constraints: (tuple, list)):
        """
        Apply the ``constraints`` to the specified objects in the world.

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
            Compile the constraint `c` into the proper C-level Bullet object.
            """
            # Get handles to the two objects. This will raise a KeyError unless
            # both objects exist.
            rb_a = self.rigidBodies[c.rb_a]
            rb_b = self.rigidBodies[c.rb_b]

            # Construct the specified constraint type. Raise an error if the
            # constraint could not be constructed (eg the constraint name is
            # unknown).
            if c.type.upper() == 'P2P':
                out = azBullet.Point2PointConstraint(
                        rb_a, rb_b,
                        Vec3(*c.data.pivot_a),
                        Vec3(*c.data.pivot_b)
                    )
            else:
                assert False
            # Return the Bullet constraint object.
            return out

        # Compile a list of all Bullet constraints.
        try:
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
    def compileCollisionShape(self, objID: int, obj: _MotionState):
        """
        Return the correct Bullet collision shape based on ``obj``.

        This is a convenience method only.

        fixme: document return types.
        fixme: find out how to combine mass/inertia of multi body objects.

        :param int objID: object ID.
        :param _MotionState obj: Azrael's meta data that describes the body.
        :return:
        """
        # Create the compound shape that will hold all other shapes.
        compound = azBullet.CompoundShape()

        # Aggregate the total mass and inertia.
        tot_mass = 0
        tot_inertia = Vec3(0, 0, 0)

        # Create the collision shapes one by one.
        for cs in obj.cshape:
            # Convert the input data to a CollShapeMeta tuple. This is
            # necessary if the data passed to us here comes straight from the
            # database because then it it is merely a list of values, not (yet)
            # a named tuple.
            cs = CollShapeMeta(*cs)

            # Determine which CollisionShape to instantiate.
            csname = cs.type.upper()
            if csname == 'SPHERE':
                child = azBullet.SphereShape(*cs.cs)
            elif csname == 'BOX':
                child = azBullet.BoxShape(Vec3(*cs.cs))
            elif csname == 'EMPTY':
                child = azBullet.EmptyShape()
            else:
                child = azBullet.EmptyShape()
                msg = 'Unrecognised collision shape <{}>'.format(csname)
                self.logit.warning(msg)

            # Ask Bullet to compute the mass and inertia for us. The inertia will
            # be passed as a reference whereas the 'mass' is irrelevant due to how
            # the C++ function was wrapped.
            mass = 1.0 / obj.imass
            if obj.imass > 1E-4:
                # The calculate_local_inertia function will update the `inertia`
                # variable directly.
                inertia = child.calculateLocalInertia(mass)
            else:
                inertia = Vec3(0, 0, 0)

            # Compute inertia magnitude and warn about unreasonable values.
            l = np.array(inertia.topy())
            l = np.dot(l, l)
            if not (1E-5 < l < 20):
                self.logit.warning('Inertia = {:.1E}'.format(l))
            del l

            # Add the collision shape at the respective position and
            # orientation relative to the parent.
            t = azBullet.Transform(Quaternion(*cs.rot), Vec3(*cs.pos))
            compound.addChildShape(t, child)
            tot_mass += mass
            tot_inertia += inertia

        # Apply the scale.
        compound.setLocalScaling(Vec3(obj.scale, obj.scale, obj.scale))

        return RetVal(True, None, (tot_mass, tot_inertia, compound))

    @typecheck
    def createRigidBody(self, objID: int, obj: _MotionState):
        """
        Create a new rigid body ``obj`` with ``objID``.

        :param int objID: ID of new rigid body.
        :param _MotionState obj: State Variables of rigid body.
        :return: Success
        """
        # Convert orientation and position to Bullet types.
        rot = Quaternion(*obj.orientation)
        pos = Vec3(*obj.position)

        # Build the collision shape.
        ret = self.compileCollisionShape(objID, obj)
        mass, inertia, cshape = ret.data

        # Create a motion state for the initial orientation and position.
        ms = azBullet.DefaultMotionState(azBullet.Transform(rot, pos))

        # Instantiate the actual rigid body object.
        ci = azBullet.RigidBodyConstructionInfo(mass, ms, cshape, inertia)
        body = PyRigidBody(ci)

        # Set additional parameters.
        body.setFriction(1)
        body.setDamping(0.02, 0.02)
        body.setSleepingThresholds(0.1, 0.1)

        # Attach my own admin structure to the object.
        body.azrael = (objID, obj)

        # Add the rigid body to the object cache.
        self.rigidBodies[objID] = body
        return RetVal(True, None, None)
