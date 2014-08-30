# distutils: language = c++
# distutils: sources = ['bullet.cpp', 'util.cpp']
# distutils: include_dirs = ['/usr/include/bullet/']
# distutils: library_dirs = []
# distutils: libraries = ['BulletCollision', 'BulletDynamics', 'LinearMath']
"""
Cython will parse the above comments and pass the options along to distutils.

To compile and test this extension:

  >> python3 setup.py build_ext --inplace
  >> python3 runme.py
"""


# Import the Cython version of NumPy
import numpy as np
cimport numpy as np

import azrael.bullet.bullet_data as bullet_data

from azrael.config import LEN_SV_FLOATS

"""
Cython wrapper for the C++ class.
"""
cdef extern from "bullet.hpp":
    cdef cppclass BulletPhys:
        BulletPhys(int, int)
        int compute(const long&, long*, const double&, const long&)
        int getObjectData(const long &numIDs, const long *IDs,
                          const long &bufLen, double* buf)
        int setObjectData(const long &numIDs, const long *IDs,
                          const long &bufLen, double *buf)
        int getPairCache(const long &N, long *buf)
        int applyForce(const long &ID, double *force, double *rel_pos)
        int applyForceAndTorque(const long &ID, double *force, double *torque)
        int getPairCacheSize()
        int removeObject(const long &numIDs, long *IDs)


"""
Python Interface to C++ class based on the Cython wrapper (see above).

This class holds an instance of the C++ class and defines some
Python methods to interact with it. Those Python methods do nothing
more than calling the respective C++ methods.

"""
cdef class PyBulletPhys:
    # Instance of the C++ class we are wrapping here.
    cdef BulletPhys *thisptr      

    def __cinit__(self, int bulletID, int coll_filter):
        self.thisptr = new BulletPhys(bulletID, coll_filter)

    def __dealloc__(self):
        del self.thisptr

    def compute(self, IDs, delta_t, max_substeps):
        # Convert the inputs to the correct data format.
        cdef np.ndarray[long] ids = np.array(IDs, np.int64)

        # Call the C++ function.
        N = len(IDs)
        return self.thisptr.compute(N, <long*>ids.data, delta_t, max_substeps)

    def getObjectData(self, IDs):
        # Convert the inputs to the correct data format.
        cdef np.ndarray[long] ids = np.array(IDs, np.int64)

        # Allocate enough memory to hold all the SV data supplied by Bullet.
        N = LEN_SV_FLOATS * len(IDs)
        cdef np.ndarray[double] buf = np.zeros(N, np.float64)

        # Call the C++ function.
        ret = self.thisptr.getObjectData(
            len(IDs), <long*>ids.data, len(buf), <double*>buf.data)
        return ret, bullet_data.fromNumPyString(np.fromstring(buf))

    def setObjectData(self, IDs, buf_in):
        # Convert the inputs to the correct data format.
        cdef np.ndarray[long] ids = np.array(IDs, np.int64)
        cdef np.ndarray[double] buf = buf_in.toNumPyString()

        # Call the C++ function.
        return self.thisptr.setObjectData(
            len(IDs), <long*>ids.data, len(buf), <double*>buf.data)

    def applyForce(self, ID, force, rel_pos):
        assert len(force) == 3
        assert len(rel_pos) == 3

        # Convert the inputs to the correct data format.
        cdef np.ndarray[double] f = np.array(force, np.float64)
        cdef np.ndarray[double] p = np.array(rel_pos, np.float64)

        # Call the C++ function.
        return self.thisptr.applyForce(ID, <double*>f.data, <double*>p.data)

    def applyForceAndTorque(self, ID, force, torque):
        assert len(force) == 3
        assert len(torque) == 3

        # Convert the inputs to the correct data format.
        cdef np.ndarray[double] f = np.array(force, np.float64)
        cdef np.ndarray[double] p = np.array(torque, np.float64)

        # Call the C++ function.
        return self.thisptr.applyForceAndTorque(
            ID, <double*>f.data, <double*>p.data)

    def removeObject(self, IDs):
        # Convert the inputs to the correct data format.
        cdef np.ndarray[long] ids = np.array(IDs, np.int64)

        # Call the C++ function.
        return self.thisptr.removeObject(len(IDs), <long*>ids.data)

    def getPairCache(self):
        # Query the size of the pair cache (in int64 units).
        pcs = self.thisptr.getPairCacheSize()

        # Allocate a buffer that is large enough to hold all pairs.
        cdef np.ndarray[long] buf = np.zeros(pcs, dtype=long)

        # Retrieve the actual buffer from the C++ code.
        nb = self.thisptr.getPairCache(buf.nbytes, <long*>buf.data)

        # Sanity check: we the number of returned bytes must be a multiple of
        # 16 because every object uses a 64Bit ID (8 Bytes), and they can only
        # be returned in pairs (hence 16 Bytes).
        if nb % 16 == 0:
            return True, buf
        else:
            return False, buf
