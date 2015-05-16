cdef class Transform:
    cdef btTransform *thisptr

    def __cinit__(self, Quaternion q=Quaternion(0, 0, 0, 1), Vec3 c=Vec3(0, 0, 0)):
        self.thisptr = new btTransform(q.ptr_Quaternion[0], c.ptr_Vector3[0]) 

    def setIdentity(self):
        self.thisptr.setIdentity()

    def setOrigin(self, Vec3 v):
        self.thisptr.setOrigin(v.ptr_Vector3[0])

    def getOrigin(self):
        v = Vec3(0, 0, 0)
        v.ptr_Vector3[0] = self.thisptr.getOrigin()
        return v
        
    def setRotation(self, Quaternion q):
        self.thisptr.setRotation(q.ptr_Quaternion[0])

    def getRotation(self):
        q = Quaternion()
        q.ptr_Quaternion[0] = self.thisptr.getRotation()
        return q

    def __dealloc__(self):
        del self.thisptr
