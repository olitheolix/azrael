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
Create a platform environment with local gravity.

This demo was originally developed in tandem with 'ship_boostercube' to create
a platform environment. However, this Azrael simulation does not make any
assumption about the client that will be using it.
"""
import time
import argparse
import demolib
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
        description=('Azrael Platform World'),
        formatter_class=argparse.RawTextHelpFormatter)

    # Shorthand.
    padd = parser.add_argument

    # Add the command line options.
    padd('--loglevel', type=int, metavar='level', default=1,
         help='Specify error log level (0: Debug, 1:Info)')

    # Run the parser.
    param = parser.parse_args()
    return param


def addPlatforms():
    # Connect to Azrael.
    client = azrael.clerk.Clerk()

    # Geometry and collision shape for platform.
    vert, cshapes = demolib.cubeGeometry(2, 0.1, 2)

    # Rigid body data for platforms (defines their physics, not appearance).
    body = demolib.getRigidBody(
        cshapes={'cs': cshapes},
        linFactor=[0, 0, 0],
        rotFactor=[0, 0, 0]
    )

    # Geometry for the platforms (defines their appearance, not physics).
    fm = demolib.getFragMetaRaw(
        vert=vert,
        uv=[],
        rgb=[],
        scale=1,
        pos=(0, 0, 0),
        rot=(0, 0, 0, 1)
    )
    frags = {'frag_1': fm}

    # Define the platform template and upload it to Azrael.
    template = Template('platform', body, frags, {}, {})
    ret = client.addTemplates([template])

    # Spawn several platforms at different positions. Their positions are
    # supposed to create the impression of a stairway. The values assume the
    # camera is at [0, 0, 10] and points in -z direction.
    platforms = []
    for ii in range(5):
        pos = (-10 + ii * 5, -ii * 2, -20)
        platforms.append(
            {
                'templateID': 'platform',
                'rbs': {
                    'position': pos,
                    'velocityLin': (0, 0, 0),
                    'scale': 1,
                    'imass': 20
                }
            }
        )
    platformIDs = client.spawn(platforms)

    # Tag all platforms with a custom string.
    cmd = {platformID: 'Platform' for platformID in platformIDs.data}
    assert client.setCustomData(cmd)


def main():
    # Parse the command line.
    param = parseCommandLine()

    # Helper class to start/stop Azrael stack and other processes.
    az = azrael.startup.AzraelStack(param.loglevel)
    az.start()
    print('Azrael now live')

    # Setup the parcour of platforms.
    addPlatforms()

    # Apply gravity in the vicinity of the platforms.
    print('Setting grid...', end='', flush=True)
    ofs = np.array([-5, -5, -5], np.float64)
    val = np.zeros((30, 30, 30, 3))
    val[:, :, :] = [0, -5, 0]
    ret = vectorgrid.setRegion('force', ofs, val)
    del ofs, val, ret
    print('done')
    print('Simulation setup complete')

    # Wait forever.
    while True:
        time.sleep(100)

    # Stop Azrael stack.
    az.stop()
    print('Clean shutdown')


if __name__ == '__main__':
    main()
