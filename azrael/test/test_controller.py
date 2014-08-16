"""
Test the controller base class.

The controller class is merely a convenience class to wrap the Clerk
commands. As such the tests here merely test these wrappers. See `test_clerk`
if you want to see thorough tests for the Clerk functionality.
"""

import sys
import time
import pytest
import IPython
import subprocess
import numpy as np

import azrael.clerk
import azrael.clacks
import azrael.controller
import azrael.types as types
import azrael.config as config
import azrael.bullet.btInterface as btInterface

from azrael.util import int2id, id2int

ipshell = IPython.embed
ControllerBase = azrael.controller.ControllerBase


def killall():
    subprocess.call(['pkill', 'killme'])


def test_ping():
    """
    Send a ping to the Clerk and check the response is correct.
    """
    killall()

    # Start Clerk and instantiate Controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerBase()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    ok, ret = ctrl.ping()
    assert (ok, ret) == (True, 'pong clerk'.encode('utf8'))

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()

    killall()
    print('Test passed')


def test_spawn_one_controller():
    """
    Ask Clerk to spawn one (echo) controller.
    """
    killall()

    # Start Clerk and instantiate Controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerBase()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    # Instruct the server to spawn a Controller named 'Echo'. The call will
    # return the ID of the controller which must be '2' ('0' is invalid and '1'
    # was already given to the controller in the WS handler).
    templateID = np.int64(1).tostring()
    ok, ctrl_id = ctrl.spawn('Echo', templateID, np.zeros(3))
    assert (ok, ctrl_id) == (True, int2id(2))

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()

    killall()
    print('Test passed')


def test_spawn_and_talk_to_one_controller():
    """
    Ask Clerk to spawn one (echo) controller. Then send a message to that
    controller to ensure everything works.
    """
    killall()

    # Start Clerk and instantiate Controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerBase()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    # Instruct the server to spawn a Controller named 'Echo'. The call will
    # return the ID of the controller which must be '2' ('0' is invalid and '1'
    # was already given to the controller in the WS handler).
    templateID = np.int64(1).tostring()
    ok, ctrl_id = ctrl.spawn('Echo', templateID, np.zeros(3))
    assert (ok, ctrl_id) == (True, int2id(2))

    # Send a message to `ctrl_id`.
    msg_orig = 'test'.encode('utf8')
    ok, ret = ctrl.sendMessage(ctrl_id, msg_orig)
    assert ok

    # Fetch the response. Poll for it a few times because it may not arrive
    # immediately.
    for ii in range(5):
        src, msg_ret = ctrl.recvMessage()
        if src is not None:
            break
        time.sleep(0.1)
    assert src is not None

    # The source must be the newly created process and the response must be the
    # original messages prefixed with the controller ID.
    assert src == ctrl_id
    if ctrl_id + msg_orig != msg_ret:
        print(msg_ret)
    assert ctrl_id + msg_orig == msg_ret

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()

    killall()
    print('Test passed')


def test_spawn_and_get_state_variables():
    """
    Spawn a new Controller and query its state variables.
    """
    killall()

    # Start Clerk and instantiate Controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerBase()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    # Instruct the server to spawn a Controller named 'Echo'. The call will
    # return the ID of the controller which must be '2' ('0' is invalid and '1'
    # was already given to the controller in the WS handler).
    templateID = np.int64(1).tostring()
    ok, id0 = ctrl.spawn('Echo', templateID, pos=np.ones(3), vel=-np.ones(3))
    assert (ok, id0) == (True, int2id(2))

    ok, sv = ctrl.getStateVariables(id0)
    assert (ok, len(sv)) == (True, config.LEN_SV_BYTES + config.LEN_ID)

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()

    killall()
    print('Test passed')


