cdef class CollisionShape:
    cdef btCollisionShape *ptr_CollisionShape

    def __cinit__(self):
        self.ptr_CollisionShape = NULL

    def setLocalScaling(self, vec3 scaling):
        self.ptr_CollisionShape.setLocalScaling(scaling.thisptr[0])

    def getLocalScaling(self):
        v = vec3()
        v.thisptr[0] = self.ptr_CollisionShape.getLocalScaling()
        return v

    def calculateLocalInertia(self, double mass, vec3 inertia):
        self.ptr_CollisionShape.calculateLocalInertia(btScalar(mass), inertia.thisptr[0])

    def getName(self):
        return self.ptr_CollisionShape.getName()


cdef class ConcaveShape(CollisionShape):
    cdef btConcaveShape *ptr_ConcaveShape

    def __cinit__(self):
        self.ptr_ConcaveShape = NULL


cdef class StaticPlaneShape(ConcaveShape):
    cdef btStaticPlaneShape *ptr_StaticPlaneShape

    def __cinit__(self):
        self.ptr_StaticPlaneShape = NULL

    def __init__(self, vec3 v, double plane_const):
        self.ptr_StaticPlaneShape = new btStaticPlaneShape(
                v.thisptr[0], btScalar(plane_const))

        # Assign the base pointers.
        self.ptr_ConcaveShape = <btConcaveShape*>self.ptr_StaticPlaneShape
        self.ptr_CollisionShape = <btCollisionShape*>self.ptr_StaticPlaneShape

    def __dealloc__(self):
        if self.ptr_StaticPlaneShape != NULL:
            del self.ptr_StaticPlaneShape


cdef class EmptyShape(ConcaveShape):
    cdef btEmptyShape *ptr_EmptyShape

    def __cinit__(self):
        self.ptr_EmptyShape = NULL

    def __init__(self):
        self.ptr_EmptyShape = new btEmptyShape()

        # Assign the base pointers.
        self.ptr_ConcaveShape = <btConcaveShape*>self.ptr_EmptyShape
        self.ptr_CollisionShape = <btCollisionShape*>self.ptr_EmptyShape

    def __dealloc__(self):
        if self.ptr_EmptyShape != NULL:
            del self.ptr_EmptyShape


cdef class ConvexShape(CollisionShape):
    cdef btConvexShape *ptr_ConvexShape

    def __cinit__(self):
        self.ptr_ConvexShape = NULL


cdef class ConvexInternalShape(ConvexShape):
    cdef btConvexInternalShape *ptr_ConvexInternalShape

    def __cinit__(self):
        self.ptr_ConvexInternalShape = NULL


cdef class SphereShape(ConvexInternalShape):
    cdef btSphereShape *ptr_SphereShape

    def __cinit__(self):
        self.ptr_SphereShape = NULL

    def __init__(self, double radius):
        self.ptr_SphereShape = new btSphereShape(btScalar(radius))

        # Assign the base pointers.
        self.ptr_ConvexInternalShape = <btConvexInternalShape*>self.ptr_SphereShape
        self.ptr_ConvexShape = <btConvexShape*>self.ptr_SphereShape
        self.ptr_CollisionShape = <btCollisionShape*>self.ptr_SphereShape

    def __dealloc__(self):
        if self.ptr_SphereShape != NULL:
            del self.ptr_SphereShape


cdef class PolyhedralConvexShape(ConvexInternalShape):
    cdef btPolyhedralConvexShape *ptr_PolyhedralConvexShape

    def __cinit__(self):
        self.ptr_PolyhedralConvexShape = NULL


cdef class BoxShape(PolyhedralConvexShape):
    cdef btBoxShape *ptr_BoxShape

    def __cinit__(self, vec3 v):
        self.ptr_BoxShape = NULL

    def __init__(self, vec3 v):
        self.ptr_BoxShape = new btBoxShape(v.thisptr[0])

        # Assign the base pointers.
        self.ptr_PolyhedralConvexShape = <btPolyhedralConvexShape*>self.ptr_BoxShape
        self.ptr_ConvexInternalShape = <btConvexInternalShape*>self.ptr_BoxShape
        self.ptr_ConvexShape = <btConvexShape*>self.ptr_BoxShape
        self.ptr_CollisionShape = <btCollisionShape*>self.ptr_BoxShape

    def __dealloc__(self):
        if self.ptr_BoxShape != NULL:
            del self.ptr_BoxShape
