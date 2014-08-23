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

import sys
import pytest
import IPython
import subprocess
import numpy as np

import azrael.types as types
import azrael.config as config
import azrael.protocol as protocol
import azrael.bullet.btInterface as btInterface

from azrael.util import int2id, id2int

ipshell = IPython.embed


def killall():
    subprocess.call(['pkill', 'killme'])


def test_encoding_add_get_template(clientType='ZeroMQ'):
    """
    The the {en,de}coding related to the {add,get}Template functions.
    """

    killall()
    
    # Test parameters and constants.
    cs = btInterface.defaultData().cshape
    geo = np.array([1,2,3], np.float64)
    b0 = types.booster(0, pos=np.zeros(3), orient=[0, 0, 1], max_force=0.5)
    b1 = types.booster(0, pos=np.zeros(3), orient=[1, 1, 0], max_force=0.6)
    f0 = types.factory(0, pos=np.zeros(3), orient=[0, 0, 1], speed=[0.1, 0.5])

    # ----------------------------------------------------------------------
    # Controller --> Clerk.
    # ----------------------------------------------------------------------
    ok, enc = protocol.ToClerk_GetTemplate_Encode(np.int64(1).tostring())
    ok, dec = protocol.ToClerk_GetTemplate_Decode(enc)
    assert dec[0] == np.int64(1).tostring()

    # ----------------------------------------------------------------------
    # Clerk --> Controller.
    # ----------------------------------------------------------------------
    ok, enc = protocol.FromClerk_GetTemplate_Encode(cs, geo, [b0, b1], [f0])
    ok, dec = protocol.FromClerk_GetTemplate_Decode(enc)
    assert np.array_equal(dec.cs, cs)
    assert np.array_equal(dec.geo, geo)
    assert len(dec.boosters) == 2
    assert len(dec.factories) == 1

    print('Test passed')


if __name__ == '__main__':
    test_encoding_add_get_template()
