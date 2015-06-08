from basic cimport *
from rigid_body cimport *

cdef extern from "btBulletDynamicsCommon.h":
    cdef enum btTypedConstraintType:
        POINT2POINT_CONSTRAINT_TYPE
        HINGE_CONSTRAINT_TYPE
        CONETWIST_CONSTRAINT_TYPE
        D6_CONSTRAINT_TYPE
        SLIDER_CONSTRAINT_TYPE
        CONTACT_CONSTRAINT_TYPE
        D6_SPRING_CONSTRAINT_TYPE
        GEAR_CONSTRAINT_TYPE
        FIXED_CONSTRAINT_TYPE
        MAX_CONSTRAINT_TYPE

    cdef enum RotateOrder:
        RO_XYZ
        RO_XZY
        RO_YXZ
        RO_YZX
        RO_ZXY
        RO_ZYX

    cdef cppclass btTypedObject:
        btTypedObject(int objectType)
        int getObjectType()

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

    cdef cppclass btGeneric6DofConstraint:
        btGeneric6DofConstraint(btRigidBody &rbA, btRigidBody &rbB,
                                const btTransform &frameInA,
                                const btTransform &frameInB,
                                bint useLinearReferenceFrameA)
        void setLinearLowerLimit(const btVector3 &linearLower)
        void getLinearLowerLimit(btVector3 &linearLower)
        void setLinearUpperLimit(const btVector3 &linearUpper)
        void getLinearUpperLimit(btVector3 &linearUpper)
        void setAngularLowerLimit (const btVector3 &angularLower)
        void getAngularLowerLimit(btVector3 &angularLower)
        void setAngularUpperLimit(const btVector3 &angularUpper)
        void getAngularUpperLimit(btVector3 &angularUpper)

    cdef cppclass btGeneric6DofSpringConstraint:
        btGeneric6DofSpringConstraint(btRigidBody &rbA,
                                      btRigidBody &rbB,
                                      const btTransform &frameInA,
                                      const btTransform &frameInB,
                                      bint useLinearReferenceFrameA)
        void enableSpring(int index, bint onOff)
        void setStiffness(int index, btScalar stiffness)
        void setDamping(int index, btScalar damping)
        void setEquilibriumPoint()

    cdef cppclass btGeneric6DofSpring2Constraint:
        btGeneric6DofSpring2Constraint(btRigidBody &rbA,
                                       btRigidBody &rbB,
                                       const btTransform &frameInA,
                                       const btTransform &frameInB,
                                       RotateOrder rotOrder)
        void enableSpring(int index, bint onOff)
        void setStiffness(int index, btScalar stiffness)
        void setDamping(int index, btScalar damping)
        void setEquilibriumPoint()
        void setBounce(int index, btScalar bounce)
