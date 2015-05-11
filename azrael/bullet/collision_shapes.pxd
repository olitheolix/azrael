from basic cimport *

cdef extern from "btBulletDynamicsCommon.h":
    cdef cppclass btCollisionShape:
        btCollisionShape()
        void setLocalScaling(const btVector3 &scaling)
        btVector3 &getLocalScaling()
        void calculateLocalInertia(btScalar mass, btVector3 &inertia)
        char *getName()

