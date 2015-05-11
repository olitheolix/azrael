from azBullet cimport *
from basic cimport *
from transform cimport *

cdef extern from "btBulletDynamicsCommon.h":
    cdef cppclass btMotionState:
        btMotionState()
        void getWorldTransform(btTransform &worldTrans)
        void setWorldTransform(const btTransform &worldTrans)

cdef extern from "btBulletDynamicsCommon.h":
    cdef cppclass btDefaultMotionState:
        btDefaultMotionState(btTransform &startTrans)
