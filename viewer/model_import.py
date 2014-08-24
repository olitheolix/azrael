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

import os
import sys
import time
import IPython
import pyassimp
import pyassimp.postprocess
import PIL.Image
import numpy as np

ipshell = IPython.embed


def normaliseModel(scene):
    # Find arithmetic model center.
    minval = np.zeros((len(scene.meshes), 3))
    maxval = np.zeros_like(minval)
    for idx, mm in enumerate(scene.meshes):
        minval[idx, :] = np.amin(mm.vertices, axis=0)
        maxval[idx, :] = np.amax(mm.vertices, axis=0)
    minval = np.amin(minval, axis=0)
    maxval = np.amax(maxval, axis=0)
    ofs = (minval + maxval) / 2

    # Center the model and find the largest distance from the center.
    max_dist = 1E-5
    for idx, mm in enumerate(scene.meshes):
        mm.vertices -= ofs

        # Determine the largest norm.
        dist = np.amax(np.sqrt(np.sum(mm.vertices ** 2, axis=1)))
        if dist > max_dist:
            max_dist = dist

    # Scale the model so that the distance to the farthest vertex is unity.
    for idx, mm in enumerate(scene.meshes):
        mm.vertices /= max_dist


def loadMaterials(scene, fname):
    material_list = []
    for mat_idx, mat in enumerate(scene.materials):
        if 'file' in mat.properties.keys():
            mat_aux = dict(mat.properties)
            model_dir = os.path.split(fname)[0]
            texture_file = model_dir + '/' + mat_aux[('file', 1)]
            img = PIL.Image.open(texture_file)
            width, height = img.size
            img = img.transpose(PIL.Image.FLIP_TOP_BOTTOM)
            RGB = np.fromstring(img.tobytes(), np.uint8)

            del mat_aux, model_dir, texture_file, img
        else:
            RGB = (255 * np.array(mat.properties['diffuse']))
            RGB = RGB.astype(np.uint8)
            width = height = 1

        assert (len(RGB) == width * height * 3)
        material_list.append({'RGB': RGB.tolist(),
                              'width': width,
                              'height': height})
    return material_list


def loadObjects(scene, material_list):
    mat2mesh = {}
    for idx, mm in enumerate(scene.meshes):
        mat_idx = mm.materialindex
        if mat_idx not in mat2mesh:
            mat2mesh[mat_idx] = []
        mat2mesh[mat_idx].append(idx)
    del idx, mm, mat_idx

    set_vertex = []
    set_UV = []
    set_RGB = []
    set_width = []
    set_height = []

    # Loop over all materials.
    for mat_idx in mat2mesh:
        vertex_material = []
        UV_material = []
        mat = material_list[mat_idx]

        # Loop over all the meshes that use the current material and
        # concatenate their vertices and UV maps.
        for mesh_idx in mat2mesh[mat_idx]:
            mesh = scene.meshes[mesh_idx]

            # Flatten the mesh data, which comes as an Nx3 array.
            vert = (mesh.vertices).flatten()
            assert len(vert) % 9 == 0

            # Copy the UV coordinates, if there are any.
            if len(mesh.texturecoords) > 0:
                UV = mesh.texturecoords[0][:, :2]
                UV = UV.flatten()
            else:
                UV = 0.5 * np.ones(2 * (len(vert) // 3))

            assert (len(UV) // 2 == len(vert) // 3)

            # Add the vertices, and UV maps to the set.
            vertex_material.extend(vert.tolist())
            UV_material.extend(UV.tolist())

        # Now that all those meshes from the scene that share the same material
        set_vertex.append(vertex_material)
        set_UV.append(UV_material)
        set_RGB.append(material_list[mat_idx]['RGB'])
        set_width.append(material_list[mat_idx]['width'])
        set_height.append(material_list[mat_idx]['height'])
    return set_vertex, set_UV, set_RGB, set_width, set_height


def loadModelAll(fname):
    scene = pyassimp.load(fname, pyassimp.postprocess.aiProcess_Triangulate)

    # Center and normalise the mesh.
    normaliseModel(scene)

    # Load all the materials.
    material_list = loadMaterials(scene, fname)

    # Associate mesh indexes with material indexes.
    vert, UV, RGB, width, height = loadObjects(scene, material_list)

    # Sanity check: the number of vertices must match the number of UV pairs.
    assert (len(UV) == len(vert))
    for ii in range(len(UV)):
        assert (len(UV[ii]) // 2 == len(vert[ii]) // 3)

    # Return the data as a dictionary.
    data = {'vertices': vert,
            'UV': UV,
            'RGB': RGB,
            'width': width,
            'height': height}
    return data


def loadModelMesh(fname):
    data = loadModelAll(fname)
    del data['UV'], data['RGB'], data['width'], data['height']

    data['colors'] = []
    for vert in data['vertices']:
        # Create a random color vector. The alpha value is 1.0.
        col = np.random.rand(4 * (len(vert) // 3))
        col[3::4] = 1.0
        data['colors'].append(col.tolist())
    return data


if __name__ == '__main__':
    fname = 'models/pencil/pencil.obj'
    #fname = 'models/house/house.obj'
    #fname = "models/cube/Rubik's Cube.obj"

    data = loadModelAll(fname)
    data = loadModelMesh(fname)
