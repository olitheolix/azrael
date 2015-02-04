#!/usr/bin/python3

# Copyright 2014, Oliver Nagy <olitheolix@gmail.com>
#
# This file is part of Azrael (https://github.com/olitheolix/azrael)
#
# Azrael is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# Azrael is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with Azrael. If not, see <http://www.gnu.org/licenses/>.

"""
Demonstrate the interaction of a force grid with objects.

To this end, this script will spawn a few cubes and a dedicated process to
periodically modify the force field in a wave-like fashion. The force
is the sole source of forces acting on the cubes and Leonard will thus, in
effect, simulate cubes "riding" the wave.
"""

# Add the viewer directory to the Python path.
import os
import sys
import time
import pymongo
import IPython
import logging
import argparse
import subprocess
import demo_default
import multiprocessing

import numpy as np
import matplotlib.pyplot as plt


# Convenience.
ipshell = IPython.embed


def parseCommandLine():
    """
    Parse program arguments.
    """
    # Create the parser.
    parser = argparse.ArgumentParser(
        description=('Azrael Demo Script'),
        formatter_class=argparse.RawTextHelpFormatter)

    # Shorthand.
    padd = parser.add_argument

    # Add the command line options.
    padd('--noviewer', action='store_true', default=False,
         help='Do not spawn a viewer')
    padd('--noinit', action='store_true', default=False,
         help='Do not load any models')
    padd('--port', metavar='port', type=int, default=8080,
         help='Port number')
    padd('--numcubes', metavar='X,Y,Z', type=str, default='1,1,1',
         help='Number of cubes in each dimension')
    padd('--loglevel', type=int, metavar='level', default=1,
         help='Specify error log level (0: Debug, 1:Info)')
    padd('--resetinterval', type=int, metavar='T', default=-1,
         help='Simulation will reset every T seconds')

    # Run the parser.
    param = parser.parse_args()
    try:
        numcubes = [int(_) for _ in param.numcubes.split(',')]
        assert len(numcubes) == 3
        assert min(numcubes) >= 0
        assert sum(numcubes) >= 0
        param.numcubes = numcubes
    except (TypeError, ValueError, AssertionError):
        print('The <numcubes> argument is invalid')
        sys.exit(1)

    return param


def setupLogging(loglevel):
    """
    Change the log level of the 'Azrael' loggers (defined in azrael.config).
    """
    logger = logging.getLogger('azrael')
    if loglevel == 0:
        logger.setLevel(logging.DEBUG)
    elif loglevel == 1:
        logger.setLevel(logging.INFO)
    elif loglevel == 2:
        logger.setLevel(logging.WARNING)
    else:
        print('Unknown log level {}'.format(loglevel))
        sys.exit(1)


def waitForMongo():
    """
    Block until MongoDB can be contacted.

    The main purpose of this function is to avoid problems when running from a
    Docker container because MongoDB takes a while (up to 1min) to actually
    start up and accept connections.
    """
    print('Waiting for MongoDB to come online', end='', flush=True)
    t0 = time.time()
    while True:
        try:
            client = pymongo.MongoClient()
            break
        except pymongo.errors.ConnectionFailure:
            print('.', end='', flush=True)
            time.sleep(1)
    print('. Done ({}s)'.format(int(time.time() - t0)))


def startAzrael(param):
    """
    Start all Azrael processes and return their process handles.
    """
    database.init(reset=True)

    # Delete all grids and define a pristine force grid.
    assert vectorgrid.deleteAllGrids().ok
    assert vectorgrid.defineGrid(name='force', vecDim=3, granularity=1).ok

    # Spawn Azrael's APIs.
    clerk = azrael.clerk.Clerk()
    clerk.start()
    clacks = azrael.clacks.ClacksServer()
    clacks.start()

    # Define additional templates.
    attr = demo_default.spawnCubes(*param.numcubes, center=(0, 0, 10))

    # Start the physics engine.
    #leo = leonard.LeonardBase()
    #leo = leonard.LeonardBullet()
    #leo = leonard.LeonardSweeping()
    leo = leonard.LeonardDistributedZeroMQ()
    leo.start()

    return (clerk, clacks, leo), attr


def stopAzrael(clerk, clacks, leo):
    """
    Stop ``clerk``, ``clacks``, and ``leo``.
    """
    clerk.terminate()
    clacks.terminate()
    leo.terminate()
    clerk.join()
    clacks.join()
    leo.join()


