from basic cimport *
from transform cimport *

cdef extern from "btBulletDynamicsCommon.h":
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
        btVector3 getHalfExtentsWithMargin()
        const btVector3 &getHalfExtentsWithoutMargin()

    cdef cppclass btSphereShape:
        btSphereShape(btScalar radius)
        btScalar getRadius()

    cdef cppclass btConcaveShape:
        btConcaveShape()

    cdef cppclass btEmptyShape:
        btEmptyShape()

    cdef cppclass btStaticPlaneShape:
        btStaticPlaneShape(btVector3 &v, btScalar plane_const)

    cdef cppclass btCompoundShape:
       btCompoundShape(bint enableDynamicAabbTree)
       void addChildShape(const btTransform &localTransform, btCollisionShape *shape)
       btCollisionShape *getChildShape(int index)
       void removeChildShape(btCollisionShape *shape)
       int getNumChildShapes()
