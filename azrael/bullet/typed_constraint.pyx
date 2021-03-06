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

    def __repr__(self):
        return 'Unknown TypedConstraint'

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
        if self.ptr_Point2PointConstraint != NULL:
            del self.ptr_Point2PointConstraint

            self.ptr_Point2PointConstraint = NULL
            self.ptr_TypedObject = NULL
            self.ptr_TypedConstraint = NULL

    def __repr__(self):
        s = 'Point2PointConstraint: {} - {}'
        s = s.format(self._ref_rbA.azGetBodyID(), self._ref_rbB.azGetBodyID())
        return s

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


cdef class Generic6DofConstraint(TypedConstraint):
    cdef btGeneric6DofConstraint *ptr_Generic6DofConstraint

    def __cinit__(self):
        self.ptr_Generic6DofConstraint = NULL

    def __init__(self, RigidBody rbA,
                       RigidBody rbB,
                       Transform frameInA,
                       Transform frameInB,
                       bint refIsA):
        self.ptr_Generic6DofConstraint = new btGeneric6DofConstraint(
            rbA.ptr_RigidBody[0],
            rbB.ptr_RigidBody[0],
            frameInA.ptr_Transform[0],
            frameInB.ptr_Transform[0],
            refIsA)

        # Keep handles to the two objects alive.
        self._ref_rbA = rbA
        self._ref_rbB = rbB

        # Assign the base pointers.
        self.ptr_TypedConstraint = <btTypedConstraint*?>self.ptr_Generic6DofConstraint
        self.ptr_TypedObject = <btTypedObject*?>self.ptr_TypedConstraint

    def __dealloc__(self):
        if self.ptr_Generic6DofConstraint != NULL:
            del self.ptr_Generic6DofConstraint

            self.ptr_Generic6DofConstraint = NULL
            self.ptr_TypedObject = NULL
            self.ptr_TypedConstraint = NULL

    def __repr__(self):
        s = 'Generic6DofConstraint: {} - {}'
        s = s.format(self._ref_rbA.azGetBodyID(), self._ref_rbB.azGetBodyID())
        return s

    def setLinearLowerLimit(self, Vec3 lim):
        self.ptr_Generic6DofConstraint.setLinearLowerLimit(lim.ptr_Vector3[0])

    def getLinearLowerLimit(self):
        ret = Vec3()
        self.ptr_Generic6DofConstraint.getLinearLowerLimit(ret.ptr_Vector3[0])
        return ret

    def setLinearUpperLimit(self, Vec3 lim):
        self.ptr_Generic6DofConstraint.setLinearUpperLimit(lim.ptr_Vector3[0])

    def getLinearUpperLimit(self):
        ret = Vec3()
        self.ptr_Generic6DofConstraint.getLinearUpperLimit(ret.ptr_Vector3[0])
        return ret

    def setAngularLowerLimit(self, Vec3 lim):
        self.ptr_Generic6DofConstraint.setAngularLowerLimit(lim.ptr_Vector3[0])

    def getAngularLowerLimit(self):
        ret = Vec3()
        self.ptr_Generic6DofConstraint.getAngularLowerLimit(ret.ptr_Vector3[0])
        return ret

    def setAngularUpperLimit(self, Vec3 lim):
        self.ptr_Generic6DofConstraint.setAngularUpperLimit(lim.ptr_Vector3[0])

    def getAngularUpperLimit(self):
        ret = Vec3()
        self.ptr_Generic6DofConstraint.getAngularUpperLimit(ret.ptr_Vector3[0])
        return ret


