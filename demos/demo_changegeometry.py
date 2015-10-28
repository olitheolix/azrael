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
import json
import requests
import argparse
import demo_default
import multiprocessing

import numpy as np
import demolib
import demo_default

# Import the necessary Azrael modules.
import model_import
import azrael
import pyazrael
import azrael.util as util

from IPython import embed as ipshell
from azrael.aztypes import FragMeta, FragRaw


def loadSphere():
    """
    Return the geometry of a sphere.

    The sphere data is loaded from 'sphere.obj' which is part of the repo.

    :return: (vert, uv, rgb)
    """
    # Assemble path to the model.
    p = os.path.dirname(os.path.abspath(__file__))
    fname = os.path.join(p, 'models', 'sphere', 'sphere.obj')

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
    Alternate the geometry between a sphere and a textured cube.

    Note that the original collision shape will not be updated.
    """
    def __init__(self, period=1):
        """
        Update the geometry every ``period`` seconds.
        """
        super().__init__()
        self.period = period

        # Address of Clerk.
        self.addr_webserver = '127.0.0.1'
        self.port_webserver = 8080

    def run(self):
        """
        """
        # Return immediately if no resets are required.
        if self.period == -1:
            return

        # Instantiate Client.
        client = pyazrael.AzraelClient()

        # Query all object IDs. This happens only once which means the geometry
        # swap does not affect newly generated objects.
        time.sleep(1)
        ret = client.getAllObjectIDs()
        objIDs = ret.data
        print('\n-- {} objects --\n'.format(len(objIDs)))

        # Backup all models currently in the scene.
        geo_meta = client.getFragments(objIDs).data
        base_url = 'http://{}:{}'.format(
            self.addr_webserver, self.port_webserver)
        geo_orig = {}
        for objID in objIDs:
            geo_orig[objID] = {}
            for frag_name in geo_meta[objID]:
                url = base_url + geo_meta[objID][frag_name]['url_frag']
                url += '/model.json'
                tmp = requests.get(url).content
                tmp = json.loads(tmp.decode('utf8'))
                geo_orig[objID][frag_name] = {
                    'fragtype': 'RAW',
                    'scale': 1,
                    'fragdata': FragRaw(**tmp),
                }
                del url, tmp
            del objID
        del geo_meta, base_url

        # Compile a set of sphere models for all objects. These will be
        # periodically swapped out for the original models.
        sphere_vert, sphere_uv, sphere_rgb = loadSphere()
        sphere = FragRaw(sphere_vert, sphere_uv, sphere_rgb)
        geo_spheres = {}
        for objID in objIDs:
            geo_spheres[objID] = {
                _: {'fragtype': 'RAW', 'scale': 1, 'fragdata': sphere}
                for _ in geo_orig[objID]}
        del sphere_vert, sphere_uv, sphere_rgb, sphere

        cnt = 0
        while True:
            # Update the counter and pause for the specified time.
            cnt = (cnt + 1) % 20
            time.sleep(self.period)

            # Swap out the geometry.
            if (cnt % 2) == 1:
                geo = geo_spheres
            else:
                geo = geo_orig

            # Apply the new geometry to each fragment.
            ret = client.setFragments(geo)
            if not ret.ok:
                print('--> Terminating geometry updates')
                sys.exit(1)

            # Modify the global scale and a fragment position.
            scale = (cnt + 1) / 10
            new_frag_states = {}
            new_body_states = {}
            for objID in objIDs:
                # Modify the position of the second fragment.
                new_frag_states[objID] = {
                    'frag_2': {
                        'scale': scale,
                        'position': [-10 + cnt, 0, 0]
                }}
                new_body_states[objID] = {'cshapes': {}}
            client.setFragments(new_frag_states)

            # Print status for user.
            print('Scale={:.1f}'.format(scale))


def main():
    # Parse the command line.
    param = demo_default.parseCommandLine()

    # Helper class to start/stop Azrael stack and other processes.
    az = azrael.startup.AzraelStack(param.loglevel)

    # Start Azrael services.
    with azrael.util.Timeit('Startup Time', True):
        az.start()
        if not param.noinit:
            # Define additional templates.
            demo_default.spawnCubes(*param.cubes, center=(0, 0, 10))

        # Launch a dedicated process to periodically reset the simulation.
        time.sleep(2)
        az.startProcess(demo_default.ResetSim(period=param.reset))

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
