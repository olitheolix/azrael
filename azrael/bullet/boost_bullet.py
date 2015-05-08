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

# fixme: rename boost_bullet
#        rename obj to body (and related names)
import sys
import logging
import azrael.util

import azBullet

import numpy as np
import azrael.config as config
import azrael.bullet.bullet_data as bullet_data

from IPython import embed as ipshell
from azrael.types import typecheck, RetVal, _MotionState, CollisionShape

# Convenience.
# fixme: names
btVector3 = azBullet.vec3
btQuaternion = azBullet.Quaternion
MotionState = bullet_data.MotionState

# fixme: docu
class MyRigidBody(azBullet.RigidBody):
    def __init__(self, mass, ms, cshape, inertia):
        super().__init__(mass, ms, cshape, inertia)


class PyBulletPhys():
    """
    High level wrapper around the low level Bullet bindings.

    The Bullet bindings use here are courtesy of Hogni Gylfaso
    https://github.com/Klumhru/boost-python-bullet
    """
    def __init__(self, engineID: int):
        # To distinguish engines.
        self.engineID = engineID

        # fixme: clean up
        # Instnatiate a solver for a dynamic world.
        # self.broadphase = pybullet.btDbvtBroadphase()
        # self.collisionConfig = pybullet.btDefaultCollisionConfiguration()
        # self.dispatcher = pybullet.btCollisionDispatcher(self.collisionConfig)
        # self.solver = pybullet.btSequentialImpulseConstraintSolver()
        # self.dynamicsWorld = pybullet.btDiscreteDynamicsWorld(
        #     self.dispatcher,
        #     self.broadphase,
        #     self.solver,
        #     self.collisionConfig
        # )

        # fixme: rename BulletBase
        self.dynamicsWorld = azBullet.BulletBase()

        # Disable gravity.
        self.dynamicsWorld.setGravity(0, 0, 0)

        # Not sure what this does but it was recommended at
        # http://bulletphysics.org/Bullet/phpBB3/viewtopic.php?t=9441
        # dynamicsWorld->getSolverInfo().m_solverMode |= \
        #     SOLVER_USE_2_FRICTION_DIRECTIONS

        # Dictionary of all objects.
        self.all_objs = {}

        # Auxiliary dictionary to avoid motion states and collision shapes to
        # be garbage collected because Bullet will internally only hold
        # pointers to them.
        self.motion_states = {}
        self.collision_shapes = {}

    def removeObject(self, objIDs: (list, tuple)):
        """
        Remove ``objIDs`` from Bullet and return the number of removed objects.

        Non-existing objects are ignored and not counted.

        :param list objIDs: list of objIDs to remove.
        :return: number of actually removed objects.
        :rtype: int
        """
        cnt = 0
        # Remove every object, skipping non-existing ones.
        for objID in objIDs:
            # Skip non-existing objects.
            if objID not in self.all_objs:
                continue

            # Delete the object from all caches.
            del self.all_objs[objID]
            del self.motion_states[objID]
            del self.collision_shapes[objID]
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
        # Add the objects from the cache to the Bullet simulation.
        for objID in objIDs:
            # Abort immediately if the object does not exist in the local
            if objID not in self.all_objs:
                print('Object <{}> does not exist'.format(objID))
                return RetVal(False, None, None)

        for objID in objIDs:
            # Add the body to the world and make sure it is activated, as
            # Bullet may otherwise decide to simply set its velocity to zero
            # and ignore the body.
            obj = self.all_objs[objID]
            self.dynamicsWorld.addRigidBody(obj)
            obj.forceActivationState(4)

        # The max_substeps parameter instructs Bullet to subdivide the
        # specified timestep (dt) into at most max_substeps. For example, if
        # dt= 0.1 and max_substeps=10, then, internally, Bullet will simulate
        # no finer than dt / max_substeps = 0.01s.
        self.dynamicsWorld.stepSimulation(dt, max_substeps)

        # Remove the object from the simulation again.
        for objID in objIDs:
            self.dynamicsWorld.removeRigidBody(self.all_objs[objID])
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
        if objID not in self.all_objs:
            print('Cannot set force of unknown object <{}>'.format(objID))
            return RetVal(False, None, None)

        # Convenience.
        obj = self.all_objs[objID]

        # Convert the force and torque to btVector3.
        b_force = btVector3(*force)
        b_torque = btVector3(*torque)

        # Clear pending forces (should be cleared automatically by Bullet when
        # it steps the simulation) and apply the new ones.
        obj.clearForces()
        obj.applyCentralForce(b_force)
        obj.applyTorque(b_torque)
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
        if objID not in self.all_objs:
            msg = 'Cannot set force of unknown object <{}>'.format(objID)
            return RetVal(False, msg, None)

        # Convenience.
        obj = self.all_objs[objID]

        # Convert the force and torque to btVector3.
        b_force = btVector3(*force)
        b_relpos = btVector3(*rel_pos)

        # Clear pending forces (should be cleared automatically by Bullet when
        # it steps the simulation) and apply the new ones.
        obj.clearForces()
        obj.applyForce(b_force, b_relpos)
        return RetVal(True, None, None)

    def getObjectData(self, objIDs: (list, tuple)):
        """
        Return State Variables of all ``objIDs``.

        This method aborts immediately if one or more objects in ``objIDs`` do
        not exists.

        :param list objIDs: the IDs of all objects to retrieve.
        :return: list of ``_MotionState`` instances.
        :rtype: list
        """
        out = []

        # Compile a list of object attributes.
        for objID in objIDs:
            # Abort immediately if one or more objects don't exist.
            if objID not in self.all_objs:
                msg = 'Cannot find object with ID <{}>'.format(objID)
                return RetVal(False, msg, None)

            # Convenience.
            obj = self.all_objs[objID]
            scale = obj.azrael[1].scale

            # fixme: clean up below
            # Determine rotation and position.
            _ = obj.getCenterOfMassTransform().getRotation()