cdef class Generic6DofSpringConstraint(Generic6DofConstraint):
    cdef btGeneric6DofSpringConstraint *ptr_Generic6DofSpringConstraint

    def __cinit__(self):
        self.ptr_Generic6DofSpringConstraint = NULL

    def __init__(self, RigidBody rbA,
                       RigidBody rbB,
                       Transform frameInA,
                       Transform frameInB,
                       bint refIsA):
        self.ptr_Generic6DofSpringConstraint = new btGeneric6DofSpringConstraint(
            rbA.ptr_RigidBody[0],
            rbB.ptr_RigidBody[0],
            frameInA.ptr_Transform[0],
            frameInB.ptr_Transform[0],
            refIsA)

        # Keep handles to the two objects alive.
        self._ref_rbA = rbA
        self._ref_rbB = rbB

        # Assign the base pointers.
        self.ptr_TypedConstraint = <btTypedConstraint*?>self.ptr_Generic6DofSpringConstraint
        self.ptr_Generic6DofConstraint = <btGeneric6DofConstraint*?>self.ptr_Generic6DofSpringConstraint
        self.ptr_TypedObject = <btTypedObject*?>self.ptr_TypedConstraint

    def __dealloc__(self):
        if self.ptr_Generic6DofSpringConstraint != NULL:
            del self.ptr_Generic6DofSpringConstraint

            self.ptr_Generic6DofSpringConstraint = NULL
            self.ptr_Generic6DofConstraint = NULL
            self.ptr_TypedObject = NULL
            self.ptr_TypedConstraint = NULL

    def __repr__(self):
        s = 'Generic6DofSpringConstraint: {} - {}'
        s = s.format(self._ref_rbA.azGetBodyID(), self._ref_rbB.azGetBodyID())
        return s

    def enableSpring(self, int index, bint onOff):
        if not (0 <= index < 6):
            return
        self.ptr_Generic6DofSpringConstraint.enableSpring(index, onOff)

    def setStiffness(self, int index, double stiffness):
        if not (0 <= index < 6):
            return
        self.ptr_Generic6DofSpringConstraint.setStiffness(index, btScalar(stiffness))

    def setDamping(self, int index, double damping):
        if not (0 <= index < 6):
            return
        self.ptr_Generic6DofSpringConstraint.setDamping(index, btScalar(damping))

    def setEquilibriumPoint(self, int index, double val):
        self.ptr_Generic6DofSpringConstraint.setEquilibriumPoint(index, btScalar(val))


cdef class Generic6DofSpring2Constraint(Generic6DofConstraint):
    cdef btGeneric6DofSpring2Constraint *ptr_Generic6DofSpring2Constraint

    def __cinit__(self):
        self.ptr_Generic6DofSpring2Constraint = NULL

    def __init__(self, RigidBody rbA,
                       RigidBody rbB,
                       Transform frameInA,
                       Transform frameInB,
                       RotateOrder rotOrder=RO_XYZ):
        self.ptr_Generic6DofSpring2Constraint = new btGeneric6DofSpring2Constraint(
            rbA.ptr_RigidBody[0],
            rbB.ptr_RigidBody[0],
            frameInA.ptr_Transform[0],
            frameInB.ptr_Transform[0],
            rotOrder)

        # Keep handles to the two objects alive.
        self._ref_rbA = rbA
        self._ref_rbB = rbB

        # Assign the base pointers.
        self.ptr_TypedConstraint = <btTypedConstraint*?>self.ptr_Generic6DofSpring2Constraint
        self.ptr_Generic6DofConstraint = <btGeneric6DofConstraint*?>self.ptr_Generic6DofSpring2Constraint
        self.ptr_TypedObject = <btTypedObject*?>self.ptr_TypedConstraint

    def __dealloc__(self):
        if self.ptr_Generic6DofSpring2Constraint != NULL:
            del self.ptr_Generic6DofSpring2Constraint

            self.ptr_Generic6DofSpring2Constraint = NULL
            self.ptr_Generic6DofConstraint = NULL
            self.ptr_TypedObject = NULL
            self.ptr_TypedConstraint = NULL

    def __repr__(self):
        s = 'Generic6DofSpring2Constraint: {} - {}'
        s = s.format(self._ref_rbA.azGetBodyID(), self._ref_rbB.azGetBodyID())
        return s

    def enableSpring(self, int index, bint onOff):
        if not (0 <= index < 6):
            return
        self.ptr_Generic6DofSpring2Constraint.enableSpring(index, onOff)

    def setStiffness(self, int index, double stiffness):
        if not (0 <= index < 6):
            return
        self.ptr_Generic6DofSpring2Constraint.setStiffness(index, btScalar(stiffness))

    def setDamping(self, int index, double damping):
        if not (0 <= index < 6):
            return
        self.ptr_Generic6DofSpring2Constraint.setDamping(index, btScalar(damping))

    def setEquilibriumPoint(self, int index, double val):
        self.ptr_Generic6DofSpring2Constraint.setEquilibriumPoint(index, btScalar(val))

    def setBounce(self, int index, double bounce):
        self.ptr_Generic6DofSpring2Constraint.setBounce(index, btScalar(bounce))
