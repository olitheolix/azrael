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

import sys
import logging
import IPython
import azrael.util

import numpy as np
import bullet as pybullet
import azrael.config as config
import azrael.bullet.bullet_data as bullet_data

from azrael.typecheck import typecheck

ipshell = IPython.embed

# Convenience.
btVector3 = pybullet.btVector3
btQuaternion = pybullet.btQuaternion
BulletData = bullet_data.BulletData
_BulletData = bullet_data._BulletData
RetVal = azrael.util.RetVal


class PyBulletPhys():
    """
    High level wrapper around the low level Bullet bindings.

    The Bullet bindings use here are courtesy of Hogni Gylfaso
    https://github.com/Klumhru/boost-python-bullet
    """
    def __init__(self, engineID: int):
        # To distinguish engines.
        self.engineID = engineID

        # Instnatiate a solver for a dynamic world.
        self.broadphase = pybullet.btDbvtBroadphase()
        self.collisionConfig = pybullet.btDefaultCollisionConfiguration()
        self.dispatcher = pybullet.btCollisionDispatcher(self.collisionConfig)
        self.solver = pybullet.btSequentialImpulseConstraintSolver()
        self.dynamicsWorld = pybullet.btDiscreteDynamicsWorld(
            self.dispatcher,
            self.broadphase,
            self.solver,
            self.collisionConfig
        )

        # Gravity is disabled by default.
        self.dynamicsWorld.gravity = pybullet.btVector3(0, 0, 0)

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
            self.dynamicsWorld.add_rigid_body(obj)
            obj.activate()

        # The max_substeps parameter instructs Bullet to subdivide the
        # specified timestep (dt) into at most max_substeps. For example, if
        # dt= 0.1 and max_substeps=10, then, internally, Bullet will simulate
        # no finer than dt / max_substeps = 0.01s.
        self.dynamicsWorld.step_simulation(dt, max_substeps)

        # Remove the object from the simulation again.
        for objID in objIDs:
            self.dynamicsWorld.remove_rigidbody(self.all_objs[objID])
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
        obj.clear_forces()
        obj.apply_central_force(b_force)
        obj.apply_torque(b_torque)
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
        obj.clear_forces()
        obj.apply_force(b_force, b_relpos)
        return RetVal(True, None, None)

    def getObjectData(self, objIDs: (list, tuple)):
        """
        Return State Variables of all ``objIDs``.

        This method aborts immediately if one or more objects in ``objIDs`` do
        not exists.

        :param list objIDs: the IDs of all objects to retrieve.
        :return: list of ``_BulletData`` instances.
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

            # Determine rotation and position.
            _ = obj.get_center_of_mass_transform().get_rotation()
            rot = [_.x, _.y, _.z, _.w]
            _ = obj.get_center_of_mass_transform().get_origin()
            pos = [_.x, _.y, _.z]

            # Determine linear and angular velocity.
            _ = obj.linear_velocity
            vLin = [_.x, _.y, _.z]
            _ = obj.angular_velocity
            vRot = [_.x, _.y, _.z]

            # Dummy value for the collision shape.
            cshape = obj.azrael[1].cshape

            # Linear/angular factors.
            _ = obj.linear_factor
            axesLockLin = [_.x, _.y, _.z]
            _ = obj.angular_factor
            axesLockRot = [_.x, _.y, _.z]

            # Construct a new _BulletData structure and add it to the list that
            # will eventually be returned to the caller.
            out.append(
                _BulletData(obj.azrael[1].scale, obj.inv_mass, obj.restitution,
                            rot, pos, vLin, vRot, cshape, axesLockLin,
                            axesLockRot, 0))
        return RetVal(True, None, out[0])

    @typecheck
    def setObjectData(self, objID: int, obj: _BulletData):
        """
        Update State Variables of ``objID`` to ``obj``.

        Create a new object with ``objID`` if it does not yet exist.

        :param int objID: the IDs of all objects to retrieve.
        :param ``_BulletData`` obj: object description.
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
        tmp = pybullet.btTransform(rot, pos)
        body.set_center_of_mass_transform(tmp)
        body.linear_velocity = btVector3(*obj.velocityLin)
        body.angular_velocity = btVector3(*obj.velocityRot)
        body.restitution = obj.restitution
        body.linear_factor = btVector3(*obj.axesLockLin)
        body.angular_factor = btVector3(*obj.axesLockRot)

        # Build and assign the new collision shape, if necessary.
        old = body.azrael[1]
        if (old.scale != obj.scale) or \
           not (np.array_equal(old.cshape, obj.cshape)):
            body.collision_shape = self.compileCollisionShape(objID, obj).data
        del old

        # Update the mass but leave the inertia intact. This is somewhat
        # awkward to implement because Bullet returns the inverse values yet
        # expects the non-inverted ones in 'set_mass_props'.
        m = obj.imass
        i = body.get_inv_inertia_diag_local()
        if (m < 1E-10) or (i.x < 1E-10) or (i.y < 1E-10) or (i.z < 1E-10):
            # Use safe values if either the inertia or the mass is too small
            # for inversion.
            m = i.x = i.y = i.z = 1
        else:
            # Inverse mass and inertia.
            i.x = 1 / i.x
            i.y = 1 / i.y
            i.z = 1 / i.z
            m = 1 / m

        # Apply the new mass and inertia.
        body.set_mass_props(m, i)

        # Overwrite the old BulletData instance with the latest version.
        body.azrael = (objID, obj)
        return RetVal(True, None, None)

    @typecheck
    def compileCollisionShape(self, objID: int, obj: _BulletData):
        """
        Return the correct Bullet collision shape based on ``obj``.

        This is a convenience method only.

        :param int objID: object ID.
        :param _BulletData obj: Azrael's meta data that describes the body.
        :return: Bullet collision shape.
        """
        # Instantiate a new collision shape.
        if obj.cshape[0] == 3:
            # Sphere.
            cshape = pybullet.btSphereShape(obj.scale)
        elif obj.cshape[0] == 4:
            # Prism.
            w, h, l = obj.scale * np.array(obj.cshape[1:]) / 2
            cshape = pybullet.btBoxShape(btVector3(w, h, l))
        else:
            # Empty- or unrecognised collision shape.
            if obj.cshape[0] != 0:
                print('Unrecognised collision shape ', obj.cshape)

            # The actual collision shape.
            cshape = pybullet.btEmptyShape()

        # Add the collision shape to a list. Albeit not explicitly used
        # anywhere this is necessary regradless to ensure the underlying points
        # are kept alive (Bullet does not own them but accesses them).
        self.collision_shapes[objID] = cshape
        return RetVal(True, None, cshape)

    @typecheck
    def createRigidBody(self, objID: int, obj: _BulletData):
        """
        Create a new rigid body ``obj`` with ``objID``.

        :param int objID: ID of new rigid body.
        :param _BulletData obj: State Variables of rigid body.
        :return: Success
        """
        # Convert orientation and position to btVector3.
        rot = btQuaternion(*obj.orientation)
        pos = btVector3(*obj.position)

        # Build the collision shape.
        ret = self.compileCollisionShape(objID, obj)
        cshape = ret.data

        # Create a motion state for the initial orientation and position.
        ms = pybullet.btDefaultMotionState(pybullet.btTransform(rot, pos))

        # Ask Bullet to compute the mass and inertia for us. The inertia will
        # be passed as a reference whereas the 'mass' is irrelevant due to how
        # the C++ function was wrapped.
        inertia = btVector3(0, 0, 0)
        mass = 1.0 / obj.imass
        if obj.imass > 1E-4:
            # The calcuate_local_inertia function will update the `inertia`
            # variable directly.
            cshape.calculate_local_inertia(mass, inertia)

        # Compute inertia magnitude and warn about unreasonable values.
        if (inertia.length > 20) or (inertia.length < 1E-5):
            print('Bullet warning: Inertia = {}'.format(inertia.length))

        # Bullet requires this admin structure to construct the rigid body.
        ci = pybullet.btRigidBodyConstructionInfo(mass, ms, cshape, inertia)

        # Instantiate the actual rigid body object.
        body = pybullet.btRigidBody(ci)

        # Set additional parameters.
        body.friction = 1
        body.set_damping(0.02, 0.02)
        body.set_sleeping_thresholds(0.1, 0.1)

        # Attach my own admin structure to the object.
        body.azrael = (objID, obj)

        # Add the rigid body to the object cache.
        self.all_objs[objID] = body

        # Add the mostion state to a list. Albeit not explicitly used anywhere
        # this is necessary regradless to ensure the underlying points are kept
        # alive (Bullet does not own them but accesses them).
        self.motion_states[objID] = ms

        return RetVal(True, None, None)
