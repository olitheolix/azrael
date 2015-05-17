cdef class MotionState:
    cdef btMotionState *ptr_MotionState

    def __cinit__(self):
        self.ptr_MotionState = NULL

    def __init__(self):
        raise NotImplementedError

    def __dealloc__(self):
        if self.ptr_MotionState != NULL:
            del self.ptr_MotionState
            self.ptr_MotionState = NULL

    def __repr__(self):
        return repr(self.getWorldTransform())

    def topy(self):
        return self.getWorldTransform().topy()

    def getWorldTransform(self):
        t = Transform()
        self.ptr_MotionState.getWorldTransform(t.ptr_Transform[0])
        return t

    def setWorldTransform(self, Transform worldTrans):
        self.ptr_MotionState.setWorldTransform(worldTrans.ptr_Transform[0])

 
cdef class DefaultMotionState(MotionState):
    cdef btDefaultMotionState *ptr_DefaultMotionState

    def __cinit__(self):
        self.ptr_DefaultMotionState = NULL

    def __init__(self, Transform t=Transform()):
        self.ptr_DefaultMotionState = new btDefaultMotionState(t.ptr_Transform[0])
        self.ptr_MotionState = <btMotionState*>self.ptr_DefaultMotionState

    def __dealloc__(self):
        if self.ptr_DefaultMotionState != NULL:
            del self.ptr_DefaultMotionState
            self.ptr_MotionState = NULL
            self.ptr_DefaultMotionState = NULL
