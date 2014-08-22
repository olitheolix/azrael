import sys
import time
import pytest
import logging
import IPython
import websocket
import subprocess
import numpy as np

import azrael.clerk
import azrael.config as config
import azrael.clacks as clacks
import azrael.wsclient as wsclient
import azrael.controller as controller

from azrael.util import int2id, id2int

ControllerBaseWS = wsclient.ControllerBaseWS

ipshell = IPython.embed


def killall():
    subprocess.call(['pkill', 'killme'])


def test_server():
    """
    Ensure the server terminates the connection when garbage collected.
    This is mostly to make the unit tests easier to administrate.
    """
    killall()

    # Start Clerk.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()

    # Start server and give it some time to initialise.
    server = clacks.ClacksServer()
    server.start()

    # Start a client and ping the server.
    client = ControllerBaseWS('ws://127.0.0.1:8080/websocket', 1)
    assert client.ping()
    del client

    # Terminate the server object.
    server.terminate()
    server.join()
    del server

    # Connection must now be impossible.
    with pytest.raises(ConnectionRefusedError):
        ControllerBaseWS('ws://127.0.0.1:8080/websocket', 1)

    clerk.terminate()
    clerk.join()
    killall()

    print('Test passed')


def test_connect():
    """
    Ping the websocket server.
    """
    killall()

    # Start Clerk.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()

    # Start server and client.
    server = clacks.ClacksServer()
    server.start()
    client = ControllerBaseWS('ws://127.0.0.1:8080/websocket', 1)
    assert client.ping()
    server.terminate()
    clerk.terminate()
    server.join()
    clerk.join()
    killall()

    print('Test passed')


def test_timeout():
    """
    WS connection must timeout if it is inactive for too long.
    """
    killall()

    # Start Clerk.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()

    # Start server and client.
    server = clacks.ClacksServer()
    server.start()
    client = ControllerBaseWS('ws://127.0.0.1:8080/websocket', 1)

    # Read from the WS. Since the server is not writing to that socket the call
    # will block and must raise a timeout eventually.
    with pytest.raises(websocket.WebSocketTimeoutException):
        client.recvFromClacks()

    # Shutdown.
    server.terminate()
    clerk.terminate()
    server.join()
    clerk.join()
    killall()

    print('Test passed')


def test_clerk_ping():
    """
    Ping the clerk instance.
    """
    killall()

    # Start server and client.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()

    server = clacks.ClacksServer()
    server.start()

    # This is the actual test: connect and send 'PING' command.
    client = ControllerBaseWS('ws://127.0.0.1:8080/websocket', 1)
    assert client.ping_clerk()

    # Shutdown.
    server.terminate()
    clerk.terminate()
    server.join()
    clerk.join()
    killall()

    print('Test passed')


def test_websocket_getID():
    """
    Query the controller ID associated with this WebSocket.
    """
    killall()

    # Start server and client.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    server = clacks.ClacksServer()
    server.start()

    # Make sure we are connected.
    client = ControllerBaseWS('ws://127.0.0.1:8080/websocket', 1)
    assert client.objID == int2id(1)

    # Shutdown.
    server.terminate()
    clerk.terminate()
    server.join()
    clerk.join()
    killall()

    print('Test passed')


def test_spawn_one_controller():
    """
    Ask Clerk to spawn one (echo) controller.
    """
    killall()

    # Start server and client.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    server = clacks.ClacksServer()
    server.start()

    # Make sure the system is live.
    client = ControllerBaseWS('ws://127.0.0.1:8080/websocket', 1)
    assert client.ping_clerk()

    # Instruct the server to spawn a Controller named 'Echo'. The call will
    # return the ID of the controller which must be '2' ('0' is invalid and '1'
    # was already given to the controller in the WS handler).
    templateID = np.int64(1).tostring()
    ok, ctrl_id = client.spawn('Echo', templateID, np.zeros(3))
    print(ok, ctrl_id)
    assert (ctrl_id, ok) == (int2id(2), True)

    # Shutdown.
    server.terminate()
    clerk.terminate()
    server.join()
    clerk.join()
    killall()

    print('Test passed')


