cdef class CollisionObject:
    cdef MotionState _ref_ms
    cdef CollisionShape _ref_cs
    cdef btCollisionObject *ptr_CollisionObject

    def __cinit__(self):
        self.ptr_CollisionObject = NULL
        self._ref_ms = self._ref_cs = None

    def getCollisionShape(self):
        cs = CollisionShape()
        cs.ptr_CollisionShape = self.ptr_CollisionObject.getCollisionShape()
        return cs

    def setCollisionShape(self, CollisionShape collisionShape):
        self.ptr_CollisionObject.setCollisionShape(collisionShape.ptr_CollisionShape)
