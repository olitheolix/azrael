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
import azrael.types as types
import azrael.config as config
import azrael.vectorgrid as vectorgrid

from IPython import embed as ipshell
from azrael.types import Template, FragMeta, FragRaw


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
    padd('--port', metavar='port', type=int, default=azrael.config.port_webserver,
         help='Port number')
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

    # Rigid body parameters.
    scale = 1
    imass = 1
    restitution = 0.9
    rotation = (0, 0, 0, 1)
    position = (0, 0, 0)
    velocityLin = (0, 0, 0)
    velocityRot = (0, 0, 0)
    axesLockLin = (0, 0, 0)
    axesLockRot = (0, 0, 0)
    version = 0
    cshapes = {'cs': cshapes}

    # Rigid body data for platforms (defines their physics, not appearance).
    body = azrael.types.RigidBodyData(
        scale, imass, restitution, rotation,
        position, velocityLin, velocityRot,
        cshapes, axesLockLin, axesLockRot,
        version)
    
    # Geometry for the platforms (defines their appearance, not physics).
    fr = FragRaw(vert, uv=[], rgb=[])
    fm = FragMeta(fragtype='RAW', scale=1, position=position,
                  rotation=rotation, fragdata=fr)
    frags = {'frag_1': fm}

    # Define the platform template and upload it to Azrael.
    template = Template('platform', body, frags, {}, {})
    ret = client.addTemplates([template])

    # Spawn several platforms at different positions. The overall impression
    # will be akin to a stairway.
    platforms = []
    for ii in range(5):
        pos = (ii * 5, -ii * 2, ii * 5)
        platforms.append(
            {'templateID': 'platform',
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

    # Apply gravity in the vincinity of the platforms.
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
