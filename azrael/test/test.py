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
import base64
import numpy as np

from azrael.types import FragmentMeta, FragDae, FragRaw
from azrael.types import CollShapeMeta, CollShapeEmpty, CollShapeSphere
from azrael.types import CollShapeBox, CollShapePlane
from azrael.types import RigidBodyState, RigidBodyStateOverride
from azrael.types import Constraint6DofSpring2, ConstraintP2P, ConstraintMeta
from azrael.types import _RigidBodyState


def getCSEmpty(aid='csempty', pos=[0, 0, 0], rot=[0, 0, 0, 1]):
    """
    Convenience function to construct an Empty shape.
    """
    return CollShapeMeta(aid, 'empty', pos, rot, CollShapeEmpty())


def getCSBox(aid='csbox', pos=[0, 0, 0], rot=[0, 0, 0, 1], dim=[1, 1, 1]):
    """
    Convenience function to construct a Box shape.
    """
    return CollShapeMeta(aid, 'box', pos, rot, CollShapeBox(*dim))


def getCSSphere(aid='cssphere', pos=[0, 0, 0], rot=[0, 0, 0, 1], radius=1):
    """
    Convenience function to construct a Sphere shape.
    """
    return CollShapeMeta(aid, 'sphere', pos, rot, CollShapeSphere(radius))


def getCSPlane(aid='csplane', pos=[0, 0, 0], rot=[0, 0, 0, 1],
               normal=[0, 0, 1], ofs=0):
    """
    Convenience function to construct a Plane in the x/y dimension.
    """
    return CollShapeMeta(aid, 'plane', pos, rot, CollShapePlane(normal, ofs))


def getFragDae():
    b = os.path.dirname(__file__)
    dae_file = open(b + '/cube.dae', 'rb').read()
    dae_rgb1 = open(b + '/rgb1.png', 'rb').read()
    dae_rgb2 = open(b + '/rgb2.jpg', 'rb').read()

    dae_file = base64.b64encode(dae_file).decode('utf8')
    dae_rgb1 = base64.b64encode(dae_rgb1).decode('utf8')
    dae_rgb2 = base64.b64encode(dae_rgb2).decode('utf8')
    frag = FragDae(dae=dae_file,
                   rgb={'rgb1.png': dae_rgb1,
                        'rgb2.jpg': dae_rgb2})
    return frag


def getFragRaw():
    vert = np.random.randint(0, 100, 9).tolist()
    uv = np.random.randint(0, 100, 6).tolist()
    rgb = np.random.randint(0, 100, 3).tolist()
    return FragRaw(vert, uv, rgb)


def getP2P(aid='constraint_p2p', rb_a=1, rb_b=2):
    """
    Return a Point2Point constraint for bodies ``rb_a`` and ``rb_b`.
    """
    pivot_a, pivot_b = (0, 0, -1), (0, 0, 1)
    p2p = ConstraintP2P(pivot_a, pivot_b)
    return ConstraintMeta(aid, 'p2p', rb_a, rb_b, p2p)


def get6DofSpring2(aid='constraint_6dofspring2', rb_a=1, rb_b=2):
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


def isEqualCS(la, lb):
    """
    fixme: docu, and probably a few tests.
    """
    for a, b in zip(la, lb):
        a = CollShapeMeta(*a)
        b = CollShapeMeta(*b)
        assert list(a.csdata) == list(b.csdata)
        for f in a._fields:
            assert list(getattr(a, f)) == list(getattr(b, f))
    return True


def isEqualBD(bd1: _RigidBodyState, bd2: _RigidBodyState):
    """
    Return *True* if the content of ``bd1`` is (roughly) equal to ``bd2``.

    This is a convenience function only.
    """
    for f in _RigidBodyState._fields:
        a, b = getattr(bd1, f), getattr(bd2, f)
        try:
            if f == 'cshapes':
                assert isinstance(bd1, (tuple, list))
                assert isinstance(bd2, (tuple, list))
                for csm_a, csm_b in zip(a, b):
                    tmp_a = CollShapeMeta(*csm_a)
                    tmp_b = CollShapeMeta(*csm_b)
                    tmp_a = tmp_a._replace(csdata=list(tmp_a.csdata))
                    tmp_b = tmp_b._replace(csdata=list(tmp_b.csdata))
                    tmp_a = tmp_a._replace(position=list(tmp_a.position))
                    tmp_b = tmp_b._replace(position=list(tmp_b.position))
                    tmp_a = tmp_a._replace(rotation=list(tmp_a.rotation))
                    tmp_b = tmp_b._replace(rotation=list(tmp_b.rotation))
                    tmp_a = list(tmp_a)
                    tmp_b = list(tmp_b)
                    assert tmp_a == tmp_b
            else:
                assert np.allclose(a, b, atol=1E-9)
        except (AssertionError, ValueError):
            return False
    return True