#            rot = [_.x, _.y, _.z, _.w]
            rot = _.tolist()
            _ = obj.getCenterOfMassTransform().getOrigin()
#            pos = [_.x, _.y, _.z]
            pos = _.tolist()

            # Determine linear and angular velocity.
            _ = obj.getLinearVelocity()
#            vLin = [_.x, _.y, _.z]
            vLin = _.tolist()
            _ = obj.getAngularVelocity()
#            vRot = [_.x, _.y, _.z]
            vRot = _.tolist()

            # Dummy value for the collision shape.
            # fixme: this must be the JSON version of collisionShape description
            cshape = obj.azrael[1].cshape

            # Linear/angular factors.
            _ = obj.getLinearFactor()
#            axesLockLin = [_.x, _.y, _.z]
            axesLockLin = _.tolist()

            _ = obj.getAngularFactor()
#            axesLockRot = [_.x, _.y, _.z]
            axesLockRot = _.tolist()

            # Construct a new _MotionState structure and add it to the list
            # that will eventually be returned to the caller.
            # fixme: do not use azrael[1].scale but query the scale from the
            # collisionShape object
            csname = obj.getCollisionShape().getName()
            cs2 = CollisionShape(csname.decode('utf8'), None)
            out.append(
                _MotionState(obj.azrael[1].scale, obj.getInvMass(),
                             obj.getRestitution(), rot, pos, vLin, vRot, cshape,
                             axesLockLin, axesLockRot, 0, cs2))
        return RetVal(True, None, out[0])

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
        if objID not in self.all_objs:
            self.createRigidBody(objID, obj)

        # Convenience.
        body = self.all_objs[objID]

        # Convert orientation and position to btVector3.
        rot = btQuaternion(*obj.orientation)
        pos = btVector3(*obj.position)

        # Assign body properties.
        tmp = azBullet.Transform(rot, pos)
        body.setCenterOfMassTransform(tmp)
        body.setLinearVelocity(btVector3(*obj.velocityLin))
        body.setAngularVelocity(btVector3(*obj.velocityRot))
        body.setRestitution(obj.restitution)
        body.setLinearFactor(btVector3(*obj.axesLockLin))
        body.setAngularFactor(btVector3(*obj.axesLockRot))

        # Build and assign the new collision shape, if necessary.
        old = body.azrael[1]
        if (old.scale != obj.scale) or \
           not (np.array_equal(old.cshape, obj.cshape)):
            # fixme: why is there an "body.azrael[1].cshape" and another
            # "body.collision_shape"?
            # fixme: the new collision shape must be applied with
            # "body.setCollisionShape" method.
            # fixme: the current tests for changing the scale and/or shape are rubbish.
            self.compileCollisionShape(objID, obj).data
            body.setCollisionShape(self.collision_shapes[objID])
        del old

        # Update the mass but leave the inertia intact. This is somewhat
        # awkward to implement because Bullet returns the inverse values yet
        # expects the non-inverted ones in 'set_mass_props'.
        m = obj.imass
        x, y, z = body.getInvInertiaDiagLocal().tolist()
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
        body.setMassProps(m, btVector3(x, y, z))

        # Overwrite the old MotionState instance with the latest version.
        body.azrael = (objID, obj)
        return RetVal(True, None, None)

    @typecheck
    def compileCollisionShape(self, objID: int, obj: _MotionState):
        """
        Return the correct Bullet collision shape based on ``obj``.

        This is a convenience method only.

        :param int objID: object ID.
        :param _MotionState obj: Azrael's meta data that describes the body.
        :return: Bullet collision shape.
        """
        # Instantiate a new collision shape.
        scale = btVector3(obj.scale, obj.scale, obj.scale)
        if obj.cshape[0] == 3:
            # Sphere.
            cshape = azBullet.SphereShape(1)
        elif obj.cshape[0] == 4:
            # Prism.
            w, h, l = np.array(obj.cshape[1:]) / 2
            cshape = azBullet.BoxShape(btVector3(w, h, l))
        else:
            # Empty- or unrecognised collision shape.
            if obj.cshape[0] != 0:
                print('Unrecognised collision shape ', obj.cshape)

            # The actual collision shape.
            cshape = azBullet.EmptyShape()

        # Apply the scale.
        cshape.setLocalScaling(scale)

        # Add the collision shape to a list. Albeit not explicitly used
        # anywhere this is necessary regardless to ensure the underlying pointers
        # are kept alive (Bullet only accesse them but does not own them).
        self.collision_shapes[objID] = cshape
        return RetVal(True, None, cshape)

    @typecheck
    def createRigidBody(self, objID: int, obj: _MotionState):
        """
        Create a new rigid body ``obj`` with ``objID``.

        :param int objID: ID of new rigid body.
        :param _MotionState obj: State Variables of rigid body.
        :return: Success
        """
        # Convert orientation and position to btVector3.
        rot = btQuaternion(*obj.orientation)
        pos = btVector3(*obj.position)

        # Build the collision shape.
        ret = self.compileCollisionShape(objID, obj)
        cshape = ret.data

        # Create a motion state for the initial orientation and position.
        ms = azBullet.DefaultMotionState(azBullet.Transform(rot, pos))

        # Ask Bullet to compute the mass and inertia for us. The inertia will
        # be passed as a reference whereas the 'mass' is irrelevant due to how
        # the C++ function was wrapped.
        inertia = btVector3(0, 0, 0)
        mass = 1.0 / obj.imass
        if obj.imass > 1E-4:
            # The calcuate_local_inertia function will update the `inertia`
            # variable directly.
            cshape.calculateLocalInertia(mass, inertia)

        # Compute inertia magnitude and warn about unreasonable values.
        l = np.array(inertia.tolist())
        l = np.dot(l, l)
        if not (1E-5 < l < 20):
            print('Bullet warning: Inertia = {}'.format(l))
        del l

        # Instantiate the actual rigid body object.
        body = MyRigidBody(mass, ms, cshape, inertia)

        # Set additional parameters.
        body.setFriction(1)
        body.setDamping(0.02, 0.02)
        body.setSleepingThresholds(0.1, 0.1)

        # Attach my own admin structure to the object.
        body.azrael = (objID, obj)

        # Add the rigid body to the object cache.
        self.all_objs[objID] = body

        # Add the mostion state to a list. Albeit not explicitly used anywhere
        # this is necessary regradless to ensure the underlying points are kept
        # alive (Bullet does not own them but accesses them).
        self.motion_states[objID] = ms

        return RetVal(True, None, None)
