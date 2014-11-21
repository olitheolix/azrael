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

from collections import namedtuple
from azrael.typecheck import typecheck
from azrael.protocol_json import loads, dumps

ipshell = IPython.embed

# Convenience.
btVector3 = pybullet.btVector3
btQuaternion = pybullet.btQuaternion
BulletData = bullet_data.BulletData


class PyBulletPhys():
    def __init__(self, engineID: int):
        self.engineID = engineID

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
        self.dynamicsWorld.gravity = pybullet.btVector3(0, 0, 0)

        # Not sure what this does but it was recommended at
        # http://bulletphysics.org/Bullet/phpBB3/viewtopic.php?t=9441
        # dynamicsWorld->getSolverInfo().m_solverMode |= \
        #     SOLVER_USE_2_FRICTION_DIRECTIONS

        self.all_objs = {}
        self.motion_states = {}
        self.collision_shapes = {}

    def removeObject(self, objIDs: (list, tuple)):
        cnt = 0
        for objID in objIDs:
            if objID not in self.all_objs:
                continue
            del self.all_objs[objID]
            del self.motion_states[objID]
            del self.collision_shapes[objID]
            cnt += 1
        return cnt
        
    def compute(self, objIDs, delta_t, max_substeps):
        # Add the objects from the cache to the Bullet simulation.
        for objID in objIDs:
            # Abort immediately if the object does not exist in the local
            if objID not in self.all_objs:
                print('Object <{}> does not exist'.format(objID))
                return 1

        for objID in objIDs:
            # Add the body to the world and make sure it is activated, as
            # Bullet may otherwise decide to simply set its velocity to zero
            # and ignore the body.
            obj = self.all_objs[objID]
            self.dynamicsWorld.add_rigid_body(obj)
            obj.activate()
        
        # The max_substeps parameter instructs Bullet to subdivide the specified
        # timestep (delta_t) into at most max_substeps. For example, if
        # delta_t = 0.1 and max_substeps=10, then, internally, Bullet will
        # simulate no finer than delta_t / max_substeps = 0.01s.
        self.dynamicsWorld.step_simulation(delta_t, max_substeps)
        
        # Remove the object from the simulation again.
        for objID in objIDs:
            self.dynamicsWorld.remove_rigidbody(self.all_objs[objID])
        
    def applyForceAndTorque(self, objID, force, torque):
        if objID not in self.all_objs:
            print('Cannot set force of unknown object <{}>'.format(objID))
            return 1

        obj = self.all_objs[objID]
        b_force = btVector3(*force)
        b_torque = btVector3(*torque)
        obj.clear_forces()
        obj.apply_central_force(b_force)
        obj.apply_torque(b_torque)

    def applyForce(self, objID, force, rel_pos):
        if objID not in self.all_objs:
            print('Cannot set force of unknown object <{}>'.format(objID))
            return 1

        obj = self.all_objs[objID]
        b_force = btVector3(*force)
        b_relpos = btVector3(*rel_pos)
        obj.clear_forces()
        obj.apply_force(b_force, b_relpos)

    def getObjectData(self, IDs: (list, tuple)):
        out = []
        for objID in IDs:
            if objID not in self.all_objs:
                print('Cannot find object with ID <{}>'.format(objID))
                return 1, []

            obj = self.all_objs[objID]
            _, radius, scale = obj.azrael

            # Determine rotation and position.
            _ = obj.get_center_of_mass_transform().get_rotation()
            rot = np.array([_.x, _.y, _.z, _.w], np.float64)
            _ = obj.get_center_of_mass_transform().get_origin()
            pos = np.array([_.x, _.y, _.z], np.float64)

            # Determine linear and angular velocity.
            _ = obj.linear_velocity
            vLin = np.array([_.x, _.y, _.z], np.float64)
            _ = obj.angular_velocity
            vRot = np.array([_.x, _.y, _.z], np.float64)

            # Dummy value for the collision shape.
            cshape = np.zeros(4, np.float64)
            out.append(BulletData(radius, scale, obj.inv_mass, obj.restitution,
                        rot, pos, vLin, vRot, cshape))
        return 0, out[0]

    def setObjectData(self, IDs: (list, tuple), obj):
        objID = IDs[0]

        rot = btQuaternion(*obj.orientation)
        pos = btVector3(*obj.position)

        # Assign the inverse mass.
        new_inv_mass = float(obj.imass)

        if objID in self.all_objs:
            # Object already downloaded --> just update.
            tmp = pybullet.btTransform(rot, pos)
            body = self.all_objs[objID]
            body.set_center_of_mass_transform(tmp)
            body.linear_velocity = btVector3(*obj.velocityLin)
            body.angular_velocity = btVector3(*obj.velocityRot)
            body.friction = 1
            body.restitution = obj.restitution
            body.azrael = (objID, obj.radius, obj.scale)
            m = obj.imass
            i = body.get_inv_inertia_diag_local()
            i.z = 1 / i.z
            i.z = 1 / i.z
            i.z = 1 / i.z
            body.set_mass_props(1 / m, i)
            return True
        
        # Instantiate a new collision shape.
        if obj.cshape[0] == 3:
            cshape = pybullet.btSphereShape(obj.scale * obj.radius)
        elif obj.cshape[0] == 4:
            width = obj.scale * obj.cshape[1] / 2
            height = obj.scale * obj.cshape[2] / 2
            length = obj.scale * obj.cshape[3] / 2
            cshape = pybullet.btBoxShape(btVector3(width, height, length))
        else:
            if obj.cshape[0] != 0:
                print('Unrecognised collision shape ', obj.cshape)
            cshape = pybullet.btEmptyShape()

            # Ensure the object cannot collide (strange things will happen
            # otherwise once Bullet tries to estimate the inertia for an empty
            # shape).
            new_inv_mass = 0.0

        # Create a motion state for the initial orientation and position.
        ms = pybullet.btDefaultMotionState(pybullet.btTransform(rot, pos))

        # Add the collision shape and motion state to the local cache. Neither
        # is explicitly used anymore but the pointers are were passed to Bullet
        # calls and Bullet did not make a copy of it. Therefore, we have to
        # keep a reference to them alive as the smart pointer logic would
        # otherwise remove it.
        self.collision_shapes[objID] = cshape
        self.motion_states[objID] = ms

        # Ask Bullet to compute the mass and inertia for us.
        inertia = btVector3(0, 0, 0)
        mass = 0
        if new_inv_mass > 1E-4:
          # The calcuate_local_inertia function will update the `inertia`
          # variable directly.
          mass = 1.0 / new_inv_mass
          cshape.calculate_local_inertia(mass, inertia)

        # Compute inertia magnitude and warn about unreasonable values.
        if (inertia.length > 20) or (inertia.length < 1E-5):
            print('Bullet warning: Inertia = {}'.format(inertia.length))
        
        # Instantiate the admin structure for the rigid object.
        body_CI = pybullet.btRigidBodyConstructionInfo(mass, ms, cshape, inertia)
        
        # Based on the admin structure, instantiate the actual object.
        body = pybullet.btRigidBody(body_CI)
        body.linear_velocity = btVector3(*obj.velocityLin)
        body.angular_velocity = btVector3(*obj.velocityRot)
        body.set_damping(0.02, 0.02)
        body.set_sleeping_thresholds(0.1, 0.1)
        body.friction = 1
        body.restitution = obj.restitution

        # Attach my own admin structure to the object.
        body.azrael = (objID, obj.radius, obj.scale)
        
        # Add the rigid body to the object cache.
        self.all_objs[objID] = body
