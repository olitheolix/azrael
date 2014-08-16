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

"""
Test the Clerk only. Use a modified Controller to this end which allows to send
raw bytestrings to bypass all convenience wrappers that the Controller class
offers and test purely the Clerk.
"""

import sys
import time
import pytest
import IPython
import websocket
import subprocess
import numpy as np

import azrael.clerk
import azrael.types as types
import azrael.config as config
import azrael.clacks as clacks
import azrael.commands as commands
import azrael.wsclient as wsclient
import azrael.controller as controller
import azrael.bullet.btInterface as btInterface

from azrael.util import int2id, id2int

ipshell = IPython.embed


class ControllerTest(controller.ControllerBase):
    def testSend(self, data):
        """
        For testing only. Pass data verbatim to Clerk.
        """
        assert isinstance(data, bytes)
        self.sock_cmd.send(data)
        ret = self.sock_cmd.recv()
        if len(ret) == 0:
            return False, 'Invalid response from Clerk'

        if ret[0] == 0:
            return True, ret[1:]
        else:
            return False, ret[1:]


def killall():
    subprocess.call(['pkill', 'killme'])


def test_connect():
    """
    Connect to Clerk and make sure we get correct ID.
    """
    killall()

    # Start a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()

    # Instantiate a Controller and connect it the Clerk (would happen
    # automatically if we ran it as a process and called the 'run' method, but
    # for this test we will not start it as a separate process).
    ctrl = ControllerTest()
    ctrl.setupZMQ()
    ctrl.connectToClerk()
    assert ctrl.objID == int2id(1)

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()
    killall()

    print('Test passed')


def test_invalid():
    """
    Send an invalid command to the Clerk.
    """
    killall()

    # Start Clerk and instantiate a Controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerTest()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    # Send an invalid command and ensure Clerk returns an error code.
    ok, ret = ctrl.testSend(config.cmd['invalid_cmd'])
    assert (ok, ret) == (False, 'Invalid Command'.encode('utf8'))

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()
    killall()

    print('Test passed')


def test_ping():
    """
    Send a ping to the Clerk and check the response is correct.
    """
    killall()

    # Start Clerk and instantiate a Controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerTest()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    # Send the Ping command.
    ok, ret = ctrl.ping()
    assert (ok, ret) == (True, 'pong clerk'.encode('utf8'))

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()
    killall()

    print('Test passed')


def test_get_id():
    """
    Request a new ID for this controller.
    """
    killall()

    # Start Clerk and instantiate a Controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerTest()
    ctrl.setupZMQ()

    # Request new IDs. It must increase with every request, starting at 1.
    for ii in range(3):
        objID = ctrl.connectToClerk()
        assert objID == int2id(ii + 1)

        # Clear the objID as the `connectToClerk` method will otherwise not
        # request a new one.
        ctrl.objID = None

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()
    killall()

    print('Test passed')


def test_send_receive_message():
    """
    Try to send a message to a random controller ID. The ID itself does not
    matter because the Clerk silently drops messages for non-existing
    controllers.
    """
    killall()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)

    # Test parameters.
    src, dst, data = int2id(5), int2id(10), 'blah'.encode('utf8')
    
    # Retrieve a non-existing message.
    ok, msg = clerk.recvMessage(src)
    assert (ok, msg) == (True, b'')

    # Dispatch a message.
    ok, msg = clerk.sendMessage(src, dst, data)
    assert ok

    # Attempt to retrieve it with the wrong 'dst' -- we must get nothing.
    ok, msg = clerk.recvMessage(src)
    assert (ok, msg) == (True, b'')

    # Now retrieve it with the correct ID, and the retrieve it once more to
    # ensure that the same message is not delivered twice.
    ok, msg = clerk.recvMessage(dst)
    assert (ok, msg) == (True, src + data)
    ok, msg = clerk.recvMessage(dst)
    assert (ok, msg) == (True, b'')

    print('Test passed')


def test_spawn():
    """
    Test the 'spawn' command in the Clerk.
    """
    killall()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)

    # Test parameters (the 'Echo' controller is a hard coded dummy controller
    # that is always available).
    sv = btInterface.defaultData()
    ctrl_name = 'Echo'

    # Unknown controller name.
    templateID = np.int64(1).tostring()
    ok, ret = clerk.spawn('aaaa', templateID, sv)
    assert (ok, ret) == (False, 'Unknown Controller Name')

    # Invalid templateID.
    templateID = np.int64(100).tostring()
    ok, ret = clerk.spawn(ctrl_name, templateID, sv)
    assert (ok, ret) == (False, 'Invalid Template ID')

    # All parameters are now valid. We must be assigne ID=1 because this is the
    # first ID in an otherwise pristine system.
    templateID = np.int64(1).tostring()
    ok, ret = clerk.spawn('Echo', templateID, sv)
    assert (ok, ret) == (True, int2id(1))

    print('Test passed')


