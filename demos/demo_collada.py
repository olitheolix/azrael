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
import argparse

import numpy as np
import demo_default as demolib

# Import the necessary Azrael modules.
import model_import
import azrael.client
import azrael.util as util
import azrael.parts as parts
import azrael.config as config

from IPython import embed as ipshell
from azrael.types import Template, MetaFragment, FragDae, FragState


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


def spawnColladaModel(scale, fname):
    """
    Import the collada file ``fname`` as a new template and spawn it.
    """
    # Get a Client instance.
    client = azrael.client.Client()

    # Collada format: a .dae file plus a list of textures in jpg or png format.
    b = os.path.dirname(__file__)
    b = os.path.join(b, '..', 'azrael', 'test')
    dae_file = open(b + '/cube.dae', 'rb').read()
    dae_rgb1 = open(b + '/rgb1.png', 'rb').read()
    dae_rgb2 = open(b + '/rgb2.jpg', 'rb').read()
    f_dae = FragDae(dae=dae_file,
                    rgb={'rgb1.png': dae_rgb1,
                         'rgb2.jpg': dae_rgb2})
    del b

    # Put both fragments into a valid list of MetaFragments.
    frags = [MetaFragment('dae', 'f_dae', f_dae)]

    temp = Template('Collada', [4, 1, 1, 1], frags, [], [])
    assert client.addTemplates([temp]).ok
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
         'template': temp.id}
    ret = client.spawn([d])
    objID = ret.data[0]
    print('done (ID=<{}>)'.format(objID))

    return objID


def main():
    # Parse the command line.
    param = parseCommandLine()

    # Helper class to start/stop Azrael stack and other processes.
    az = azrael.startup.AzraelStack(param.loglevel)

    # Start Azrael services.
    with azrael.util.Timeit('Startup Time', True):
        az.start()
        if not param.noinit:
            # Define a sphere with boosters and spawn an instance thereof.
            p = os.path.dirname(os.path.abspath(__file__))
            p = os.path.join(p, '..', 'viewer', 'models', 'sphere')
            fname = os.path.join(p, 'sphere.obj')
            spawnColladaModel(scale=1.25, fname=fname)

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
    az.stop()
    print('Clean shutdown')


if __name__ == '__main__':
    main()