def test_multi_controller():
    """
    Start a few echo Controllers processes. Then manually operate one
    Controller instance to bounce messages off the other controllers.
    """
    killall()

    # Start Clerk and instantiate Controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerBase()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    # Launch the Controllers (default implementation is an echo).
    num_proc = 10
    proc = [ControllerBase() for _ in range(num_proc)]
    for p in proc:
        p.start()

    # Send a random message to all Controllers (the Clerk object should have
    # assigned them the numbers [0, num_proc-1])
    err = None
    try:
        # The message.
        t = 'test'.encode('utf8')

        # Compile list of object IDs. The list starts with ID 2 because ID=0 is
        # invalid and ID=1 was already given to the 'ctrl' controller,
        obj_ids = [int2id(_) for _ in range(2, num_proc + 2)]

        # Send the test message to every controller. Every controller gets a
        # distinct one because it contains the ID of the target controller.
        for dst in obj_ids:
            assert ctrl.sendMessage(dst, t + dst)

        # Every echo controller should return the same message prefixed with
        # its own ID.
        for ii in range(num_proc):
            src, msg = ctrl.recvMessage()
            while len(msg) == 0:
                time.sleep(.02)
                src, msg = ctrl.recvMessage()
            # Start/end of message must both contain the dst ID.
            assert msg[:config.LEN_ID] == msg[-config.LEN_ID:]
    except AssertionError as e:
        err = e

    # Terminate controller processes.
    for p in proc:
        p.terminate()
        p.join()

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()

    if err is not None:
        raise err

    killall()
    print('Test passed')


def test_create_template_objects():
    """
    Spawn default objects and query their geometry. Then define new objects
    with custom geometry, spawn them, and check their geometry is correct.

    This test is almost identical to
    test_clacks.test_create_template_objects. The main difference is that this
    one uses a controller instance directly, whereas the other test uses a
    WS to connect to the controller.
    """
    killall()

    # Start Clerk and instantiate Controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerBase()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    # Instruct the server to spawn an invisible dummy object (templateID=1) and
    # assicate an 'Echo' instance with it. The call will return the ID of the
    # controller which must be '2' ('0' is invalid and '1' was already given to
    # the controller in the WS handler).
    templateID = np.int64(1).tostring()
    ok, id_0 = ctrl.spawn('Echo', templateID, np.zeros(3))
    assert (ok, id_0) == (True, int2id(2))

    # Must return no geometry because the default object (templateID=1) has none.
    ok, geo_0 = ctrl.getGeometry(templateID)
    assert (ok, geo_0) == (True, b'')

    # Define a new object template. The geometry data is arbitrary but its
    # length must be divisible by 9.
    geo_0_ref = bytes(range(0, 9))
    cs_0_ref = np.array([1, 1, 1, 1]).tostring()
    geo_1_ref = bytes(range(9, 18))
    cs_1_ref = np.array([3, 1, 1, 1]).tostring()
    ok, id_0 = ctrl.newObjectTemplate(cs_0_ref, geo_0_ref)
    assert ok
    ok, id_1 = ctrl.newObjectTemplate(cs_1_ref, geo_1_ref)
    assert ok

    # Check the geometries again.
    ok, geo_0 = ctrl.getGeometry(id_0)
    assert (ok, geo_0) == (True, geo_0_ref)
    ok, geo_1 = ctrl.getGeometry(id_1)
    assert (ok, geo_1) == (True, geo_1_ref)

    # Query the geometry for a non-existing object.
    ok, ret = ctrl.getGeometry(np.int64(200).tostring())
    assert not ok

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()

    killall()
    print('Test passed')


def test_getAllObjectIDs():
    """
    Ensure the getAllObjectIDs command reaches Clerk.
    """
    killall()
    
    # Parameters and constants for this test.
    objID_2 = int2id(2)
    templateID = np.int64(1).tostring()

    # Start Clerk and instantiate two Controllers.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerBase()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    # So far no objects have been spawned.
    ok, ret = ctrl.getAllObjectIDs()
    assert (ok, ret) == (True, [])

    # Spawn a new object.
    templateID = np.int64(1).tostring()
    ok, ret = ctrl.spawn('Echo', templateID, np.zeros(3))
    assert (ok, ret) == (True, objID_2)

    # The object list must now contain the ID of the just spawned object.
    ok, ret = ctrl.getAllObjectIDs()
    assert (ok, ret) == (True, [objID_2])

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()

    # Kill all spawned Controller processes.
    killall()

