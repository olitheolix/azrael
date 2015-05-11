cdef class CollisionObject:
    cdef btCollisionObject *ptr_CollisionObject

    def __cinit__(self):
        self.ptr_CollisionObject = NULL

    def getCollisionShape(self):
        cs = CollisionShape()
        cs.ptr_CollisionShape = self.ptr_CollisionObject.getCollisionShape()
        return cs

    def setCollisionShape(self, CollisionShape collisionShape):
        self.ptr_CollisionObject.setCollisionShape(collisionShape.ptr_CollisionShape)
