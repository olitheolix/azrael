#!/bin/bash

# Activate the Azrael Anaconda environment.
source activate azrael

# Default demo.
CMD="/demo_default.py --noviewer" 

# Override the default demo if one was specified.
case "$1" in
    forcegrid) 
     CMD="demo_forcegrid.py --noviewer --reset=30 --cubes=3,3,1 --linear=1 --circular=1" 
     ;; 
    asteroids) 
     CMD="demo_asteroids.py --noviewer -N3"
     ;; 
    *) 
     CMD="demo_default.py --noviewer" 
     ;; 
esac 

# Build the full command.
CMD="python demos/$CMD"

# Print the command we will actually run.
echo "Azrael startup command: "
echo "  >> $CMD"

# Run the command.
$CMD
