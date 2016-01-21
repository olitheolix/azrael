#!/bin/bash
#
# Accept the name of a demo and spawn it with reasonable default
# arguments. This script is not intended to be used outside the
# Azrael/Docker container.

# Abort if we are not inside an AZrael/Docker container.
if [ -z $INSIDEDOCKER ]; then
    echo 'Must be inside Docker container'
    exit 1
fi

# Spawn a shell if no arguments were provided.
if [ -z $1 ]; then
    exec bash
fi

# Activate the Anaconda environment.
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
    clerk)
        exec python -c "import azrael.clerk; azrael.clerk.Clerk().run()"
        ;;
    webapi)
        exec python -c "import azrael.web; azrael.web.WebServer().run()"
        ;;
    leonard)
        exec python -c "import azrael.leonard; azrael.leonard.LeonardDistributedZeroMQ().run()"
        ;;
    info)
        exec python -c "import azrael; import azutils; import pprint; pprint.pprint(azutils.getAzraelServiceHosts('/etc/hosts'))"
        ;;
    *)
        exec $*
        ;;
esac

# Prepend the demo directory.
CMD="python demos/$CMD"

# Replace this script with the actual command.
echo "Azrael startup command: "
echo "  >> $CMD"
exec $CMD