def test_get_statevar():
    """
    Test the 'get_statevar' command in the Clerk.
    """
    killall()

    # Test parameters and constants.
    ctrl_name = 'Echo'
    objID_1 = int2id(1)
    objID_2 = int2id(2)
    sv_1 = btInterface.defaultData(position=np.arange(3), vlin=[2, 4, 6])
    sv_2 = btInterface.defaultData(position=[2, 4, 6], vlin=[6, 8, 10])
    templateID = np.int64(1).tostring()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)
    
    # Retrieve the SV for a non-existing ID.
    ok, ret = clerk.getStateVariables([int2id(10)])
    assert (ok, ret) == (False, 'One or more IDs do not exist')

    # Spawn a new object. It must have ID=1.
    ok, ret = clerk.spawn(ctrl_name, templateID, sv_1)
    assert (ok, ret) == (True, objID_1)

    # Retrieve the SV for a non-existing ID --> must fail.
    ok, ret = clerk.getStateVariables([int2id(10)])
    assert (ok, ret) == (False, 'One or more IDs do not exist')

    # Retrieve the SV for the existing ID=1.
    ok, ret = clerk.getStateVariables([objID_1])
    assert (ok, ret[:config.LEN_ID]) == (True, objID_1)

    # Verify the SV data.
    ret_sv = btInterface.unpack(np.fromstring(ret[config.LEN_ID:]))
    for ii in range(len(sv_1)):
        assert np.array_equal(ret_sv[ii], sv_1[ii])

    # Spawn a second object.
    ok, ret = clerk.spawn(ctrl_name, templateID, sv_2)
    assert (ok, ret) == (True, objID_2)
    
    # Retrieve the state variables for both objects.
    for objID, ref_sv in zip([objID_1, objID_2], [sv_1, sv_2]):
        ok, ret = clerk.getStateVariables([objID])
        assert (ok, ret[:config.LEN_ID]) == (True, objID)

        ret_sv = btInterface.unpack(np.fromstring(ret[config.LEN_ID:]))
        for ii in range(len(sv_1)):
            assert np.array_equal(ret_sv[ii], ref_sv[ii])

    print('Test passed')


def test_create_new_template_object():
    """
    Create a new objects template.
    """
    killall()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)

    # Request geometry of a non-existing object.
    ok, ret = clerk.getGeometry(np.int64(200).tostring())
    assert (ok, ret) == (False, 'ID does not exist')

    # Request geometry of an existing default object. This particular object
    # has no geometry.
    id_2 = np.int64(1).tostring()
    ok, ret = clerk.getGeometry(id_2)
    assert (ok, ret) == (True, b'')

    # Define a new raw object. The geometry data is arbitrary but its length
    # must be divisible by 9.
    geo_0_ref = bytes(range(0, 9))
    cs_0_ref = np.array([1, 1, 1, 1]).tostring()
    ok, id_3 = clerk.newTemplate(cs_0_ref, geo_0_ref)
    assert ok

    # Query the new object.
    ok, ret = clerk.getGeometry(id_3)
    assert (ok, ret) == (True, geo_0_ref)
    
    # Attempt to insert an object with a geometry that is not an integer
    # multiple of 9.
    geo_0_ref = bytes(range(0, 5))
    cs_0_ref = np.array([1, 1, 1, 1]).tostring()
    ok, id_3 = clerk.newTemplate(cs_0_ref, geo_0_ref)
    assert not ok

    print('Test passed')


def test_set_force():
    """
    The logic for the 'set_force' and 'suggest_pos' commands are
    identical. Therefore test them both with a single function here.
    """
    killall()

    # Parameters and constants for this test.
    id_1 = int2id(1)
    sv = btInterface.defaultData()
    force = np.array([1, 2, 3], np.float64)
    relpos = np.array([4, 5, 6], np.float64)

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)

    # Invalid/non-existing ID.
    ok, ret = clerk.setForce(int2id(0), force, relpos)
    assert (ok, ret) == (False, 'ID does not exist')

    # Spawn a new object. It must have ID=1.
    templateID = np.int64(1).tostring()
    ok, ret = clerk.spawn('Echo', templateID, sv)
    assert (ok, ret) == (True, id_1)

    # Invalid/non-existing ID.
    ok, ret = clerk.setForce(id_1, force, relpos)
    assert (ok, ret) == (True, '')

    print('Test passed')


