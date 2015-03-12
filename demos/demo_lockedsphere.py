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
Create a sphere with three boosters and four geometry fragments.

The four geometry fragments comprise the hull of the sphere, and three
individual "flames" to visualise the output of the three boosters.

Use this script in conjunction with ``ctrl_PDController.py``.
"""
import os
import sys
import time
import IPython
import argparse

import numpy as np
import demo_default as demolib

# Import the necessary Azrael modules.
import model_import
import azrael.client
import azrael.util as util
import azrael.parts as parts

from azrael.util import Template, Fragment, FragState

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


def spawnBoosterSphere(scale, fname):
    """
    Define a sphere with three boosters and four fragments.

    The first fragment comprises the hull (ie. the sphere itself), whereas
    remaining three fragments reprsent the "flames" that come out of the
    boosters.
    """
    # Get a Client instance.
    client = azrael.client.Client()

    # Load the model.
    print('  Importing <{}>... '.format(fname), end='', flush=True)
    mesh = model_import.loadModelAll(fname)

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

    # Attach six boosters, two for every axis.
    dir_x = np.array([1, 0, 0])
    dir_y = np.array([0, 1, 0])
    dir_z = np.array([0, 0, 1])
    pos_center = np.zeros(3)

    b0 = parts.Booster(partID=0, pos=pos_center, direction=dir_x,
                       minval=0, maxval=10.0, force=0)
    b1 = parts.Booster(partID=1, pos=pos_center, direction=dir_y,
                       minval=0, maxval=10.0, force=0)
    b2 = parts.Booster(partID=2, pos=pos_center, direction=dir_z,
                       minval=0, maxval=10.0, force=0)
    del dir_x, dir_y, dir_z, pos_center

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
             Fragment('b_x', vert_b, z, z),
             Fragment('b_y', vert_b, z, z),
             Fragment('b_z', vert_b, z, z),
             ]
    temp = Template(tID, cs, frags, [b0, b1, b2], [])
    assert client.addTemplates([temp]).ok
    del cs, frags, temp, z
    print('done')

    # Spawn the template near the center.
    print('  Spawning object... ', end='', flush=True)
    d = {'scale': scale,
         'imass': 0.1,
         'position': [0, 0, -10],
         'orientation': [0, 0, 0, 1],
         'axesLockLin': [1, 1, 1],
         'axesLockRot': [0, 0, 0],
         'template': tID}
    ret = client.spawn([d])
    objID = ret.data[0]
    print('done (ID=<{}>)'.format(objID))

    # Disable the booster fragments by settings its scale to Zero.
    newStates = {objID: [
        FragState('b_x', 0, [0, 0, 0], [0, 0, 0, 1]),
        FragState('b_y', 0, [0, 0, 0], [0, 0, 0, 1]),
        FragState('b_z', 0, [0, 0, 0], [0, 0, 0, 1]),
        ]}
    assert client.updateFragmentStates(newStates).ok
    return objID


def main():
    # Parse the command line.
    param = parseCommandLine()

    # Start Azrael services.
    with azrael.util.Timeit('Startup Time', True):
        az = demolib.RunAzrael(param)
        if not param.noinit:
            # Define a sphere with boosters and spawn an instance thereof.
            p = os.path.dirname(os.path.abspath(__file__))
            p = os.path.join(p, '..', 'viewer', 'models', 'sphere')
            fname = os.path.join(p, 'sphere.obj')
            spawnBoosterSphere(scale=1.25, fname=fname)

            # Add the specified number of cubes in a grid layout.
            demolib.spawnCubes(*param.cubes, center=(0, 0, 10))
            del p, fname

        # Launch a dedicated process to periodically reset the simulation.
        time.sleep(2)
        az.startProcess(demolib.ResetSim(period=param.reset))

    print('Azrael now live')

    # Start the Qt Viewer. This call will block until the viewer exits.
    demolib.launchQtViewer(param)

    # Stop Azrael stack.
    del az
    print('Clean shutdown')


if __name__ == '__main__':
    main()