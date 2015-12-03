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
Create a line of cubes and use it to "plot" a Sine function.
"""
import sys
import time
import demolib
import argparse
import multiprocessing
import numpy as np

# Import the necessary Azrael modules.
import azrael.clerk
import azrael.startup
import azrael.aztypes as aztypes
import azrael.config as config
import azrael.vectorgrid as vectorgrid

from IPython import embed as ipshell
from azrael.aztypes import Template


def parseCommandLine():
    """
    Parse program arguments.
    """
    # Create the parser.
    parser = argparse.ArgumentParser(
        description=('Azrael Sine Demo'),
        formatter_class=argparse.RawTextHelpFormatter)

    # Shorthand.
    padd = parser.add_argument

    # Add the command line options.
    padd('--noviewer', action='store_true', default=False,
         help='Do not spawn a viewer')
    padd('--port', metavar='port', type=int, default=azrael.config.port_webapi,
         help='Port number')
    padd('--loglevel', type=int, metavar='level', default=1,
         help='Specify error log level (0: Debug, 1:Info)')

    # Run the parser.
    param = parser.parse_args()
    return param


class ModifyScale(multiprocessing.Process):
    """
    Periodically modify the size of the cubes to visualise a sinusoidal
    signal with the lines of cubes.
    """
    def run(self):
        # Connect to Azrael.
        client = azrael.clerk.Clerk()

        # Poll the simulation until an object with the correct tag appears.
        while True:
            ret = client.getCustomData(None)
            assert ret.ok
            objIDs = [k for (k, v) in ret.data.items() if v == 'PlotObject']
            if len(objIDs) == 1:
                objID = objIDs[0]
                print('Found the object (ID={})'.format(objID))
                break
            time.sleep(0.5)

        # Fetch all fragment names.
        ret = client.getFragments([objID])
        assert ret.ok
        frag_names = sorted(ret.data[objID].keys())

        # Periodically update the scale values of each cube.
        cnt = 0
        while True:
            # Increment loop counter.
            cnt += 1

            # Compute a sine wave and convert it to scale values.
            t = np.linspace(0, 1, len(frag_names))
            phi = np.pi * (cnt / 10)
            scale = np.sin(2 * np.pi * t  + phi)

            # Scale values must be non-negative.
            scale = (1 + scale) / 2

            # Apply the scale values to the cubes.
            cmd = {}
            for scale, frag_name in zip(scale.tolist(), frag_names):
                cmd[frag_name] = {'op': 'mod', 'scale': scale}
            ret = client.setFragments({objID: cmd})

            # Wait.
            time.sleep(0.1)


def addLineOfCubes(numCubes=15):
    # Connect to Azrael.
    client = azrael.clerk.Clerk()

    # Get the mesh and collision shape for a single cube.
    vert, csmetabox = demolib.cubeGeometry(0.5, 0.5, 0.5)

    # Create a fragment template (convenience only for the loop below).
    ref_frag = demolib.getFragMetaRaw(vert=vert, uv=[], rgb=[])

    # Create the fragments and line them up in a line along the x-axis.
    frags = {}
    centre = (numCubes - 1) / 2
    for idx in range(numCubes):
        frag_name = str(idx)
        frag_pos = [(idx - centre) * 2, 0, 0]
        frags[frag_name] = ref_frag._replace(position=frag_pos)

    # Rigid body description (defines its physics, not its appearance).
    body = demolib.getRigidBody(cshapes={'cs': csmetabox})

    # Define the object template (physics and appearance) and upload to Azrael.
    template = Template('PlotObject', body, frags, {}, {})
    ret = client.addTemplates([template])

    # Spawn one instance.
    templates = [{'templateID': 'PlotObject', 'rbs': {'position': [0, 0, 0]}}]
    ret = client.spawn(templates)
    assert ret.ok
    objID = ret.data[0]

    # Tag the object.
    assert client.setCustomData({objID: 'PlotObject'})


def main():
    # Parse the command line.
    param = parseCommandLine()

    # Helper class to start/stop Azrael stack and other processes.
    az = azrael.startup.AzraelStack(param.loglevel)
    az.start()
    print('Azrael now live')

    # Spawn the line of cubes that will serve as the stems of the plot.
    p = ModifyScale()
    p.start()
    addLineOfCubes()

    # Launch Qt viewer and wait for it to exit.
    demolib.launchQtViewer(param)

    # Stop Azrael stack.
    p.terminate()
    p.join()
    az.stop()
    print('Clean shutdown')


if __name__ == '__main__':
    main()