def test_suggest_position():
    """
    The logic for the 'set_force' and 'suggest_pos' commands are
    identical. Therefore thest them both with a single function here.
    """
    killall()

    # Parameters and constants for this test.
    id_1 = int2id(1)
    sv = btInterface.defaultData()
    force = np.array([1, 2, 3], np.float64)
    templateID = np.int64(1).tostring()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)

    # Invalid/non-existing ID.
    ok, ret = clerk.suggestPosition(int2id(0), force)
    assert (ok, ret) == (False, 'ID does not exist')

    # Spawn a new object. It must have ID=1.
    ok, ret = clerk.spawn('Echo', templateID, sv)
    assert (ok, ret) == (True, id_1)

    # Invalid/non-existing ID.
    ok, ret = clerk.suggestPosition(id_1, force)
    assert (ok, ret) == (True, '')

    print('Test passed')


def test_create_fetch_template():
    """
    Add a new object to the templateID DB and query it again.
    """
    killall()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)

    # Request and invalid ID.
    ok, out = clerk.getTemplate('blah'.encode('utf8'))
    assert not ok

    # Clerk has a few default objects. This one has no collision shape...
    ok, out = clerk.getTemplate(np.int64(1).tostring())
    assert ok
    assert out[0] == np.array([0, 1, 1, 1], np.float64).tostring()

    # ... this one is a sphere...
    ok, out = clerk.getTemplate(np.int64(2).tostring())
    assert ok
    assert out[0] == np.array([3, 1, 1, 1], np.float64).tostring()

    # ... and this one is a cube.
    ok, out = clerk.getTemplate(np.int64(3).tostring())
    assert ok
    assert out[0] == np.array([4, 1, 1, 1], np.float64).tostring()

    # Add a new object template.
    cs = np.array([1, 2, 3, 4], np.float64).tostring()
    geo = np.array([5, 6, 7, 8], np.float64).tostring()
    ok, templateID = clerk.addTemplate(cs, geo, [], [])

    # Fetch the just added template again.
    ok, out = clerk.getTemplate(templateID)
    assert ok
    assert out[0] == np.array([1, 2, 3, 4], np.float64).tostring()
    assert out[1] == np.array([5, 6, 7, 8], np.float64).tostring()

    # Define a new object with two boosters and one factory unit.
    # The 'boosters' and 'factories' arguments are a list of named
    # tuples. Their first argument is the unit ID (Azrael does not assign
    # automatically assign any IDs).
    cs = np.array([1, 2, 3, 4], np.float64).tostring()
    geo = np.array([5, 6, 7, 8], np.float64).tostring()
    b0 = types.booster(0, pos=np.zeros(3), orient=[0, 0, 1], max_force=0.5)
    b1 = types.booster(1, pos=np.zeros(3), orient=[0, 0, 1], max_force=0.5)
    f0 = types.factory(0, pos=np.zeros(3), orient=[0, 0, 1], speed=[0.1, 0.5])

    # Add the new template.
    ok, templateID = clerk.addTemplate(cs, geo, [b0, b1], [f0])

    # Retrieve the just created object and verify the CS and geometry.
    ok, out = clerk.getTemplate(templateID)
    assert ok
    assert np.array_equal(out[0], cs)
    assert np.array_equal(out[1], geo)

    # The template must also feature two boosters and one factory.
    assert len(out[2]) == 2
    assert len(out[3]) == 1

    # Explicitly verify the booster- and factory units. The easisest (albeit
    # not most readable) way to do the comparison is to convert the unit
    # descriptions (which are named tuples) to byte strings and compare those.
    out_boosters = [types.booster_tostring(_) for _ in out[2]]
    out_factories = [types.factory_tostring(_) for _ in out[3]]
    assert types.booster_tostring(b0) in out_boosters
    assert types.booster_tostring(b1) in out_boosters
    assert types.factory_tostring(f0) in out_factories

    print('Test passed')


def test_get_raw_object_id():
    """
    Spawn two objects from different templates. Then query the template ID
    based on the object ID.
    """
    killall()

    # Parameters and constants for this test.
    id_0, id_1 = int2id(1), int2id(2)
    templateID_0, templateID_1 = np.int64(1).tostring(), np.int64(3).tostring()
    sv = btInterface.defaultData()
    
    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)

    # Spawn a new object. It must have ID=1.
    ok, ctrl_id = clerk.spawn('Echo', templateID_0, sv)
    assert (ok, ctrl_id) == (True, id_0)

    # Spawn another object from a different template.
    ok, ctrl_id = clerk.spawn('Echo', templateID_1, sv)
    assert (ok, ctrl_id) == (True, id_1)

    # Retrieve template of first object.
    ok, ret = clerk.getTemplateID(id_0)
    assert (ok, ret) == (True, templateID_0)
    
    # Retrieve template of second object.
    ok, ret = clerk.getTemplateID(id_1)
    assert (ok, ret) == (True, templateID_1)
    
    # Attempt to retrieve a non-existing object.
    ok, ret = clerk.getTemplateID(int2id(100))
    assert not ok

    # Shutdown.
    killall()

    print('Test passed')


