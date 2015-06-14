from azBullet cimport *
from basic cimport *
from collision_shapes cimport *
from transform cimport *
from motion_state cimport *
from collision_object cimport *
from rigid_body cimport *


cdef extern from "btBulletDynamicsCommon.h" namespace "btRigidBody":
    cdef cppclass btRigidBodyConstructionInfo:
        btRigidBodyConstructionInfo(
            btScalar mass, btMotionState* motionState,
            btCollisionShape* collisionShape,
            const btVector3& localInertia)

        btMotionState*    m_motionState
        btTransform       m_startWorldTransform
        btCollisionShape* m_collisionShape
        bint              m_additionalDamping
        btVector3         m_localInertia
        btScalar          m_mass
        btScalar          m_linearDamping
        btScalar          m_angularDamping
        btScalar          m_friction
        btScalar          m_rollingFriction
        btScalar          m_restitution
        btScalar          m_linearSleepingThreshold
        btScalar          m_angularSleepingThreshold
        btScalar          m_additionalDampingFactor
        btScalar          m_additionalLinearDampingThresholdSqr
        btScalar          m_additionalAngularDampingThresholdSqr
        btScalar          m_additionalAngularDampingFactor


cdef extern from "btBulletDynamicsCommon.h":
    cdef cppclass btRigidBody:
        btRigidBody (btRigidBodyConstructionInfo &constructionInfo)

        # {get,set}UserPointer
        void *getUserPointer()
        void setUserPointer(void *userPointer)

        # {get,set}MotionState
        btMotionState *getMotionState()
        void setMotionState(btMotionState*)

        # {get,set}Restitution
        void setRestitution(btScalar r)
        btScalar getRestitution()

        # CenterOfMassTransform.
        void setCenterOfMassTransform(const btTransform &xform)
        btTransform &getCenterOfMassTransform()

        # ------------------------------------------------------------
        void forceActivationState(int newState)

        # Mass- and inertia related.
        btScalar getInvMass()
        btVector3 &getInvInertiaDiagLocal()
        void setMassProps(btScalar mass, const btVector3 &inertia)

        # Force functions: clearForces, applyForce, applyTorque,
        #                  applyCentralForce, getTotalForce, getTotalTorque
        void clearForces()
        void applyForce(const btVector3& force, const btVector3& rel_pos)
        void applyTorque(const btVector3& torque)
        void applyCentralForce(const btVector3& force)
        const btVector3& getTotalForce()
        const btVector3& getTotalTorque()

        # setSleepingThresholds and get{Linear,Angular}SleepingThreshold
        void setSleepingThresholds(btScalar linear, btScalar angular)
        btScalar getLinearSleepingThreshold()
        btScalar getAngularSleepingThreshold()

        # {set,get}Friction
        void setFriction (btScalar frict)
        btScalar getFriction()

        # {set,get}Damping
        void setDamping(btScalar lin_damping, btScalar ang_damping)
        btScalar getLinearDamping()
        btScalar getAngularDamping()

        # {set,get}{Linear,Angular}Factor
        void setLinearFactor(const btVector3& linearFactor)
        void setAngularFactor(const btVector3& angFac)
        btVector3& getLinearFactor()
        btVector3& getAngularFactor()

        # {get,set}{Linear,Angular}Velocity
        void setAngularVelocity(const btVector3& ang_vel)
        void setLinearVelocity(const btVector3& lin_vel)
        btVector3& getLinearVelocity()
        btVector3& getAngularVelocity()
