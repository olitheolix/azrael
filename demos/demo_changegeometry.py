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
import os
import sys
import time
import IPython
import argparse
import demo_default
import multiprocessing

import numpy as np
import demo_default as demolib

# Import the necessary Azrael modules.
import model_import
import azrael.client
import azrael.util as util
import azrael.vectorgrid as vectorgrid
import azrael.physics_interface as physAPI

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


def loadSphere():
    """
    Return the geometry of a sphere.

    The sphere data is loaded from 'sphere.obj' which is part of the repo.

    :return: (vert, uv, rgb)
    """
    # Assemble path to the model.
    p = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(p, '..', 'viewer', 'models', 'sphere')
    fname = os.path.join(p, 'sphere.obj')

    # Import the model geometry.
    print('  Importing <{}>... '.format(fname), end='', flush=True)
    mesh = model_import.loadModelAll(fname)

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

    # Return the geometry.
    return vert, uv, rgb


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
            demolib.addModel(scale=1.25, fname=fname)

            # Define additional templates.
            demolib.spawnCubes(*param.cubes, center=(0, 0, 10))
            del p, fname

        # Launch a dedicated process to periodically reset the simulation.
        time.sleep(2)
        az.startProcess(demolib.ResetSim(period=param.reset))

    print('Azrael now live')

    # Start the process that periodically changes the geometries. Add the
    # process to the list of processes.
    az.startProcess(SetGeometry(2))

    # Start the Qt Viewer. This call will block until the viewer exits.
    demolib.launchQtViewer(param)

    # Stop Azrael stack.
    az.stop()
    print('Clean shutdown')


if __name__ == '__main__':
    main()
