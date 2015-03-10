#!/usr/bin/python3

# Copyright 2015, Oliver Nagy <olitheolix@gmail.com>
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
Create a sphere, one or more cubes (see --cubes parameter), and launch the
Qt Viewer.

.. note:: This script will kill all running Azrael instances and create a new
   one.
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
sys.path.insert(0, os.path.join(p, '..'))
sys.path.insert(0, os.path.join(p, '../viewer'))
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

from azrael.util import Template, Fragment, FragState

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
    padd('--cubes', metavar='X,Y,Z', type=str, default='1,1,1',
         help='Number of cubes in each dimension')
    padd('--loglevel', type=int, metavar='level', default=1,
         help='Specify error log level (0: Debug, 1:Info)')
    padd('--reset', type=int, metavar='T', default=-1,
         help='Simulation will reset every T seconds')

    # Run the parser.
    param = parser.parse_args()
    try:
        cubes = [int(_) for _ in param.cubes.split(',')]
        assert len(cubes) == 3
        assert min(cubes) >= 0
        assert sum(cubes) >= 0
        param.cubes = cubes
    except (TypeError, ValueError, AssertionError):
        print('The <cubes> argument is invalid')
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
    # Get a Client instance.
    client = azrael.client.Client()

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

    b0 = parts.Booster(partID=0, pos=pos_left, direction=-dir_up,
                       minval=0, maxval=10.0, force=0)
    b1 = parts.Booster(partID=1, pos=pos_center, direction=dir_forward,
                       minval=0, maxval=1000.0, force=0)
    b2 = parts.Booster(partID=2, pos=-pos_left, direction=dir_up,
                       minval=0, maxval=10.0, force=0)
    b3 = parts.Booster(partID=3, pos=pos_center, direction=-dir_forward,
                       minval=0, maxval=1000.0, force=0)
    del dir_up, dir_forward, pos_left, pos_center

    # Construct a Tetrahedron (triangular Pyramid). This is going to be the
    # (super simple) "flame" that comes out of the (still invisible) boosters.
    y = 0.5 * np.arctan(np.pi / 6)
    a = (-0.5, -y, 1)
    b = (0.5, -y, 1)
    c = (0, 3 / 4 - y, 1)
    d = (0, 0, 0)
    vert_b = [(a + b + c) +
              (a + b + d) +
              (a + c + d) +
              (b + c + d)]
    vert_b = np.array(vert_b[0], np.float64)
    del a, b, c, d, y

    # Add the template to Azrael.
    print('  Adding template to Azrael... ', end='', flush=True)
    tID = 'ground'
    cs = np.array([3, 1, 1, 1], np.float64)
    z = np.array([])
    frags = [Fragment('frag_1', vert, uv, rgb),
             Fragment('b_left', vert_b, z, z),
             Fragment('b_right', vert_b, z, z),
             ]
    temp = Template(tID, cs, frags, [b0, b1, b2, b3], [])
    assert client.addTemplates([temp]).ok
    del cs, frags, temp, z
    print('done')

    # Spawn the template near the center.
    print('  Spawning object... ', end='', flush=True)
    pos, orient = [0, 0, -10], [0, 1, 0, 0]
    d = {'scale': scale,
         'imass': 0.1,
         'position': pos,
         'orientation': orient,
         'axesLockLin': [1, 1, 1],
         'axesLockRot': [0, 0, 1],
         'template': tID}
    ret = client.spawn([d])
    objID = ret.data[0]
    print('done (ID=<{}>)'.format(objID))

    # Disable the booster fragments by settings its scale to Zero.
    newStates = {objID: [
        FragState('b_left', 0, [0, 0, 0], [0, 0, 0, 1]),
        FragState('b_right', 0, [0, 0, 0], [0, 0, 0, 1]),
        ]}
    assert client.updateFragmentStates(newStates).ok

    # Construct an attribute object (will be needed to reset the simulation).
    z = np.zeros(3, np.float64)
    attr = BulletDataOverride(
        position=pos, velocityLin=z, velocityRot=z, orientation=orient)
    return objID, attr