def test_spawn_and_talk_to_one_controller():
    """
    Ask Clerk to spawn one (echo) controller. Then send a message to that
    controller to ensure everything works.
    """
    killall()

    # Start server and client.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    server = clacks.ClacksServer()
    server.start()

    # Make sure the system is live.
    client = ControllerBaseWS('ws://127.0.0.1:8080/websocket', 1)
    assert client.ping_clerk()

    # Instruct the server to spawn a Controller named 'Echo'. The call will
    # return the ID of the controller which must be '2' ('0' is invalid and '1'
    # was already given to the Controller in Clacks).
    templateID = np.int64(1).tostring()
    ok, client_id = client.spawn('Echo', templateID, np.zeros(3))
    assert (ok, client_id) == (True, int2id(2))

    # Dispatch the test message.
    msg_orig = 'test'.encode('utf8')
    ok, ret = client.sendMessage(client_id, msg_orig)
    assert ok

    for ii in range(5):
        ok, data = client.recvMessage()
        assert isinstance(ok, bool)
        if ok:
            src, msg_ret = data
        else:
            src, msg_ret = None, None

        if ok and (src is not None):
            break
        time.sleep(0.1)
    assert src is not None

    # The source must be the newly created process and the response must be the
    # original messages prefixed with the controller ID.
    print(src, client_id)
    print(msg_ret)
    assert src == client_id
    assert (client_id + msg_orig) == msg_ret

    # Shutdown.
    server.terminate()
    clerk.terminate()
    server.join()
    clerk.join()
    killall()

    print('Test passed')


def test_spawn_and_get_state_variables():
    """
    Spawn a new Controller and query its state variables.
    """
    killall()

    # Start server and client.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    server = clacks.ClacksServer()
    server.start()

    # Make sure the system is live.
    client = ControllerBaseWS('ws://127.0.0.1:8080/websocket', 1)
    assert client.ping_clerk()

    # Instruct the server to spawn a Controller named 'Echo'. The call will
    # return the ID of the controller which must be '2' ('0' is invalid and '1'
    # was already given to the controller in the WS handler).
    templateID = np.int64(1).tostring()
    ok, id_0 = client.spawn('Echo', templateID, pos=np.ones(3), vel=-np.ones(3))
    assert (ok, id_0) == (True, int2id(2))

    ok, sv = client.getStateVariables(id_0)
    assert (ok, len(sv)) == (True, 1)
    assert id_0 in sv
    assert np.array_equal(sv[id_0].position, np.ones(3))
    assert np.array_equal(sv[id_0].velocityLin, -np.ones(3))

    ok, all_ids = client.getAllObjectIDs()
    assert (ok, all_ids) == (True, [id_0])

    ok, sv = client.getStateVariables(id_0)
    assert np.array_equal(sv[id_0].position, np.ones(3))
    assert np.array_equal(sv[id_0].velocityLin, -np.ones(3))

    # Spawn two more controllers and query their state variables all at once.
    ok, id_1 = client.spawn('Echo', templateID, pos=2 * np.ones(3), vel=-2 * np.ones(3))
    assert (ok, id_1) == (True, int2id(3))
    ok, id_2 = client.spawn('Echo', templateID, pos=3 * np.ones(3), vel=-3 * np.ones(3))
    assert (ok, id_2) == (True, int2id(4))
    
    ok, all_ids = client.getAllObjectIDs()
    assert (ok, set(all_ids)) == (True, set([id_0, id_1, id_2]))

    ok, sv = client.getStateVariables(all_ids)
    assert set(sv.keys()) == set(all_ids)

    assert np.array_equal(sv[id_0].position, 1 * np.ones(3))
    assert np.array_equal(sv[id_0].velocityLin, 1 * -np.ones(3))
    assert np.array_equal(sv[id_1].position, 2 * np.ones(3))
    assert np.array_equal(sv[id_1].velocityLin, -2 * np.ones(3))
    assert np.array_equal(sv[id_2].position, 3 * np.ones(3))
    assert np.array_equal(sv[id_2].velocityLin, -3 * np.ones(3))

    # Set the force vector twice. The reasons for testing this twice is a
    # bug I once had.
    f = np.ones(3, np.float64)
    p = 2 * f
    ok, ret = client.setForce(id_1, f)
    assert ok
    ok, ret = client.setForce(id_1, f + 1)
    assert ok

    # Set the suggested position.
    ok, ret = client.suggestPosition(id_1, f)
    assert ok
    ok, ret = client.suggestPosition(id_1, f + 1)
    assert ok
    del f

    # Shutdown.
    server.terminate()
    clerk.terminate()
    server.join()
    clerk.join()
    killall()

    print('Test passed')


