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
Import a Blender model into Azrael.

This is a somewhat hackish proof of concept only to validate that it is well
possible to import models from Blender. Albeit not production ready the
'sample.blend' model features three individual fragments, one which with a
texture.

This script, in conjunction with Blender itself and the auxiliary script
'parse_blender_scene.py' (called from within Blender) make it possible to
automatically determine build Box collision shapes for each fragment and render
the object.


Usage
-----

Replace Blender's default Python interpreter with the one from the Azrael
environment. For instance, for Blender 2.76:
  >> cd path/to/blender/2.76
  >> mv python python.orig
  >> ln -s path/to/anaconda/envs/azrael python

Then run this demo with:
  >> python demos/demo_blender.py


Todo
----

  - See todo list in 'parse_blender_scene.py'.
  - Incorporate the import functionality into demolib.
  - Can 'model_import.py' be made redundant?

"""
import os
import sys
import PIL
import time
import json
import demolib
import tempfile
import argparse
import pyassimp
import subprocess
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


def processBlenderFile(fname):
    """
    Parse the content of fname with a Python script from inside Blender.

    That Python script started from Blender will write information about the
    scene to a temporary file. The name of that file will be returned to the
    caller to peruse as necessary.

    :param str fname: Name of Blender file.
    :return: file name (str).
    """
    # Sanity check.
    if not os.path.exists(fname):
        print('Error: Blender file <{}> does not exist'.format(fname))
        sys.exit(1)

    # Create a temporary file and specify that it must not be deleted when
    # closed again.
    fname_out = tempfile.NamedTemporaryFile(delete=False).name

    # Compile the path to the Python script that Blender should execute.
    fname_script = 'parse_blender_scene.py'
    fname_script = os.path.join(os.path.dirname(__file__), fname_script)

    # Tell Blender to load the scene and run the Python script without spawning
    # a user interface. If everything goes well we will have a new file
    # `fname_out` with the content created fname_script.
    cmd = [
        'blender',
        fname,
        '--background',
        '--python', fname_script,
        '--azrael', fname_out,
    ]
    subprocess.call(cmd)

    # Return the name with the meta information.
    return fname_out


def loadMaterials(scene, fname):
    """
    Return a list of textures data for each material.

    The materials are specified in the AssImp `scene`. The `fname` argument is
    the path to the original Blender file. It is only necessary to extract the
    path since all texture images are specified relative to this file.

    Each element in the returned list is a dictionary that contains the image
    itself, as well as its dimensions.

    :param scene: AssImp scene
    :param str fname: Blender file name.
    :return: list[dict]
    """
    # Get the path to the model file (textures are specified relative to it).
    fname = os.path.abspath(fname)
    fpath, fname = os.path.split(fname)
    del fname

    # Load the texture for each material.
    materials = []
    for mat_idx, mat in enumerate(scene.materials):
        fname_texture = None
        try:
            # Extract the texture file name via the magic key name
            # `('file', 1)`. This key is defined in the Python wrapper for
            # AssImp.
            mat_aux = dict(mat.properties)
            fname_texture = mat_aux[('file', 1)]

            # Construct absolute path to texture image.
            if fname_texture.startswith('//'):
                fname_texture = fname_texture[2:]
            fname_texture = os.path.join(fpath, fname_texture)

            # Debug print.
            print('Loading texture <{}>'.format(fname_texture))

            # Load the image (may raise a FileNotFoundError).
            img = PIL.Image.open(fname_texture)
        except (FileNotFoundError, KeyError):
            # Could not load the texture image.
            materials.append({'RGB': [], 'width': 0, 'height': 0})
            if fname_texture is None:
                print('Could not load material index {}'.format(mat_idx))
            else:
                print('Could not find texture <{}>'.format(fname_texture))
            continue

        # Convert the image to an RGB array.
        width, height = img.size
        img = img.transpose(PIL.Image.ROTATE_270)
        RGB = np.fromstring(img.tobytes(), np.uint8).tolist()
        del mat_aux, fname_texture, img

        # Sanity check.
        assert (len(RGB) == width * height * 3)
        materials.append({'RGB': RGB, 'width': width, 'height': height})
    return materials


def loadBlender(fname_blender: str):
    """
    Compile and return the fragments and collision shapes from ``fname``.

    The ``fname`` file must specify a Blender file.

    :param str fname: Blender file name
    :return: (frags dict, cshapes dict)
    """
    # Use Blender itself to load the Blender file. This will trigger a script
    # inside Blender that creates a JSON file with custom scene data. The name
    # of that file is returned in 'fname_az'.
    fname_az = processBlenderFile(fname_blender)

    # Load the collision shape data and geometry.
    pp = pyassimp.postprocess
    azFile = json.loads(open(fname_az, 'rb').read().decode('utf8'))
    scene = pyassimp.load(fname_blender, pp.aiProcess_Triangulate)
    del fname_az, pp

    # Sanity check: both must contain information about the exact same objects.
    assert set(azFile.keys()) == {_.name for _ in scene.meshes}

    # Load all the materials.
    materials = loadMaterials(scene, fname_blender)

    # Compile fragments and collision shapes for Azrael.
    frags, cshapes = {}, {}
    for mesh in scene.meshes:
        # Get the material for this mesh.
        material = materials[mesh.materialindex]

        # Iterate over the faces and rebuild the vertices.
        azData = azFile[mesh.name]
        vert = np.zeros(len(mesh.faces) * 9)
        for idx, face in enumerate(mesh.faces):
            tmp = [mesh.vertices[_] for _ in face]
            start, stop = idx * 9, (idx + 1) * 9
            vert[start:stop] = np.hstack(tmp)
            del start, stop, tmp, idx, face

        # Copy the UV coordinates, if there are any.
        if len(mesh.texturecoords) > 0:
            uv = np.zeros(len(mesh.faces) * 6)
            for idx, face in enumerate(mesh.faces):
                tmp = [mesh.texturecoords[0][_, :2] for _ in face]
                start, stop = 6 * idx, 6 * (idx + 1)
                uv[start:stop] = np.hstack(tmp)
                del start, stop, tmp, idx, face
        else:
            uv = 0.5 * np.ones(2 * (len(vert) // 3))

        # Sanity check.
        assert (len(uv) // 2 == len(vert) // 3)

        # Azrael does not allow 'dots', yet Bullet uses it prominently to name
        # objects. As a quick fix, simply replace the dots with something else.
        # fixme: should be redundant once #149 (https://trello.com/c/wcHX3qGd)
        # is implemented.
        azname = mesh.name.replace('.', 'x')

        # Unpack the position and orientation of the mesh in world coordinates.
        pos, rot, dim = azData['pos'], azData['rot'], np.array(azData['dimensions'])

        # Unpack the interior points and put them into any kind of byte string.
        # This will be attached as yet another file to the fragment data.
        interior_points = json.dumps(azData['interior_points']).encode('utf8')

        # Create a RAW fragment.
        scale = 1
        rgb, width, height = material['RGB'], material['width'], material['height']
        frag = demolib.getFragMetaRaw(vert, uv, rgb, scale, pos, rot, width, height)
        frag.files['interior_points'] = interior_points
        frags[azname] = frag

        # Construct the BOX collision shape based on the Blender dimensions.
        hlen_x, hlen_y, hlen_z = (dim / 2).tolist()
        box = aztypes.CollShapeBox(hlen_x, hlen_y, hlen_z)

        # Construct the CollshapeMeta data.
        cshapes[azname] = aztypes.CollShapeMeta('box', pos, rot, box)
        del azData, vert, dim, scale, rgb, width, height, hlen_x, hlen_y, hlen_z
    return frags, cshapes


def spawnObject(client, frags, cshapes):
    """
    """
    # Rigid body description (defines its physics, not its appearance).
    body = demolib.getRigidBody(cshapes=cshapes)

    # Define the object template (physics and appearance) and upload to Azrael.
    template = Template('BlenderObject', body, frags, {}, {})
    ret = client.addTemplates([template])

    # Spawn one instance.
    templates = [{'templateID': 'BlenderObject', 'rbs': {'position': [0, 0, 0]}}]
    ret = client.spawn(templates)
    assert ret.ok
    objID = ret.data[0]


def main():
    # Specify Blender file.
    fname_blender = 'models/sample/sample.blend'
    fname_blender = os.path.join(os.path.dirname(__file__), fname_blender)

    # Parse the command line.
    param = parseCommandLine()

    # Helper class to start/stop Azrael stack and other processes.
    az = azrael.startup.AzraelStack(param.loglevel)
    az.start()
    print('Azrael now live')

    # Connect to Azrael.
    client = azrael.clerk.Clerk()

    # Load the model and convert it to fragments and collision shapes.
    frags, cshapes = loadBlender(fname_blender)

    # Create a template and spawn an object from it.
    spawnObject(client, frags, cshapes)

    # Wait for the user to terminate the program.
    if param.noviewer:
        # Wait until <Ctrl-C>
        demolib.waitForever()
    else:
        # Launch Qt Viewer in new process and wait until the user quits it.
        demolib.launchQtViewer().wait()

    # Stop Azrael stack.
    az.stop()
    print('Clean shutdown')


if __name__ == '__main__':
    main()
