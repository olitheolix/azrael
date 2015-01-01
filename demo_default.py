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
Start a new viewer.

A new Azrael instance will be created if none is live yet.
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
import multiprocessing

import numpy as np
import matplotlib.pyplot as plt

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
import azrael.controller as controller
import azrael.vectorgrid as vectorgrid
import azrael.bullet.btInterface as btInterface
del p


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


def loadGroundModel(scale, model_name):
    """
    Import a new template and spawn it.

    This will become the first object to populate the simulation.
    """
    # Create a controller and connect to Azrael.
    ctrl = controller.ControllerBase(addr_clerk=config.addr_clerk)
    ctrl.setupZMQ()
    ctrl.connectToClerk()

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
    vert = scale * np.array(vert)
    uv = np.array(uv, np.float32)
    rgb = np.array(rgb, np.uint8)
    print('done')

    # Attach four boosters: left (points down), front (points back), right
    # (points up), and back (point forward).
    dir_up = np.array([0, +1, 0])
    dir_forward = np.array([0, 0, -1])
    pos_left = np.array([-1.5, 0, 0])
    pos_center = np.zeros(3)

    b0 = parts.Booster(
        partID=0, pos=pos_left, direction=-dir_up, max_force=10.0)
    b1 = parts.Booster(
        partID=1, pos=pos_center, direction=dir_forward, max_force=1000.0)
    b2 = parts.Booster(
        partID=2, pos=-pos_left, direction=dir_up, max_force=10.0)
    b3 = parts.Booster(
        partID=3, pos=pos_center, direction=-dir_forward, max_force=1000.0)
    del dir_up, dir_forward, pos_left, pos_center

    # Add the template to Azrael.
    print('  Adding template to Azrael... ', end='', flush=True)
    tID = 'ground'.encode('utf8')
    cs = np.array([3, 1, 1, 1], np.float64)
    ok, _ = ctrl.addTemplate(tID, cs, vert, uv, rgb, [b0, b1, b2, b3], [])

    # Spawn the template near the center and call it 'ground'.
    print('  Spawning object... ', end='', flush=True)
    pos, ori = [0, 0, -10], [0, 1, 0, 0]
    ok, objID = ctrl.spawn(
        None, tID, pos, orient=ori, imass=0.1, scale=scale,
        axesLockLin=[1, 1, 1], axesLockRot=[0, 0, 1])
    print('done (ID=<{}>)'.format(objID))

    # Construct an attribute object (will be needed to reset the simulation).
    z = np.zeros(3, np.float64)
    attr = btInterface.PosVelAccOrient(pos, z, z, ori)
    return objID, attr


