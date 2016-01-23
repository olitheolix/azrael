#!/bin/bash
#
# Translate mnemonic names for demos and services to the
# corresponding python command with the correct arguments.
# 
# If the first argument is not a recognised mnemonic then execute the
# specified command verbatim.
# 
# Note: this script will have PID 1 and is thus the only process to
# which Docker will send the SIGTERM signal upon shutdown. To ensure
# the signal is propagates to the Python program it is paramount to
# start them with the 'exec' keyword. This will replace this very
# process with a new one without changing the PID.
#
# A good article on the intricacies of when and how Docker sends
# signals is here:
# https://www.ctl.io/developers/blog/post/gracefully-stopping-docker-containers

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
source /opt/conda/bin/activate azrael

# Start the specified demo or run a custom command.
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
