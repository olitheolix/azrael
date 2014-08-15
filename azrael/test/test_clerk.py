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
            return 'Invalid response from Clerk', False

        if ret[0] == 0:
            return ret[1:], True
        else:
            return ret[1:], False


def killall():
    subprocess.call(['pkill', 'killme'])


def test_connect():
    """
    Connect to Clerk and make sure we get correct ID.
    """
    killall()

    # Start Clerk.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()

    ctrl = ControllerTest()
    ctrl.setupZMQ()
    ctrl.connectToClerk()
    assert ctrl.objID == int2id(1)

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()
    print('Test passed')


def test_invalid():
    """
    Send a ping to the Clerk and check the response is correct.
    """
    killall()

    # Start Clerk and instantiate controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerTest()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    ret, ok = ctrl.testSend(config.cmd['invalid_cmd'])
    assert not ok
    assert ret == 'Invalid Command'.encode('utf8')

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()
    print('Test passed')


def test_ping():
    """
    Send a ping to the Clerk and check the response is correct.
    """
    killall()

    # Start Clerk and instantiate controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerTest()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    ret, ok = ctrl.testSend(config.cmd['ping_clerk'])
    assert ok
    assert ret == 'pong clerk'.encode('utf8')

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()
    print('Test passed')


def test_get_id():
    """
    Request a new ID for this controller.
    """
    killall()

    # Start Clerk and instantiate controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerTest()
    ctrl.setupZMQ()

    # Request new IDs. It must increase with every request, starting at 1.
    for ii in range(3):
        ret, ok = ctrl.testSend(config.cmd['get_id'])
        assert ok
        assert ret == int2id(ii + 1)

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()
    print('Test passed')


def test_send_message():
    """
    Try to send a message to a random controller ID. The ID itself does not
    matter because the Clerk silently drops messages for non-existing
    controllers.
    """
    killall()

    # Start Clerk and instantiate controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerTest()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    # Invalid command sequence because it misses sender- and destination ID.
    cmd = config.cmd['send_msg']
    ret, ok = ctrl.testSend(cmd)
    assert (ok, ret) == (False, 'Insufficient arguments'.encode('utf8'))

    # Still invalid command sequence because it misses destination ID.
    cmd += int2id(2)
    ret, ok = ctrl.testSend(cmd)
    assert (ok, ret) == (False, 'Insufficient arguments'.encode('utf8'))

    # Valid command sequence.
    cmd += int2id(2) + 'blah'.encode('utf8')
    ret, ok = ctrl.testSend(cmd)
    assert (ok, ret) == (True, b'')

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()
    print('Test passed')


def test_get_message():
    """
    Test the 'get_msg' command in the Clerk.
    """
    killall()

    # Start Clerk and instantiate controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerTest()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    # Invalid command sequence because it misses ID of controller for which we
    # want to fetch a message.
    ret, ok = ctrl.testSend(config.cmd['get_msg'])
    assert (ok, ret) == (False, 'Insufficient arguments'.encode('utf8'))

    # Valid command. Must return an empty message because none has been
    # posted for the object yet.
    ret, ok = ctrl.testSend(config.cmd['get_msg'] + int2id(1))
    assert (ok, ret) == (True, b'')

    # Post a message for ID 1.
    src, dst = int2id(1), int2id(2)
    cmd = config.cmd['send_msg']
    cmd += src + dst + 'blah'.encode('utf8')
    ret, ok = ctrl.testSend(cmd)
    assert (ok, ret) == (True, b'')

    # Fetch the just posted message.
    ret, ok = ctrl.testSend(config.cmd['get_msg'] + dst)
    assert (ok, ret) == (True, src + 'blah'.encode('utf8'))

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()
    print('Test passed')


