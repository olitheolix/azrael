cdef class Scalar:
    cdef btScalar *thisptr

    def __cinit__(self, double x=0):
        self.thisptr = new btScalar(x)

    def __dealloc__(self):
        del self.thisptr

    def value(self):
        return <double>(self.thisptr[0])

    def __repr__(self):
        return str(<double>self.thisptr[0])

cdef class Vec3:
    cdef btVector3 *thisptr

    def __cinit__(self, double x=0, double y=0, double z=0):
        self.thisptr = new btVector3(x, y, z)

    def __dealloc__(self):
        del self.thisptr

    def __neg__(self):
        ret = Vec3()
        ret.thisptr[0] = -self.thisptr[0]
        return ret

    def __add__(Vec3 self, Vec3 v):
        ret = Vec3()
        ret.thisptr[0] = self.thisptr[0] + v.thisptr[0]
        return ret

    def __sub__(Vec3 self, Vec3 v):
        ret = Vec3()
        ret.thisptr[0] = self.thisptr[0] - v.thisptr[0]
        return ret

    def __richcmp__(Vec3 x, Vec3 y, int op):
        if op == Py_EQ:
            return (x.thisptr[0] == y.thisptr[0])
        elif op == Py_NE:
            return (x.thisptr[0] != y.thisptr[0])
        else:
            assert False

    def tolist(self):
        t = self.thisptr
        return (<double>t.x(), <double>t.y(), <double>t.z())

    def __repr__(self):
        return repr(self.tolist())


cdef class Quaternion:
    cdef btQuaternion *ptr_Quaternion

    def __cinit__(self, double x=0, double y=0, double z=0, double w=1):
        self.ptr_Quaternion = new btQuaternion(x, y, z, w)

    def __dealloc__(self):
        del self.ptr_Quaternion

    def tolist(self):
        t = self.ptr_Quaternion
        return (<double>t.x(), <double>t.y(), <double>t.z(), <double>t.w())

    def __repr__(self):
        return repr(self.tolist())
