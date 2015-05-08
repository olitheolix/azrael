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

Converted hello world program:
  >> python3 hello.py
"""
from cpython.object cimport Py_EQ, Py_NE
from cython.operator cimport dereference as deref

"""
Cython wrapper for the C++ class.
"""
cdef extern from "btBulletDynamicsCommon.h":
    cdef cppclass btDefaultCollisionConfiguration:
        btDefaultCollisionConfiguration()

    cdef cppclass btCollisionDispatcher:
        btCollisionDispatcher(btDefaultCollisionConfiguration* config)

    cdef cppclass btBroadphaseInterface:
        btBroadphaseInterface()

    cdef cppclass btDbvtBroadphase:
        btDbvtBroadphase()

    cdef cppclass btSequentialImpulseConstraintSolver:
        btSequentialImpulseConstraintSolver()

    cdef cppclass btDiscreteDynamicsWorld:
        btDiscreteDynamicsWorld(
                btCollisionDispatcher *dispatcher,
                btBroadphaseInterface *pairCache,
                btSequentialImpulseConstraintSolver *constraintSolver,
                btDefaultCollisionConfiguration *collisionConfiguration)
        void setGravity(const btVector3 &v)
        btVector3 getGravity()
        void addRigidBody(btRigidBody *body)
        int stepSimulation(btScalar timeStep, int maxSubSteps, btScalar fixedTimeStep)
        void removeRigidBody(btRigidBody *body)
 
    cdef cppclass btScalar:
        btScalar(double s)

    cdef cppclass btQuaternion:
        btQuaternion(double x, double y, double z, double w)

        const btScalar &x()
        const btScalar &y()
        const btScalar &z()
        const btScalar &w()

    cdef cppclass btVector3:
        btVector3(double, double, double)
        btVector3(btScalar, btScalar, btScalar)
        bint operator==(btVector3)
        bint operator!=(btVector3)
        btVector3 operator-()
        btVector3 operator+()
        btVector3 operator+(btVector3)
        btVector3 operator-(btVector3)

        const btScalar &x()
        const btScalar &y()
        const btScalar &z()

    cdef cppclass btTransform:
        btTransform()
        btTransform(btQuaternion &q, btVector3 &c)
        void setIdentity()
        void setOrigin(btVector3 &origin)
        btVector3 &getOrigin()
        btQuaternion getRotation()
        void setRotation(const btQuaternion &q)

    cdef cppclass btMotionState:
        btMotionState()
        void getWorldTransform(btTransform &worldTrans)
        void setWorldTransform(const btTransform &worldTrans)

    cdef cppclass btDefaultMotionState:
        btDefaultMotionState(btTransform &startTrans)

    cdef cppclass btCollisionShape:
        btCollisionShape()
        void setLocalScaling(const btVector3 &scaling)
        btVector3 &getLocalScaling()
        void calculateLocalInertia(btScalar mass, btVector3 &inertia)
        char *getName()

    cdef cppclass btConvexShape:
        btConvexShape()

    cdef cppclass btConvexInternalShape:
        btConvexInternalShape()

    cdef cppclass btPolyhedralConvexShape:
        btPolyhedralConvexShape()

    cdef cppclass btBoxShape:
        btBoxShape(btVector3)

    cdef cppclass btSphereShape:
        btSphereShape(btScalar radius)

    cdef cppclass btConcaveShape:
        btConcaveShape()

    cdef cppclass btEmptyShape:
        btEmptyShape()

    cdef cppclass btStaticPlaneShape:
        btStaticPlaneShape(btVector3 &v, btScalar plane_const)

    cdef cppclass btCollisionObject:
        btCollisionObject()
        btCollisionShape *getCollisionShape()
        void setCollisionShape(btCollisionShape *collisionShape)

    cdef cppclass btRigidBody:
        btRigidBody(
            btScalar mass,
            btMotionState *motionState,
            btCollisionShape *collisionShape,
            btVector3 &localInertia)

        # getMotionState
        btMotionState *getMotionState()
        void setMotionState(btMotionState*)

        # {get,set}Restitution
        void setRestitution(btScalar r)
        btScalar getRestitution()

        # CenterOfMassTransform.
        void setCenterOfMassTransform(const btTransform &xform)
        btTransform &getCenterOfMassTransform()

        # ------------------------------------------------------------
        void forceActivationState(int newState)

        # Mass- and inertia related.
        btScalar getInvMass()
        btVector3 &getInvInertiaDiagLocal()
        void setMassProps(btScalar mass, const btVector3 &inertia)

        # Force functions: clearForces, applyForce, applyTorque,
        #                  applyCentralForce, getTotalForce, getTotalTorque
        void clearForces()
        void applyForce(const btVector3& force, const btVector3& rel_pos)
        void applyTorque(const btVector3& torque)
        void applyCentralForce(const btVector3& force)
        const btVector3& getTotalForce()
        const btVector3& getTotalTorque()

        # setSleepingThresholds and get{Linear,Angular}SleepingThreshold
        void setSleepingThresholds(btScalar linear, btScalar angular)
        btScalar getLinearSleepingThreshold()
        btScalar getAngularSleepingThreshold()

        # {set,get}Friction
        void setFriction (btScalar frict)
        btScalar getFriction()

        # {set,get}Damping
        void setDamping(btScalar lin_damping, btScalar ang_damping)
        btScalar getLinearDamping()
        btScalar getAngularDamping()

        # {set,get}{Linear,Angular}Factor
        void setLinearFactor(const btVector3& linearFactor)
        void setAngularFactor(const btVector3& angFac)
        btVector3& getLinearFactor()
        btVector3& getAngularFactor()

        # {get,set}{Linear,Angular}Velocity
        void setAngularVelocity(const btVector3& ang_vel)
        void setLinearVelocity(const btVector3& lin_vel)
        btVector3& getLinearVelocity()
        btVector3& getAngularVelocity()


"""
Python Interface to C++ class based on the Cython wrapper (see above).