def test_spawn():
    """
    Test the 'spawn' command in the Clerk.
    """
    killall()

    # Start Clerk and instantiate controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerTest()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    # Name of controller and its length in bytes.
    ctrl_name = 'Echo'.encode('utf8')
    ctrl_len = bytes([len(ctrl_name)])

    sv = btInterface.defaultData()
    sv = btInterface.pack(sv).tostring()

    # Invalid command: misses length byte.
    ret, ok = ctrl.testSend(config.cmd['spawn'])
    assert (ok, ret) == (False, 'Insufficient arguments'.encode('utf8'))

    # Invalid command: has a length byte but it does not match the name.
    payload = b'\01' + ctrl_name
    ret, ok = ctrl.testSend(config.cmd['spawn'] + payload)
    assert (ok, ret) == (False, 'Invalid Payload Length'.encode('utf8'))

    # Invalid command: has a length byte but it does not match the name.
    payload = b'\0A' + ctrl_name
    ret, ok = ctrl.testSend(config.cmd['spawn'] + payload)
    assert (ok, ret) == (False, 'Invalid Payload Length'.encode('utf8'))

    # Valid command but unknown name.
    objdescid = np.int64(1).tostring()
    payload = ctrl_len + 'aaaa'.encode('utf8') + objdescid + sv
    ret, ok = ctrl.testSend(config.cmd['spawn'] + payload)
    assert (ok, ret) == (False, 'Unknown Controller Name'.encode('utf8'))

    # Valid command but objdescid does not denote an existing object.
    objdescid = np.int64(100).tostring()
    payload = ctrl_len + ctrl_name + objdescid + sv
    ret, ok = ctrl.testSend(config.cmd['spawn'] + payload)
    assert (ok, ret) == (False, 'Invalid Raw Object ID'.encode('utf8'))

    # Valid command and name. The returned ID must be ID=2 because ID=0 is
    # invalid and ID=1 was already handed out to the 'ctrl' object.
    objdescid = np.int64(1).tostring()
    payload = ctrl_len + ctrl_name + objdescid + sv
    ret, ok = ctrl.testSend(config.cmd['spawn'] + payload)
    assert (ok, ret) == (True, int2id(2))

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()
    print('Test passed')


def test_get_statevar():
    """
    Test the 'get_statevar' command in the Clerk.
    """
    killall()

    # Start Clerk and instantiate controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerTest()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    ctrl_name = 'Echo'.encode('utf8')
    ctrl_len = bytes([len(ctrl_name)])

    # Insufficient parameters.
    ret, ok = ctrl.testSend(config.cmd['get_statevar'])
    assert (ok, ret) == (False, 'Insufficient arguments'.encode('utf8'))

    # Retrieve the SV for a non-existing ID.
    ret, ok = ctrl.testSend(config.cmd['get_statevar'] + int2id(10))
    assert (ok, ret) == (False, 'ID does not exist'.encode('utf8'))

    # Retrieve the SV of all objects. Must still be empty because we have not
    # spawned any yet.
    ret, ok = ctrl.testSend(config.cmd['get_statevar'] + int2id(0))
    assert (ok, ret) == (True, b'')

    # Spawn a new object. The returned ID must be ID=2 because ID=0 is
    # invalid and ID=1 was already handed out to the 'ctrl' object.
    id_2 = int2id(2)
    sv2 = btInterface.defaultData(position=np.arange(3), vlin=[2, 4, 6])
    sv2 = btInterface.pack(sv2).tostring()
    objdesc = np.int64(1).tostring()
    payload = ctrl_len + ctrl_name + objdesc + sv2
    ret, ok = ctrl.testSend(config.cmd['spawn'] + payload)
    assert (ok, ret) == (True, id_2)

    # Retrieve the SV for a non-existing ID.
    ret, ok = ctrl.testSend(config.cmd['get_statevar'] + int2id(10))
    assert (ok, ret) == (False, 'ID does not exist'.encode('utf8'))

    # Retrieve the SV for ID=2.
    ret, ok = ctrl.testSend(config.cmd['get_statevar'] + id_2)
    assert (ok, ret) == (True, id_2 + sv2)

    # Retrieve the SV of all objects. Must return the same as previous call
    # since there is only one object yet.
    ret, ok = ctrl.testSend(config.cmd['get_statevar'] + int2id(0))
    assert (ok, ret) == (True, id_2 + sv2)

    # Spawn a second object and retrieve all state variables.
    id_3 = int2id(3)
    sv3 = btInterface.defaultData(position=[2, 4, 6], vlin=[6, 8, 10])
    sv3 = btInterface.pack(sv3).tostring()
    payload = ctrl_len + ctrl_name + objdesc + sv3
    ret, ok = ctrl.testSend(config.cmd['spawn'] + payload)
    assert (ok, ret) == (True, id_3)

    # There must be two state vectors, each of which is preceed by the object
    # ID.
    ret, ok = ctrl.testSend(config.cmd['get_statevar'] + int2id(0))
    assert ok
    assert len(ret) == 2 * len(sv2) + 2 * config.LEN_ID

    # Make sure both state vectors were returned exactly once.
    t0, t1 = ret[config.LEN_ID + len(sv2):], ret[:config.LEN_ID + len(sv2)]
    if t0[:config.LEN_ID] == id_2:
        t0 = t0[:config.LEN_ID], t0[config.LEN_ID:]
        assert t0 == (id_2, sv2)
        t1 = t1[:config.LEN_ID], t1[config.LEN_ID:]
        assert t1 == (id_3, sv3)
    elif t0[:config.LEN_ID] == id_3:
        t0 = t0[:config.LEN_ID], t0[config.LEN_ID:]
        assert t0 == (id_3, sv3)
        t1 = t1[:config.LEN_ID], t1[config.LEN_ID:]
        assert t1 == (id_2, sv2)
    else:
        assert False

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()
    print('Test passed')


