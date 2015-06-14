from libc.stdlib cimport malloc, free

cdef class RigidBodyConstructionInfo:
    cdef MotionState _ref_ms
    cdef CollisionShape _ref_cs
    cdef btRigidBodyConstructionInfo *ptr_RigidBodyConstructionInfo

    def __cinit__(self):
        self.ptr_RigidBodyConstructionInfo = NULL

    def __init__(self, double mass, MotionState ms, CollisionShape cs,
                  Vec3 inert=Vec3(0, 0, 0)):
        self.ptr_RigidBodyConstructionInfo = new btRigidBodyConstructionInfo(
            btScalar(mass),
            ms.ptr_MotionState,
            cs.ptr_CollisionShape,
            inert.ptr_Vector3[0])

        # Keep a handle to the MotionState and CollisionShape to ensure they
        # stay alive until this object destructs. Otherwise it would be well
        # possible that the caller deletes the passed in 'ms' or 'cs' object in
        # which case this class will end up with an invalid pointer to where
        # the 'cs' and 'ms' data used to be.
        self._ref_ms = ms
        self._ref_cs = cs

    def __dealloc__(self):
        if self.ptr_RigidBodyConstructionInfo != NULL:
            del self.ptr_RigidBodyConstructionInfo

    property motionState:
        def __get__(self):
            if (<long>self.ptr_RigidBodyConstructionInfo.m_motionState
                != <long>self._ref_ms.ptr_MotionState):
                raise AssertionError(
                    'Invalid pointer in ConstructionInfo.motionState attribute')
            return self._ref_ms

        def __set__(self, MotionState ms):
            self._ref_ms = ms
            self.ptr_RigidBodyConstructionInfo.m_motionState = ms.ptr_MotionState

        def __del__(self):
            pass

    property collisionShape:
        def __get__(self):
            if (<long>self.ptr_RigidBodyConstructionInfo.m_collisionShape
                != <long>self._ref_cs.ptr_CollisionShape):
                raise AssertionError(
                    'Invalid pointer in ConstructionInfo.collisionShape attribute')
            return self._ref_cs

        def __set__(self, CollisionShape cs):
            self._ref_cs = cs
            self.ptr_RigidBodyConstructionInfo.m_collisionShape = cs.ptr_CollisionShape

        def __del__(self):
            pass

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

    def __cinit__(self):
        self.ptr_RigidBody = NULL

    def __init__(self, RigidBodyConstructionInfo ci, int bodyID=0):
        self.ptr_RigidBody = new btRigidBody(ci.ptr_RigidBodyConstructionInfo[0])
        self._ref_cs = ci._ref_cs
        self._ref_ms = ci._ref_ms

        # Assign the base pointers.
        self.ptr_CollisionObject = <btCollisionObject*?>self.ptr_RigidBody

        # Store the body ID in Azrael. This comes in handy when matching
        # objects returned by Bullet with the particular RigidBody object in
        # Python.
        cdef int *tmp = <int*>malloc(sizeof(int))
        self.ptr_RigidBody.setUserPointer(<void*>tmp)
        self.azSetBodyID(bodyID)

    def __dealloc__(self):
        if self.ptr_RigidBody != NULL:
            if self.ptr_RigidBody.getUserPointer() != NULL:
               free(self.ptr_RigidBody.getUserPointer())
            del self.ptr_RigidBody

    def azSetBodyID(self, int bodyID):
        cdef int *tmp = <int*>self.ptr_RigidBody.getUserPointer()
        tmp[0] = bodyID

    def azGetBodyID(self):
        cdef int *tmp = <int*>self.ptr_RigidBody.getUserPointer()
        return (tmp[0])

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
        # Verify that self._ref_ms points to the same object that the underlying
        # btRigidBody uses.
        cdef btMotionState *tmp = self.ptr_RigidBody.getMotionState()
        if <long>tmp != <long>self._ref_ms.ptr_MotionState:
            raise AssertionError('Invalid pointer in RigidBody.getMotionState')

        # Return the MotionState.
        return self._ref_ms

    def setMotionState(self, MotionState ms):
        # Update our local copy of the motion state.
        self._ref_ms = ms
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