def fixme_test_create_raw_objects():
    """
    Spawn default objects and query their geometry. Then define new objects
    with custom geometry, spawn them, and check their geometry is correct.

    This test is almost identical to
    test_controller.test_create_raw_objects. The main difference is that this
    one uses a WS interface, whereas the other test uses a controller instance
    directly.
    """
    killall()

    # Start server and client.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    server = clacks.ClacksServer()
    server.start()

    # Make sure the system is live.
    client = wsclient.WebsocketClient('ws://127.0.0.1:8080/websocket', 1)
    assert client.ping_clerk()

    # Instruct the server to spawn an invisible dummy object (templateID=1) and
    # assicate an 'Echo' instance with it. The call will return the ID of the
    # controller which must be '2' ('0' is invalid and '1' was already given to
    # the controller in the WS handler).
    templateID = np.int64(1).tostring()
    ok, id_0 = client.spawn('Echo', templateID, np.zeros(3))
    assert (ok, id_0) == (True, int2id(2))

    # Must return no geometry because the default object (templateID=1) has none.
    ok, geo_0 = client.getGeometry(templateID)
    assert (ok, geo_0) == (True, b'')

    # Define a new raw object. The geometry data is arbitrary but its length
    # must be divisible by 9.
    geo_0_ref = np.arange(9).astype(np.float64)
    cs_0_ref = np.array([1, 1, 1, 1], np.float64)
    geo_1_ref = np.arange(9, 18).astype(np.float64)
    cs_1_ref = np.array([3, 1, 1, 1], np.float64)
    ok, id_0 = client.newObjectTemplate(cs_0_ref, geo_0_ref)
    assert ok
    ok, id_1 = client.newObjectTemplate(cs_1_ref, geo_1_ref)
    assert ok

    # Check the geometries again.
    ok, geo_0 = client.getGeometry(id_0)
    assert (ok, geo_0) == (True, geo_0_ref.tostring())
    ok, geo_1 = client.getGeometry(id_1)
    assert (ok, geo_1) == (True, geo_1_ref.tostring())
    print('check')

    # Query the geometry of a non-existing object.
    ok, ret = client.getGeometry(np.int64(200).tostring())
    assert not ok

    # Shutdown.
    server.terminate()
    clerk.terminate()
    server.join()
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
    server = clacks.ClacksServer()
    server.start()

    # Make sure the system is live before attaching a client.
    client = ControllerBaseWS('ws://127.0.0.1:8080/websocket', 1)
    assert client.ping_clerk()

    # So far no objects have been spawned.
    ok, ret = client.getAllObjectIDs()
    assert (ok, ret) == (True, [])

    # Spawn a new object.
    ok, ret = client.spawn('Echo', templateID, np.zeros(3))
    assert (ok, ret) == (True, objID_2)

    # The object list must now contain the ID of the just spawned object.
    ok, ret = client.getAllObjectIDs()
    assert (ok, ret) == (True, [objID_2])

    # Terminate the Clerk.
    clerk.terminate()
    server.terminate()
    clerk.join()
    server.join()

    # Kill all spawned Controller processes.
    killall()

    print('Test passed')


def test_get_template():
    """
    Spawn some objects from the default templates and query their template IDs.
    """
    killall()

    # Parameters and constants for this test.
    id_0, id_1 = int2id(2), int2id(3)
    templateID_0, templateID_1 = np.int64(1).tostring(), np.int64(3).tostring()

    # Start Clerk and instantiate controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    server = clacks.ClacksServer()
    server.start()

    # Make sure the system is live before attaching a client.
    client = ControllerBaseWS('ws://127.0.0.1:8080/websocket', 1)
    assert client.ping_clerk()

    # Spawn a new object. It must have ID=2 because ID=1 was already given to
    # the `ctrl` instance inside the websocket handler.
    ok, ctrl_id = client.spawn('Echo', templateID_0, np.zeros(3))
    assert (ok, ctrl_id) == (True, id_0)

    # Spawn another object from a different template.
    ok, ctrl_id = client.spawn('Echo', templateID_1, np.zeros(3))
    assert (ok, ctrl_id) == (True, id_1)

    # Retrieve template of first object.
    ok, ret = client.getTemplateID(id_0)
    assert (ok, ret) == (True, templateID_0)
    
    # Retrieve template of second object.
    ok, ret = client.getTemplateID(id_1)
    assert (ok, ret) == (True, templateID_1)
    
    # Attempt to retrieve a non-existing object.
    ok, ret = client.getTemplateID(int2id(100))
    assert not ok

    # Shutdown.
    server.terminate()
    clerk.terminate()
    server.join()
    clerk.join()
    killall()
    
    print('Test passed')


if __name__ == '__main__':
    test_get_template()
    test_getAllObjectIDs()
#    fixme_test_create_raw_objects()
    test_spawn_one_controller()
    test_spawn_and_talk_to_one_controller()
    test_spawn_and_get_state_variables()
    test_server()
    test_connect()
    test_timeout()
    test_clerk_ping()
    test_websocket_getID()
