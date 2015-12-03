cdef extern from "btBulletDynamicsCommon.h":
    cdef cppclass btScalar:
        btScalar(double s)

    cdef cppclass btQuaternion:
        btQuaternion()
        btQuaternion(double x, double y, double z, double w)

        const btScalar &x()
        const btScalar &y()
        const btScalar &z()
        const btScalar &w()
        bint operator==(btScalar)
        btQuaternion &operator* (const btQuaternion &q)
        btQuaternion &normalize()
        btQuaternion normalized()
        btQuaternion inverse() const
        btScalar length2() const

    cdef cppclass btVector3:
        btVector3()
        btVector3(double, double, double)
        btVector3(btScalar, btScalar, btScalar)
        bint operator==(btVector3)
        bint operator!=(btVector3)
        btVector3 operator-()
        btVector3 operator+()
        btVector3 operator+(btVector3)
        btVector3 operator-(btVector3)
        btVector3 &operator*(btScalar &s)
        btVector3 &operator/(btScalar &s)

        const btScalar &x()
        const btScalar &y()
        const btScalar &z()