def test_create_new_raw_object():
    """
    Create new raw objects.
    """
    killall()

    # Start Clerk and instantiate controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerTest()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    # Insufficient parameters.
    ret, ok = ctrl.testSend(config.cmd['new_raw_object'])
    assert (ok, ret) == (False, 'Insufficient arguments'.encode('utf8'))

    # Insufficient parameters.
    ret, ok = ctrl.testSend(config.cmd['get_geometry'])
    assert (ok, ret) == (False, 'Insufficient arguments'.encode('utf8'))

    # Request geometry of non-existing object.
    id_2 = np.int64(200).tostring()
    ret, ok = ctrl.testSend(config.cmd['get_geometry'] + id_2)
    assert (ok, ret) == (False, 'ID does not exist'.encode('utf8'))

    # Request geometry of an existing default object. This particular object
    # has no geometry.
    id_2 = np.int64(1).tostring()
    ret, ok = ctrl.testSend(config.cmd['get_geometry'] + id_2)
    assert (ok, ret) == (True, b'')

    # Define a new raw object. The geometry data is arbitrary but its length
    # must be divisible by 9.
    geo_0_ref = bytes(range(0, 9))
    cs_0_ref = np.array([1, 1, 1, 1]).tostring()
    id_3, ok = ctrl.testSend(config.cmd['new_raw_object'] + cs_0_ref + geo_0_ref)
    assert ok

    # Query the new object.
    ret, ok = ctrl.testSend(config.cmd['get_geometry'] + id_3)
    assert (ok, ret) == (True, geo_0_ref)
    
    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()
    print('Test passed')


def test_set_force():
    """
    The logic for the 'set_force' and 'suggest_pos' commands are
    identical. Therefore test them both with a single function here.
    """
    killall()

    # Start Clerk and instantiate controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerTest()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    # Specify force and relative position of the force.
    force = np.array([1, 2, 3], np.float64)
    relpos = np.array([4, 5, 6], np.float64)

    # Insufficient parameters: missing ID, force, and rel position.
    ret, ok = ctrl.testSend(config.cmd['set_force'])
    assert (ok, ret) == (False, 'Insufficient arguments'.encode('utf8'))

    # Insufficient parameters: missing force and rel position.
    ret, ok = ctrl.testSend(config.cmd['set_force'] + int2id(0))
    assert (ok, ret) == (False, 'Insufficient arguments'.encode('utf8'))

    # Insufficient parameters: missing rel position.
    ret, ok = ctrl.testSend(config.cmd['set_force'] + int2id(0) + force.tostring())
    assert (ok, ret) == (False, 'Insufficient arguments'.encode('utf8'))

    # Invalid/non-existing ID.
    cmd = int2id(0) + force.tostring() + relpos.tostring()
    ret, ok = ctrl.testSend(config.cmd['set_force'] + cmd)
    assert (ok, ret) == (False, 'ID does not exist'.encode('utf8'))

    # Spawn a new object. The returned ID must be ID=2 because ID=0 is
    # invalid and ID=1 was already handed out to the 'ctrl' object.
    id_2 = int2id(2)
    sv2 = np.arange(6).astype(np.float64).tostring()
    sv2 = btInterface.defaultData()
    sv2 = btInterface.pack(sv2).tostring()
    objdesc = np.int64(1).tostring()
    payload = bytes([4]) + 'Echo'.encode('utf8') + objdesc + sv2
    ret, ok = ctrl.testSend(config.cmd['spawn'] + payload)
    assert (ok, ret) == (True, id_2)

    # Invalid/non-existing ID.
    cmd = id_2 + force.tostring() + relpos.tostring()
    ret, ok = ctrl.testSend(config.cmd['set_force'] + cmd)
    assert (ok, ret) == (True, b'')

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()
    print('Test passed')


