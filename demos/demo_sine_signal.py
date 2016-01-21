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
    padd('--loglevel', type=int, metavar='level', default=1,
         help='Specify error log level (0: Debug, 1:Info)')

    # Run the parser.
    param = parser.parse_args()
    return param


class SineWaveGenerator:
    """
    Scale the cubes to visualise a Sine wave.
    """
    def __init__(self, client):
        self.client = client
        self.objID = None
        self.cnt = 0

    def waitForObject(self, name):
        """
        Wait until the object ``name`` is present in the simulation.

        Return the objID.
        """
        # Poll the simulation until an object with the correct tag appears.
        while True:
            ret = self.client.getCustomData(None)
            assert ret.ok
            objIDs = [k for (k, v) in ret.data.items() if v == name]
            if len(objIDs) == 1:
                self.objID = objIDs[0]
                break
            time.sleep(0.5)

        # Fetch all fragment names.
        ret = self.client.getFragments([self.objID])
        assert ret.ok
        self.frag_names = sorted(ret.data[self.objID].keys())
        return self.objID

    def updatePlot(self):
        """
        Compute a new phase value and update the Sine wave accordingly.
        """
        # Increment loop counter.
        self.cnt += 1

        # Compute a sine wave and convert it to scale values.
        t = np.linspace(0, 1, len(self.frag_names))
        phi = np.pi * (self.cnt / 10)
        scale = np.sin(2 * np.pi * t + phi)

        # Scale values must be non-negative in Azrael.
        scale = (1 + scale) / 2

        # Apply the scale values to the cubes.
        cmd = {}
        for scale, frag_name in zip(scale.tolist(), self.frag_names):
            cmd[frag_name] = {'op': 'mod', 'scale': scale}
        assert self.client.setFragments({self.objID: cmd}).ok


def addLineOfCubes(client, objName: str, numCubes: int):
    """
    Spawn a single body with ``numCubes`` fragments.

    The body will also be tagged with `objName`.
    """
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
    assert client.setCustomData({objID: objName})


def main():
    # Parse the command line.
    param = parseCommandLine()

    # Helper class to start/stop Azrael stack and other processes.
    az = azrael.startup.AzraelStack(param.loglevel)
    az.start()
    print('Azrael now live')

    # Connect to Azrael.
    client = azrael.clerk.Clerk()

    # Spawn the line of cubes that will serve as the plot markers.
    objName = 'PlotObject'
    addLineOfCubes(client, objName, 15)

    # Create the Sine wave generator and wait until it found the object.
    swg = SineWaveGenerator(client)
    swg.waitForObject(objName)

    # Wait for the user to terminate the program.
    if param.noviewer:
        # Wait until <Ctrl-C>
        demolib.waitForever()
    else:
        # Launch Qt Viewer in new process and wait until the user quits it.
        viewer = demolib.launchQtViewer()
        while viewer.poll() is None:
            time.sleep(0.1)
            swg.updatePlot()
        viewer.wait()

    # Stop Azrael stack.
    az.stop()
    print('Clean shutdown')


if __name__ == '__main__':
    main()
