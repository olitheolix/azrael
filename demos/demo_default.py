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
import argparse
import PIL.Image
import subprocess
import multiprocessing

# Import 'setproctitle' *before* NumPy, even though it is not even used
# in this script. Howver, if it is import after NumPy then the various Azrael
# modules cannot rename themselves. No, I do not know why.
import setproctitle
import numpy as np

# Import the necessary Azrael modules.
p = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(p, '..'))
sys.path.insert(0, os.path.join(p, '../viewer'))
import model_import
import azrael.client
import azrael.startup
import azrael.util as util
import azrael.parts as parts
import azrael.config as config
import azrael.leo_api as leoAPI
del p

from IPython import embed as ipshell
from azrael.types import Template, MetaFragment, FragRaw, FragState
from azrael.types import CollShapeMeta, CollShapeEmpty, CollShapeSphere
from azrael.types import CollShapeBox


# Convenience.
RigidBodyStateOverride = leoAPI.RigidBodyStateOverride


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
    padd('--port', metavar='port', type=int, default=azrael.config.port_clacks,
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


def loadBoosterCubeBlender():
    """
    Load the Booster Sphere model from "boostercube.dae".

    This is function is custom made for the model because the Collada model
    exported via Blender is only partially imported. In particular, the
    ``loadModel`` function will only return the vertices for the body (cube)
    and one thruster. This function will scale-, rotate-, and copy that
    thruster so that each side of the cube has one. Furthermore, it will
    manually assign colors.
    """

    # Load the Collada model.
    p = os.path.dirname(os.path.abspath(__file__))
    fname = os.path.join(p, 'boostercube.dae')
    vert, uv, rgb = loadModel(fname)

    # Extract the body and thruster component.
    body, thruster_z = np.array(vert[0]), np.array(vert[1])

    # The body should be a unit cube, but I do not know what Blender created
    # exactly. Therefore, determine the average position values (which should
    # all have the same value except for the sign).
    body_scale = np.mean(np.abs(body))

    # Reduce the thruster size, translate it to the cube's surface, and
    # duplicate on -z axis.
    thruster_z = 0.3 * np.reshape(thruster_z, (len(thruster_z) // 3, 3))
    thruster_z += [0, 0, -.6]
    thruster_z = thruster_z.flatten()
    thruster_z = np.hstack((thruster_z, -thruster_z))

    # Reshape the vertices into an N x 3 matrix and duplicate for the other
    # four thrusters.
    thruster_z = np.reshape(thruster_z, (len(thruster_z) // 3, 3))
    thruster_x, thruster_y = np.array(thruster_z), np.array(thruster_z)

    # We will compute the thrusters for the remaining two cube faces with a
    # 90degree rotation around the x- and y axis.
    s2 = 1 / np.sqrt(2)
    quat_x = util.Quaternion(s2, [s2, 0, 0])
    quat_y = util.Quaternion(s2, [0, s2, 0])
    for ii, (tx, ty) in enumerate(zip(thruster_x, thruster_y)):
        thruster_x[ii] = quat_x * tx
        thruster_y[ii] = quat_y * ty

    # Flatten the arrays.
    thruster_z = thruster_z.flatten()
    thruster_x = thruster_x.flatten()
    thruster_y = thruster_y.flatten()

    # Combine all thrusters and the body into a single triangle mesh. Then
    # scale the entire mesh to ensure the cube part is indeed a unit cube.
    vert = np.hstack((thruster_z, thruster_x, thruster_y, body))
    vert /= body_scale

    # Assign the same base color to all three thrusters.
    rgb_thruster = np.tile([0.8, 0, 0], len(thruster_x) // 3)
    rgb_thrusters = np.tile(rgb_thruster, 3)

    # Assign a color to the body.
    rgb_body = np.tile([0.8, 0.8, 0.8], len(body) // 3)

    # Combine the RGB vectors into single one to match the vector of vertices.
    rgb = np.hstack((rgb_thrusters, rgb_body))
    del rgb_thruster, rgb_thrusters, rgb_body

    # Add some random "noise" to the colors.
    rgb += 0.2 * (np.random.rand(len(rgb)) - 0.5)

    # Convert the RGB values from a triple of [0, 1] floats to a triple of [0,
    # 255] integers.
    rgb = rgb.clip(0, 1)
    rgb = np.array(rgb * 255, np.uint8)

    # Return the model data.
    return vert, uv, rgb


def loadModel(fname):
    """
    Load 3D model from ``fname`` and return the vertices, UV, and RGB arrays.
    """
    # Load the model.
    print('  Importing <{}>... '.format(fname), end='', flush=True)
    mesh = model_import.loadModelAll(fname)

    # The model may contain several sub-models. Each one has a set of vertices,
    # UV- and texture maps. The following code simply flattens the three lists
    # of lists into just three lists.
    vert = np.array(mesh['vertices']).flatten()
    uv = np.array(mesh['UV']).flatten()
    rgb = np.array(mesh['RGB']).flatten()

    return vert, uv, rgb


def addBoosterCubeTemplate(scale, vert, uv, rgb):
    # Get a Client instance.
    client = azrael.client.Client()

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

    b0 = parts.Booster(partID='0', pos=pos_left, direction=-dir_up,
                       minval=0, maxval=10.0, force=0)
    b1 = parts.Booster(partID='1', pos=pos_center, direction=dir_forward,
                       minval=0, maxval=1000.0, force=0)
    b2 = parts.Booster(partID='2', pos=-pos_left, direction=dir_up,
                       minval=0, maxval=10.0, force=0)
    b3 = parts.Booster(partID='3', pos=pos_center, direction=-dir_forward,
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
    cs = CollShapeBox(1, 1, 1)
    cs = CollShapeMeta('box', '', (0, 0, 0), (0, 0, 0, 1), cs)
    z = np.array([])
    frags = [
        MetaFragment('frag_1', 'raw', FragRaw(vert, uv, rgb)),
        MetaFragment('b_left', 'raw', FragRaw(vert_b, z, z)),
        MetaFragment('b_right', 'raw', FragRaw(vert_b, z, z)),
    ]
    temp = Template(tID, [cs], frags, [b0, b1, b2, b3], [])
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
         'axesLockRot': [1, 1, 1],
         'template': tID}
    ret = client.spawn([d])
    objID = ret.data[0]
    print('done (ID=<{}>)'.format(objID))

    # Disable the booster fragments by settings their scale to Zero.
    newStates = {objID: [
        FragState('b_left', 0, [0, 0, 0], [0, 0, 0, 1]),
        FragState('b_right', 0, [0, 0, 0], [0, 0, 0, 1]),
    ]}
    assert client.updateFragmentStates(newStates).ok


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

    # Vertices that define a Cube.
    vert = 1 * np.array([
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
    cs = CollShapeBox(1, 1, 1)
    cs = CollShapeMeta('box', '', (0, 0, 0), (0, 0, 0, 1), cs)
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
    img = PIL.Image.open(fname)
    img = np.array(img)
    rgb = np.rollaxis(np.flipud(img), 1).flatten()

    # ----------------------------------------------------------------------
    # Create templates for the factory output.
    # ----------------------------------------------------------------------
    tID_1 = 'Product1'
    tID_2 = 'Product2'
    frags_1 = [MetaFragment('frag_1', 'raw', FragRaw(0.75 * vert, uv, rgb))]
    frags_2 = [MetaFragment('frag_1', 'raw', FragRaw(0.24 * vert, uv, rgb))]
    t1 = Template(tID_1, [cs], frags_1, [], [])
    t2 = Template(tID_2, [cs], frags_2, [], [])
    assert client.addTemplates([t1, t2]).ok
    del frags_1, frags_2, t1, t2

    # ----------------------------------------------------------------------
    # Define a cube with boosters and factories.
    # ----------------------------------------------------------------------
    # Two boosters, one left, one right. Both point in the same direction.
    b0 = parts.Booster(partID='0', pos=[+0.05, 0, 0], direction=[0, 0, 1],
                       minval=0, maxval=10.0, force=0)
    b1 = parts.Booster(partID='1', pos=[-0.05, 0, 0], direction=[0, 0, 1],
                       minval=0, maxval=10.0, force=0)

    # Two factories, one left one right. They will eject the new objects
    # forwards and backwards, respectively.
    f0 = parts.Factory(
        partID='0', pos=[+1.5, 0, 0], direction=[+1, 0, 0],
        templateID=tID_1, exit_speed=[0.1, 1])
    f1 = parts.Factory(
        partID='1', pos=[-1.5, 0, 0], direction=[-1, 0, 0],
        templateID=tID_2, exit_speed=[0.1, 1])

    # Add the template.
    tID_3 = 'BoosterCube'
    frags = [MetaFragment('frag_1', 'raw', FragRaw(vert, uv, rgb))]
    t3 = Template(tID_3, [cs], frags, [b0, b1], [f0, f1])
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
        frags = [MetaFragment('frag_1', 'raw', FragRaw(vert, curUV, rgb)),
                 MetaFragment('frag_2', 'raw', FragRaw(vert, curUV, rgb))]
        tmp = Template(tID, [cs], frags, [b0, b1], [])
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
                pos *= -(2 + cube_spacing)

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
        ret = client.getBodyStates(ret.data)
        assert ret.ok
        allowed_objIDs = {k: v['sv'] for k, v in ret.data.items()
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
                    client.removeObject(objID)

            # Forcefully reset the position and velocity of every object. Do
            # this several times since network latency may result in some
            # objects being reset sooner than others.
            RigidBodyStateOverride = azrael.leo_api.RigidBodyStateOverride
            for ii in range(5):
                for objID, SV in allowed_objIDs.items():
                    tmp = RigidBodyStateOverride(
                        position=SV.position,
                        velocityLin=SV.velocityLin,
                        velocityRot=SV.velocityRot,
                        orientation=SV.orientation)
                    client.setBodyState(objID, tmp)
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
            p = os.path.join(p, '..', 'viewer', 'models')
            fname = os.path.join(p, 'sphere', 'sphere.obj')
#            fname = os.path.join(p, 'house', 'house.obj')
#            fname = '/home/oliver/delme/export/monster.dae'
#            fname = os.path.join(p, 'test.obj')
            scale, model_name = (1.25, fname)
            # scale, model_name = (
            #     50, 'viewer/models/vatican/vatican-cathedral.3ds')
            # scale, model_name = (
            #     1.25, 'viewer/models/house/house.3ds')
            vert, uv, rgb = loadModel(model_name)

            # Load the Booster Cube Model created in Blender.
            scale, (vert, uv, rgb) = 1, loadBoosterCubeBlender()

            # Wrap the UV data into a BoosterCube template and add it to
            # Azrael.
            addBoosterCubeTemplate(scale, vert, uv, rgb)

            # Define additional templates, in this case the wall of cubes.
            spawnCubes(*param.cubes, center=(0, 0, 10))
            del p, fname, model_name

        # Launch a dedicated process to periodically reset the simulation.
        time.sleep(2)
        az.startProcess(ResetSim(period=param.reset))

    print('Azrael now live')

    # Start the Qt Viewer. This call will block until the viewer exits.
    launchQtViewer(param)

    # Stop Azrael stack.
    az.stop()
    print('Clean shutdown')


if __name__ == '__main__':
    main()
