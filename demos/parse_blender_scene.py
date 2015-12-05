"""
Parse the current Blender scene and write information about each object to a
JSON file. The information includes the BBox size for each object as well as
its position and orientation. In addition this script samples volume of each
object to create a volumetric point cloud that approximates the object.

Whoever loads the output file may compile an approximate collision shape
geometry from the BBoxes, or use the point cloud to eg define the geometry for
an FDTD scheme. Both are proof of concepts only to gauge the possibilities.

Usage:
  >> activate azrael
  >> blender sample.blend --background --python parse_blender_scene.py

Useful Blender API info:
  http://www.blender.org/api/blender_python_api_2_74_5/bpy.types.Object.html

Todo:
  - support Blender object hierarchies; not sure how Blender stores the child
    positions relative to their parent (look at 'obj.matrix_local' and
    'obj.matrix_parent' transform).
"""
import sys
import bpy
import json
import pickle
import subprocess
import numpy as np

# Blender module.
from mathutils import Vector

# Set the Python version string to the one for the current Anaconda
# environment. The reason is opaque but the IPython import below will
# fail otherwise. This hack seems unnecessary for any of the other imports.
version = subprocess.check_output(['python', '-c', 'import sys; print(sys.version)'])
sys.version = version.decode('utf8')
del version

# Now we can safely import IPython's 'embed' function.
from IPython import embed as ipshell


def is_inside(obj, src):
    """
    Return 1 if the point ``src`` is inside ``obj``.

    This function casts a ray from ``src`` to (almost) infinity and counts the
    number of intersections with faces from ``obj``. If this number is odd then
    ``src`` must be inside, otherwise outside.
    """
    # Create a random point far away.
    phi, theta = 2 * np.pi * np.random.rand(2)
    x = np.cos(phi) * np.cos(theta)
    y = np.sin(phi) * np.cos(theta)
    z = np.sin(theta)
    dst = 1000 * Vector([x, y, z])
    del phi, theta, x, y, z

    # Very short vector pointing along the ray.
    ofs = 0.0001 * (dst - src).normalized()

    # Count the number of faces that this ray intersects.
    face_idx = 0
    num_intersect = -1
    while (face_idx != -1):
        src, _, face_idx = obj.ray_cast(src + ofs, dst)
        num_intersect += 1

    return num_intersect % 2


def findInteriorPoints(obj):
    """
    Sample the BBox volume and determine interior points.
    """
    if obj.name != 'Cube':
        return

    # Create the sample points in each dimension to sample the BBox volume.
    N = 21
    dim = np.array(obj.dimensions, np.float64) / 2 + 0.5
    vec_x = np.linspace(-dim[0], dim[0], N)
    vec_y = np.linspace(-dim[1], dim[1], N)
    vec_z = np.linspace(-dim[2], dim[2], N)

    # Sample the BBox volume and determine for each point if it is actually
    # inside the object.
    out = np.zeros((len(vec_x) * len(vec_y) * len(vec_z), 3), np.float64)
    idx = 0
    for ix, vx in enumerate(vec_x):
        for iy, vy in enumerate(vec_y):
            for iz, vz in enumerate(vec_z):
                if is_inside(obj, Vector([vx, vy, vz])):
                    out[idx] = [vx, vy, vz]
                    idx += 1

    # Debug visualisation.
    if False:
        nz, tot = len(out.nonzero()[0]), np.prod(out.shape)
        print('#Nonzero: {} / {}  ({:.1f}%)'.format(nz, tot, 100 * nz / tot))
        tmp = {'vec_x': vec_x, 'vec_y': vec_y, 'vec_z': vec_z, 'out': out}
        pickle.dump(tmp, open('delme.pickle', 'wb'))
        subprocess.call(['python', 'show_volume.py'])
        sys.exit()

    # Return the list of interior point coordinates.
    out = out.round(3)
    return out.tolist()


def main():
    print()
    out = {}

    try:
        idx = sys.argv.index('--azrael')
        sys.argv.pop(idx)
        fname_out = sys.argv.pop(idx)
    except (ValueError, IndexError):
        print('Please provide the --azrael <fname> argument')
        return 1

    isDebug = False

    # Compile a dictionary of volumetric information about each object.
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue

        if isDebug:
            print('-----')
            print('Mesh: {}'.format(obj.name))

        # IMPORTANT: this must match with the rotation query. Set to
        # 'QUATERNION' if you use 'obj.rotation_quaternion' (see below). Set to
        # eg 'XYZ' if you use 'obj.rotation_euler'. Blender will _not_
        # automatically update all these variables; only the one for the
        # currently active rotation mode.
        obj.rotation_mode = 'QUATERNION'

        # Print collision shape info: type, scale, location, and rotation.
        if isDebug:
            print('  Scale: {}'.format(list(obj.scale)))
            print('  Position: {}'.format(list(obj.location)))
            print('  Rotation: {}'.format(list(obj.rotation_quaternion)))

        # Extract the mesh vertices (just for fun).
        if isDebug:
            mesh = obj.to_mesh(bpy.context.scene, True, 'PREVIEW')
            mesh.update()
            vert = list(mesh.vertices)
            vert = [_.undeformed_co for _ in vert]
            vert = [np.array(_) for _ in vert]
            print('  Found {} vertices'.format(len(vert)))
            print('    Example: ', vert[0].round(2))
            print('  BBox: ', np.array(obj.dimensions).round(2))

        transform = obj.matrix_world
        pos = transform.to_translation()
        q = transform.to_quaternion()
        rot = q[1:] + q[:1]

        # Compile data for this object that is relevant to Azrael.
        out[obj.name] = {
            'dimensions': np.array(obj.dimensions).tolist(),
            'transform': np.array(transform).tolist(),
            'pos': list(pos),
            'rot': list(rot),
            'interior_points': findInteriorPoints(obj),
        }
        del transform, pos, q, rot

    # Save the output to file.
    open(fname_out, 'wb').write(json.dumps(out).encode('utf8'))


if __name__ == '__main__':
    main()
