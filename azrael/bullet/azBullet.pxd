from basic cimport *
from rigid_body cimport *
from typed_constraint cimport *
from libcpp.vector cimport vector


# Custom callbacks functions for broadphase solver.
cdef extern from "broadphase_callback.cpp":
    cdef cppclass BroadphasePaircacheBuilder:
        BroadphasePaircacheBuilder()
        void azResetPairCache()
        vector[int] *azGetPairCache()


# Custom callbacks functions for narrowphase solver.
cdef extern from "narrowphase_callback.cpp":
    cdef void installNarrowphaseCallback(btDiscreteDynamicsWorld *world)
    cdef void resetNarrowphasePairCache();
    cdef vector[AzraelCollisionData] narrowphasePairCache
    cdef struct AzraelCollisionData:
        int aid_a
        int aid_b
        btVector3 point_a
        btVector3 point_b
        btVector3 normal_on_b


cdef extern from "btBulletDynamicsCommon.h":
    cdef cppclass btDefaultCollisionConfiguration:
        btDefaultCollisionConfiguration()

    cdef cppclass btCollisionDispatcher:
        btCollisionDispatcher(btDefaultCollisionConfiguration *config)

    cdef cppclass btBroadphaseInterface:
        btBroadphaseInterface()

    cdef cppclass btDbvtBroadphase:
        btDbvtBroadphase()

    cdef cppclass btSequentialImpulseConstraintSolver:
        btSequentialImpulseConstraintSolver()

    cdef cppclass btManifoldPoint:
        btManifoldPoint()
        btScalar getDistance()
        btVector3 &getPositionWorldOnA()
        btVector3 &getPositionWorldOnB()

    cdef cppclass btPersistentManifold:
        btPersistentManifold()
        btCollisionObject *getBody0()
        btCollisionObject *getBody1()
        int getNumContacts()
        btManifoldPoint &getContactPoint(int index)

    cdef cppclass btDispatcher:
        btDispatcher()
        int	getNumManifolds()
        btPersistentManifold *getManifoldByIndexInternal(int index)

    cdef cppclass btBroadphaseProxy:
        btBroadphaseProxy()

    cdef cppclass btOverlapFilterCallback:
        btOverlapFilterCallback()
        bint needBroadphaseCollision(btBroadphaseProxy *proxy0, btBroadphaseProxy *proxy1)

    cdef cppclass btOverlappingPairCache:
        btOverlappingPairCache()
        void setOverlapFilterCallback(btOverlapFilterCallback *callback)

    cdef cppclass btDiscreteDynamicsWorld:
        btDiscreteDynamicsWorld(
                btCollisionDispatcher *dispatcher,
                btBroadphaseInterface *pairCache,
                btSequentialImpulseConstraintSolver *constraintSolver,
                btDefaultCollisionConfiguration *collisionConfiguration)
        void updateAabbs()
        void setGravity(const btVector3 &v)
        btVector3 getGravity()
        void addRigidBody(btRigidBody *body)
        void addRigidBody(btRigidBody *body, short group, short mask)
        int stepSimulation(btScalar timeStep, int maxSubSteps, btScalar fixedTimeStep)
        void removeRigidBody(btRigidBody *body)
        void addConstraint(btTypedConstraint *constraint, bint disable)
        void removeConstraint(btTypedConstraint *constraint)
        int getNumConstraints()
        btTypedConstraint *getConstraint(int index)
        btDispatcher *getDispatcher()
        void performDiscreteCollisionDetection()
        btOverlappingPairCache *getPairCache()
