#!/bin/bash

# Abort at the first error.
set -e

# The name of the Anaconda environment.
envname=azrael

# Build the latest AssImp library and Python bindings. Ideally I could
# upload this package to Anaconda.org but library linking issues
# seem to only make this package work on the host where it was
# compiled. Therefore, we have to compile right here and now.
conda build --python=3.4 recipes/assimp

# Create a new Anaconda environment called 'azrael'.
conda env create --name $envname python=3.4

# Install the local AssImp package into the new environment.
conda install -y -n $envname assimp --use-local

# Update the environement according to the environment file. This
# cannot happen earlier because Anaconda would otherwise not find the
# AssImp package that we compiled earlier.
conda env update --name $envname --file environment.yml

# Compile the Bullet extension in the Azrael environment. This
# requires a C++ compiler suite (typically gcc) to be installed on the
# host (eg apt-get install build-essential).
source activate $envname
cd azrael/bullet
python setup.py build_ext --inplace
cd ../../
source deactivate

# Usage instructions.
echo 'Successfully create Anaconda/Azrael environment - happy hacking!'
echo "  Activate: >> source activate $envname"
echo '  Demo: >> python demos/demo_default.py --noviewer'
echo 'Thank you for trying Azrael!'
