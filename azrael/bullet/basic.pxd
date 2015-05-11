cdef extern from "btBulletDynamicsCommon.h":
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
