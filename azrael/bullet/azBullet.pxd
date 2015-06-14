from basic cimport *
from rigid_body cimport *
from typed_constraint cimport *

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
        void addConstraint(btTypedConstraint *constraint, bint disable)
        void removeConstraint(btTypedConstraint *constraint)
        int getNumConstraints()
        btTypedConstraint *getConstraint(int index)
        btDispatcher *getDispatcher()
        void performDiscreteCollisionDetection()
