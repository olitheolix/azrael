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
Create a molecule like object to demonstrate centre of mass offsets and general
inertia.
"""
import sys
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
        description=('Azrael Molecule Demo'),
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


def addMolecule():
    # Connect to Azrael.
    client = azrael.clerk.Clerk()

    # The molecule will consist of several cubes.
    vert, csmetabox = demolib.cubeGeometry(0.5, 0.5, 0.5)

    # The molecule object.
    ofs = 2
    frag_src = {
        'up': [0, ofs, 0],
        'down': [0, -ofs, 0],
        'left': [ofs, 0, 0],
        'right': [-ofs, 0, 0],
        'front': [0, 0, ofs],
        'back': [0, 0, -ofs],
        'center': [0, 0, 0],
    }
    del ofs
#    frag_src = {'down': frag_src['down']}
#    frag_src = {'center': frag_src['center']}

    frags, cshapes = {}, {}
    for name, pos in frag_src.items():
        frags[name] = demolib.getFragMetaRaw(
            vert=vert,
            uv=[],
            rgb=[],
            scale=1,
            pos=pos,
            rot=[0, 0, 0, 1],
        )

        cshapes[name] = csmetabox._replace(position=pos)
        del name, pos
    del frag_src

    # Rigid body data parameters (defines its physics, not appearance). Specify
    # the centre of mass (com) and principal axis rotation (paxis) for the
    # inertia values.
    body = demolib.getRigidBody(
        imass=0.1,
        com=[0, -1, 0],
        inertia=[1, 2, 3],
        paxis=[0, 0, 0, 1],
        cshapes=cshapes,
    )

    # Define the object template and upload it to Azrael.
    template = Template('molecule', body, frags, {}, {})
    ret = client.addTemplates([template])

    # Spawn one molecule.
    templates = [{'templateID': 'molecule', 'rbs': {'position': [0, 0.5, 0]}}]
    objID = client.spawn(templates)


def main():
    # Parse the command line.
    param = parseCommandLine()

    # Helper class to start/stop Azrael stack and other processes.
    az = azrael.startup.AzraelStack(param.loglevel)
    az.start()
    print('Azrael now live')

    # Spawn the molecule object.
    addMolecule()

    # Either wait forever or start the Qt Viewer and wait for it to return.
    if param.noviewer:
        demolib.waitForever()
    else:
        viewer = demolib.launchQtViewer()
        viewer.wait()

    # Stop Azrael stack.
    az.stop()
    print('Clean shutdown')


if __name__ == '__main__':
    main()
