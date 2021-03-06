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
This module does not contain any tests but utility functions often used in
other tests.
"""
import os
import json
import subprocess
import numpy as np
import azrael.leonard

from azrael.aztypes import FragMeta, Template
from azrael.aztypes import CollShapeMeta, CollShapeEmpty, CollShapeSphere
from azrael.aztypes import CollShapeBox, CollShapePlane, RigidBodyData
from azrael.aztypes import Constraint6DofSpring2, ConstraintP2P, ConstraintMeta

# List of Leonard/WorkerManager processes started as part of a test.
test_leo_procs = []


def killAzrael():
    # Kill all Azrael processes and delete all grids.
    subprocess.run(['pkill', 'Azreal:'], check=False)
    assert azrael.vectorgrid.deleteAllGrids().ok


def shutdownLeonard():
    """
    Terminate all WorkerManager instances and call Leonard's 'shutdown' method.

    This method works in tandem with 'getLeonard'.
    """
    for leo, wm in test_leo_procs:
        # Termiante the WorkerManager instance (if we event created one).
        if wm is not None:
            wm.terminate()
            wm.join()

        # Call Leonard' shutdown method.
        leo.shutdown()

    # Reset the list.
    test_leo_procs.clear()


def getLeonard(LeonardCls=azrael.leonard.LeonardBase):
    """
    Return a ``LeonardCls`` instance.

    This is a convenience function to reduce code duplication in tests.

    :param cls LeonardCls: Leonard class to instantiate.
    """
    # Return a Leonard instance.
    leo = LeonardCls()

    # Some Leonard classes rely on separate minion processes. For those classes
    # we will instantiate a WorkerManager.
    if LeonardCls == azrael.leonard.LeonardDistributedZeroMQ:
        wm = azrael.leonard.WorkerManager(
            numWorkers=3,
            minSteps=500,
            maxSteps=700,
            workerCls=azrael.leonard.LeonardWorkerZeroMQ
        )
        wm.start()
    else:
        wm = None

    # Add the currente Leonard and WorkerManager to the list. If the teardown
    # methods in the tests call the 'shutdownLeonard' function (see above) then
    # this takes care of cleanly terminating the processes (and closing the
    # sockets).
    test_leo_procs.append((leo, wm))
    leo.setup()
    return leo


def getCSEmpty(pos=[0, 0, 0], rot=[0, 0, 0, 1]):
    """
    Convenience function to construct an Empty shape.
    """
    return CollShapeMeta('empty', pos, rot, CollShapeEmpty())


def getCSBox(pos=[0, 0, 0], rot=[0, 0, 0, 1], dim=[1, 1, 1]):
    """
    Convenience function: return collision shape for Box.
    """
    return CollShapeMeta('box', pos, rot, CollShapeBox(*dim))


def getCSSphere(pos=[0, 0, 0], rot=[0, 0, 0, 1], radius=1):
    """
    Convenience function: return collision shape for Sphere.
    """
    return CollShapeMeta('sphere', pos, rot, CollShapeSphere(radius))


def getCSPlane(pos=[0, 0, 0], rot=[0, 0, 0, 1], normal=[0, 0, 1], ofs=0):
    """
    Convenience function: return collision shape for a Plane in the x/y
    dimension.
    """
    return CollShapeMeta('plane', pos, rot, CollShapePlane(normal, ofs))


def getFragRaw(scale=1, pos=(0, 0, 0), rot=(0, 0, 0, 1)):
    """
    Convenience function: return typical RAW fragment.
    """
    # Create a random RAW fragment.
    model = {
        'vert': np.random.randint(0, 100, 9).tolist(),
        'uv': np.random.randint(0, 100, 6).tolist(),
        'rgb': np.random.randint(0, 100, 3).tolist()
    }

    # Make it compatible with HTTP transport.
    model = json.dumps(model).encode('utf8')

    # Create a dictionary of all the files that constitute this model (RAW
    # models only have a single file called 'model.json').
    files = {'model.json': model}

    # Return the fragment description.
    return FragMeta(fragtype='RAW',
                    scale=scale,
                    position=pos,
                    rotation=rot,
                    files=files)


def getFragDae(scale=1, pos=(0, 0, 0), rot=(0, 0, 0, 1)):
    """
    Convenience function: return typical Collada fragment.
    """
    # Create a random Collada file and two textures.
    dae_file = bytes(np.random.randint(0, 100, 3).astype(np.uint8))
    dae_rgb1 = bytes(np.random.randint(0, 100, 3).astype(np.uint8))
    dae_rgb2 = bytes(np.random.randint(0, 100, 3).astype(np.uint8))

    # Create a dictionary of all the files that constitute this model.
    files = {
        'model.dae': dae_file,
        'rgb1.png': dae_rgb1,
        'rgb2.jpg': dae_rgb2,
    }

    return FragMeta(fragtype='DAE', scale=scale, position=pos,
                    rotation=rot, files=files)


def getP2P(aid='constraint_p2p', rb_a='1', rb_b='2',
           pivot_a=(0, 0, -1), pivot_b=(0, 0, 1)):
    """
    Return a Point2Point constraint for bodies ``rb_a`` and ``rb_b`.
    """
    p2p = ConstraintP2P(pivot_a, pivot_b)
    return ConstraintMeta(aid, 'p2p', rb_a, rb_b, p2p)


def get6DofSpring2(aid='constraint_6dofspring2', rb_a='1', rb_b='2'):
    """
    Return a 6DofSpring2 constraint for bodies ``rb_a`` and ``rb_b`.
    """
    dof = Constraint6DofSpring2(
        frameInA=(0, 0, 0, 0, 0, 0, 1),
        frameInB=(0, 0, 0, 0, 0, 0, 1),
        stiffness=(1, 2, 3, 4, 5.5, 6),
        damping=(2, 3.5, 4, 5, 6.5, 7),
        equilibrium=(-1, -1, -1, 0, 0, 0),
        linLimitLo=(-10.5, -10.5, -10.5),
        linLimitHi=(10.5, 10.5, 10.5),
        rotLimitLo=(-0.1, -0.2, -0.3),
        rotLimitHi=(0.1, 0.2, 0.3),
        bounce=(1, 1.5, 2),
        enableSpring=(True, False, False, False, False, False))
    return ConstraintMeta(aid, '6DOFSPRING2', rb_a, rb_b, dof)


def getRigidBody(scale: (int, float)=1,
                 imass: (int, float)=1,
                 restitution: (int, float)=0.9,
                 com: (tuple, list, np.ndarray)=(0, 0, 0),
                 inertia: (tuple, list, np.ndarray)=(1, 1, 1),
                 paxis: (tuple, list, np.ndarray)=(0, 0, 0, 1),
                 rotation: (tuple, list)=(0, 0, 0, 1),
                 position: (tuple, list, np.ndarray)=(0, 0, 0),
                 velocityLin: (tuple, list, np.ndarray)=(0, 0, 0),
                 velocityRot: (tuple, list, np.ndarray)=(0, 0, 0),
                 cshapes: dict={'cssphere': getCSSphere()},
                 linFactor: (tuple, list, np.ndarray)=(1, 1, 1),
                 rotFactor: (tuple, list, np.ndarray)=(1, 1, 1),
                 version: int=0):
    return RigidBodyData(
        scale, imass, restitution, com, inertia, paxis,
        rotation, position, velocityLin, velocityRot,
        cshapes, linFactor, rotFactor, version)


def getTemplate(name='template',
                rbs=None,
                fragments={},
                boosters={},
                factories={},
                custom=''):
    if rbs is None:
        rbs = getRigidBody(cshapes={'cssphere': getCSSphere()})

    return Template(name, rbs, fragments, boosters, factories, custom)
