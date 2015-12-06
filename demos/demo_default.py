# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

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
import argparse
import PIL.Image
import subprocess
import multiprocessing
import demolib

import numpy as np

# Import the necessary Azrael modules.
p = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(p, '..'))
del p

import pyazrael
import azrael.startup
import azrael.util as util
import azrael.config as config
import azrael.leo_api as leoAPI
import azrael.aztypes as aztypes

from IPython import embed as ipshell
from azrael.aztypes import Template, CollShapeMeta
from azrael.aztypes import CollShapeEmpty, CollShapeSphere, CollShapeBox


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
    padd('--port', metavar='port', type=int, default=config.port_webapi,
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


def addBoosterCubeTemplate(scale, vert, uv, rgb):
    # Get a Client instance.
    client = pyazrael.AzraelClient()

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

    boosters = {
        '0': aztypes.Booster(position=pos_left, direction=-dir_up, force=0),
        '1': aztypes.Booster(position=pos_center, direction=dir_forward, force=0),
        '2': aztypes.Booster(position=-pos_left, direction=dir_up, force=0),
        '3': aztypes.Booster(position=pos_center, direction=-dir_forward, force=0)
    }
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
    cs = CollShapeBox(1, 1, 1)
    cs = CollShapeMeta('box', (0, 0, 0), (0, 0, 0, 1), cs)
    z = np.array([])
    frags = {
        'frag_1': demolib.getFragMetaRaw(vert, uv, rgb),
        'b_left': demolib.getFragMetaRaw(vert_b, z, z),
        'b_right': demolib.getFragMetaRaw(vert_b, z, z),
    }

    body = demolib.getRigidBody()
    temp = Template(tID, body, frags, boosters, {})
    assert client.addTemplates([temp]).ok
    del cs, frags, temp, z
    print('done')

    # Spawn the template near the center.
    print('  Spawning object... ', end='', flush=True)
    pos, orient = [0, 0, -10], [0, 1, 0, 0]
    new_obj = {
        'templateID': tID,
        'rbs': {
            'scale': scale,
            'imass': 0.1,
            'position': pos,
            'rotation': orient,
            'linFactor': [1, 1, 1],
            'rotFactor': [1, 1, 1]}
    }
    ret = client.spawn([new_obj])
    objID = ret.data[0]
    print('done (ID=<{}>)'.format(objID))

    # Disable the booster fragments by settings their scale to Zero.
    newStates = {objID: {
        'b_left': {'op': 'mod', 'scale': 0},
        'b_right': {'op': 'mod', 'scale': 0},
    }}
    assert client.setFragments(newStates).ok


def addTexturedCubeTemplates(numCols, numRows, numLayers):
    # Get a Client instance.
    client = pyazrael.AzraelClient()

    # Geometry and collision shape for cube.
    vert, cs = demolib.cubeGeometry()

    # Assign the UV coordinates. Each vertex needs a coordinate pair. That
    # means each triangle needs 6 coordinates. And the cube has 12 triangles.
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
    img = PIL.Image.open(fname)
    img = np.array(img)
    rgb = np.rollaxis(np.flipud(img), 1).flatten()

    # ----------------------------------------------------------------------
    # Create templates for the factory output.
    # ----------------------------------------------------------------------
    tID_1 = 'Product1'
    tID_2 = 'Product2'
    frags_1 = {'frag_1': demolib.getFragMetaRaw(0.75 * vert, uv, rgb)}
    frags_2 = {'frag_1': demolib.getFragMetaRaw(0.24 * vert, uv, rgb)}
    body = demolib.getRigidBody(cshapes={'0': cs})
    t1 = Template(tID_1, body, frags_1, {}, {})
    t2 = Template(tID_2, body, frags_2, {}, {})
    assert client.addTemplates([t1, t2]).ok
    del frags_1, frags_2, t1, t2

    # ----------------------------------------------------------------------
    # Define a cube with boosters and factories.
    # ----------------------------------------------------------------------
    # Two boosters, one left, one right. Both point in the same direction.
    boosters = {
        '0': aztypes.Booster(position=[+0.05, 0, 0], direction=[0, 0, 1], force=0),
        '1': aztypes.Booster(position=[-0.05, 0, 0], direction=[0, 0, 1], force=0)
    }

    # Two factories, one left one right. They will eject the new objects
    # forwards and backwards, respectively.
    factories = {
        '0': aztypes.Factory(position=[+1.5, 0, 0], direction=[+1, 0, 0],
                             templateID=tID_1, exit_speed=[0.1, 1]),
        '1': aztypes.Factory(position=[-1.5, 0, 0], direction=[-1, 0, 0],
                             templateID=tID_2, exit_speed=[0.1, 1])
    }

    # Add the template.
    tID_3 = 'BoosterCube'
    frags = {'frag_1': demolib.getFragMetaRaw(vert, uv, rgb)}
    body = demolib.getRigidBody(cshapes={'0': cs})
    t3 = Template(tID_3, body, frags, boosters, factories)
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
            img = PIL.Image.open(fname)
            img = np.array(img)
            rgb = np.rollaxis(np.flipud(img), 1).flatten()
            curUV = uv
        except FileNotFoundError:
            texture_errors += 1
            rgb = curUV = np.array([])

        # Create the template.
        tID = ('BoosterCube_{}'.format(ii))
        frags = {'frag_1': demolib.getFragMetaRaw(vert, curUV, rgb),
                 'frag_2': demolib.getFragMetaRaw(vert, curUV, rgb)}
        body = demolib.getRigidBody(cshapes={'0': cs})
        tmp = Template(tID, body, frags, boosters, {})
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
    return tID_cube


def spawnCubes(numCols, numRows, numLayers, center=(0, 0, 0)):
    """
    Spawn multiple cubes in a regular grid.

    The number of cubes equals ``numCols`` * ``numRows`` * ``numLayers``. The
    center of this "prism" is at ``center``.

    Every cube has two boosters and two factories. The factories can themselves
    spawn more (purely passive) cubes.
    """
    tID_cube = addTexturedCubeTemplates(numCols, numRows, numLayers)

    # Get a Client instance.
    client = pyazrael.AzraelClient()

    # ----------------------------------------------------------------------
    # Spawn the differently textured cubes in a regular grid.
    # ----------------------------------------------------------------------
    # The cubes currently have a size of 2. The grid spacing must thus be
    # larger than 2 if the cubes are not to touch each other.
    cube_size = 2 + 0.1

    # Compute the grid position. The grid is centered at `center`.
    positions = np.array(list(np.ndindex(numCols, numRows, numLayers)))
    positions = positions - np.mean(positions, axis=0)
    positions = positions * cube_size + center

    # Specify the initial state for each cube and spawn them.
    t0 = time.time()
    allObjs = [
        {'templateID': tID_cube[idx], 'rbs': {'position': pos.tolist()}}
        for idx, pos in enumerate(positions)
    ]
    print('Spawning {} objects: '.format(len(allObjs)), end='', flush=True)
    ret = client.spawn(allObjs)
    if not ret.ok:
        print('** Error:')
        print(ret)
        assert False
    print(' {:.1f}s'.format(time.time() - t0))

    # Make 'frag_2' invisible by setting its scale to zero.
    for objID in ret.data:
        cmd = {objID: {'frag_2': {'op': 'mod', 'scale': 0}}}
        assert client.setFragments(cmd).ok
        assert client.setCustomData({objID: 'asteroid'}).ok


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
        client = pyazrael.AzraelClient()

        # Query all objects in the scene. These are the only objects that will
        # survive the reset.
        ret = client.getAllObjectIDs()
        assert ret.ok
        ret = client.getRigidBodies(ret.data)
        assert ret.ok
        allowed_objIDs = {k: v['rbs'] for k, v in ret.data.items()
                          if v is not None}
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
                    client.removeObjects([objID])

            # Forcefully reset the position and velocity of every object. Do
            # this several times since network latency may result in some
            # objects being reset sooner than others.
            for ii in range(5):
                for objID, SV in allowed_objIDs.items():
                    tmp = {
                        'position': SV.position,
                        'velocityLin': SV.velocityLin,
                        'velocityRot': SV.velocityRot,
                        'rotation': SV.rotation}
                    assert client.setRigidBodies({objID: tmp}).ok
                time.sleep(0.1)


def main():
    # Parse the command line.
    param = parseCommandLine()

    # Helper class to start/stop Azrael stack and other processes.
    az = azrael.startup.AzraelStack(param.loglevel)

    # Start Azrael services.
    with azrael.util.Timeit('Startup Time', True):
        az.start()
        if not param.noinit:
            # Add a model to the otherwise empty simulation. The sphere is
            # in the repo whereas the Vatican model is available here:
            # http://artist-3d.com/free_3d_models/dnm/model_disp.php?\
            # uid=3290&count=count
            p = os.path.dirname(os.path.abspath(__file__))
            fname = os.path.join(p, 'models', 'sphere', 'sphere.obj')
#            fname = os.path.join(p, 'house', 'house.obj')
#            fname = '/home/oliver/delme/export/monster.dae'
#            fname = os.path.join(p, 'test.obj')
            scale, model_name = (1.25, fname)
            # scale, model_name = (
            #     50, 'viewer/models/vatican/vatican-cathedral.3ds')
            # scale, model_name = (
            #     1.25, 'viewer/models/house/house.3ds')
            vert, uv, rgb = demolib.loadModel(model_name)

            # Load the Booster Cube Model created in Blender.
            scale, (vert, uv, rgb) = 1, demolib.loadBoosterCubeBlender()

            # Wrap the UV data into a BoosterCube template and add it to
            # Azrael.
            addBoosterCubeTemplate(scale, vert, uv, rgb)

            # Define additional templates, in this case the wall of cubes.
            # Spawn them a bit to the right and back.
            spawnCubes(*param.cubes, center=(5, 0, -5))
            del p, fname, model_name

        # Launch a dedicated process to periodically reset the simulation.
        time.sleep(2)
        az.startProcess(ResetSim(period=param.reset))

    print('Azrael now live')

    # Either wait forever or start the Qt Viewer and wait for it to return.
    if param.noviewer:
        demolib.waitForever()
    else:
        viewer = demolib.launchQtViewer()
        viewer.wait()

    # Stop Azrael stack.
    az.stop()
    print('Clean shutdown')


if __name__ == '__main__':
    main()
