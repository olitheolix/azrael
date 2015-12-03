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
An experiment to import a Blender model in Collada format.

This demo loads the file and automatically assigns collision shapes based on
the names of the meshes.

..note:: This script is experimental! It makes many hard coded assumption about
    the content of the Blender/Collada model.
"""
import os
import sys
import time
import pyassimp
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
    padd('--noviewer', action='store_true', default=False,
         help='Do not spawn a viewer')
    padd('--port', metavar='port', type=int, default=azrael.config.port_webapi,
         help='Port number')
    padd('--loglevel', type=int, metavar='level', default=1,
         help='Specify error log level (0: Debug, 1:Info)')

    # Run the parser.
    param = parser.parse_args()
    return param


def inverseTransform(transform):
    """
    Return the 4x4 matrix does undoes ``transform``.
    """
    transform = np.array(transform)
    rot = transform[:3, :3]
    translate = transform[:3, 3]

    scale = rot.dot(rot.T)
    scale = np.mean(np.diag(scale))

    i_translate = np.eye(4)
    i_translate[:3, 3] = -translate

    i_rot = np.eye(4)
    i_rot[:3, :3] = rot.T / scale

    return scale, i_rot.dot(i_translate)


def loadColladaModel(filename):
    """
    Load the Collada modle created in Blender. This function makes the
    following hard coded assumptions about that file:

    * It contains a node called 'Parent'
    * That parent contains a mesh called 'MainBody'.
    """
    # Load the scene.
    scene = pyassimp.load(filename)

    # Find the node called 'Parent' (hard coded assumption that must be matched
    # by Blender model).
    p = None
    print('\nModel file contains the following meshes:')
    for child in scene.rootnode.children:
        print('  *', child.name)
        if child.name == 'Parent':
            p = child

    # The Parent node must exist, and it must contain one mesh called
    # 'MainBody'.
    assert p is not None
    objs = {_.name: _ for _ in p.children}
    assert 'MainBody' in objs

    # For later: compute the inverse transform of MainBody.
    scale, i_transform = inverseTransform(objs['MainBody'].transformation)

    gfmr = demolib.getFragMetaRaw
    frags, cshapes = {}, {}
    for name in objs:
        # 4x4 transformation matrix for current mesh (this is always in global
        # coordinates, not relative to anything).
        t = np.array(objs[name].transformation)

        # Vertices of current mesh (Nx3).
        vert = objs[name].meshes[0].vertices

        # Transpose vertex matrix to obtain the 3xN matrix. Then add a row of
        # 1s to obtain a 4xN matrix.
        vert = vert.T
        vert = np.vstack((vert, np.ones(vert.shape[1])))

        # Scale/rotatate/translate the vertices relative to the position of the
        # MainBody. Then drop the (auxiliary) last row again to get back to a
        # Nx3 matrix of vertices.
        vert = i_transform.dot(t.dot(vert))
        vert = vert[:-1, :].T

        # Flatten the vertex matrix into a simple list and compile it into a
        # fragment.
        vert = vert.flatten()
        frags[name] = gfmr(vert, uv=[], rgb=[], scale=1)

        # All bodies whose name starts with 'cs' get a spherical collision
        # shape.
        if name.lower().startswith('cs'):
            # Compute the combined transformation matrix that represents the
            # difference between the MainBody's position and this one. To find
            # this, simpy apply the invers transform of the MainBody to the
            # transform of the locat body. The latter would move the current
            # object to its correct position in world coordinates, and the
            # former will undo offset and rotation of the MainBody.
            t = i_transform.dot(t)

            # Determine the position.
            # Fixme: also determine the quaternion and scale from the total
            # transformation matrix.
            _pos = tuple(t[:3, 3].tolist())
            _rot = (0, 0, 0, 1)

            # Create a spherical collision shape and place it relative to the
            # MainBody.
            sphere = aztypes.CollShapeSphere(1)
            cshapes[name] = aztypes.CollShapeMeta('sphere', _pos, _rot, sphere)

    return frags, cshapes


def spawn_model():
    # Load the geometry.
    p = os.path.dirname(os.path.abspath(__file__))
    filename = os.path.join(p, 'models', 'cshape_experiment', 'csbodies.dae')
    frags, cshapes = loadColladaModel(filename)
    body = demolib.getRigidBody(cshapes=cshapes, position=(0, 0, 0))

    # Get a Clerk instance. Then upload the template to Azrael.
    print('\nAdding model template... ', end='', flush=True)
    client = azrael.clerk.Clerk()
    tID = 'mymodel'
    assert client.addTemplates([Template(tID, body, frags, {}, {})]).ok
    del body, frags
    print('done')

    # Spawn the template at the center.
    print('Spawning model... ', end='', flush=True)
    new_obj = {
        'templateID': tID,
        'rbs': {
            'scale': 1,
            'imass': 0.1,
            'position': [0, 0, 0],
            'rotation': [0, 0, 0, 1],
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

    # Helper class to start/stop Azrael stack and other processes.
    az = azrael.startup.AzraelStack(param.loglevel)
    az.start()
    time.sleep(1)
    print('Azrael now live')

    # Spawn the model. Then either launch the Qt viewer or wait forever.
    spawn_model()
    demolib.launchQtViewer(param)

    # Stop Azrael stack.
    az.stop()
    print('Clean shutdown')


if __name__ == '__main__':
    main()
