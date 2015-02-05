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

    demo_default = 'python3 demo_default.py --noviewer --numcubes 4,4,1'

    # Add the command line options.
    padd('program', nargs=1,
         help='Specify the demo script (plus arguments) to run')

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
    subprocess.call(cmd_mongo, shell=True, stdout=subprocess.DEVNULL)


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
            if ii >= 60:
                print(' error. Could not connect to MongoDB -- Abort')
                sys.exit(1)
            print('.', end='', flush=True)
            time.sleep(2)
        print(' success')

    print('MongoDB now live. Starting Azrael')

    # Actually start Azrael.
    try:
        subprocess.call(param.program, shell=True)
    except KeyboardInterrupt:
        pass

    # Shutdown the Mongo process (if we were the ones how started it).
    if mongo_proc is not None:
        print('Shutting down MongoDB')
        mongo_proc.terminate()
        mongo_proc.join()

    print('Container finished')


if __name__ == '__main__':
    main()
