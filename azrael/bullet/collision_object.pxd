from basic cimport *
from collision_shapes cimport *

cdef extern from "btBulletDynamicsCommon.h":
    cdef cppclass btCollisionObject:
        btCollisionObject()
        btCollisionShape *getCollisionShape()
        void setCollisionShape(btCollisionShape *collisionShape)

        # {get,set}UserPointer
        void *getUserPointer()
        void setUserPointer(void *userPointer)
