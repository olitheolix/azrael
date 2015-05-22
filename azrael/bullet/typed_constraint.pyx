cdef class TypedConstraintType:
    cdef readonly int POINT2POINT_CONSTRAINT_TYPE
    cdef readonly int HINGE_CONSTRAINT_TYPE
    cdef readonly int CONETWIST_CONSTRAINT_TYPE
    cdef readonly int D6_CONSTRAINT_TYPE
    cdef readonly int SLIDER_CONSTRAINT_TYPE
    cdef readonly int CONTACT_CONSTRAINT_TYPE
    cdef readonly int D6_SPRING_CONSTRAINT_TYPE
    cdef readonly int GEAR_CONSTRAINT_TYPE
    cdef readonly int FIXED_CONSTRAINT_TYPE
    cdef readonly int MAX_CONSTRAINT_TYPE

    def __cinit__(self):
       self.POINT2POINT_CONSTRAINT_TYPE = POINT2POINT_CONSTRAINT_TYPE
       self.HINGE_CONSTRAINT_TYPE = HINGE_CONSTRAINT_TYPE
       self.CONETWIST_CONSTRAINT_TYPE = CONETWIST_CONSTRAINT_TYPE
       self.D6_CONSTRAINT_TYPE = D6_CONSTRAINT_TYPE
       self.SLIDER_CONSTRAINT_TYPE = SLIDER_CONSTRAINT_TYPE
       self.CONTACT_CONSTRAINT_TYPE = CONTACT_CONSTRAINT_TYPE
       self.D6_SPRING_CONSTRAINT_TYPE = D6_SPRING_CONSTRAINT_TYPE
       self.GEAR_CONSTRAINT_TYPE = GEAR_CONSTRAINT_TYPE
       self.FIXED_CONSTRAINT_TYPE = FIXED_CONSTRAINT_TYPE
       self.MAX_CONSTRAINT_TYPE = MAX_CONSTRAINT_TYPE


cdef class TypedObject:
    cdef btTypedObject *ptr_TypedObject

    def __cinit__(self):
        self.ptr_TypedObject = NULL

    def __init__(self, int objectType):
        raise NotImplementedError

    def __dealloc__(self):
        pass

    def getObjectType(self):
        return self.ptr_TypedObject.getObjectType()


cdef class TypedConstraint(TypedObject):
    cdef RigidBody _ref_rbA, _ref_rbB
    cdef btTypedConstraint *ptr_TypedConstraint

    def __cinit__(self):
        self.ptr_TypedConstraint = NULL
        self._ref_rbA = self._ref_rbB = None

        # Assign the base pointers.
        self.ptr_TypedObject = <btTypedObject*?>self.ptr_TypedConstraint

    def __init__(self):
        pass

    def __dealloc__(self):
        pass

    def getRigidBodyA(self):
        return self._ref_rbA

    def getRigidBodyB(self):
        return self._ref_rbB

    def isEnabled(self):
        return self.ptr_TypedConstraint.isEnabled()

    def setEnabled(self, bint enabled):
        self.ptr_TypedConstraint.setEnabled(enabled)
    

cdef class Point2PointConstraint(TypedConstraint):
    cdef btPoint2PointConstraint *ptr_Point2PointConstraint

    def __cinit__(self):
        self.ptr_Point2PointConstraint = NULL

    def __init__(self, RigidBody rbA,
                       RigidBody rbB,
                       Vec3 pivotInA,
                       Vec3 pivotInB):
        self.ptr_Point2PointConstraint = new btPoint2PointConstraint(
            rbA.ptr_RigidBody[0], rbB.ptr_RigidBody[0],
            pivotInA.ptr_Vector3[0], pivotInB.ptr_Vector3[0])

        # Keep handles to the two objects alive.
        self._ref_rbA = rbA
        self._ref_rbB = rbB

        # Assign the base pointers.
        self.ptr_TypedConstraint = <btTypedConstraint*?>self.ptr_Point2PointConstraint
        self.ptr_TypedObject = <btTypedObject*?>self.ptr_TypedConstraint
        
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