This class holds an instance of the C++ class and defines some
Python methods to interact with it. Those Python methods do nothing
more than calling the respective C++ methods.

"""
cdef class scalar:
    cdef btScalar *thisptr

    def __cinit__(self, double x=0):
        self.thisptr = new btScalar(x)

    def __dealloc__(self):
        del self.thisptr

    def value(self):
        return <double>(self.thisptr[0])

    def __repr__(self):
        return str(<double>self.thisptr[0])


cdef class vec3:
    cdef btVector3 *thisptr

    def __cinit__(self, double x=0, double y=0, double z=0):
        self.thisptr = new btVector3(x, y, z)

    def __dealloc__(self):
        del self.thisptr

    def __neg__(self):
        ret = vec3()
        ret.thisptr[0] = -self.thisptr[0]
        return ret

    def __add__(vec3 self, vec3 v):
        ret = vec3()
        ret.thisptr[0] = self.thisptr[0] + v.thisptr[0]
        return ret

    def __sub__(vec3 self, vec3 v):
        ret = vec3()
        ret.thisptr[0] = self.thisptr[0] - v.thisptr[0]
        return ret

    def __richcmp__(vec3 x, vec3 y, int op):
        if op == Py_EQ:
            return (x.thisptr[0] == y.thisptr[0])
        elif op == Py_NE:
            return (x.thisptr[0] != y.thisptr[0])
        else:
            assert False

    def tolist(self):
        t = self.thisptr
        return (<double>t.x(), <double>t.y(), <double>t.z())

    def __repr__(self):
        return repr(self.tolist())


cdef class Quaternion:
    cdef btQuaternion *ptr_Quaternion

    def __cinit__(self, double x=0, double y=0, double z=0, double w=1):
        self.ptr_Quaternion = new btQuaternion(x, y, z, w)

    def __dealloc__(self):
        del self.ptr_Quaternion

    def tolist(self):
        t = self.ptr_Quaternion
        return (<double>t.x(), <double>t.y(), <double>t.z(), <double>t.w())

    def __repr__(self):
        return repr(self.tolist())

cdef class CollisionShape:
    cdef btCollisionShape *ptr_CollisionShape

    def __cinit__(self):
        self.ptr_CollisionShape = NULL

    def setLocalScaling(self, vec3 scaling):
        self.ptr_CollisionShape.setLocalScaling(scaling.thisptr[0])

    def getLocalScaling(self):
        v = vec3()
        v.thisptr[0] = self.ptr_CollisionShape.getLocalScaling()
        return v

    def calculateLocalInertia(self, double mass, vec3 inertia):
        self.ptr_CollisionShape.calculateLocalInertia(btScalar(mass), inertia.thisptr[0])

    def getName(self):
        return self.ptr_CollisionShape.getName()

cdef class child1(CollisionShape):
    cdef btStaticPlaneShape *ptr_child1

    def __cinit__(self):
        self.ptr_child1 = NULL

    def __init__(self):
        print('Child 1 creates pointers')
        self.ptr_child1 = new btStaticPlaneShape(btVector3(0, 0, 0), btScalar(1))
        self.ptr_CollisionShape = <btCollisionShape*?> self.ptr_child1

    def showme(self):
        print('--- Child 1 ---')
        print('ptr_CollisionShape=', <long?>self.ptr_CollisionShape)
        print('ptr_child1=', <long?>self.ptr_child1)
        print('---------------')        


cdef class child2(child1):
    """
    Will only allocate memory once and assign the pointers inherited from all parents.

    c2 = bt.child2()
    c2.showme()
    """
    cdef btStaticPlaneShape *ptr_child2

    def __cinit__(self):
        self.ptr_child2 = NULL

    def __init__(self):
        print('Child 2 creates pointers')
        self.ptr_child2 = new btStaticPlaneShape(btVector3(0, 0, 0), btScalar(1))
        self.ptr_child1 = <btStaticPlaneShape*?> self.ptr_child2
        self.ptr_CollisionShape = <btCollisionShape*?> self.ptr_child2

    def showme(self):
        print('--- Child 2 ---')
        print('ptr_CollisionShape=', <long?>self.ptr_CollisionShape)
        print('ptr_child1=', <long?>self.ptr_child1)
        print('ptr_child2=', <long?>self.ptr_child2)
        print('---------------')        


cdef class ConcaveShape(CollisionShape):
    cdef btConcaveShape *ptr_ConcaveShape

    def __cinit__(self):
        self.ptr_ConcaveShape = NULL


cdef class StaticPlaneShape(ConcaveShape):
    cdef btStaticPlaneShape *ptr_StaticPlaneShape

    def __cinit__(self):
        self.ptr_StaticPlaneShape = NULL

    def __init__(self, vec3 v, double plane_const):
        self.ptr_StaticPlaneShape = new btStaticPlaneShape(
                v.thisptr[0], btScalar(plane_const))

        # Assign the base pointers.
        self.ptr_ConcaveShape = <btConcaveShape*>self.ptr_StaticPlaneShape
        self.ptr_CollisionShape = <btCollisionShape*>self.ptr_StaticPlaneShape

    def __dealloc__(self):
        if self.ptr_StaticPlaneShape != NULL:
            del self.ptr_StaticPlaneShape


cdef class EmptyShape(ConcaveShape):
    cdef btEmptyShape *ptr_EmptyShape

    def __cinit__(self):
        self.ptr_EmptyShape = NULL

    def __init__(self):
        self.ptr_EmptyShape = new btEmptyShape()

        # Assign the base pointers.
        self.ptr_ConcaveShape = <btConcaveShape*>self.ptr_EmptyShape
        self.ptr_CollisionShape = <btCollisionShape*>self.ptr_EmptyShape

    def __dealloc__(self):
        if self.ptr_EmptyShape != NULL:
            del self.ptr_EmptyShape


cdef class ConvexShape(CollisionShape):
    cdef btConvexShape *ptr_ConvexShape

    def __cinit__(self):
        self.ptr_ConvexShape = NULL


cdef class ConvexInternalShape(ConvexShape):
    cdef btConvexInternalShape *ptr_ConvexInternalShape

    def __cinit__(self):
        self.ptr_ConvexInternalShape = NULL


cdef class SphereShape(ConvexInternalShape):
    cdef btSphereShape *ptr_SphereShape

    def __cinit__(self):
        self.ptr_SphereShape = NULL

    def __init__(self, double radius):
        self.ptr_SphereShape = new btSphereShape(btScalar(radius))

        # Assign the base pointers.
        self.ptr_ConvexInternalShape = <btConvexInternalShape*>self.ptr_SphereShape
        self.ptr_ConvexShape = <btConvexShape*>self.ptr_SphereShape
        self.ptr_CollisionShape = <btCollisionShape*>self.ptr_SphereShape

    def __dealloc__(self):
        if self.ptr_SphereShape != NULL:
            del self.ptr_SphereShape


cdef class PolyhedralConvexShape(ConvexInternalShape):
    cdef btPolyhedralConvexShape *ptr_PolyhedralConvexShape

    def __cinit__(self):
        self.ptr_PolyhedralConvexShape = NULL


cdef class BoxShape(PolyhedralConvexShape):
    cdef btBoxShape *ptr_BoxShape

    def __cinit__(self, vec3 v):
        self.ptr_BoxShape = NULL

    def __init__(self, vec3 v):
        self.ptr_BoxShape = new btBoxShape(v.thisptr[0])

        # Assign the base pointers.
        self.ptr_PolyhedralConvexShape = <btPolyhedralConvexShape*>self.ptr_BoxShape
        self.ptr_ConvexInternalShape = <btConvexInternalShape*>self.ptr_BoxShape
        self.ptr_ConvexShape = <btConvexShape*>self.ptr_BoxShape
        self.ptr_CollisionShape = <btCollisionShape*>self.ptr_BoxShape

    def __dealloc__(self):
        if self.ptr_BoxShape != NULL:
            del self.ptr_BoxShape


cdef class Transform:
    cdef btTransform *thisptr

    def __cinit__(self, Quaternion q=Quaternion(0, 0, 0, 1), vec3 c=vec3(0, 0, 0)):
        self.thisptr = new btTransform(q.ptr_Quaternion[0], c.thisptr[0]) 

    def setIdentity(self):
        self.thisptr.setIdentity()

    def setOrigin(self, vec3 v):
        self.thisptr.setOrigin(v.thisptr[0])

    def getOrigin(self):
        v = vec3(0, 0, 0)
        v.thisptr[0] = self.thisptr.getOrigin()
        return v
        
    def setRotation(self, Quaternion q):
        self.thisptr.setRotation(q.ptr_Quaternion[0])

    def getRotation(self):
        q = Quaternion()
        q.ptr_Quaternion[0] = self.thisptr.getRotation()
        return q

    def __dealloc__(self):
        del self.thisptr


cdef class MotionState:
    cdef btMotionState *ptr_MotionState

    def __cinit__(self):
        self.ptr_MotionState = NULL

    def getWorldTransform(self):
        t = Transform()
        self.ptr_MotionState.getWorldTransform(t.thisptr[0])
        return t

    def setWorldTransform(self, Transform worldTrans):
        self.ptr_MotionState.setWorldTransform(worldTrans.thisptr[0])

 
cdef class DefaultMotionState(MotionState):
    cdef btDefaultMotionState *ptr_DefaultMotionState

    def __cinit__(self, Transform t=Transform()):
        self.ptr_DefaultMotionState = new btDefaultMotionState(t.thisptr[0])
        self.ptr_MotionState = <btMotionState*>self.ptr_DefaultMotionState

    def __dealloc__(self):
        del self.ptr_DefaultMotionState


cdef class CollisionObject:
    cdef btCollisionObject *ptr_CollisionObject

    def __cinit__(self):
        self.ptr_CollisionObject = NULL

    def getCollisionShape(self):
        cs = CollisionShape()
        cs.ptr_CollisionShape = self.ptr_CollisionObject.getCollisionShape()
        return cs

    def setCollisionShape(self, CollisionShape collisionShape):
        self.ptr_CollisionObject.setCollisionShape(collisionShape.ptr_CollisionShape)


cdef class RigidBody(CollisionObject):
    cdef btRigidBody *thisptr

    def __cinit__(self, double mass, MotionState ms, CollisionShape cs, vec3 localInertia):
        self.thisptr = NULL

    def __init__(self, double mass, MotionState ms, CollisionShape cs, vec3 localInertia):
        self.thisptr = new btRigidBody(
            btScalar(mass),
            ms.ptr_MotionState,
            cs.ptr_CollisionShape,
            localInertia.thisptr[0])

        # Assign the base pointers.
        self.ptr_CollisionObject = <btCollisionObject*?>self.thisptr

    def __dealloc__(self):
        if self.thisptr != NULL:
            del self.thisptr

    def setRestitution(self, double r):
        self.thisptr.setRestitution(btScalar(r))

    def getRestitution(self):
        return <double>self.thisptr.getRestitution()

    def getLinearFactor(self):
        p = vec3()
        p.thisptr[0] = self.thisptr.getLinearFactor()
        return p

    def setLinearFactor(self, vec3 linearFactor):
        self.thisptr.setLinearFactor(linearFactor.thisptr[0])

    def getAngularFactor(self):
        p = vec3()
        p.thisptr[0] = self.thisptr.getAngularFactor()
        return p

    def setAngularFactor(self, vec3 angularFactor):
        self.thisptr.setAngularFactor(angularFactor.thisptr[0])

    def getLinearVelocity(self):
        p = vec3()
        p.thisptr[0] = self.thisptr.getLinearVelocity()
        return p

    def setLinearVelocity(self, vec3 linearVelocity):
        self.thisptr.setLinearVelocity(linearVelocity.thisptr[0])

    def getAngularVelocity(self):
        p = vec3()
        p.thisptr[0] = self.thisptr.getAngularVelocity()
        return p

    def setAngularVelocity(self, vec3 angularVelocity):
        self.thisptr.setAngularVelocity(angularVelocity.thisptr[0])

    def getMotionState(self):
        ms = MotionState()
        ms.ptr_MotionState = self.thisptr.getMotionState()
        return ms

    def setMotionState(self, MotionState ms):
        self.thisptr.setMotionState(ms.ptr_MotionState)

    def getLinearSleepingThreshold(self):
        return <double>self.thisptr.getLinearSleepingThreshold()

    def getAngularSleepingThreshold(self):
        return <double>self.thisptr.getAngularSleepingThreshold()

    def setSleepingThresholds(self, double linear, double angular):
        self.thisptr.setSleepingThresholds(btScalar(linear), btScalar(angular))

    def setFriction(self, double friction):
        self.thisptr.setFriction(btScalar(friction))

    def getFriction(self):
        return <double>self.thisptr.getFriction()

    def setDamping(self, double lin_damping, double ang_damping):
        self.thisptr.setDamping(btScalar(lin_damping), btScalar(ang_damping))

    def getLinearDamping(self):
        return <double>self.thisptr.getLinearDamping()

    def getAngularDamping(self):
        return <double>self.thisptr.getAngularDamping()

    def getTotalForce(self):
        p = vec3()
        p.thisptr[0] = self.thisptr.getTotalForce()
        return p

    def getTotalTorque(self):
        p = vec3()
        p.thisptr[0] = self.thisptr.getTotalTorque()
        return p

    def clearForces(self):
        self.thisptr.clearForces()

    def applyForce(self, vec3 force, vec3 pos):
        self.thisptr.applyForce(force.thisptr[0], pos.thisptr[0])

    def applyCentralForce(self, vec3 force):
        self.thisptr.applyCentralForce(force.thisptr[0])

    def applyTorque(self, vec3 torque):
        self.thisptr.applyTorque(torque.thisptr[0])

    def setMassProps(self, double mass, vec3 inertia):
        self.thisptr.setMassProps(btScalar(mass), inertia.thisptr[0])

    def getInvMass(self):
        return <double>self.thisptr.getInvMass()

    def getInvInertiaDiagLocal(self):
        p = vec3()
        p.thisptr[0] = self.thisptr.getInvInertiaDiagLocal()
        return p

    def forceActivationState(self, int newState):
        """
        The possible activation states are defined in  btCollisionObject.h
          * ACTIVE_TAG 1               --> ?
          * ISLAND_SLEEPING 2          --> ?
          * WANTS_DEACTIVATION 3       --> ?
          * DISABLE_DEACTIVATION 4     --> Make object active forever
          * DISABLE_SIMULATION 5       --> Deactivate object forever
        """
        self.thisptr.forceActivationState(newState)

    def getCenterOfMassTransform(self):
        t = Transform()
        t.thisptr[0] = self.thisptr.getCenterOfMassTransform()
        return t

    def setCenterOfMassTransform(self, Transform xform):
        self.thisptr.setCenterOfMassTransform(xform.thisptr[0])


cdef class BulletBase:
    """
    Framework class that sets up a complete simulation environment.
    """
    cdef btDefaultCollisionConfiguration *collisionConfiguration
    cdef btCollisionDispatcher *dispatcher
    cdef btDbvtBroadphase *pairCache
    cdef btSequentialImpulseConstraintSolver *solver
    cdef btDiscreteDynamicsWorld *dynamicsWorld

    def __cinit__(self):
        self.collisionConfiguration = new btDefaultCollisionConfiguration()
        self.dispatcher = new btCollisionDispatcher(self.collisionConfiguration)
        self.pairCache = new btDbvtBroadphase()
        self.solver = new btSequentialImpulseConstraintSolver()
        self.dynamicsWorld = new btDiscreteDynamicsWorld(
            self.dispatcher,
            # Downcast to the base class.
            <btBroadphaseInterface*>self.pairCache,
            self.solver,
            self.collisionConfiguration)

    def __dealloc__(self):
        del self.dynamicsWorld
        del self.solver
        del self.pairCache
        del self.dispatcher
        del self.collisionConfiguration

    def setGravity(self, double x, double y, double z):
        self.dynamicsWorld.setGravity(btVector3(x, y, z))

    def getGravity(self):
        cdef btVector3 *r
        r = new btVector3(0, 0, 0)
        r[0] = self.dynamicsWorld.getGravity()
        x = <double>(r[0].x())
        y = <double>(r[0].y())
        z = <double>(r[0].z())
        del r
        return (x, y, z)

    def addRigidBody(self, RigidBody body):
        self.dynamicsWorld.addRigidBody(body.thisptr)

    def stepSimulation(self, double timeStep, int maxSubSteps):
        self.dynamicsWorld.stepSimulation(
            btScalar(timeStep), maxSubSteps, btScalar(1.0 / 60.0))

    def removeRigidBody(self, RigidBody body):
        self.dynamicsWorld.removeRigidBody(body.thisptr)
