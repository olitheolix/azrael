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
import numpy as np
from azrael.types import FragDae, FragRaw, CollShapeMeta


def createFragDae():
    b = os.path.dirname(__file__)
    dae_file = open(b + '/cube.dae', 'rb').read()
    dae_rgb1 = open(b + '/rgb1.png', 'rb').read()
    dae_rgb2 = open(b + '/rgb2.jpg', 'rb').read()
    frag = FragDae(dae=dae_file,
                   rgb={'rgb1.png': dae_rgb1,
                        'rgb2.jpg': dae_rgb2})
    return frag


def createFragRaw():
    vert = np.random.randint(0, 100, 9).tolist()
    uv = np.random.randint(0, 100, 2).tolist()
    rgb = np.random.randint(0, 100, 3).tolist()
    return FragRaw(vert, uv, rgb)


def isEqualCS(la, lb):
    """
    fixme: docu, and probably a few tests.
    """
    for a, b in zip(la, lb):
        a = CollShapeMeta(*a)
        b = CollShapeMeta(*b)
        assert list(a.cshape) == list(b.cshape)
        for f in a._fields:
            assert list(getattr(a, f)) == list(getattr(b, f))
    return True
