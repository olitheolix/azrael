from basic cimport *

cdef extern from "btBulletDynamicsCommon.h":
    cdef cppclass btTransform:
        btTransform()
        btTransform(btQuaternion &q, btVector3 &c)
        void setIdentity()
        void setOrigin(btVector3 &origin)
        btVector3 &getOrigin()
        btQuaternion getRotation()
        void setRotation(const btQuaternion &q)

