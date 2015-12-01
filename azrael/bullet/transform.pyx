from collections import namedtuple
NT = namedtuple('Transform', 'origin rotation')

cdef class Transform:
    cdef btTransform *ptr_Transform

    def __cinit__(self):
        self.ptr_Transform = NULL

    def __init__(self, Quaternion q=Quaternion(0, 0, 0, 1), Vec3 c=Vec3(0, 0, 0)):
        self.ptr_Transform = new btTransform(q.ptr_Quaternion[0], c.ptr_Vector3[0]) 

    def __dealloc__(self):
        if self.ptr_Transform != NULL:
            del self.ptr_Transform

    def __repr__(self):
        tmp = self.topy()
        attr = ['{}={}'.format(name, getattr(tmp, name)) for name in tmp._fields]
        return '  '.join(attr)

    def __mul__(Transform self, Vec3 v):
        cdef btVector3 tmp = self.ptr_Transform[0] * v.ptr_Vector3[0]
        return Vec3(<double>tmp.x(), <double>tmp.y(), <double>tmp.z())

    def topy(self):
        p, r = self.getOrigin(), self.getRotation()
        ret = NT(p.topy(), r.topy())
        return ret

    def setIdentity(self):
        self.ptr_Transform.setIdentity()

    def setOrigin(self, Vec3 v):
        self.ptr_Transform.setOrigin(v.ptr_Vector3[0])

    def getOrigin(self):
        v = Vec3(0, 0, 0)
        v.ptr_Vector3[0] = self.ptr_Transform.getOrigin()
        return v
        
    def setRotation(self, Quaternion q):
        self.ptr_Transform.setRotation(q.ptr_Quaternion[0])

    def getRotation(self):
        q = Quaternion()
        q.ptr_Quaternion[0] = self.ptr_Transform.getRotation()
        return q

    def inverse(self):
        ret = Transform()
        ret.ptr_Transform[0] = self.ptr_Transform.inverse()
        return ret

    def mult(self, Transform a, Transform b):
        self.ptr_Transform.mult(a.ptr_Transform[0], b.ptr_Transform[0])
