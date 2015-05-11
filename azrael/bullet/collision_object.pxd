from basic cimport *
from collision_shapes cimport *

cdef extern from "btBulletDynamicsCommon.h":
    cdef cppclass btCollisionObject:
        btCollisionObject()
        btCollisionShape *getCollisionShape()
        void setCollisionShape(btCollisionShape *collisionShape)

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

