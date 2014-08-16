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

import pytest
import numpy as np
import azrael.unpack as unpack
import azrael.config as config
import azrael.bullet.btInterface as btInterface

from azrael.util import int2id, id2int


def test_sendMsg():
    """
    Compile byte string and verify it unpacks correctly.
    """
    src, dst, data = int2id(2), int2id(3), 'blah'.encode('utf8')
    
    # Invalid command sequence because it misses sender- and destination ID.
    cmd = b''
    ok, msg = unpack.sendMsg(cmd)
    assert (ok, msg) == (False, 'Insufficient arguments')

    # Still invalid command sequence because it misses destination ID.
    cmd += src
    ok, msg = unpack.sendMsg(cmd)
    assert (ok, msg) == (False, 'Insufficient arguments')

    # Valid command sequence.
    cmd += dst + data
    ok, msg = unpack.sendMsg(cmd)
    assert (ok, msg) == (True, (src, dst, data))

    print('Test passed')


def test_recvMsg():
    """
    Compile byte string and verify it unpacks correctly.
    """
    # Our own object ID (made up for this test).
    objID = int2id(5)
    
    # Invalid command sequence because it misses our ID.
    ok, msg = unpack.recvMsg(b'')
    assert (ok, msg) == (False, 'Insufficient arguments')

    # Valid command sequence.
    ok, msg = unpack.recvMsg(objID)
    assert (ok, msg) == (True, (objID, ))

    print('Test passed')


def test_spawn():
    """
    Compile byte string and verify it unpacks correctly.
    """

    # Name of controller and its length in bytes.
    ctrl_name = 'Echo'.encode('utf8')
    ctrl_len = bytes([len(ctrl_name)])

    sv = btInterface.defaultData()
    sv_bin = btInterface.pack(sv).tostring()

    # Invalid command: misses length byte.
    ok, ret = unpack.spawn(b'')
    assert (ok, ret) == (False, 'Insufficient arguments')

    # Invalid command: has a length byte but it is invalid (too short).
    ok, ret = unpack.spawn(b'\01' + ctrl_name)
    assert (ok, ret) == (False, 'Invalid Payload Length')

    # Invalid command: has a length byte but it is also invalid (too long).
    ok, ret = unpack.spawn(b'\0A' + ctrl_name)
    assert (ok, ret) == (False, 'Invalid Payload Length')

    # Valid command sequence.
    templateID = np.int64(1).tostring()
    ok, ret = unpack.spawn(ctrl_len + ctrl_name + templateID + sv_bin)
    assert (ok, ret[:2]) == (True, (ctrl_name.decode('utf8'), templateID))

    # Verify that the SV data is intact.
    for idx in range(len(sv)):
        assert np.array_equal(ret[2][idx], sv[idx])

    print('Test passed')


def test_getSV():
    """
    Compile byte string and verify it unpacks correctly.
    """

    # Test parameters and constants.
    id_1, id_2 = int2id(1), int2id(2)

    ok, ret = unpack.getSV(b'')
    assert (ok, ret) == (False, 'Insufficient arguments')

    ok, ret = unpack.getSV(id_1 + b'\x01')
    assert (ok, ret) == (False, 'Not divisible by objID length')

    ok, ret = unpack.getSV(id_1)
    assert (ok, ret) == (True, ([id_1], ))

    ok, ret = unpack.getSV(id_1 + id_2)
    assert (ok, ret) == (True, ([id_1, id_2], ))

    print('Test passed')


def test_newTemplate():
    """
    Compile byte string and verify it unpacks correctly.
    """
    ok, ret = unpack.newTemplate(b'')
    assert (ok, ret) == (False, 'Insufficient arguments')

    print('Test passed')
    

def test_getGeometry():
    """
    Compile byte string and verify it unpacks correctly.
    """
    ok, ret = unpack.getGeometry(b'')
    assert (ok, ret) == (False, 'Insufficient arguments')

    print('Test passed')
    

def test_setForce():
    """
    Compile byte string and verify it unpacks correctly.
    """
    # Parameters and constants for this test.
    objID = int2id(0)
    force = np.array([1, 2, 3], np.float64)
    relpos = np.array([4, 5, 6], np.float64)

    # Insufficient parameters: missing ID, force, and rel position.
    ok, ret = unpack.setForce(b'')
    assert (ok, ret) == (False, 'Insufficient arguments')

    # Insufficient parameters: missing force and rel position.
    ok, ret = unpack.setForce(objID)
    assert (ok, ret) == (False, 'Insufficient arguments')

    # Insufficient parameters: missing rel position.
    ok, ret = unpack.setForce(objID + force.tostring())
    assert (ok, ret) == (False, 'Insufficient arguments')

    # Correct parameter format.
    ok, ret = unpack.setForce(objID + force.tostring() + relpos.tostring())
    objID_ret, force_ret, pos_ret = ret
    assert ok
    assert objID_ret == objID
    assert np.array_equal(pos_ret, pos_ret)
    assert np.array_equal(force_ret, force)

    print('Test passed')
    

def test_suggestPosition():
    """
    Compile byte string and verify it unpacks correctly.
    """
    # Parameters and constants for this test.
    objID = int2id(0)
    pos = np.array([4, 5, 6], np.float64)

    # Insufficient parameters: missing ID and force vector.
    ok, ret = unpack.suggestPos(b'')
    assert (ok, ret) == (False, 'Insufficient arguments')

    # Insufficient parameters: missing force vector.
    ok, ret = unpack.suggestPos(objID)
    assert (ok, ret) == (False, 'Insufficient arguments')

    # Correct byte stream.
    ok, (objID_ret, pos_ret) = unpack.suggestPos(objID + pos.tostring())
    assert ok
    assert objID == objID_ret
    assert np.array_equal(pos, pos_ret)
    
    print('Test passed')
    

if __name__ == '__main__':
    test_suggestPosition()
    test_setForce()
    test_newTemplate()
    test_getGeometry()
    test_sendMsg()
    test_recvMsg()
    test_spawn()
    test_getSV()
