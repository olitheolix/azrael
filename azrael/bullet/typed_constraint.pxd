from basic cimport *
from rigid_body cimport *

cdef extern from "btBulletDynamicsCommon.h":
    cdef enum btTypedConstraintType:
        POINT2POINT_CONSTRAINT_TYPE=3
        HINGE_CONSTRAINT_TYPE
        CONETWIST_CONSTRAINT_TYPE
        D6_CONSTRAINT_TYPE
        SLIDER_CONSTRAINT_TYPE
        CONTACT_CONSTRAINT_TYPE
        D6_SPRING_CONSTRAINT_TYPE
        GEAR_CONSTRAINT_TYPE
        FIXED_CONSTRAINT_TYPE
        MAX_CONSTRAINT_TYPE

    cdef cppclass btTypedConstraint:
        btTypedConstraint(btTypedConstraintType t, btRigidBody &rbA)
        btTypedConstraint(btTypedConstraintType t, btRigidBody &rbA, btRigidBody &rbB)
        btRigidBody &getRigidBodyA()
        btRigidBody &getRigidBodyB()
        bint isEnabled()
        void setEnabled(bint enabled)
        int getUserConstraintType()
        void setUserConstraintType(int userConstraintType)

    cdef cppclass btPoint2PointConstraint:
        btPoint2PointConstraint(btRigidBody &rbA, btRigidBody &rbB,
            const btVector3 &pivotInA, const btVector3 &pivotInB)
        void setPivotA(const btVector3 &pivotA)
        void setPivotB(const btVector3 &pivotB)
        btVector3 &getPivotInA()
        btVector3 &getPivotInB()