def test_get_template():
    """
    Spawn some objects from the default templates and query their template IDs.
    """
    killall()

    # Parameters and constants for this test.
    id_0, id_1 = int2id(2), int2id(3)
    templateID_0, templateID_1 = np.int64(1).tostring(), np.int64(3).tostring()
    
    # Start Clerk and instantiate Controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerBase()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    # Spawn a new object. It must have ID=2 because ID=1 was already given to
    # the controller.
    ok, ctrl_id = ctrl.spawn('Echo', templateID_0, np.zeros(3))
    assert (ok, ctrl_id) == (True, id_0)

    # Spawn another object from a different template.
    ok, ctrl_id = ctrl.spawn('Echo', templateID_1, np.zeros(3))
    assert (ok, ctrl_id) == (True, id_1)

    # Retrieve template of first object.
    ok, ret = ctrl.getTemplateID(id_0)
    assert (ok, ret) == (True, templateID_0)
    
    # Retrieve template of second object.
    ok, ret = ctrl.getTemplateID(id_1)
    assert (ok, ret) == (True, templateID_1)
    
    # Attempt to retrieve a non-existing object.
    ok, ret = ctrl.getTemplateID(int2id(100))
    assert not ok

    # Shutdown.
    clerk.terminate()
    clerk.join()

    killall()
    print('Test passed')
    

def test_create_fetch_template():
    """
    Add a new object to the templateID DB and query it again.
    """
    killall()

    # Start Clerk and instantiate Controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerBase()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    # Request an invalid ID.
    ok, ret = ctrl.getTemplate('blah'.encode('utf8'))
    assert not ok

    # Clerk has a few default objects. This one has no collision shape...
    ok, ret = ctrl.getTemplate(np.int64(1).tostring())
    assert ok
    assert np.array_equal(ret.cs, [0, 1, 1, 1])
    assert len(ret.geo) == len(ret.boosters) == len(ret.factories) == 0

    # ... this one is a sphere...
    ok, ret = ctrl.getTemplate(np.int64(2).tostring())
    assert ok
    assert np.array_equal(ret.cs, [3, 1, 1, 1])
    assert len(ret.geo) == len(ret.boosters) == len(ret.factories) == 0

    # ... and this one is a cube.
    ok, ret = ctrl.getTemplate(np.int64(3).tostring())
    assert ok
    assert np.array_equal(ret.cs, [4, 1, 1, 1])
    assert len(ret.geo) == len(ret.boosters) == len(ret.factories) == 0

    # Add a new object template.
    cs = np.array([1, 2, 3, 4], np.float64)
    geo = np.array([5, 6, 7, 8], np.float64)
    ok, templateID = ctrl.addTemplate(cs, geo, [], [])

    # Fetch the just added template again.
    ok, ret = ctrl.getTemplate(templateID)
    assert np.array_equal(ret.cs, cs)
    assert np.array_equal(ret.geo, geo)
    assert len(ret.boosters) == len(ret.factories) == 0

    # Define a new object with two boosters and one factory unit.
    # The 'boosters' and 'factories' arguments are a list of named
    # tuples. Their first argument is the unit ID (Azrael does not
    # automatically assign any).
    cs = np.array([1, 2, 3, 4], np.float64)
    geo = np.array([5, 6, 7, 8], np.float64)
    b0 = types.booster(0, pos=np.zeros(3), orient=[0, 0, 1], max_force=0.5)
    b1 = types.booster(1, pos=np.zeros(3), orient=[0, 0, 1], max_force=0.5)
    f0 = types.factory(0, pos=np.zeros(3), orient=[0, 0, 1], speed=[0.1, 0.5])

    # Add the new template.
    ok, templateID = ctrl.addTemplate(cs, geo, [b0, b1], [f0])

    # Retrieve the just created object and verify the CS and geometry.
    ok, ret = ctrl.getTemplate(templateID)
    assert np.array_equal(ret.cs, cs)
    assert np.array_equal(ret.geo, geo)

    # The template must also feature two boosters and one factory.
    assert len(ret.boosters) == 2
    assert len(ret.factories) == 1

    # Explicitly verify the booster- and factory units. The easisest (albeit
    # not most readable) way to do the comparison is to convert the unit
    # descriptions (which are named tuples) to byte strings and compare those.
    out_boosters = [types.booster_tostring(_) for _ in ret.boosters]
    out_factories = [types.factory_tostring(_) for _ in ret.factories]
    assert types.booster_tostring(b0) in out_boosters
    assert types.booster_tostring(b1) in out_boosters
    assert types.factory_tostring(f0) in out_factories

    print('Test passed')


if __name__ == '__main__':
    test_create_fetch_template()
    test_get_template()
    test_getAllObjectIDs()
    test_create_template_objects()
    test_ping()
    test_spawn_one_controller()
    test_spawn_and_talk_to_one_controller()
    test_spawn_and_get_state_variables()
    test_multi_controller()
