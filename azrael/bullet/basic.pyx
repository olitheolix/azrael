cdef class Scalar:
    cdef btScalar *ptr_btScalar

    def __cinit__(self):
        self.ptr_btScalar = NULL

    def __init__(self, double x=0):
        self.ptr_btScalar = new btScalar(x)

    def __dealloc__(self):
        if self.ptr_btScalar != NULL:
            del self.ptr_btScalar
            self.ptr_btScalar = NULL

    def value(self):
        return <double>(self.ptr_btScalar[0])

    def __repr__(self):
        return str(<double>self.ptr_btScalar[0])

cdef class Vec3:
    cdef btVector3 *ptr_Vector3

    def __cinit__(self):
        self.ptr_Vector3 = NULL

    def __init__(self, double x=0, double y=0, double z=0):
        self.ptr_Vector3 = new btVector3(x, y, z)

    def __dealloc__(self):
        if self.ptr_Vector3 != NULL:
            del self.ptr_Vector3
            self.ptr_Vector3 = NULL

    def __neg__(self):
        ret = Vec3()
        ret.ptr_Vector3[0] = -self.ptr_Vector3[0]
        return ret

    def __add__(Vec3 self, Vec3 v):
        ret = Vec3()
        ret.ptr_Vector3[0] = self.ptr_Vector3[0] + v.ptr_Vector3[0]
        return ret

    def __sub__(Vec3 self, Vec3 v):
        ret = Vec3()
        ret.ptr_Vector3[0] = self.ptr_Vector3[0] - v.ptr_Vector3[0]
        return ret

    def __richcmp__(Vec3 x, Vec3 y, int op):
        if op == Py_EQ:
            return (x.ptr_Vector3[0] == y.ptr_Vector3[0])
        elif op == Py_NE:
            return (x.ptr_Vector3[0] != y.ptr_Vector3[0])
        else:
            assert False

    def topy(self):
        t = self.ptr_Vector3
        return (<double>t.x(), <double>t.y(), <double>t.z())

    def __repr__(self):
        return repr(self.topy())


cdef class Quaternion:
    cdef btQuaternion *ptr_Quaternion

    def __cinit__(self):
        self.ptr_Quaternion = NULL

    def __init__(self, double x=0, double y=0, double z=0, double w=1):
        self.ptr_Quaternion = new btQuaternion(x, y, z, w)

    def __dealloc__(self):
        if self.ptr_Quaternion != NULL:
            del self.ptr_Quaternion
            self.ptr_Quaternion = NULL

    def topy(self):
        t = self.ptr_Quaternion
        return (<double>t.x(), <double>t.y(), <double>t.z(), <double>t.w())

    def __richcmp__(Quaternion a, Quaternion b, int op):
        def isEqual():
            p_a = a.ptr_Quaternion
            p_b = b.ptr_Quaternion
            return (
                (<double?>p_a.x() == <double?>p_b.x()) and 
                (<double?>p_a.y() == <double?>p_b.y()) and
                (<double?>p_a.z() == <double?>p_b.z()) and
                (<double?>p_a.w() == <double?>p_b.w()))
            
        if op == Py_EQ:
            return isEqual()
        elif op == Py_NE:
            return not isEqual()
        else:
            assert False

    def __repr__(self):
        return repr(self.topy())
