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
Load the Manhatten map.

To create the Manhatten map ('manhatten.json') follow this YouTube tutorial
https://youtu.be/S6LbKH6NnZU
"""
import os
import sys
import time
import argparse
import demolib
import numpy as np

# Import the necessary Azrael modules.
import azrael.clerk
import azrael.startup
import azrael.config as config
import azrael.aztypes as aztypes

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
    padd('--port', metavar='port', type=int, default=azrael.config.port_webapi,
         help='Port number')
    padd('--loglevel', type=int, metavar='level', default=1,
         help='Specify error log level (0: Debug, 1:Info)')

    # Run the parser.
    param = parser.parse_args()
    return param


def spawn_city():
    # Add the template to Azrael.
    print('  Adding city template... ', end='', flush=True)
    tID = 'city'

    # Collision shape for city.
    cs = aztypes.CollShapeBox(1, 1, 1)
    cs = aztypes.CollShapeMeta('box', (0, 0, 0), (0, 0, 0, 1), cs)
    body = demolib.getRigidBody(cshapes={'0': cs}, position=(0, 0, 0))

    # Load the Manhatten geometry.
    FM3JS = demolib.getFragMeta3JS
    frags = {'main': FM3JS(['manhatten.json'], scale=0.1, pos=(0, -10, 0))}

    # Get a Clerk instance. Then upload the template to Azrael.
    client = azrael.clerk.Clerk()
    assert client.addTemplates([Template(tID, body, frags, {}, {})]).ok
    del cs, body, frags
    print('done')

    # Spawn the template near the center.
    print('  Spawning city... ', end='', flush=True)
    pos, orient = [0, 0, -20], [0, 1, 0, 0]
    new_obj = {
        'templateID': tID,
        'rbs': {
            'scale': 1,
            'imass': 0.1,
            'position': pos,
            'rotation': orient,
            'linFactor': [1, 1, 1],
            'rotFactor': [1, 1, 1]}
    }
    ret = client.spawn([new_obj])
    assert ret.ok

    # Status message. Then return the object ID of the model.
    print('done (ID=<{}>)'.format(ret.data[0]))
    return ret.data[0]


def main():
    # Parse the command line.
    param = parseCommandLine()

    if not os.path.exists('manhatten.json'):
        print('Cannot open <manhatten.json>')
        print('Please create it according to https://youtu.be/S6LbKH6NnZU ')
        sys.exit(1)

    # Helper class to start/stop Azrael stack and other processes.
    az = azrael.startup.AzraelStack(param.loglevel)
    az.start()
    time.sleep(1)
    print('Azrael now live')

    # Spawn the city. Then wait forever.
    spawn_city()
    while True:
        time.sleep(60)

    # Stop Azrael stack.
    az.stop()
    print('Clean shutdown')


if __name__ == '__main__':
    main()