def spawnCubes(numCols, numRows, numLayers, center=(0, 0, 0)):
    """
    Spawn multiple cubes in a regular grid.

    The number of cubes equals ``numCols`` * ``numRows`` * ``numLayers``. The
    center of this "prism" is at ``center``.

    Every cube has two boosters and two factories. The factories can themselves
    spawn more (purely passive) cubes.
    """
    # Establish connection to Azrael.
    ctrl = controller.ControllerBase(addr_clerk=config.addr_clerk)
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    # Cube vertices.
    vert = 0.5 * np.array([
        -1.0, -1.0, -1.0,   -1.0, -1.0, +1.0,   -1.0, +1.0, +1.0,
        -1.0, -1.0, -1.0,   -1.0, +1.0, +1.0,   -1.0, +1.0, -1.0,
        +1.0, -1.0, -1.0,   +1.0, +1.0, +1.0,   +1.0, -1.0, +1.0,
        +1.0, -1.0, -1.0,   +1.0, +1.0, -1.0,   +1.0, +1.0, +1.0,
        +1.0, -1.0, +1.0,   -1.0, -1.0, -1.0,   +1.0, -1.0, -1.0,
        +1.0, -1.0, +1.0,   -1.0, -1.0, +1.0,   -1.0, -1.0, -1.0,
        +1.0, +1.0, +1.0,   +1.0, +1.0, -1.0,   -1.0, +1.0, -1.0,
        +1.0, +1.0, +1.0,   -1.0, +1.0, -1.0,   -1.0, +1.0, +1.0,
        +1.0, +1.0, -1.0,   -1.0, -1.0, -1.0,   -1.0, +1.0, -1.0,
        +1.0, +1.0, -1.0,   +1.0, -1.0, -1.0,   -1.0, -1.0, -1.0,
        -1.0, +1.0, +1.0,   -1.0, -1.0, +1.0,   +1.0, -1.0, +1.0,
        +1.0, +1.0, +1.0,   -1.0, +1.0, +1.0,   +1.0, -1.0, +1.0
        ])

    # Convenience.
    cs = np.array([4, 1, 1, 1], np.float64)
    uv = np.array([], np.float64)
    rgb = np.array([], np.uint8)

    uv = np.zeros(12 * 6, np.float64)
    uv[0:6] = [0, 0, 1, 0, 1, 1]
    uv[6:12] = [0, 0, 1, 1, 0, 1]
    uv[12:18] = [1, 0, 0, 1, 0, 0]
    uv[18:24] = [1, 0, 1, 1, 0, 1]
    uv[24:30] = [0, 0, 1, 1, 0, 1]
    uv[30:36] = [0, 0, 1, 0, 1, 1]
    uv[36:42] = [1, 1, 1, 0, 0, 0]
    uv[42:48] = [1, 1, 0, 0, 0, 1]
    uv[48:54] = [0, 1, 1, 0, 1, 1]
    uv[54:60] = [0, 1, 0, 0, 1, 0]
    uv[60:66] = [0, 1, 0, 0, 1, 0]
    uv[66:72] = [1, 1, 0, 1, 1, 0]

    uv = np.array(uv, np.float64)

    img = plt.imread('azrael/static/img/texture_5.jpg')
    rgb = np.rollaxis(np.flipud(img), 1).flatten()

    # ----------------------------------------------------------------------
    # Create templates for the factory output.
    # ----------------------------------------------------------------------
    tID_1 = 'Product1'.encode('utf8')
    tID_2 = 'Product2'.encode('utf8')
    ctrl.addTemplate(tID_1, cs, 0.75 * vert, uv, rgb, [], [])
    ctrl.addTemplate(tID_2, cs, 0.24 * vert, uv, rgb, [], [])

    # ----------------------------------------------------------------------
    # Define a cube with boosters and factories.
    # ----------------------------------------------------------------------
    # Two boosters, one left, one right. Both point in the same direction.
    b0 = parts.Booster(
        partID=0, pos=[+0.05, 0, 0], direction=[0, 0, 1], max_force=10.0)
    b1 = parts.Booster(
        partID=1, pos=[-0.05, 0, 0], direction=[0, 0, 1], max_force=10.0)

    # Two factories, one left one right. They will eject the new objects
    # forwards and backwards, respectively.
    f0 = parts.Factory(
        partID=0, pos=[+1.5, 0, 0], direction=[+1, 0, 0],
        templateID=tID_1, exit_speed=[0.1, 1])
    f1 = parts.Factory(
        partID=1, pos=[-1.5, 0, 0], direction=[-1, 0, 0],
        templateID=tID_2, exit_speed=[0.1, 1])

    # Add the template.
    tID_3 = 'BoosterCube'.encode('utf8')
    ok, _ = ctrl.addTemplate(tID_3, cs, vert, uv, rgb, [b0, b1], [f0, f1])
    assert ok

    # ----------------------------------------------------------------------
    # Define more booster cubes, each with a different texture.
    # ----------------------------------------------------------------------
    tID_cube = {}
    for ii in range(numRows * numCols * numLayers):
        # File name of texture.
        fname = 'azrael/static/img/texture_{}.jpg'.format(ii + 1)

        # Load the texture image. If the image is unavailable do not endow the
        # cube with a texture.
        try:
            img = plt.imread(fname)
            rgb = np.rollaxis(np.flipud(img), 1).flatten()
            curUV = uv
        except FileNotFoundError:
            print('Could not load texture <{}>'.format(fname))
            rgb = curUV = np.array([])

        # Create the template.
        tID = ('BoosterCube_{}'.format(ii)).encode('utf8')
        ok, _ = ctrl.addTemplate(tID, cs, vert, curUV, rgb, [b0, b1], [])
        assert ok

        # Add the templateID to a dictionary because we will need it in the
        # next step to spawn the templates.
        tID_cube[ii] = tID

    # ----------------------------------------------------------------------
    # Spawn the differently textured cubes in a regular grid.
    # ----------------------------------------------------------------------
    cube_idx = 0
    cube_spacing = 0.1
    default_attributes = []
    for row in range(numRows):
        for col in range(numCols):
            for lay in range(numLayers):
                # Base position of cube.
                pos = np.array([col, row, lay], np.float64)

                # Add space in between cubes.
                pos *= -(1 + cube_spacing)

                # Correct the cube's position to ensure the center of the
                # grid coincides with the origin.
                pos[0] += (numCols // 2) * (1 + cube_spacing)
                pos[1] += (numRows // 2) * (1 + cube_spacing)
                pos[2] += (numLayers // 2) * (1 + cube_spacing)

                # Move the grid to position ``center``.
                pos += np.array(center)

                # Spawn the cube and update the index counter. The intitial
                # velocity, acceleration, and orientation is neutral.
                ok, objID = ctrl.spawn(None, tID_cube[cube_idx], pos)
                cube_idx += 1

                # Record the original position of the object (this will be
                # needed when the simulation is reset).
                default_attributes.append((objID, pos))

    # Convert the positions to proper PosVecAccOrient tuples. In these tuples
    # only the position differs. The inital velocities, accelerations, and
    # orientations are all identical).
    z = np.zeros(3, np.float64)
    o = np.array([0, 0, 0, 1], np.float64)
    default_attributes = [(_[0], btInterface.PosVelAccOrient(_[1], z, z, o))
                          for _ in default_attributes]
    return default_attributes


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
    # Delete all grids but define a force grid (will not be used but
    # Leonard throws a lot of harmless warnings otherwise).
    assert vectorgrid.deleteAllGrids().ok
    assert vectorgrid.defineGrid(name='force', elDim=3, granularity=1).ok

    # Spawn Azrael's APIs.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    clacks = azrael.clacks.ClacksServer()
    clacks.start()
    btInterface.initSVDB(reset=True)

    if not param.noinit:
        # Add a model to the otherwise empty simulation. The sphere is
        # in the repo whereas the Vatican model is available here:
        # http://artist-3d.com/free_3d_models/dnm/model_disp.php?\
        # uid=3290&count=count
        model_name = (1.25, 'viewer/models/sphere/sphere.obj')
        #model_name = (50, 'viewer/models/vatican/vatican-cathedral.3ds')
        #model_name = (1.25, 'viewer/models/house/house.3ds')
        tmp = loadGroundModel(*model_name)

        # Define additional templates.
        default_attributes = spawnCubes(*param.numcubes, center=(0, 0, 10))
        default_attributes.append(tmp)

    # Start the physics engine.
    #leo = leonard.LeonardBase()
    #leo = leonard.LeonardBulletMonolithic()
    #leo = leonard.LeonardBulletSweeping()
    #leo = leonard.LeonardBulletSweepingMultiST()
    leo = leonard.LeonardBulletSweepingMultiMT()
    leo.start()

    return (clerk, clacks, leo), default_attributes


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

        This process override the attribtes of all objects in that list with
        the corresponding value. This happens every ``period`` seconds.

        To prevent simulation resets altoghether set ``period`` to -1.
        """
        super().__init__()
        self.default_attributes = default_attributes
        self.period = period

    def run(self):
        """
        Create a Controller.
        """
        # Return immediately if no resets are required.
        if self.period == -1:
            return

        ctrl = controller.ControllerBase(addr_clerk=config.addr_clerk)
        ctrl.setupZMQ()
        ctrl.connectToClerk()

        # Query all objects in the scene. These are the only objects that will
        # survive the reset.
        ok, allowed_objIDs = ctrl.getAllObjectIDs()

        # Periodically override the attributes with their default
        # values. Override the attributes several times because it is well
        # possible that not all override commands reach Leonard in the same
        # frame, which means some objects will be reset, others will not, and
        # that may cause strange artefacts in the next physics update step,
        # especially when the objects now partially overlap.
        while True:
            # Wait until the timeout expires.
            time.sleep(self.period)

            # Remove all newly added objects.
            ok, cur_objIDs = ctrl.getAllObjectIDs()
            for objID in cur_objIDs:
                if objID not in allowed_objIDs:
                    ctrl.deleteObject(objID)

            # Forcefully reset the position and velocity of every object. Do
            # this several times since network latency may result in some
            # objects being reset sooner than others.
            for ii in range(5):
                for objID, pos in self.default_attributes:
                    ctrl.overrideAttributes(objID, pos)
                time.sleep(0.1)


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
    rs.join()
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

    # Start Azrael.
    main()
