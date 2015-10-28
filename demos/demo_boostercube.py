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
import os
import sys
import time
import argparse
import demolib
import demo_default
import numpy as np

# Import the necessary Azrael modules.
import model_import
import pyazrael
import azrael
import azrael.util as util
import azrael.aztypes as aztypes

from IPython import embed as ipshell
from azrael.aztypes import Template, FragMeta, FragRaw


def spawnSpaceship(scale, fname):
    """
    Define a sphere with three boosters and four fragments.

    The first fragment comprises the hull (ie. the sphere itself), whereas
    remaining three fragments reprsent the "flames" that come out of the
    boosters.
    """
    # Get a Client instance.
    client = pyazrael.AzraelClient()

    # Load the model.
    vert, uv, rgb = demolib.loadBoosterCubeBlender()
    frag_cube = FragRaw(vert, uv, rgb)
    del vert, uv, rgb

    # Attach six boosters, two for every axis.
    dir_x = np.array([1, 0, 0])
    dir_y = np.array([0, 1, 0])
    dir_z = np.array([0, 0, 1])
    pos = (0, 0, 0)
    B = aztypes.Booster
    boosters = {
        'b_x': B(pos=pos, direction=(1, 0, 0), minval=0, maxval=10.0, force=0),
        'b_y': B(pos=pos, direction=(0, 1, 0), minval=0, maxval=10.0, force=0),
        'b_z': B(pos=pos, direction=(0, 0, 1), minval=0, maxval=10.0, force=0)
    }
    del dir_x, dir_y, dir_z, pos, B

    # Load sphere and color it blue(ish). This is going to be the (super
    # simple) "flame" that comes out of the (still invisible) boosters.
    p = os.path.dirname(os.path.abspath(__file__))
    fname = os.path.join(p, 'models', 'sphere', 'sphere.obj')
    vert, uv, rgb = demolib.loadModel(fname)
    rgb = np.tile([0, 0, 0.8], len(vert) // 3)
    rgb += 0.2 * np.random.rand(len(rgb))
    rgb = np.array(255 * rgb.clip(0, 1), np.uint8)
    frag_flame = FragRaw(vert, np.array([]), rgb)
    del p, fname, vert, uv, rgb

    # Add the template to Azrael.
    print('  Adding template to Azrael... ', end='', flush=True)
    tID = 'spaceship'
    cs = aztypes.CollShapeBox(scale, scale, scale)
    cs = aztypes.CollShapeMeta('box', (0, 0, 0), (0, 0, 0, 1), cs)
    body = demolib.getRigidBody(cshapes={'0': cs})
    pos, rot = (0, 0, 0), (0, 0, 0, 1)
    frags = {
        'frag_1': FragMeta('raw', scale, pos, rot, frag_cube),
        'b_x': FragMeta('raw', 0, pos, rot, frag_flame),
        'b_y': FragMeta('raw', 0, pos, rot, frag_flame),
        'b_z': FragMeta('raw', 0, pos, rot, frag_flame),
    }
    temp = Template(tID, body, frags, boosters, {})
    assert client.addTemplates([temp]).ok
    del cs, frags, temp, frag_cube, frag_flame, scale, pos, rot
    print('done')


def main():
    # Parse the command line.
    param = demo_default.parseCommandLine()

    # Helper class to start/stop Azrael stack and other processes.
    az = azrael.startup.AzraelStack(param.loglevel)

    # Start Azrael services.
    with azrael.util.Timeit('Startup Time', True):
        az.start()
        if not param.noinit:
            # Define a sphere with boosters and spawn an instance thereof.
            p = os.path.dirname(os.path.abspath(__file__))
            fname = os.path.join(p, 'models', 'sphere', 'sphere.obj')
            spawnSpaceship(scale=1.0, fname=fname)

            # Add the specified number of cubes in a grid layout.
            demo_default.addTexturedCubeTemplates(2, 2, 1)
            del p, fname

        # Launch a dedicated process to periodically reset the simulation.
        time.sleep(2)
        az.startProcess(demo_default.ResetSim(period=param.reset))

    print('Azrael now live')

    # Start the Qt Viewer. This call will block until the viewer exits.
    demolib.launchQtViewer(param)

    # Stop Azrael stack.
    az.stop()
    print('Clean shutdown')


if __name__ == '__main__':
    main()
