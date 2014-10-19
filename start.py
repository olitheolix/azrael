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

import numpy as np
import matplotlib.pyplot as plt


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

    # run the parser.
    param = parser.parse_args()
    try:
        numcubes = [int(_) for _ in param.numcubes.split(',')]
        assert len(numcubes) == 3
        assert min(numcubes) >= 0
        assert sum(numcubes) >= 1
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
    ctrl = wscontroller.WSControllerBase('ws://127.0.0.1:8080/websocket')
    assert ctrl.pingClacks()

    # Load the model.
    print('  Importing <{}>... '.format(model_name), end='', flush=True)
    mesh = model_import.loadModelAll(model_name)

    # The model may contain several sub-models. Each one has a set of vertices,
    # UV- and texture maps. The following code simply turns the three list of
    # lists to three lists.
    vert = np.array(mesh['vertices']).flatten()
    uv = np.array(mesh['UV']).flatten()
    rgb = np.array(mesh['RGB']).flatten()

    # Ensure the data has the correct format.
    vert = scale * np.array(vert)
    uv = np.array(uv, np.float32)
    rgb = np.array(rgb, np.uint8)
    print('done')

    # Attach trhee boosters to the mode: left, center, and right.
    dir_0, dir_1, dir_2 = [0, 0, -1], [0, 0, -1], [0, 0, +1]
    pos_0, pos_1, pos_2 = [-1.5, 0, 0], [0, 0, 0], [+1.5, 0, 0]
    b0 = parts.Booster(
        partID=0, pos=pos_0, direction=dir_0, max_force=10.0)
    b1 = parts.Booster(
        partID=1, pos=pos_1, direction=dir_1, max_force=1000.0)
    b2 = parts.Booster(
        partID=2, pos=pos_2, direction=dir_2, max_force=10.0)

    # Add the template to Azrael.
    print('  Adding template to Azrael... ', end='', flush=True)
    tID = 'ground'.encode('utf8')
    cs = np.array([3, 1, 1, 1], np.float64)
    ok, _ = ctrl.addTemplate(tID, cs, vert, uv, rgb, [b0, b1, b2], [])

    # Spawn the template near the center and call it 'ground'.
    print('  Spawning object... ', end='', flush=True)
    ret = ctrl.spawn(None, tID, [0, 0, -10], orient=[0, 1, 0, 0],
                     imass=0.1, scale=scale)
    print('done (ID=<{}>)'.format(ret[1]))


def spawnCubes(numCols, numRows, numLayers):
    """
    Define a cubic template and spawn ``numInstances`` of it.

    Every cube has two boosters and two factories. The factories can themselves
    spawn more (purely passive) cubes.

    The cubes will be arranged regularly in the scene.
    """
    # Establish connection to Azrael.
    ctrl = wscontroller.WSControllerBase('ws://127.0.0.1:8080/websocket')
    assert ctrl.pingClacks()

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
        partID=0, pos=[+0.005, 0, 0], direction=[0, 0, 1], max_force=10.0)
    b1 = parts.Booster(
        partID=1, pos=[-0.005, 0, 0], direction=[0, 0, 1], max_force=10.0)

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
    # Spawn the differently textures cubes in a regular grid.
    # ----------------------------------------------------------------------
    idx = 0
    spacing = 0.1
    for row in range(numRows):
        for col in range(numCols):
            for lay in range(numLayers):
                # Base position of cube.
                pos = np.array([col, row, lay], np.float64)

                # Add space in between cubes.
                pos *= -(1 + spacing)

                # Correct the cube position to ensure the center of the
                # grid coincides with (0, 0, 0) in world coordinates.
                pos[0] += (numCols // 2) * (1 + spacing)
                pos[1] += (numRows // 2) * (1 + spacing)
                pos[2] += 10

                # Spawn the cube and update the index counter.
                ok, objID = ctrl.spawn(None, tID_cube[idx], pos)
                idx += 1


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


def main():
    # Parse the command line.
    param = parseCommandLine()

    setupLogging(param.loglevel)

    # Flush the timing database.
    util.resetTiming()

    # Determine if Azrael is live.
    try:
        addr = 'ws://127.0.0.1:{}/websocket'.format(param.port)
        wscontroller.WSControllerBase(addr)
        is_azrael_live = True
    except ConnectionRefusedError as err:
        is_azrael_live = False

    if not is_azrael_live:
        print('Starting Azrael...')

        # Kill all left over processes from previous runs.
        subprocess.call(['pkill', 'killme'])

        # Start the Azrael processes.
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
            loadGroundModel(*model_name)

            # Define additional templates.
            spawnCubes(*param.numcubes)

        # Start the physics engine.
        #leo = leonard.LeonardBase()
        #leo = leonard.LeonardBaseWPRMQ(1, leonard.LeonardRMQWorker)
        #leo = leonard.LeonardBaseWPRMQ(1, leonard.LeonardRMQWorkerBullet)
        #leo = leonard.LeonardBulletMonolithic()
        #leo = leonard.LeonardBulletSweeping()
        #leo = leonard.LeonardBulletSweepingMultiST()
        leo = leonard.LeonardBulletSweepingMultiMT()
        leo.start()

        print('Azrael now live')
    else:
        print('Azrael already live')

    # Launch the viewer process.
    try:
        if param.noviewer:
            while True:
                time.sleep(360000)
        else:
            subprocess.call(['python3', 'viewer/viewer.py'])
    except KeyboardInterrupt:
        pass

    if not is_azrael_live:
        # Shutdown Azrael.
        clerk.terminate()
        clacks.terminate()
        leo.terminate()
        clerk.join()
        clacks.join()
        leo.join()

    print('Clean shutdown')


if __name__ == '__main__':
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
    import azrael.wscontroller as wscontroller
    import azrael.bullet.btInterface as btInterface
    del p

    # Start Azrael.
    main()
