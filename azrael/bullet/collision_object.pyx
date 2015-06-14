cdef class CollisionObject:
    cdef MotionState _ref_ms
    cdef CollisionShape _ref_cs
    cdef btCollisionObject *ptr_CollisionObject

    def __cinit__(self):
        self.ptr_CollisionObject = NULL
        self._ref_ms = self._ref_cs = None

    def __dealloc__(self):
        if self.ptr_CollisionObject != NULL:
            if self.ptr_CollisionObject.getUserPointer() != NULL:
                free(self.ptr_CollisionObject.getUserPointer())
                self.ptr_CollisionObject.setUserPointer(NULL)

    def getCollisionShape(self):
        cdef btCollisionShape *tmp = self.ptr_CollisionObject.getCollisionShape()
        if <long>tmp != <long>self._ref_cs.ptr_CollisionShape:
            raise AssertionError(
                'Invalid pointer in CollisionObject.getCollisionShape')
        return self._ref_cs

    def setCollisionShape(self, CollisionShape collisionShape):
        self._ref_cs = collisionShape
        self.ptr_CollisionObject.setCollisionShape(collisionShape.ptr_CollisionShape)

    def azSetBodyID(self, int bodyID):
        cdef int *tmp

        # If the user pointer is still NULL then allocate an int and assign it
        # to the user pointer.
        if self.azGetBodyID() is None:
            tmp = <int*>malloc(sizeof(int))
            assert tmp != NULL
            self.ptr_CollisionObject.setUserPointer(<void*>tmp)

        # Update the bodyID value.
        tmp = <int*>self.ptr_CollisionObject.getUserPointer()
        tmp[0] = bodyID

    def azGetBodyID(self):
        cdef void *tmp = self.ptr_CollisionObject.getUserPointer()
        if tmp == NULL:
            return None
        else:
            return (<int*>tmp)[0]
