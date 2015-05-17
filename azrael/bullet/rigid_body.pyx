cdef class RigidBodyConstructionInfo:
    cdef btRigidBodyConstructionInfo *ptr_RigidBodyConstructionInfo

    def __cinit__(self, double mass, MotionState ms, CollisionShape cs,
                  Vec3 inert=Vec3(0, 0, 0)):
        self.ptr_RigidBodyConstructionInfo = NULL

    def __init__(self, double mass, MotionState ms, CollisionShape cs,
                  Vec3 inert=Vec3(0, 0, 0)):
        self.ptr_RigidBodyConstructionInfo = new btRigidBodyConstructionInfo(
            btScalar(mass),
            ms.ptr_MotionState,
            cs.ptr_CollisionShape,
            inert.ptr_Vector3[0])

    def __dealloc__(self):
        if self.ptr_RigidBodyConstructionInfo != NULL:
            del self.ptr_RigidBodyConstructionInfo

    property localInertia:
        def __get__(self):
            v = Vec3()
            v.ptr_Vector3[0] = self.ptr_RigidBodyConstructionInfo.m_localInertia
            return v

        def __set__(self, Vec3 value):
            self.ptr_RigidBodyConstructionInfo.m_localInertia = value.ptr_Vector3[0]

        def __del__(self):
            pass


    property mass:
        def __get__(self):
            return <double>self.ptr_RigidBodyConstructionInfo.m_mass

        def __set__(self, double value):
            self.ptr_RigidBodyConstructionInfo.m_mass = btScalar(value)

        def __del__(self):
            pass


    property linearDamping:
        def __get__(self):
            return <double>self.ptr_RigidBodyConstructionInfo.m_linearDamping

        def __set__(self, double value):
            self.ptr_RigidBodyConstructionInfo.m_linearDamping = btScalar(value)

        def __del__(self):
            pass


    property angularDamping:
        def __get__(self):
            return <double>self.ptr_RigidBodyConstructionInfo.m_angularDamping

        def __set__(self, double value):
            self.ptr_RigidBodyConstructionInfo.m_angularDamping = btScalar(value)

        def __del__(self):
            pass


    property friction:
        def __get__(self):
            return <double>self.ptr_RigidBodyConstructionInfo.m_friction

        def __set__(self, double value):
            self.ptr_RigidBodyConstructionInfo.m_friction = btScalar(value)

        def __del__(self):
            pass


    property rollingFriction:
        def __get__(self):
            return <double>self.ptr_RigidBodyConstructionInfo.m_rollingFriction

        def __set__(self, double value):
            self.ptr_RigidBodyConstructionInfo.m_rollingFriction = btScalar(value)

        def __del__(self):
            pass


    property restitution:
        def __get__(self):
            return <double>self.ptr_RigidBodyConstructionInfo.m_restitution

        def __set__(self, double value):
            self.ptr_RigidBodyConstructionInfo.m_restitution = btScalar(value)

        def __del__(self):
            pass


    property linearSleepingThreshold:
        def __get__(self):
            return <double>self.ptr_RigidBodyConstructionInfo.m_linearSleepingThreshold

        def __set__(self, double value):
            self.ptr_RigidBodyConstructionInfo.m_linearSleepingThreshold = btScalar(value)

        def __del__(self):
            pass


    property angularSleepingThreshold:
        def __get__(self):
            return <double>self.ptr_RigidBodyConstructionInfo.m_angularSleepingThreshold

        def __set__(self, double value):
            self.ptr_RigidBodyConstructionInfo.m_angularSleepingThreshold = btScalar(value)

        def __del__(self):
            pass


    property additionalDampingFactor:
        def __get__(self):
            return <double>self.ptr_RigidBodyConstructionInfo.m_additionalDampingFactor

        def __set__(self, double value):
            self.ptr_RigidBodyConstructionInfo.m_additionalDampingFactor = btScalar(value)

        def __del__(self):
            pass


    property additionalLinearDampingThresholdSqr:
        def __get__(self):
            return <double>self.ptr_RigidBodyConstructionInfo.m_additionalLinearDampingThresholdSqr

        def __set__(self, double value):
            self.ptr_RigidBodyConstructionInfo.m_additionalLinearDampingThresholdSqr = btScalar(value)

        def __del__(self):
            pass


    property additionalAngularDampingThresholdSqr:
        def __get__(self):
            return <double>self.ptr_RigidBodyConstructionInfo.m_additionalAngularDampingThresholdSqr

        def __set__(self, double value):
            self.ptr_RigidBodyConstructionInfo.m_additionalAngularDampingThresholdSqr = btScalar(value)

        def __del__(self):
            pass


    property additionalAngularDampingFactor:
        def __get__(self):
            return <double>self.ptr_RigidBodyConstructionInfo.m_additionalAngularDampingFactor

        def __set__(self, double value):
            self.ptr_RigidBodyConstructionInfo.m_additionalAngularDampingFactor = btScalar(value)

        def __del__(self):
            pass