def spawnCubes(numCols, numRows, numLayers, center=(0, 0, 0)):
    """
    Spawn multiple cubes in a regular grid.

    The number of cubes equals ``numCols`` * ``numRows`` * ``numLayers``. The
    center of this "prism" is at ``center``.

    Every cube has two boosters and two factories. The factories can themselves
    spawn more (purely passive) cubes.
    """
    # Get a Client instance.
    client = azrael.client.Client()

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

    # Compile the path to the texture file.
    path_base = os.path.dirname(os.path.abspath(__file__))
    path_base = os.path.join(path_base, '..', 'azrael', 'static', 'img')
    fname = os.path.join(path_base, 'texture_5.jpg')

    # Load the texture and convert it to flat vector because this is how OpenGL
    # will want it.
    img = plt.imread(fname)
    rgb = np.rollaxis(np.flipud(img), 1).flatten()

    # ----------------------------------------------------------------------
    # Create templates for the factory output.
    # ----------------------------------------------------------------------
    tID_1 = 'Product1'
    tID_2 = 'Product2'
    frags_1 = [Fragment('frag_1', 0.75 * vert, uv, rgb)]
    frags_2 = [Fragment('frag_1', 0.24 * vert, uv, rgb)]
    t1 = Template(tID_1, cs, frags_1, [], [])
    t2 = Template(tID_2, cs, frags_2, [], [])
    assert client.addTemplates([t1, t2]).ok
    del frags_1, frags_2, t1, t2

    # ----------------------------------------------------------------------
    # Define a cube with boosters and factories.
    # ----------------------------------------------------------------------
    # Two boosters, one left, one right. Both point in the same direction.
    b0 = parts.Booster(partID=0, pos=[+0.05, 0, 0], direction=[0, 0, 1],
                       minval=0, maxval=10.0, force=0)
    b1 = parts.Booster(partID=1, pos=[-0.05, 0, 0], direction=[0, 0, 1],
                       minval=0, maxval=10.0, force=0)

    # Two factories, one left one right. They will eject the new objects
    # forwards and backwards, respectively.
    f0 = parts.Factory(
        partID=0, pos=[+1.5, 0, 0], direction=[+1, 0, 0],
        templateID=tID_1, exit_speed=[0.1, 1])
    f1 = parts.Factory(
        partID=1, pos=[-1.5, 0, 0], direction=[-1, 0, 0],
        templateID=tID_2, exit_speed=[0.1, 1])

    # Add the template.
    tID_3 = 'BoosterCube'
    frags = [Fragment('frag_1', vert, uv, rgb)]
    t3 = Template(tID_3, cs, frags, [b0, b1], [f0, f1])
    assert client.addTemplates([t3]).ok
    del frags, t3

    # ----------------------------------------------------------------------
    # Define more booster cubes, each with a different texture.
    # ----------------------------------------------------------------------
    tID_cube = {}
    templates = []
    texture_errors = 0
    for ii in range(numRows * numCols * numLayers):
        # File name of texture.
        fname = os.path.join(path_base, 'texture_{}.jpg'.format(ii + 1))

        # Load the texture image. If the image is unavailable do not endow the
        # cube with a texture.
        try:
            img = plt.imread(fname)
            rgb = np.rollaxis(np.flipud(img), 1).flatten()
            curUV = uv
        except FileNotFoundError:
            texture_errors += 1
            rgb = curUV = np.array([])

        # Create the template.
        tID = ('BoosterCube_{}'.format(ii))
        frags = [Fragment('frag_1', vert, curUV, rgb),
                 Fragment('frag_2', vert, curUV, rgb)]
        tmp = Template(tID, cs, frags, [b0, b1], [])
        templates.append(tmp)

        # Add the templateID to a dictionary because we will need it in the
        # next step to spawn the templates.
        tID_cube[ii] = tID
        del frags, tmp, tID, fname

    if texture_errors > 0:
        print('Could not load texture for {} of the {} objects'
              .format(texture_errors, ii + 1))

    # Define all templates.
    print('Adding {} templates: '.format(ii + 1), end='', flush=True)
    t0 = time.time()
    assert client.addTemplates(templates).ok
    print('{:.1f}s'.format(time.time() - t0))

    # ----------------------------------------------------------------------
    # Spawn the differently textured cubes in a regular grid.
    # ----------------------------------------------------------------------
    allObjs = []
    cube_idx = 0
    cube_spacing = 0.1

    # Determine the template and position for every cube. The cubes are *not*
    # spawned in this loop, but afterwards.
    print('Compiling scene: ', end='', flush=True)
    t0 = time.time()
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

                # Store the position and template for this cube.
                allObjs.append({'template': tID_cube[cube_idx],
                                'position': pos})
                cube_idx += 1
                del pos
    print('{:,} objects ({:.1f}s)'.format(len(allObjs), time.time() - t0))
    del cube_idx, cube_spacing, row, col, lay

    # Spawn the cubes from the templates at the just determined positions.
    print('Spawning {} objects: '.format(len(allObjs)), end='', flush=True)
    t0 = time.time()
    ret = client.spawn(allObjs)
    assert ret.ok
    print(' {:.1f}s'.format(time.time() - t0))

    # Make 'frag_2' invisible by setting its scale to zero.
    for objID in ret.data:
        client.updateFragmentStates({objID: [
            FragState('frag_2', 0, [0, 0, 0], [0, 0, 0, 1])]})


