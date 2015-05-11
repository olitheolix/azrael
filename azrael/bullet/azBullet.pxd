from basic cimport *
from rigid_body cimport *

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

