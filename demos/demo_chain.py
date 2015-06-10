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
Build a chain of cubes.

fixme:
 - clean up
 - the --cubes argument only takes one argument (length of chain)
 - increase damping of the objects to avoid the perpetual jumpiness
 - the 6Dof constraint is working but ill configured
 - the code assumes there are at least 4 cubes

"""
import os
import sys
import time
import argparse
import PIL.Image
import multiprocessing

import numpy as np
import demo_default as demolib

# Import the necessary Azrael modules.
import azrael.client
import azrael.parts as parts
import azrael.util as util
import azrael.config as config
import azrael.vectorgrid as vectorgrid
import azrael.physics_interface as physAPI

from azrael.types import Template, MetaFragment, FragRaw, FragState
from azrael.types import CollShapeMeta, CollShapeEmpty, CollShapeSphere
from azrael.types import CollShapeBox, ConstraintMeta, ConstraintP2P
from azrael.types import Constraint6DofSpring2

from IPython import embed as ipshell

# Convenience.
MotionStateOverride = physAPI.MotionStateOverride


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
    padd('--linear', type=int, metavar='T', default=2,
         help='Duration of linear grid (in seconds)')
    padd('--circular', type=int, metavar='T', default=5,
         help='Duration of circular grid (in seconds)')

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


class UpdateGrid(multiprocessing.Process):
    """
    Update the force grid throughout the simulation.
    """
    def __init__(self, period_circ=1, period_lin=1):
        """
        Update the force grid values every ``period`` seconds.
        """
        super().__init__()
        self.period_lin = period_lin
        self.period_circ = period_circ

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
        Nx, Ny, Nz = 20, 20, 3

        # Lower left corner of the grid in space.
        ofs = np.array([-Nx, -Ny, 10 - Nz], np.float64)

        # Compute a counter clockwise oriented vector grid and another one the
        # always points to the center. Both calculations ignore the
        # z-dimension.
        force_rot = np.zeros((2 * Nx + 1, 2 * Ny + 1, 2 * Nz + 1, 3))
        force_lin = np.zeros_like(force_rot)
        force_grav = np.zeros_like(force_rot)
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
                v = -np.array([x, y, 0], np.float64)
                force_lin[x + Nx, y + Ny, :] = v

                force_grav[x + Nx, y + Ny, :] = np.array([-1, 0, 0])

        while True:
            ret = vg.setRegion('force', ofs, force_grav)
            time.sleep(100000000)

            # Activate the circular grid.
            ret = vg.setRegion('force', ofs, 0.3 * force_rot)
            print('Circular force')
            if not ret.ok:
                print('Could not set force grid values')
            time.sleep(self.period_circ)

            # Activate the linear grid.
            ret = vg.setRegion('force', ofs, 0.1 * force_lin)
            print('Linear force')
            if not ret.ok:
                print('Could not set force grid values')
            time.sleep(self.period_lin)


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

    # # ----------------------------------------------------------------------
    # # Create templates for the factory output.
    # # ----------------------------------------------------------------------
    # tID_1 = 'Product1'
    # tID_2 = 'Product2'
    # frags_1 = [MetaFragment('frag_1', 'raw', FragRaw(0.75 * vert, uv, rgb))]
    # frags_2 = [MetaFragment('frag_1', 'raw', FragRaw(0.24 * vert, uv, rgb))]
    # t1 = Template(tID_1, [cs], frags_1, [], [])
    # t2 = Template(tID_2, [cs], frags_2, [], [])
    # assert client.addTemplates([t1, t2]).ok
    # del frags_1, frags_2, t1, t2

    # ----------------------------------------------------------------------
    # Define a cube with boosters and factories.
    # ----------------------------------------------------------------------
    # Two boosters, one left, one right. Both point in the same direction.
    b0 = parts.Booster(partID='0', pos=[+0.05, 0, 0], direction=[0, 0, 1],
                       minval=0, maxval=10.0, force=0)
    b1 = parts.Booster(partID='1', pos=[-0.05, 0, 0], direction=[0, 0, 1],
                       minval=0, maxval=10.0, force=0)

    # # Two factories, one left one right. They will eject the new objects
    # # forwards and backwards, respectively.
    # f0 = parts.Factory(
    #     partID='0', pos=[+1.5, 0, 0], direction=[+1, 0, 0],
    #     templateID=tID_1, exit_speed=[0.1, 1])
    # f1 = parts.Factory(
    #     partID='1', pos=[-1.5, 0, 0], direction=[-1, 0, 0],
    #     templateID=tID_2, exit_speed=[0.1, 1])

    # # Add the template.
    # tID_3 = 'BoosterCube'
    # frags = [MetaFragment('frag_1', 'raw', FragRaw(vert, uv, rgb))]
    # t3 = Template(tID_3, [cs], frags, [b0, b1], [f0, f1])
    # assert client.addTemplates([t3]).ok
    # del frags, t3

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
    cube_spacing = 0.0

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
                pos *= -(4 + cube_spacing)

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

    # fixme: this code assumes there are at least 4 cubes!
    if len(allObjs) < 4:
        print('fixme: start demo with at least 4 cubes!')
        sys.exit(1)
    allObjs = []
    pos_0 = [2, 0, 10]
    pos_1 = [-2, 0, 10]
    pos_2 = [-6, 0, 10]
    pos_3 = [-10, 0, 10]
    allObjs.append({'template': tID_cube[0], 'position': pos_0})
    allObjs.append({'template': tID_cube[1], 'position': pos_1})
    allObjs.append({'template': tID_cube[2], 'position': pos_2})
    allObjs.append({'template': tID_cube[3], 'position': pos_3})

    # The first object cannot move (only rotate). It serves as an anchor for
    # the connected bodies.
    allObjs[0]['axesLockLin'] = [0, 0, 0]
    allObjs[0]['axesLockRot'] = [1, 1, 1]

    # Add a small damping factor to all bodies to avoid them moving around
    # perpetually.
    for oo in allObjs[1:]:
        oo['axesLockLin'] = [0.9, 0.9, 0.9]
        oo['axesLockRot'] = [0.9, 0.9, 0.9]

    print('{:,} objects ({:.1f}s)'.format(len(allObjs), time.time() - t0))
    del cube_idx, cube_spacing, row, col, lay

    # Spawn the cubes from the templates at the just determined positions.
    print('Spawning {} objects: '.format(len(allObjs)), end='', flush=True)
    t0 = time.time()
    ret = client.spawn(allObjs)
    assert ret.ok
    ids = ret.data
    print('{:.1f}s'.format(time.time() - t0))

    # Define the constraints.
    p2p_0 = ConstraintP2P(pivot_a=[-2, 0, 0], pivot_b=[2, 0, 0])
    p2p_1 = ConstraintP2P(pivot_a=[-2, 0, 0], pivot_b=[2, 0, 0])
    p2p_2 = ConstraintP2P(pivot_a=[-2, 0, 0], pivot_b=[2, 0, 0])
    dof = Constraint6DofSpring2(
        frameInA=[0, 0, 0, 0, 0, 0, 1],
        frameInB=[0, 0, 0, 0, 0, 0, 1],
        stiffness=[2, 2, 2, 1, 1, 1],
        damping=[1, 1, 1, 1, 1, 1],
        equilibrium=[-2, -2, -2, 0, 0, 0],
        linLimitLo=[-4.5, -4.5, -4.5],
        linLimitHi=[4.5, 4.5, 4.5],
        rotLimitLo=[-0.1, -0.2, -0.3],
        rotLimitHi=[0.1, 0.2, 0.3],
        bounce=[1, 1.5, 2],
        enableSpring=[True, False, False, False, False, False])
    constraints = [
        ConstraintMeta('p2p', ids[0], ids[1], '', p2p_0),
        ConstraintMeta('p2p', ids[1], ids[2], '', p2p_1),
        ConstraintMeta('6DOFSPRING2', ids[2], ids[3], '', dof),
    ]
    assert client.addConstraints(constraints) == (True, None, 3)

    # Make 'frag_2' invisible by setting its scale to zero.
    for objID in ret.data:
        client.updateFragmentStates({objID: [
            FragState('frag_2', 0, [0, 0, 0], [0, 0, 0, 1])]})


def main():
    # Parse the command line.
    param = parseCommandLine()

    assert vectorgrid.resetGrid('force').ok

    # Helper class to start/stop Azrael stack and other processes.
    az = azrael.startup.AzraelStack(param.loglevel)

    # Start Azrael services.
    with azrael.util.Timeit('Startup Time', True):
        az.start()
        if not param.noinit:
            # Add the specified number of cubes in a grid layout.
            spawnCubes(*param.cubes, center=(0, 0, 10))

        # Launch a dedicated process to periodically reset the simulation.
        time.sleep(2)
#        az.startProcess(demolib.ResetSim(period=param.reset))

    print('Azrael now live')

    # Start the process that periodically changes the force field. Add the
    # process handle to the list of processes.
    az.startProcess(
        UpdateGrid(period_circ=param.circular, period_lin=param.linear))

    # Start the Qt Viewer. This call will block until the viewer exits.
    demolib.launchQtViewer(param)

    # Stop Azrael stack.
    az.stop()
    print('Clean shutdown')


if __name__ == '__main__':
    main()