def test_suggest_position():
    """
    The logic for the 'set_force' and 'suggest_pos' commands are
    identical. Therefore thest them both with a single function here.
    """
    killall()

    # Start Clerk and instantiate controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerTest()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    # Insufficient parameters: missing ID and force vector.
    ret, ok = ctrl.testSend(config.cmd['suggest_pos'])
    assert (ok, ret) == (False, 'Insufficient arguments'.encode('utf8'))

    # Insufficient parameters: missing force vector.
    ret, ok = ctrl.testSend(config.cmd['suggest_pos'] + int2id(0))
    assert (ok, ret) == (False, 'Insufficient arguments'.encode('utf8'))

    # Invalid/non-existing ID.
    force = np.array([1, 2, 3], np.float64).tostring()
    ret, ok = ctrl.testSend(config.cmd['suggest_pos'] + int2id(0) + force)
    assert (ok, ret) == (False, 'ID does not exist'.encode('utf8'))

    # Spawn a new object. The returned ID must be ID=2 because ID=0 is
    # invalid and ID=1 was already handed out to the 'ctrl' object.
    id_2 = int2id(2)
    sv2 = btInterface.defaultData()
    sv2 = btInterface.pack(sv2).tostring()
    objdesc = np.int64(1).tostring()
    payload = bytes([4]) + 'Echo'.encode('utf8') + objdesc + sv2
    ret, ok = ctrl.testSend(config.cmd['spawn'] + payload)
    assert (ok, ret) == (True, id_2)

    # Invalid/non-existing ID.
    ret, ok = ctrl.testSend(config.cmd['suggest_pos'] + id_2 + force)
    assert (ok, ret) == (True, b'')

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()
    print('Test passed')


def test_create_fetch_objects():
    """
    Add a new object to the objdesc DB and query it again.
    """
    killall()

    # Start Clerk and instantiate controller.
    clerk = azrael.clerk.Clerk(reset=True)

    # Invalid ID.
    assert clerk.getObjectDescription('blah'.encode('utf8')) == None

    # Clerk defines a few default objects upon start. This one has no collision
    # shape.
    objdescid = np.int64(1).tostring()
    out = clerk.getObjectDescription(objdescid)
    assert out is not None
    assert out[0] == np.array([0, 1, 1, 1], np.float64).tostring()

    # Second default object: a sphere.
    objdescid = np.int64(2).tostring()
    out = clerk.getObjectDescription(objdescid)
    assert out is not None
    assert out[0] == np.array([3, 1, 1, 1], np.float64).tostring()

    # Third default object: a cube.
    objdescid = np.int64(3).tostring()
    out = clerk.getObjectDescription(objdescid)
    assert out is not None
    assert out[0] == np.array([4, 1, 1, 1], np.float64).tostring()

    # Create a brand new object.
    cs = np.array([1, 2, 3, 4], np.float64).tostring()
    geo = np.array([5, 6, 7, 8], np.float64).tostring()
    objdescid = clerk.createObjectDescription(cs, geo, [], [])
    out = clerk.getObjectDescription(objdescid)
    assert out is not None
    assert out[0] == np.array([1, 2, 3, 4], np.float64).tostring()
    assert out[1] == np.array([5, 6, 7, 8], np.float64).tostring()

    # Define a new object with two boosters and one factory unit.
    # The 'boosters' and 'factories' arguments are a list of named
    # tuples. The first argument to these tuples is the ID that will
    # be assigned to the unit (the user can choose that number; Azrael
    # will automatically enumerate them in any way).
    cs = np.array([1, 2, 3, 4], np.float64).tostring()
    geo = np.array([5, 6, 7, 8], np.float64).tostring()
    b0 = types.booster(0, pos=np.zeros(3), orient=[0, 0, 1], max_force=0.5)
    b1 = types.booster(1, pos=np.zeros(3), orient=[0, 0, 1], max_force=0.5)
    f0 = types.factory(0, pos=np.zeros(3), orient=[0, 0, 1], speed=[0.1, 0.5])

    # ------------------------------------------------------------
    # In Clerk: add new object description.
    # ------------------------------------------------------------
    objdescid = clerk.createObjectDescription(cs, geo, [b0, b1], [f0])

    # Retrieve the just created object.
    out = clerk.getObjectDescription(objdescid)
    assert out is not None
    assert out[0] == np.array([1, 2, 3, 4], np.float64).tostring()
    assert out[1] == np.array([5, 6, 7, 8], np.float64).tostring()
    assert len(out[2]) == 2
    assert len(out[3]) == 1

    out_boosters = [types.booster_tostring(_) for _ in out[2]]
    out_factories = [types.factory_tostring(_) for _ in out[3]]
    assert types.booster_tostring(b0) in out_boosters
    assert types.booster_tostring(b1) in out_boosters
    assert types.factory_tostring(f0) in out_factories

    print('Test passed')