def test_processControlCommand():
    """
    Create an object with some boosters and factories and send control
    commands to them.
    """
    killall()
    
    # Parameters and constants for this test.
    objID_1, objID_2 = int2id(1), int2id(2)
    templateID_1 = np.int64(1).tostring()
    sv = btInterface.defaultData()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)

    # Create a fake object. We will not need it but for this test one must
    # exist as other commands would otherwise fail.
    ok, ctrl_id = clerk.spawn('Echo', templateID_1, sv)
    assert (ok, ctrl_id) == (True, objID_1)

    # Create booster control command.
    cmd_0 = commands.controlBooster(unitID=0, force=0.2)
    cmd = commands.serialiseCommands(objID_1, [cmd_0], [])

    # Call processControlCommands. It must fail because the default object has
    # no booster.
    ok, msg = clerk.processControlCommand(cmd)
    assert not ok

    # ------------------------------------------------------------------------
    # Now repeat the test with an object that actually contains a booster.
    # ------------------------------------------------------------------------

    # Define a new object with two boosters and one factory unit.
    # The 'boosters' and 'factories' arguments are a list of named
    # tuples. The first argument to these tuples is the ID that will
    # be assigned to the unit (the user can choose that number; Azrael
    # will automatically enumerate them in any way).
    cs = np.array([1, 2, 3, 4], np.float64).tostring()
    geo = np.array([5, 6, 7, 8], np.float64).tostring()
    b0 = types.booster(0, pos=np.zeros(3), orient=[1, 0, 0], max_force=0.5)
    b1 = types.booster(1, pos=np.zeros(3), orient=[0, 1, 0], max_force=0.5)
    f0 = types.factory(0, pos=np.zeros(3), orient=[0, 0, 1], speed=[0.1, 0.5])

    # Add it to Azrael and spawn an instance.
    ok, templateID_2 = clerk.addTemplate(cs, geo, [b0, b1], [f0])
    ok, ctrl_id = clerk.spawn('Echo', templateID_2, sv)
    assert (ok, ctrl_id) == (True, objID_2)
    
    # Call processControlCommands. It must fail because the default object has
    # no booster.
    cmd_0 = commands.controlBooster(unitID=0, force=0.2)
    cmd_1 = commands.controlBooster(unitID=1, force=0.4)
    cmd = commands.serialiseCommands(objID_2, [cmd_0, cmd_1], [])
    ok, msg = clerk.processControlCommand(cmd)
    assert ok

    # Make sure the force got updated (only check the central force).
    ok, force, torque = btInterface.getForceAndTorque(objID_2)
    assert ok
    assert np.array_equal(force, [0.2, 0.4, 0])

    killall()
    print('Test passed')
    

def test_get_all_objectids():
    """
    Test getAllObjects.
    """
    killall()
    
    # Parameters and constants for this test.
    objID_1, objID_2 = int2id(1), int2id(2)
    templateID = np.int64(1).tostring()
    sv = btInterface.defaultData()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)

    # So far no objects have been spawned.
    ok, out = clerk.getAllObjectIDs()
    assert (ok, out) == (True, b'')

    # Spawn a new object.
    ok, ret = clerk.spawn('Echo', templateID, sv)
    assert (ok, ret) == (True, objID_1)
    
    # The object list must now contain the ID of the just spawned object.
    ok, out = clerk.getAllObjectIDs()
    assert (ok, out) == (True, objID_1)

    # Spawn another object.
    ok, ret = clerk.spawn('Echo', templateID, sv)
    assert (ok, ret) == (True, objID_2)

    # The object list must now contain the ID of both spawned objects.
    ok, out = clerk.getAllObjectIDs()
    assert (ok, out) == (True, objID_1 + objID_2)

    # Kill all spawned Controller processes.
    killall()

    print('Test passed')

    
if __name__ == '__main__':
    test_get_all_objectids()
    test_processControlCommand()
    test_get_raw_object_id()
    test_get_statevar()
    test_spawn()
    test_create_fetch_template()
    test_set_force()
    test_suggest_position()
    test_create_new_template_object()
    test_send_receive_message()
    test_connect()
    test_ping()
    test_invalid()
    test_get_id()
