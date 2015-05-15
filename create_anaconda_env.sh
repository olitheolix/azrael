#!/bin/bash

# Abort at the first error.
set -e

# The name of the Anacond environment.
envname=azrael

# Create a new Anaconda environment called 'azrael' based on 'environment.yml'
conda env create --name $envname --file environment.yml

# Activate the new environment.
source activate $envname

cd azrael/bullet
python setup.py build_ext --inplace
cd ../../

# Deactivate the environment, even though this will happen
# automatically once this script finishes.
source deactivate

echo 'Successfully create Anaconda/Azrael environment - happy hacking!'
echo "  Activate: >> source activate $envname"
echo '  Demo: >> python demos/demo_default.py --noviewer'
echo 'Thank you for trying Azrael!'
