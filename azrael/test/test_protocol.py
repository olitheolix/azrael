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
import azrael.protocol_json as json
import azrael.physics_interface as physAPI
import azrael.bullet.bullet_data as bullet_data

from azrael.test.test_clerk import killAzrael

ipshell = IPython.embed


def test_encoding_add_get_template(clientType='ZeroMQ'):
    """
    Test codec for {add,get}Template functions.
    """

    killAzrael()

    # Test parameters and constants.
    cs = np.array([1, 2, 3, 4], np.float64)
    vert = np.array([5, 6, 7, 8], np.float64)
    uv = np.array([9, 10], np.float64)
    rgb = np.array([1, 2, 250], np.uint8)
    aabb = float(1)

    b0 = parts.Booster(
        partID=0, pos=np.zeros(3), direction=[0, 0, 1], max_force=0.5)
    b1 = parts.Booster(
        partID=0, pos=np.zeros(3), direction=[1, 1, 0], max_force=0.6)
    f0 = parts.Factory(
        partID=0, pos=np.zeros(3), direction=[0, 0, 1],
        templateID='_templateCube'.encode('utf8'), exit_speed=[0.1, 0.5])

    # ----------------------------------------------------------------------
    # Client --> Clerk.
    # ----------------------------------------------------------------------
    # Encode source data.
    ok, enc = protocol.ToClerk_GetTemplate_Encode(np.int64(1).tostring())

    # Convert output to JSON and back (simulates the wire transmission).
    enc = json.loads(json.dumps(enc))

    # Decode the data.
    ok, dec = protocol.ToClerk_GetTemplate_Decode(enc)
    assert dec[0] == np.int64(1).tostring()

    # ----------------------------------------------------------------------
    # Clerk --> Client.
    # ----------------------------------------------------------------------
    # Encode source data.
    data = {'cshape': cs, 'vert': vert, 'uv': uv, 'rgb': rgb,
            'boosters': [b0, b1], 'factories': [f0], 'aabb': aabb}
    ok, enc = protocol.FromClerk_GetTemplate_Encode(data)

    # Convert output to JSON and back (simulates the wire transmission).
    enc = json.loads(json.dumps(enc))

    # Decode the data.
    dec = protocol.FromClerk_GetTemplate_Decode(enc)

    # Verify.
    assert dec.ok
    dec = dec.data
    assert np.array_equal(dec.cs, cs)
    assert np.array_equal(dec.vert, vert)
    assert np.array_equal(dec.uv, uv)
    assert np.array_equal(dec.rgb, rgb)
    assert len(dec.boosters) == 2
    assert len(dec.factories) == 1

    print('Test passed')


def test_send_command():
    """
    Test controlParts codec.
    """
    # Define the commands.
    cmd_0 = parts.CmdBooster(partID=0, force=0.2)
    cmd_1 = parts.CmdBooster(partID=1, force=0.4)
    cmd_2 = parts.CmdFactory(partID=0, exit_speed=0)
    cmd_3 = parts.CmdFactory(partID=2, exit_speed=0.4)
    cmd_4 = parts.CmdFactory(partID=3, exit_speed=4)
    objID = 1

    # ----------------------------------------------------------------------
    # Client --> Clerk.
    # ----------------------------------------------------------------------

    # Convenience.
    enc_fun = protocol.ToClerk_ControlParts_Encode
    dec_fun = protocol.ToClerk_ControlParts_Decode

    # Encode the booster- and factory commands.
    ok, enc = enc_fun(objID, [cmd_0, cmd_1], [cmd_2, cmd_3, cmd_4])
    assert ok

    # Convert output to JSON and back (simulates the wire transmission).
    enc = json.loads(json.dumps(enc))

    # Decode the data and verify the correct number of commands was returned.
    ok, (dec_objID, dec_booster, dec_factory) = dec_fun(enc)
    assert (ok, dec_objID) == (True, objID)
    assert len(dec_booster) == 2
    assert len(dec_factory) == 3

    # Use getattr to automatically test all attributes.
    assert dec_booster[0] == cmd_0
    assert dec_booster[1] == cmd_1
    assert dec_factory[0] == cmd_2
    assert dec_factory[1] == cmd_3
    assert dec_factory[2] == cmd_4

    # ----------------------------------------------------------------------
    # Clerk --> Client
    # ----------------------------------------------------------------------

    # Convenience.
    enc_fun = protocol.FromClerk_ControlParts_Encode
    dec_fun = protocol.FromClerk_ControlParts_Decode
    objIDs = [1, 2]

    # Encode source data.
    ok, enc = enc_fun(objIDs)
    assert ok

    # Convert output to JSON and back (simulates the wire transmission).
    enc = json.loads(json.dumps(enc))

    # Decode the data.
    ret = dec_fun(enc)
    assert (ret.ok, ret.data) == (True, objIDs)

    print('Test passed')


def test_GetStateVariable():
    """
    Test codec for BulletData tuple.
    """
    objs = [bullet_data.BulletData(), bullet_data.BulletData()]
    objIDs = [1, 2]

    # ----------------------------------------------------------------------
    # Client --> Clerk.
    # ----------------------------------------------------------------------
    # Encode source data.
    ok, enc = protocol.ToClerk_GetStateVariable_Encode(objIDs)

    # Convert output to JSON and back (simulates the wire transmission).
    enc = json.loads(json.dumps(enc))

    # Decode the data.
    ok, (dec_ids, ) = protocol.ToClerk_GetStateVariable_Decode(enc)
    assert (ok, len(dec_ids)) == (True, 2)

    # Verify.
    assert dec_ids == objIDs

    # ----------------------------------------------------------------------
    # Clerk --> Client.
    # ----------------------------------------------------------------------
    # Encode source data.
    data = dict(zip(objIDs, objs))
    ok, enc = protocol.FromClerk_GetStateVariable_Encode(data)

    # Convert output to JSON and back (simulates the wire transmission).
    enc = json.loads(json.dumps(enc))

    # Decode the data.
    dec_sv = protocol.FromClerk_GetStateVariable_Decode(enc)
    assert (dec_sv.ok, len(dec_sv.data)) == (True, 2)

    # Verify.
    dec_sv = dec_sv.data
    assert dec_sv[1] == objs[0]
    assert dec_sv[2] == objs[1]

    print('Test passed')


if __name__ == '__main__':
    test_GetStateVariable()
    test_send_command()
    test_encoding_add_get_template()
