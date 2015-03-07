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
Periodically change the geometry of the objects.
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

# Import the necessary Azrael modules.
p = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(p, 'viewer'))
import model_import
import azrael.clerk
import azrael.clacks
import azrael.client
import azrael.util as util
import azrael.parts as parts
import azrael.config as config
import azrael.leonard as leonard
import azrael.database as database
import azrael.vectorgrid as vectorgrid
import azrael.physics_interface as physAPI
del p

from azrael.util import Fragment, FragState

# Convenience.
ipshell = IPython.embed
BulletDataOverride = physAPI.BulletDataOverride



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


def loadSphere():
    """
    Import a new template and spawn it.

    This will become the first object to populate the simulation.
    """
    model_name = 'viewer/models/sphere/sphere.obj'

    # Load the model.
    print('  Importing <{}>... '.format(model_name), end='', flush=True)
    mesh = model_import.loadModelAll(model_name)

    # The model may contain several sub-models. Each one has a set of vertices,
    # UV- and texture maps. The following code simply flattens the three lists
    # of lists into just three lists.
    vert = np.array(mesh['vertices']).flatten()
    uv = np.array(mesh['UV']).flatten()
    rgb = np.array(mesh['RGB']).flatten()

    # Ensure the data has the correct format.
    vert = 0.5 * np.array(vert)
    uv = np.array(uv, np.float32)
    rgb = np.array(rgb, np.uint8)

    return vert, uv, rgb


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

        # Establish connection to Azrael.
        client = azrael.client.Client()

        # Query all objects in the scene. These are the only objects that will
        # survive the reset.
        ret = client.getAllObjectIDs()
        assert ret.ok
        ret = client.getStateVariables(ret.data)
        assert ret.ok
        allowed_objIDs = {k: v for k, v in ret.data.items() if v is not None}
        print('Took simulation snapshot for reset: ({} objects)'
              .format(len(allowed_objIDs)))

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
                for objID, SV in allowed_objIDs.items():
                    tmp = BulletDataOverride(
                        position=SV.position,
                        velocityLin=SV.velocityLin,
                        velocityRot=SV.velocityRot,
                        orientation=SV.orientation)
                    client.setStateVariable(objID, tmp)
                time.sleep(0.1)


class SetGeometry(multiprocessing.Process):
    """
    Periodically update the geometry.
    """
    def __init__(self, period=1):
        """
        Update the geometry every ``period`` seconds.
        """
        super().__init__()
        self.period = period

    def run(self):
        """
        """
        # Return immediately if no resets are required.
        if self.period == -1:
            return

        # Instantiate Client.
        client = azrael.client.Client()

        # Query all object IDs. This happens only once which means the geometry
        # swap does not affect newly generated objects.
        time.sleep(1)
        ret = client.getAllObjectIDs()
        objIDs = ret.data
        print('\n-- {} objects --\n'.format(len(objIDs)))

        # Query the geometries of all these objects.
        geometries = {_: client.getGeometry(_).data for _ in objIDs}

        sphere_vert, sphere_uv, sphere_rgb = loadSphere()
        cnt = 0
        while True:
            time.sleep(self.period)

            # Swap out the geometry.
            for objID in objIDs:
                if (cnt % 2) == 0:
                    tmp = []
                    for frag in geometries[objID].values():
                        tmp.append(Fragment(frag.name,
                                            sphere_vert,
                                            sphere_uv,
                                            sphere_rgb))
                    client.setGeometry(objID, tmp)
                else:
                    tmp = list(geometries[objID].values())
                    client.setGeometry(objID, tmp)

            # Modify the global scale and a fragment position.
            scale = (cnt + 1) / 10
            for objID in objIDs:
                # Change the scale of the overall object.
                new_sv = BulletDataOverride(scale=scale)
                client.setStateVariable(objID, new_sv)

                # Move the second fragment.
                x = -10 + cnt
                newStates = {
                    objID: [FragState('frag_2', 1, [x, 0, 0], [0, 0, 0, 1])]
                }
                client.updateFragmentStates(newStates)

            # Update counter and print status for user.
            cnt = (cnt + 1) % 20
            print('Scale={:.1f}'.format(scale))


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
    time.sleep(2)
    rs = ResetSim(default_attributes, period=param.resetinterval)
    rs.start()

    ug = SetGeometry(2)
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
    # Start Azrael.
    main()
