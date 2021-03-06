from basic cimport *

cdef extern from "btBulletDynamicsCommon.h":
    cdef cppclass btTransform:
        btTransform()
        btTransform(btQuaternion &q, btVector3 &c)
        btVector3 operator*(const btVector3 &x) const
        btTransform operator*(const btTransform &x) const
        void setIdentity()
        void setOrigin(btVector3 &origin)
        btVector3 &getOrigin()
        btQuaternion getRotation()
        void setRotation(const btQuaternion &q)
        btTransform inverse()
        void mult (const btTransform &t1, const btTransform &t2)
