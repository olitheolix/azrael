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

    # Start Clerk and instantiate controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerBase()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    ret, ok = ctrl.ping()
    assert ok
    assert ret == 'pong clerk'.encode('utf8')

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()
    print('Test passed')


def test_spawn_one_controller():
    """
    Ask Clerk to spawn one (echo) controller.
    """
    killall()

    # Start Clerk and instantiate controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerBase()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    # Instruct the server to spawn a Controller named 'Echo'. The call will
    # return the ID of the controller which must be '2' ('0' is invalid and '1'
    # was already given to the controller in the WS handler).
    objdesc = np.int64(1).tostring()
    ctrl_id, ok = ctrl.spawn('Echo', objdesc, np.zeros(3))
    assert ok
    assert ctrl_id == int2id(2)

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()
    print('Test passed')


def test_spawn_and_talk_to_one_controller():
    """
    Ask Clerk to spawn one (echo) controller. Then send a message to that
    controller to ensure everything works.
    """
    killall()

    # Start Clerk and instantiate controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerBase()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    # Instruct the server to spawn a Controller named 'Echo'. The call will
    # return the ID of the controller which must be '2' ('0' is invalid and '1'
    # was already given to the controller in the WS handler).
    objdesc = np.int64(1).tostring()
    ctrl_id, ok = ctrl.spawn('Echo', objdesc, np.zeros(3))
    assert ok
    assert ctrl_id == int2id(2)

    # Send a message to `ctrl_id`.
    msg_orig = 'test'.encode('utf8')
    ret, ok = ctrl.sendMessage(ctrl_id, msg_orig)
    assert ok

    # Fetch the response. Poll for it a few times because it may not arrive
    # immediately.
    for ii in range(5):
        src, msg_ret = ctrl.getMessage()
        if src is not None:
            break
        time.sleep(0.1)
    assert src is not None

    # The source must be the newly created process and the response must be the
    # original messages prefixed with the controller ID.
    assert src == ctrl_id
    assert ctrl_id + msg_orig == msg_ret

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()
    print('Test passed')


def test_spawn_and_get_state_variables():
    """
    Spawn a new Controller and query its state variables.
    """
    killall()

    # Start Clerk and instantiate controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerBase()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    # Instruct the server to spawn a Controller named 'Echo'. The call will
    # return the ID of the controller which must be '2' ('0' is invalid and '1'
    # was already given to the controller in the WS handler).
    objdesc = np.int64(1).tostring()
    id0, ok = ctrl.spawn('Echo', objdesc, pos=np.ones(3), vel=-np.ones(3))
    assert ok
    assert id0 == int2id(2)

    sv, ok = ctrl.getStateVariables(id0)
    assert ok
    assert len(sv) == config.LEN_SV_BYTES + config.LEN_ID

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()
    print('Test passed')


def test_clerk_multi_controller():
    """
    Start a few echo Controllers processes. Then manually operate one
    Controller instance to bounce messages off the other controllers.
    """
    killall()

    # Start Clerk and instantiate controller.
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
            src, msg = ctrl.getMessage()
            while len(msg) == 0:
                time.sleep(.02)
                src, msg = ctrl.getMessage()
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
    print('Test passed')


def test_create_raw_objects():
    """
    Spawn default objects and query their geometry. Then define new objects
    with custom geometry, spawn them, and check their geometry is correct.

    This test is almost identical to
    test_clacks.test_create_raw_objects. The main difference is that this
    one uses a controller instance directly, whereas the other test uses a
    WS to connect to the controller.
    """
    killall()

    # Start Clerk and instantiate controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerBase()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    # Instruct the server to spawn an invisible dummy object (objdesc=1) and
    # assicate an 'Echo' instance with it. The call will return the ID of the
    # controller which must be '2' ('0' is invalid and '1' was already given to
    # the controller in the WS handler).
    objdesc = np.int64(1).tostring()
    id_0, ok = ctrl.spawn('Echo', objdesc, np.zeros(3))
    assert (id_0, ok) == (int2id(2), True)

    # Must return no geometery becaus the default object (objdesc=1) has none.
    geo_0, ok = ctrl.getGeometry(objdesc)
    assert (geo_0, ok) == (b'', True)

    # Define a new raw object. The geometry data is arbitrary but its length
    # must be divisible by 9.
    geo_0_ref = bytes(range(0, 9))
    cs_0_ref = np.array([1, 1, 1, 1]).tostring()
    geo_1_ref = bytes(range(9, 18))
    cs_1_ref = np.array([3, 1, 1, 1]).tostring()
    id_0, ok = ctrl.newRawObject(cs_0_ref, geo_0_ref)
    assert ok
    id_1, ok = ctrl.newRawObject(cs_1_ref, geo_1_ref)
    assert ok

    # Check the geometries again.
    geo_0, ok = ctrl.getGeometry(id_0)
    assert (geo_0, ok) == (geo_0_ref, True)
    geo_1, ok = ctrl.getGeometry(id_1)
    assert (geo_1, ok) == (geo_1_ref, True)

    # Query the geometry for a non-existing object.
    ret, ok = ctrl.getGeometry(np.int64(200).tostring())
    assert not ok

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()
    print('Test passed')


if __name__ == '__main__':
    test_create_raw_objects()
    test_ping()
    test_spawn_one_controller()
    test_spawn_and_talk_to_one_controller()
    test_spawn_and_get_state_variables()
    test_clerk_multi_controller()