cdef class RigidBody(CollisionObject):
    cdef btRigidBody *ptr_RigidBody

    def __cinit__(self, RigidBodyConstructionInfo ci):
        self.ptr_RigidBody = NULL

    def __init__(self, RigidBodyConstructionInfo ci):
        self.ptr_RigidBody = new btRigidBody(ci.ptr_RigidBodyConstructionInfo[0])

        # Assign the base pointers.
        self.ptr_CollisionObject = <btCollisionObject*?>self.ptr_RigidBody

    def __dealloc__(self):
        if self.ptr_RigidBody != NULL:
            del self.ptr_RigidBody

    def setRestitution(self, double r):
        self.ptr_RigidBody.setRestitution(btScalar(r))

    def getRestitution(self):
        return <double>self.ptr_RigidBody.getRestitution()

    def getLinearFactor(self):
        p = Vec3()
        p.ptr_Vector3[0] = self.ptr_RigidBody.getLinearFactor()
        return p

    def setLinearFactor(self, Vec3 linearFactor):
        self.ptr_RigidBody.setLinearFactor(linearFactor.ptr_Vector3[0])

    def getAngularFactor(self):
        p = Vec3()
        p.ptr_Vector3[0] = self.ptr_RigidBody.getAngularFactor()
        return p

    def setAngularFactor(self, Vec3 angularFactor):
        self.ptr_RigidBody.setAngularFactor(angularFactor.ptr_Vector3[0])

    def getLinearVelocity(self):
        p = Vec3()
        p.ptr_Vector3[0] = self.ptr_RigidBody.getLinearVelocity()
        return p

    def setLinearVelocity(self, Vec3 linearVelocity):
        self.ptr_RigidBody.setLinearVelocity(linearVelocity.ptr_Vector3[0])

    def getAngularVelocity(self):
        p = Vec3()
        p.ptr_Vector3[0] = self.ptr_RigidBody.getAngularVelocity()
        return p

    def setAngularVelocity(self, Vec3 angularVelocity):
        self.ptr_RigidBody.setAngularVelocity(angularVelocity.ptr_Vector3[0])

    def getMotionState(self):
        ms = DefaultMotionState()
        ms.ptr_MotionState = self.ptr_RigidBody.getMotionState()
        return ms

    def setMotionState(self, MotionState ms):
        self.ptr_RigidBody.setMotionState(ms.ptr_MotionState)

    def getLinearSleepingThreshold(self):
        return <double>self.ptr_RigidBody.getLinearSleepingThreshold()

    def getAngularSleepingThreshold(self):
        return <double>self.ptr_RigidBody.getAngularSleepingThreshold()

    def setSleepingThresholds(self, double linear, double angular):
        self.ptr_RigidBody.setSleepingThresholds(btScalar(linear), btScalar(angular))

    def setFriction(self, double friction):
        self.ptr_RigidBody.setFriction(btScalar(friction))

    def getFriction(self):
        return <double>self.ptr_RigidBody.getFriction()

    def setDamping(self, double lin_damping, double ang_damping):
        self.ptr_RigidBody.setDamping(btScalar(lin_damping), btScalar(ang_damping))

    def getLinearDamping(self):
        return <double>self.ptr_RigidBody.getLinearDamping()

    def getAngularDamping(self):
        return <double>self.ptr_RigidBody.getAngularDamping()

    def getTotalForce(self):
        p = Vec3()
        p.ptr_Vector3[0] = self.ptr_RigidBody.getTotalForce()
        return p

    def getTotalTorque(self):
        p = Vec3()
        p.ptr_Vector3[0] = self.ptr_RigidBody.getTotalTorque()
        return p

    def clearForces(self):
        self.ptr_RigidBody.clearForces()

    def applyForce(self, Vec3 force, Vec3 pos):
        self.ptr_RigidBody.applyForce(force.ptr_Vector3[0], pos.ptr_Vector3[0])

    def applyCentralForce(self, Vec3 force):
        self.ptr_RigidBody.applyCentralForce(force.ptr_Vector3[0])

    def applyTorque(self, Vec3 torque):
        self.ptr_RigidBody.applyTorque(torque.ptr_Vector3[0])

    def setMassProps(self, double mass, Vec3 inertia):
        self.ptr_RigidBody.setMassProps(btScalar(mass), inertia.ptr_Vector3[0])

    def getInvMass(self):
        return <double>self.ptr_RigidBody.getInvMass()

    def getInvInertiaDiagLocal(self):
        p = Vec3()
        p.ptr_Vector3[0] = self.ptr_RigidBody.getInvInertiaDiagLocal()
        return p

    def forceActivationState(self, int newState):
        """
        The possible activation states are defined in  btCollisionObject.h
          * ACTIVE_TAG 1               --> ?
          * ISLAND_SLEEPING 2          --> ?
          * WANTS_DEACTIVATION 3       --> ?
          * DISABLE_DEACTIVATION 4     --> Make object active forever
          * DISABLE_SIMULATION 5       --> Deactivate object forever
        """
        self.ptr_RigidBody.forceActivationState(newState)

    def getCenterOfMassTransform(self):
        t = Transform()
        t.ptr_Transform[0] = self.ptr_RigidBody.getCenterOfMassTransform()
        return t

    def setCenterOfMassTransform(self, Transform t):
        self.ptr_RigidBody.setCenterOfMassTransform(t.ptr_Transform[0])
