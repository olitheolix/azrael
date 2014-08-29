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
import numpy as np

import azrael.parts as parts
import azrael.config as config
import azrael.protocol as protocol
import azrael.bullet.btInterface as btInterface
import azrael.bullet.bullet_data as bullet_data

from azrael.util import int2id, id2int
from azrael.test.test_leonard import killAzrael

ipshell = IPython.embed


def test_encoding_add_get_template(clientType='ZeroMQ'):
    """
    Test codec for {add,get}Template functions.
    """

    killAzrael()

    # Test parameters and constants.
    cs = bullet_data.BulletData().cshape
    geo = np.array([1, 2, 3], np.float64)
    b0 = parts.Booster(0, pos=np.zeros(3), orient=[0, 0, 1], max_force=0.5)
    b1 = parts.Booster(0, pos=np.zeros(3), orient=[1, 1, 0], max_force=0.6)
    f0 = parts.Factory(0, pos=np.zeros(3), orient=[0, 0, 1], speed=[0.1, 0.5])

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


def test_send_command():
    """
    Test codec for controlBooster command.
    """
    cmd_0 = parts.CmdBooster(partID=0, force=0.2)
    cmd_1 = parts.CmdBooster(partID=1, force=0.4)
    objID = int2id(1)

    enc = protocol.ToClerk_ControlParts_Encode
    dec = protocol.ToClerk_ControlParts_Decode
    ok, data = enc(objID, [cmd_0, cmd_1], [])
    assert ok

    ok, (out_objID, cmd_booster, cmd_factory) = dec(data)
    assert ok
    assert out_objID == objID
    assert len(cmd_booster) == 2
    assert len(cmd_factory) == 0

    # Use getattr to automatically test all attributes.
    assert cmd_booster[0] == cmd_0
    assert cmd_booster[1] == cmd_1

    print('Test passed')


def test_recvMsg():
    """
    Test codec for recvMsg command.
    """
    sender = int2id(5)
    msg = 'test'.encode('utf8')

    ok, aux = protocol.FromClerk_RecvMsg_Encode(sender, msg)
    assert ok
    ok, out = protocol.FromClerk_RecvMsg_Decode(aux)
    assert ok


def test_GetStateVariable():
    """
    Test codec for BulletData tuple.
    """
    objs = [bullet_data.BulletData(), bullet_data.BulletData()]
    objIDs = [int2id(1), int2id(2)]

    # ----------------------------------------------------------------------
    # Controller --> Clerk.
    # ----------------------------------------------------------------------
    ok, out = protocol.ToClerk_GetStateVariable_Encode(objIDs)
    assert ok
    assert isinstance(out, bytes)

    ok, (out_ids, ) = protocol.ToClerk_GetStateVariable_Decode(out)
    assert ok
    assert len(out_ids) == 2
    assert out_ids == objIDs

    # ----------------------------------------------------------------------
    # Clerk --> Controller.
    # ----------------------------------------------------------------------
    ok, out = protocol.FromClerk_GetStateVariable_Encode(objIDs, objs)
    assert ok
    assert isinstance(out, bytes)

    ok, out_sv = protocol.FromClerk_GetStateVariable_Decode(out)
    assert ok
    assert len(out_sv) == 2
    assert out_sv[int2id(1)] == objs[0]
    assert out_sv[int2id(2)] == objs[1]

    print('Test passed')


if __name__ == '__main__':
    test_GetStateVariable()
    test_recvMsg()
    test_send_command()
    test_encoding_add_get_template()