class ResetSim(multiprocessing.Process):
    """
    Periodically reset the simulation.
    """
    def __init__(self, default_attributes, period=-1):
        """
        The ``default_attributes`` argument is a list of (objID, attr) tuples.

        This process resets the attributes of all objects in that list with
        the corresponding value. This happens every ``period`` seconds.

        To prevent simulation resets altoghether set ``period`` to -1.
        """
        super().__init__()
        self.default_attributes = default_attributes
        self.period = period

    def run(self):
        # Return immediately if no resets are required.
        if self.period == -1:
            return

        # Instantiate Client.
        client = azrael.client.Client(addr_clerk=config.addr_clerk)

        # Query all objects in the scene. These are the only objects that will
        # survive the reset.
        ret = client.getAllObjectIDs()
        allowed_objIDs = ret.data

        # Periodically reset the SV values. Set them several times because it
        # is well possible that not all State Variables reach Leonard in the
        # same frame, which means some objects will be reset while other are
        # not. This in turn may cause strange artefacts in the next physics
        # update step, especially when the objects now partially overlap.
        while True:
            # Wait until the timeout expires.
            time.sleep(self.period)

            # Remove all newly added objects.
            ret = client.getAllObjectIDs()
            for objID in ret.data:
                if objID not in allowed_objIDs:
                    client.removeObject(objID)

            # Forcefully reset the position and velocity of every object. Do
            # this several times since network latency may result in some
            # objects being reset sooner than others.
            for ii in range(5):
                for objID, pos in self.default_attributes:
                    client.setStateVariables(objID, pos)
                time.sleep(0.1)


class UpdateGrid(multiprocessing.Process):
    """
    Update the force grid throughout the simulation.
    """
    def __init__(self, period=1):
        """
        Update the force grid values every ``period`` seconds.
        """
        super().__init__()
        self.period = period

    def run(self):
        """
        Alternate the vector grid between 2 states.

        The first state is a rotational grid to make the cubes form a
        vortex. The second grid type simpy pulls all cubes towards the center.
        """
        # Convenience.
        vg = vectorgrid

        # Specify the spatial extend of the grid. Note that eg Nx=3 means the
        # grid extends from [-3, 3] in x-direction.
        Nx, Ny, Nz = 10, 10, 3

        # Lower left corner of the grid in space.
        ofs = np.array([-Nx, -Ny, 10 - Nz], np.float64)

        # Compute a counter clockwise oriented vector grid and another one the
        # always points to the center. Both calculations ignore the
        # z-dimension.
        force_rot = np.zeros((2 * Nx + 1, 2 * Ny + 1, 2 * Nz + 1, 3))
        force_lin = np.zeros_like(force_rot)
        for x in range(-Nx, Nx + 1):
            for y in range(-Ny, Ny + 1):
                # Magnitude and phase.
                r, phi = np.sqrt(x ** 2 + y ** 2), np.arctan2(y, x)

                # Normalise the vectors to ensure the velocity does not depend
                # on the distance from the origin.
                v = np.zeros(3, np.float64)
                if r > 1E-5:
                    v[0] = -np.sin(phi)
                    v[1] = np.cos(phi)

                # Assign the value.
                force_rot[x + Nx, y + Ny, :] = v

                # Points towards the center.
                v = -0.4 * np.array([x, y, 0], np.float64)
                force_lin[x + Nx, y + Ny, :] = v

        while True:
            # Activate the circular grid.
            time.sleep(1.0 * self.period)
            ret = vg.setRegion('force', ofs, 0.1 * force_rot)
            print('Circular force')
            if not ret.ok:
                print('Could not set force grid values')

            # Activate the linear grid.
            time.sleep(2.0 * self.period)
            ret = vg.setRegion('force', ofs, 0.1 * force_lin)
            print('Linear force')
            if not ret.ok:
                print('Could not set force grid values')


def main():
    # Parse the command line.
    param = parseCommandLine()

    # Setup.
    setupLogging(param.loglevel)
    util.resetTiming()

    # Start the Azrael processes.
    with util.Timeit('Startup Time', True):
        subprocess.call(['pkill', 'killme'])
        procs, default_attributes = startAzrael(param)
    print('Azrael now live')

    # Launch process to periodically reset the simulation.
    rs = ResetSim(default_attributes, period=param.resetinterval)
    rs.start()

    ug = UpdateGrid(5)
    ug.start()

    # Launch the viewer process.
    try:
        if param.noviewer:
            time.sleep(3600000000)
        else:
            subprocess.call(['python3', 'viewer/viewer.py'])
    except KeyboardInterrupt:
        pass

    # Shutdown Azrael.
    rs.terminate()
    ug.terminate()
    rs.join()
    ug.join()
    stopAzrael(*procs)

    print('Clean shutdown')


if __name__ == '__main__':
    # Parse the command line but ignore the result since the command line will
    # be parsed again in main(). The only reason why this happens twice is to
    # intercept the '-h' flag and print the help message, regardless of whether
    # MongoDB is available or not (see ``waitForMongo`` command below).
    parseCommandLine()

    # Wait until MongoDB is live.
    waitForMongo()

    # Import the necessary Azrael modules.
    p = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(p, 'viewer'))
    import model_import
    import azrael.clerk
    import azrael.clacks
    import azrael.util as util
    import azrael.parts as parts
    import azrael.config as config
    import azrael.leonard as leonard
    import azrael.database as database
    import azrael.vectorgrid as vectorgrid
    import azrael.physics_interface as physAPI
    del p

    # Start Azrael.
    main()
