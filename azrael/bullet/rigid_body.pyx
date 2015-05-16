cdef class RigidBody(CollisionObject):
    cdef btRigidBody *thisptr

    def __cinit__(self, double mass, MotionState ms, CollisionShape cs, Vec3 localInertia):
        self.thisptr = NULL

    def __init__(self, double mass, MotionState ms, CollisionShape cs, Vec3 localInertia):
        self.thisptr = new btRigidBody(
            btScalar(mass),
            ms.ptr_MotionState,
            cs.ptr_CollisionShape,
            localInertia.ptr_Vector3[0])

        # Assign the base pointers.
        self.ptr_CollisionObject = <btCollisionObject*?>self.thisptr

    def __dealloc__(self):
        if self.thisptr != NULL:
            del self.thisptr

    def setRestitution(self, double r):
        self.thisptr.setRestitution(btScalar(r))

    def getRestitution(self):
        return <double>self.thisptr.getRestitution()

    def getLinearFactor(self):
        p = Vec3()
        p.ptr_Vector3[0] = self.thisptr.getLinearFactor()
        return p

    def setLinearFactor(self, Vec3 linearFactor):
        self.thisptr.setLinearFactor(linearFactor.ptr_Vector3[0])

    def getAngularFactor(self):
        p = Vec3()
        p.ptr_Vector3[0] = self.thisptr.getAngularFactor()
        return p

    def setAngularFactor(self, Vec3 angularFactor):
        self.thisptr.setAngularFactor(angularFactor.ptr_Vector3[0])

    def getLinearVelocity(self):
        p = Vec3()
        p.ptr_Vector3[0] = self.thisptr.getLinearVelocity()
        return p

    def setLinearVelocity(self, Vec3 linearVelocity):
        self.thisptr.setLinearVelocity(linearVelocity.ptr_Vector3[0])

    def getAngularVelocity(self):
        p = Vec3()
        p.ptr_Vector3[0] = self.thisptr.getAngularVelocity()
        return p

    def setAngularVelocity(self, Vec3 angularVelocity):
        self.thisptr.setAngularVelocity(angularVelocity.ptr_Vector3[0])

    def getMotionState(self):
        ms = MotionState()
        ms.ptr_MotionState = self.thisptr.getMotionState()
        return ms

    def setMotionState(self, MotionState ms):
        self.thisptr.setMotionState(ms.ptr_MotionState)

    def getLinearSleepingThreshold(self):
        return <double>self.thisptr.getLinearSleepingThreshold()

    def getAngularSleepingThreshold(self):
        return <double>self.thisptr.getAngularSleepingThreshold()

    def setSleepingThresholds(self, double linear, double angular):
        self.thisptr.setSleepingThresholds(btScalar(linear), btScalar(angular))

    def setFriction(self, double friction):
        self.thisptr.setFriction(btScalar(friction))

    def getFriction(self):
        return <double>self.thisptr.getFriction()

    def setDamping(self, double lin_damping, double ang_damping):
        self.thisptr.setDamping(btScalar(lin_damping), btScalar(ang_damping))

    def getLinearDamping(self):
        return <double>self.thisptr.getLinearDamping()

    def getAngularDamping(self):
        return <double>self.thisptr.getAngularDamping()

    def getTotalForce(self):
        p = Vec3()
        p.ptr_Vector3[0] = self.thisptr.getTotalForce()
        return p

    def getTotalTorque(self):
        p = Vec3()
        p.ptr_Vector3[0] = self.thisptr.getTotalTorque()
        return p

    def clearForces(self):
        self.thisptr.clearForces()

    def applyForce(self, Vec3 force, Vec3 pos):
        self.thisptr.applyForce(force.ptr_Vector3[0], pos.ptr_Vector3[0])

    def applyCentralForce(self, Vec3 force):
        self.thisptr.applyCentralForce(force.ptr_Vector3[0])

    def applyTorque(self, Vec3 torque):
        self.thisptr.applyTorque(torque.ptr_Vector3[0])

    def setMassProps(self, double mass, Vec3 inertia):
        self.thisptr.setMassProps(btScalar(mass), inertia.ptr_Vector3[0])

    def getInvMass(self):
        return <double>self.thisptr.getInvMass()

    def getInvInertiaDiagLocal(self):
        p = Vec3()
        p.ptr_Vector3[0] = self.thisptr.getInvInertiaDiagLocal()
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
        self.thisptr.forceActivationState(newState)

    def getCenterOfMassTransform(self):
        t = Transform()
        t.ptr_Transform[0] = self.thisptr.getCenterOfMassTransform()
        return t

    def setCenterOfMassTransform(self, Transform t):
        self.thisptr.setCenterOfMassTransform(t.ptr_Transform[0])