def startAzrael(param):
    """
    Start all Azrael processes and return their process handles.
    """
    subprocess.call(['pkill', 'killme'])
    time.sleep(0.2)
    database.init(reset=True)

    # Reset the profiling database and enable logging.
    azrael.util.resetTiming()
    setupLogging(param.loglevel)

    # Delete all grids but define a force grid (will not be used but
    # Leonard throws a lot of harmless warnings otherwise).
    assert vectorgrid.deleteAllGrids().ok
    assert vectorgrid.defineGrid(name='force', vecDim=3, granularity=1).ok

    # Spawn Azrael's APIs.
    clerk = azrael.clerk.Clerk()
    clerk.start()
    clacks = azrael.clacks.ClacksServer()
    clacks.start()

    if not param.noinit:
        # Add a model to the otherwise empty simulation. The sphere is
        # in the repo whereas the Vatican model is available here:
        # http://artist-3d.com/free_3d_models/dnm/model_disp.php?\
        # uid=3290&count=count
        p = os.path.dirname(os.path.abspath(__file__))
        p = os.path.join(p, '..', 'viewer', 'models', 'sphere')
        fname = os.path.join(p, 'sphere.obj')
        model_name = (1.25, fname)
        #model_name = (50, 'viewer/models/vatican/vatican-cathedral.3ds')
        #model_name = (1.25, 'viewer/models/house/house.3ds')
        loadGroundModel(*model_name)

        # Define additional templates.
        spawnCubes(*param.cubes, center=(0, 0, 10))
        del p, fname, model_name

    # Start the physics engine.
    #leo = leonard.LeonardBase()
    #leo = leonard.LeonardBullet()
    #leo = leonard.LeonardSweeping()
    leo = leonard.LeonardDistributedZeroMQ()
    leo.start()

    # Launch a dedicated process to periodically reset the simulation.
    time.sleep(2)
    rs = ResetSim(period=param.reset)
    rs.start()

    return [clerk, clacks, leo, rs]


def stopAzrael(procs):
    """
    Stop and join all ``procs``.
    """
    for proc in procs:
        proc.terminate()

    for proc in procs:
        proc.join()


def launchQtViewer(param):
    """
    Launch the Qt Viewer in a separate process.

    This function does not return until the viewer process finishes.
    """
    path_base = os.path.dirname(os.path.abspath(__file__))
    fname = os.path.join(path_base, '..', 'viewer', 'viewer.py')

    try:
        if param.noviewer:
            time.sleep(3600000000)
        else:
            subprocess.call(['python3', fname])
    except KeyboardInterrupt:
        pass
    

class ResetSim(multiprocessing.Process):
    """
    Periodically reset the simulation.
    """
    def __init__(self, period=-1):
        """
        Set ``period`` to -1 to disable simulation resets altogether.
        """
        super().__init__()
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
        allowed_objIDs = {k: v['sv'] for k, v in ret.data.items() if v is not None}
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
            BulletDataOverride = azrael.physics_interface.BulletDataOverride
            for ii in range(5):
                for objID, SV in allowed_objIDs.items():
                    tmp = BulletDataOverride(
                        position=SV.position,
                        velocityLin=SV.velocityLin,
                        velocityRot=SV.velocityRot,
                        orientation=SV.orientation)
                    client.setStateVariable(objID, tmp)
                time.sleep(0.1)


def main():
    # Parse the command line.
    param = parseCommandLine()

    # Start Azrael services.
    with azrael.util.Timeit('Startup Time', True):
        procs = startAzrael(param)
    print('Azrael now live')

    # Start the Qt Viewer.
    launchQtViewer(param)

    # Shutdown Azrael.
    stopAzrael(procs)

    print('Clean shutdown')


if __name__ == '__main__':
    main()