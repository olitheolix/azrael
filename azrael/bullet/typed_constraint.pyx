cdef class TypedConstraint:
    cdef btTypedConstraint *ptr_TypedConstraint

    def __cinit__(self):
        self.ptr_TypedConstraint = NULL
    # int getUserConstraintType()
    # void setUserConstraintType(int userConstraintType)

    def __init__(self):
        pass

    def __dealloc__(self):
        pass

    def getRigidBodyA(self):
        # fixme: this is ridiculous, just to get a RigidBody object.
        cs = SphereShape(1)
        t = Transform(Quaternion(0, 0, 0, 1), Vec3(0, 0, 0))
        ms = DefaultMotionState(t)
        mass = 1
        inertia = Vec3(0, 0, 0)
        body = RigidBody(mass, ms, cs, inertia)
        body.ptr_RigidBody[0] = self.ptr_TypedConstraint.getRigidBodyA()
        return body

    def getRigidBodyB(self):
        # fixme: this is ridiculous, just to get a RigidBody object.
        cs = SphereShape(1)
        t = Transform(Quaternion(0, 0, 0, 1), Vec3(0, 0, 0))
        ms = DefaultMotionState(t)
        mass = 1
        inertia = Vec3(0, 0, 0)
        body = RigidBody(mass, ms, cs, inertia)
        body.ptr_RigidBody[0] = self.ptr_TypedConstraint.getRigidBodyB()
        return body

    def isEnabled(self):
        return self.ptr_TypedConstraint.isEnabled()

    def setEnabled(self, bint enabled):
        self.ptr_TypedConstraint.setEnabled(enabled)
    

cdef class Point2PointConstraint(TypedConstraint):
    cdef btPoint2PointConstraint *ptr_Point2PointConstraint

    def __cinit__(self, RigidBody rbA,
                        RigidBody rbB,
                        Vec3 pivotInA,
                        Vec3 pivotInB):
        self.ptr_Point2PointConstraint = NULL

    def __init__(self, RigidBody rbA,
                       RigidBody rbB,
                       Vec3 pivotInA,
                       Vec3 pivotInB):
        self.ptr_Point2PointConstraint = new btPoint2PointConstraint(
            rbA.ptr_RigidBody[0], rbB.ptr_RigidBody[0],
            pivotInA.ptr_Vector3[0], pivotInB.ptr_Vector3[0])

        # Assign the base pointers.
        self.ptr_TypedConstraint = <btTypedConstraint*?>self.ptr_Point2PointConstraint

    def __dealloc__(self):
        if self.ptr_TypedConstraint != NULL:
            del self.ptr_TypedConstraint


    def setPivotA(self, Vec3 pivotA):
        self.ptr_Point2PointConstraint.setPivotA(pivotA.ptr_Vector3[0])

    def setPivotB(self, Vec3 pivotB):
        self.ptr_Point2PointConstraint.setPivotB(pivotB.ptr_Vector3[0])

    def getPivotInA(self):
        v = Vec3(0, 0, 0)
        v.ptr_Vector3[0] = self.ptr_Point2PointConstraint.getPivotInA()
        return v

    def getPivotInB(self):
        v = Vec3(0, 0, 0)
        v.ptr_Vector3[0] = self.ptr_Point2PointConstraint.getPivotInB()
        return v
