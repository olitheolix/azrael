#!/usr/bin/python3
"""
This script runs as the ENTRYPOINT in the Docker container. Using a dedicated
script to launch all programs allows for a clean Dockerfile syntax and easy
customisation via command line arguments when starting the container.
"""
import sys
import time
import pymongo
import argparse
import subprocess
import multiprocessing


def parseCommandLine():
    """
    Parse program arguments.
    """
    # Create the parser.
    parser = argparse.ArgumentParser(
        description=('Start Azrael in a Docker Container'),
        formatter_class=argparse.RawTextHelpFormatter)

    # Shorthand.
    padd = parser.add_argument

    # Add the command line options.
    padd('--numcubes', metavar='X,Y,Z', type=str, default='1,1,1',
         help='Number of cubes in each dimension')
    padd('--resetinterval', type=int, metavar='T', default=-1,
         help='Simulation will reset every T seconds')

    # Run the parser.
    param = parser.parse_args()
    return param


def isMongoLive():
    """
    Return *True* if MongoDB is now online.
    """
    try:
        client = pymongo.MongoClient()
    except pymongo.errors.ConnectionFailure:
        return False
        
    return True


def startMongo():
    cmd_mongo = '/usr/bin/mongod --smallfiles --dbpath /demo/mongodb'
    subprocess.call(cmd_mongo, shell=True)


def main():
    param = parseCommandLine()

    # Start MongoDB unless it is already live.
    mongo_proc = None
    if not isMongoLive():
        print('Launching MongoDB ', end='', flush=True)
        mongo_proc = multiprocessing.Process(target=startMongo)
        mongo_proc.start()

        # Wait until Mongo is up and running. Abort after 2 minutes.
        for ii in range(120):
            if isMongoLive():
                break
            print('.', end='', flush=True)
            if ii >= 119:
                print('Could not connect to MongoDB -- Abort')
                sys.exit(1)
        print(' success')

    # Compile the full command that starts Azrael.
    cmd_azrael = 'python3 demo_default.py --noviewer '
    cmd_azrael += '--numcubes {}'.format(param.numcubes)

    # Actually start Azrael.
    try:
        subprocess.call(cmd_azrael, shell=True)
    except KeyboardInterrupt:
        pass

    # Shutdown the Mongo process and quit.
    if mongo_proc is not None:
        mongo_proc.terminate()
        mongo_proc.join()


if __name__ == '__main__':
    main()
