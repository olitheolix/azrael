#!/bin/bash

# Activate the Azrael Anaconda environment and run the command. This
# will only work if Anaconda's 'activate' script is in the path, which
# is always the case inside Anaconda containers.
source activate azrael

# Select the demo or run a custom command.
case "$1" in
    forcegrid) 
     CMD="demo_forcegrid.py --noviewer --reset=30 --cubes=3,3,1 --linear=1 --circular=1" 
     ;; 
    asteroids) 
     CMD="demo_asteroids.py --noviewer -N3"
     ;; 
    asteroidsplayer)
     CMD="ship_asteroids.py"
     ;;
    *) 
     exec "$1"
     ;; 
esac 

# Prepend the demo directory.
CMD="python demos/$CMD"

# Replace this script with the actual command.
echo "Azrael startup command: "
echo "  >> $CMD"
exec $CMD
