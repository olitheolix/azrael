#!/bin/bash

# Abort at the first error.
set -e

# Create a new Anaconda environment called 'azrael' based on 'environment.yml'
conda env create --name azrael --file environment.yml

# Activate the new environment.
source activate azrael

cd azrael/bullet
python setup.py build_ext --inplace
py.test -x
cd ../../

# Deactivate the environment (happens anyway when this script finishes because
# it executes in a sub-shell).
source deactivate

echo "Development environment for Azrael was created successfully"
echo 'Type ">> source activate azrael" to start hacking'
echo 'Run a simple demo with ">> python demos/demo_default.py'
echo "Thank you for trying Azrael!"
