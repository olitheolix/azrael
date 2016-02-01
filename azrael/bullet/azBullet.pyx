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
  >> python setup.py cleanall
  >> python setup.py build_ext --inplace

Python version of Bullet's Hello World program:
  >> python hello.py
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

        # Install a custom handler that Bullet calls after each tick. The
        # handler is a pure C++ function and compiles all the collision
        # contacts that have occurred during that tick.
        installNarrowphaseCallback(self.dynamicsWorld)

        # Container to keep track of all constraints.
        self._list_constraints = []

        # No gravity by default.
        self.setGravity(Vec3(0, 0, 0))

        # Reset the collision contact pair caches.
        self.azResetPairCache()

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
        # Install the broadphase callback. This is only necessary if Bullet
        # should do the broadphase instead of Azrael, but that did not work out
        # too well (suprisingly slow, probably due to adding/removing all the
        # bodies at every step).
        self.cb_broadphase = new BroadphasePaircacheBuilder()
        self.dynamicsWorld.getPairCache().setOverlapFilterCallback(
            <btOverlapFilterCallback*?>self.cb_broadphase)

    def azResetPairCache(self):
        # Clear the pair cache that has built up in the Broadphase callback.
        self.cb_broadphase.azResetPairCache()
        resetNarrowphasePairCache()

    def azReturnPairCache(self):
        # Return latest set of broadphase collision pairs.
        cdef vector[int] *ptr_coll_pairs = self.cb_broadphase.azGetPairCache()
        ret = [int(ptr_coll_pairs[0][_]) for _ in range(len(ptr_coll_pairs[0]))]
        if len(ret) % 2 != 0:
            return []
        return set(zip(ret[0::2], ret[1::2]))

    def updateAabbs(self):
        self.dynamicsWorld.updateAabbs()

    def performDiscreteCollisionDetection(self):
        self.dynamicsWorld.performDiscreteCollisionDetection()

    def azGetLastContacts(self):
        # Convenience.
        cdef btDispatcher *dispatcher = self.dynamicsWorld.getDispatcher()

        # Allocate auxiliary variables needed later on.
        cdef btManifoldPoint ptr_mp
        cdef btPersistentManifold* contactManifold

        # This list will contain the contact information returned to the
        # caller.
        pairData = []

        # Auxiliary Python objects to gain access to the 'azGetBodyID'
        # convenience methods.
        rb_a, rb_b = CollisionObject(), CollisionObject()

        for ii in range(dispatcher.getNumManifolds()):
            contactManifold = dispatcher.getManifoldByIndexInternal(ii)

            # Skip the current pair of bodies because they are only close but
            # do not touch each other.
            if contactManifold.getNumContacts() == 0:
                continue

            # Get the two objects.
            rb_a.ptr_CollisionObject = <btCollisionObject*>(contactManifold.getBody0())
            rb_b.ptr_CollisionObject = <btCollisionObject*>(contactManifold.getBody1())

            # Query the bodyIDs of both objects. Skip the rest of this loop if
            # one (or both) objects have no ID.
            bodyIDs = rb_a.azGetBodyID(), rb_b.azGetBodyID()
            if None in bodyIDs:
                continue
            aid_a, aid_b = bodyIDs

            # Compile the list of all contact positions for the current pair.
            for jj in range(contactManifold.getNumContacts()):
                # Query the contact point structure.
                ptr_mp = contactManifold.getContactPoint(jj)

                # Add the contact point locations to our pairData dictionary.
                tmp = {
                    'aid_a': aid_a,
                    'aid_b': aid_b,
                    'point_a': (
                        <double>(ptr_mp.getPositionWorldOnA().x()),
                        <double>(ptr_mp.getPositionWorldOnA().y()),
                        <double>(ptr_mp.getPositionWorldOnA().z())
                    ),
                    'point_b': (
                        <double>(ptr_mp.getPositionWorldOnB().x()),
                        <double>(ptr_mp.getPositionWorldOnB().y()),
                        <double>(ptr_mp.getPositionWorldOnB().z())
                    ),
                }

                # Ensure aid_a < aid_b.
                if tmp['aid_a'] > tmp['aid_b']:
                    tmp['aid_a'], tmp['aid_b'] = tmp['aid_b'], tmp['aid_a']
                    tmp['point_a'], tmp['point_b'] = tmp['point_b'], tmp['point_a']
                pairData.append(tmp)

        # Explicitly set the internal pointers to NULL as the destructor of rb_a
        # and rb_b would otherwise deallocate the user pointers where the
        # bodyID is stored.
        rb_a.ptr_CollisionObject = NULL
        rb_b.ptr_CollisionObject = NULL
        return pairData

    def azGetNarrowphaseContacts(self):
        """
        Return the list of collision contacts gathered during the narrowphase.

        Each element in the list is a dictionary that contains the information
        in terms of native Python types. For instance::

        [{'aid_a': aida, 'aid_b': aidb, 'point_a': pa, 'point_b': pb}, ...]

        This method guarantees that 'aid_a' <= 'aid_b'.

        Returns:
            list(dict): 
        """
        # Shorthand for readability.
        cdef vector[AzraelCollisionData] *pc = &narrowphasePairCache

        # Compile the collision information from bullet into a Python
        # dictionary and pass it to the (Python)caller.
        out = []
        for ii in range(pc[0].size()):
            tmp = {
                'aid_a': pc[0][ii].aid_a,
                'aid_b': pc[0][ii].aid_b,
                'point_a': (
                    <double>(pc[0][ii].point_a.x()),
                    <double>(pc[0][ii].point_a.y()),
                    <double>(pc[0][ii].point_a.z())
                ),
                'point_b': (
                    <double>(pc[0][ii].point_b.x()),
                    <double>(pc[0][ii].point_b.y()),
                    <double>(pc[0][ii].point_b.z())
                ),
                # 'normal_on_b': (
                #     <double>(pc[0][ii].normal_on_b.x()),
                #     <double>(pc[0][ii].normal_on_b.y()),
                #     <double>(pc[0][ii].normal_on_b.z())
                # ),
            }

            # Swap the information if aid_a < aid_b.
            if tmp['aid_a'] > tmp['aid_b']:
                tmp['aid_a'], tmp['aid_b'] = tmp['aid_b'], tmp['aid_a']
                tmp['point_a'], tmp['point_b'] = tmp['point_b'], tmp['point_a']

            # Add the current collision info to the buffer.
            out.append(tmp)
        return out

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
        The time step denotes the amount of Seconds to advance the simulation.
        The 'maxSubSteps' parameter tells Bullet how many sub-steps it is
        allowed to use (this is for accuracy). These two parameters are
        exposed. The third parameter (`fixedTimeStep`) is determined
        automatically according to
        http://www.bulletphysics.org/mediawiki-1.5.8/index.php?title=Stepping_The_World
        """
        # Sanity check.
        if maxSubSteps < 1:
            maxSubSteps = 1

        # Clear the narrowphase pair cache.
        self.azResetPairCache()

        cdef double fixedTimeStep = (timeStep / maxSubSteps)
        self.dynamicsWorld.stepSimulation(
            btScalar(timeStep), maxSubSteps, btScalar(fixedTimeStep))

    def removeRigidBody(self, RigidBody body):
        self.dynamicsWorld.removeRigidBody(body.ptr_RigidBody)
