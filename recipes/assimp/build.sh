#!/bin/sh

#export INCLUDE_PATH=$PREFIX/include
#export LIBRARY_PATH=$PREFIX/lib

# Build the AssImp library.
cmake \
    -DCMAKE_PREFIX_PATH=${PREFIX} \
    -DCMAKE_INSTALL_PREFIX=${PREFIX} \
    -DCMAKE_C_COMPILER=${PREFIX}/bin/gcc \
    -DCMAKE_CXX_COMPILER=${PREFIX}/bin/g++

make install -j4

# Install the Python bindings.
cd port/PyAssimp
python setup.py install

# Run the test suite (not really a test suite but will at least verify
# that the AssImp library is found by PyAssImp).
cd scripts
python quicktest.py
