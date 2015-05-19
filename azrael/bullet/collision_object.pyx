cdef class CollisionObject:
    cdef MotionState _ref_ms
    cdef CollisionShape _ref_cs
    cdef btCollisionObject *ptr_CollisionObject

    def __cinit__(self):
        self.ptr_CollisionObject = NULL
        self._ref_ms = self._ref_cs = None

    def getCollisionShape(self):
        cdef btCollisionShape *tmp = self.ptr_CollisionObject.getCollisionShape()
        if <long>tmp != <long>self._ref_cs.ptr_CollisionShape:
            raise AssertionError(
                'Invalid pointer in CollisionObject.getCollisionShape')
        return self._ref_cs

    def setCollisionShape(self, CollisionShape collisionShape):
        self._ref_cs = collisionShape
        self.ptr_CollisionObject.setCollisionShape(collisionShape.ptr_CollisionShape)
