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

"""
To compile and test:
  >> python3 setup.py cleanall
  >> python3 setup.py build_ext --inplace

Python version of Bullet's Hello World program:
  >> python3 hello.py
"""
from cpython.object cimport Py_EQ, Py_NE

from basic cimport *
from collision_shapes cimport *
from transform cimport *
from motion_state cimport *
from collision_object cimport *
from rigid_body cimport *
from typed_constraint cimport *

# Important: the order of the includes matter; make sure it is compatible with
#            the class hierarchy!
include 'basic.pyx'
include 'collision_shapes.pyx'
include 'transform.pyx'
include 'motion_state.pyx'
include 'collision_object.pyx'
include 'rigid_body.pyx'
include 'typed_constraint.pyx'


cdef class BulletBase:
    """
    Framework class that sets up a complete simulation environment.
    """
    cdef btDefaultCollisionConfiguration *collisionConfiguration
    cdef btCollisionDispatcher *dispatcher
    cdef btDbvtBroadphase *pairCache
    cdef btSequentialImpulseConstraintSolver *solver
    cdef btDiscreteDynamicsWorld *dynamicsWorld
    cdef BroadphasePaircacheBuilder *cb_broadphase
    cdef list _list_constraints

    def __cinit__(self):
        # Allocate the auxiliary classes to create a btDiscreteDynamicsWorld.
        self.collisionConfiguration = new btDefaultCollisionConfiguration()
        assert self.collisionConfiguration != NULL

        self.dispatcher = new btCollisionDispatcher(self.collisionConfiguration)
        assert self.dispatcher != NULL

        self.pairCache = new btDbvtBroadphase()
        assert self.pairCache != NULL

        self.solver = new btSequentialImpulseConstraintSolver()
        assert self.solver != NULL

        # Create the simulation.
        self.dynamicsWorld = new btDiscreteDynamicsWorld(
            self.dispatcher,
            # Downcast to the base class.
            <btBroadphaseInterface*>self.pairCache,
            self.solver,
            self.collisionConfiguration)
        assert self.dynamicsWorld != NULL

        # Container to keep track of all constraints.
        self._list_constraints = []

        # No gravity by default.
        self.setGravity(Vec3(0, 0, 0))

    def __dealloc__(self):
        del self.dynamicsWorld
        del self.solver
        del self.pairCache
        del self.dispatcher
        del self.collisionConfiguration

    def setGravity(self, Vec3 v):
        self.dynamicsWorld.setGravity(v.ptr_Vector3[0])

    def getGravity(self):
        cdef btVector3 tmp = self.dynamicsWorld.getGravity()
        return Vec3(<double>tmp.x(), <double>tmp.y(), <double>tmp.z())

    def installBroadphaseCallback(self):
        # fixme: docu; rename function; user must select in ctor if they want
        # broadphase only (ie. remove this explicit method call).
        self.cb_broadphase = new BroadphasePaircacheBuilder()
        self.dynamicsWorld.getPairCache().setOverlapFilterCallback(
            <btOverlapFilterCallback*?>self.cb_broadphase)

    def azResetPairCache(self):
        # Clear the pair cache that has built up in the Broadphase callback.
        self.cb_broadphase.azResetPairCache()

    def azReturnPairCache(self):
        # Return latest set of broadphase collision pairs.
        cdef vector[int] *ptr_coll_pairs = self.cb_broadphase.azGetPairCache()
        ret = [int(ptr_coll_pairs[0][_]) for _ in range(len(ptr_coll_pairs[0]))]
        if len(ret) % 2 != 0:
            return []
        return set(zip(ret[0::2], ret[1::2]))

    def azGetCollisionPairs(self):
        # Run Broadphase.
        self.dynamicsWorld.performDiscreteCollisionDetection()

        # Convenience.
        cdef btDispatcher *dispatcher = self.dynamicsWorld.getDispatcher()

        # Allocate auxiliary variables needed later on.
        cdef btVector3 vec
        cdef btManifoldPoint ptr_mp
        cdef btPersistentManifold* contactManifold

        # Initialise the dictionary that will hold the pair cache information,
        # ie body IDs and their contact points (if any).
        pairData = {}

        # Auxiliary Python objects to gain access to the 'azGetBodyID'
        # convenience methods.
        obA, obB = CollisionObject(), CollisionObject()

        for ii in range(dispatcher.getNumManifolds()):
            contactManifold = dispatcher.getManifoldByIndexInternal(ii)

            # Get the two objects.
            obA.ptr_CollisionObject = <btCollisionObject*>(contactManifold.getBody0())
            obB.ptr_CollisionObject = <btCollisionObject*>(contactManifold.getBody1())

            # Query the bodyIDs of both objects. Skip the rest of this loop if
            # one (or both) objects have no ID.
            bodyIDs = obA.azGetBodyID(), obB.azGetBodyID()
            if None in bodyIDs:
                continue

            # Add the current body pair to the dictionary. So far this only
            # means that the objects are close, even though they may not be
            # touching.
            pairData[bodyIDs] = []

            # Compile a list of all contacts.
            for jj in range(contactManifold.getNumContacts()):
                # Query the contact point structure.
                ptr_mp = contactManifold.getContactPoint(jj)

                # Extract the contact point of both objects.
                vec = ptr_mp.getPositionWorldOnA()
                c_a = Vec3(<double>vec.x(), <double>vec.y(), <double>vec.z())

                vec = ptr_mp.getPositionWorldOnB()
                c_b = Vec3(<double>vec.x(), <double>vec.y(), <double>vec.z())

                # Add the contact point locations to our pairData dictionary.
                pairData[bodyIDs].append((c_a, c_b))

        # Explicitly set the internal pointers to NULL as the destructor of obA
        # and obA would otherwise deallocate the user pointers.
        obA.ptr_CollisionObject = NULL
        obB.ptr_CollisionObject = NULL
        return pairData

    def addRigidBody(self, RigidBody body, short group=-1, short mask=-1):
        if (group < 0) or (mask < 0):
            self.dynamicsWorld.addRigidBody(body.ptr_RigidBody)
        else:
            self.dynamicsWorld.addRigidBody(body.ptr_RigidBody, group, mask)

    def addConstraint(self, TypedConstraint constraint):
        # Return immediately if the constraint has already been added.
        if constraint in self._list_constraints:
            return

        # Add the constraint.
        self._list_constraints.append(constraint)
        self.dynamicsWorld.addConstraint(constraint.ptr_TypedConstraint, False)

    def getConstraint(self, int index):
        try:
            return self._list_constraints[index]
        except IndexError:
            return None

    def iterateConstraints(self):
        return (_ for _ in self._list_constraints)

    def removeConstraint(self, TypedConstraint constraint):
        tmp = [_ for _ in self._list_constraints if _ != constraint]
        if len(tmp) == self._list_constraints:
            # `shape` was not in the list.
            return None
        else:
            self._list_constraints = tmp
            self.dynamicsWorld.removeConstraint(constraint.ptr_TypedConstraint)

    def getNumConstraints(self):
        if len(self._list_constraints) != self.dynamicsWorld.getNumConstraints():
            raise AssertionError(
                'Invalid #Constraints in DynamicsWorld')
        return self.dynamicsWorld.getNumConstraints()

    def stepSimulation(self, double timeStep, int maxSubSteps):
        """
        The time step denotes the amount of time (in seconds) the world should
        be simulated. The the 'maxSubSteps' parameter tells Bullet how many
        sub-steps it is allowed to use (this is for accuracy). These two
        parameters are exposed. The third parameter expected by Bullet, called
        fixedTimeStep, is not exposed. Instead, it is computed to ensure a
        consistent simulation as described in
        http://www.bulletphysics.org/mediawiki-1.5.8/index.php?title=Stepping_The_World
        """
        cdef double fixedTimeStep = (timeStep / maxSubSteps)
        self.dynamicsWorld.stepSimulation(
            btScalar(timeStep), maxSubSteps, btScalar(fixedTimeStep))

    def removeRigidBody(self, RigidBody body):
        self.dynamicsWorld.removeRigidBody(body.ptr_RigidBody)