def test_get_raw_object_id():
    """
    First spawn two objects with different raw object IDS, then query them
    back. Unlike most other test, this particular tests the Clerk, the
    controller, and the WS interface all in one spot.
    """
    killall()

    # Start Clerk and instantiate controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    server = clacks.ClacksServer()
    server.start()
    ctrl = ControllerTest()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    # Make sure the system is live before attaching a client.
    client = wsclient.WebsocketClient('ws://127.0.0.1:8080/websocket', 1)
    assert client.ping_clerk()

    # Spawn a new object. The returned ID must be ID=3 because ID=0 is
    # invalid and ID={1,2} were already handed out to the 'ctrl'- and 'client'
    # object.
    id_0 = int2id(3)
    sv = btInterface.defaultData()
    sv = btInterface.pack(sv).tostring()
    objdesc_0 = np.int64(1).tostring()
    payload = bytes([4]) + 'Echo'.encode('utf8') + objdesc_0 + sv
    ret, ok = ctrl.testSend(config.cmd['spawn'] + payload)
    assert (ok, ret) == (True, id_0)

    # Spawn another object. It only differs in terms of the template object.
    id_1 = int2id(4)
    objdesc_1 = np.int64(3).tostring()
    payload = bytes([4]) + 'Echo'.encode('utf8') + objdesc_1 + sv
    ret, ok = ctrl.testSend(config.cmd['spawn'] + payload)
    assert (ok, ret) == (True, id_1)
    
    # ------------------------------------------------------------------------
    # Retrieve the template ID for this object directly from the Clerk.
    # ------------------------------------------------------------------------
    # First object.
    ret, ok = ctrl.testSend(config.cmd['get_template_id'] + id_0)
    assert (ok, ret) == (True, objdesc_0)
    
    # Second object.
    ret, ok = ctrl.testSend(config.cmd['get_template_id'] + id_1)
    assert (ok, ret) == (True, objdesc_1)
    
    # Non-existing object.
    ret, ok = ctrl.testSend(config.cmd['get_template_id'] + int2id(100))
    assert not ok
    
    # ------------------------------------------------------------------------
    # Retrieve the template ID via the Controller.
    # ------------------------------------------------------------------------
    # First object.
    ret, ok = ctrl.getTemplateID(id_0)
    assert (ok, ret) == (True, objdesc_0)
    
    # Second object.
    ret, ok = ctrl.getTemplateID(id_1)
    assert (ok, ret) == (True, objdesc_1)
    
    # Non-existing object.
    ret, ok = ctrl.testSend(config.cmd['get_template_id'] + int2id(100))
    assert not ok

    # ------------------------------------------------------------------------
    # Retrieve the template ID via the WS client.
    # ------------------------------------------------------------------------
    # First object.
    ret, ok = client.getTemplateID(id_0)
    assert (ok, ret) == (True, objdesc_0)
    
    # Second object.
    ret, ok = client.getTemplateID(id_1)
    assert (ok, ret) == (True, objdesc_1)
    
    # Non-existing object.
    ret, ok = ctrl.testSend(config.cmd['get_template_id'] + int2id(100))
    assert not ok

    # Shutdown.
    server.terminate()
    clerk.terminate()
    server.join()
    clerk.join()

    print('Test passed')


def test_processControlCommand():
    """
    Create an object with some boosters and factories and send control
    commands to them.
    """
    clerk = azrael.clerk.Clerk(reset=True)

    # Create a fake object. We will not need it but since Clerk will double
    # check its existence we need to spawn one. However, I do not want to run
    # Clerk as a full fledged process which is why I just 'hack' it in for this
    # test.
    objID = int2id(1)
    sv = btInterface.defaultData()
    sv = btInterface.pack(sv).tostring()
    btInterface.add(objID, sv, np.int64(1).tostring())

    # Create booster control command.
    cmd_0 = commands.controlBooster(unitID=0, force=0.2)
    cmd = commands.serialiseCommands(objID, [cmd_0], [])

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
    objdescid_2 = clerk.createObjectDescription(cs, geo, [b0, b1], [f0])
    objID_2 = int2id(2)
    btInterface.add(objID_2, sv, objdescid_2)
    
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

    print('Test passed')
    

if __name__ == '__main__':
    test_processControlCommand()
    test_get_raw_object_id()
    test_get_statevar()
    test_spawn()
    test_create_fetch_objects()
    test_set_force()
    test_suggest_position()
    test_create_new_raw_object()
    test_get_message()
    test_send_message()
    test_connect()
    test_ping()
    test_invalid()
    test_get_id()
