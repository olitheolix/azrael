cdef class MotionState:
    cdef btMotionState *ptr_MotionState

    def __cinit__(self):
        self.ptr_MotionState = NULL

    def getWorldTransform(self):
        t = Transform()
        self.ptr_MotionState.getWorldTransform(t.thisptr[0])
        return t

    def setWorldTransform(self, Transform worldTrans):
        self.ptr_MotionState.setWorldTransform(worldTrans.thisptr[0])

 
cdef class DefaultMotionState(MotionState):
    cdef btDefaultMotionState *ptr_DefaultMotionState

    def __cinit__(self, Transform t=Transform()):
        self.ptr_DefaultMotionState = new btDefaultMotionState(t.thisptr[0])
        self.ptr_MotionState = <btMotionState*>self.ptr_DefaultMotionState

    def __dealloc__(self):
        del self.ptr_DefaultMotionState
