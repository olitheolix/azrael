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
    client = wsclient.WebsocketClient('ws://127.0.0.1:8080/websocket', 1)
    assert client.ping()
    del client

    # Terminate the server object.
    server.terminate()
    server.join()
    del server

    # Connection must now be impossible.
    with pytest.raises(ConnectionRefusedError):
        wsclient.WebsocketClient('ws://127.0.0.1:8080/websocket', 1)

    clerk.terminate()
    clerk.join()
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
    client = wsclient.WebsocketClient('ws://127.0.0.1:8080/websocket', 1)
    assert client.ping()
    server.terminate()
    clerk.terminate()
    server.join()
    clerk.join()
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
    client = wsclient.WebsocketClient('ws://127.0.0.1:8080/websocket', 1)

    # Read from the WS. Since the server is not writing to that socket the call
    # will block and must raise a timeout eventually.
    with pytest.raises(websocket.WebSocketTimeoutException):
        client.recvFromClacks()

    # Shutdown.
    server.terminate()
    clerk.terminate()
    server.join()
    clerk.join()

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
    client = wsclient.WebsocketClient('ws://127.0.0.1:8080/websocket', 1)
    assert client.ping_clerk()

    # Shutdown.
    server.terminate()
    clerk.terminate()
    server.join()
    clerk.join()
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
    client = wsclient.WebsocketClient('ws://127.0.0.1:8080/websocket', 1)
    assert client.getID() == (int2id(1), True)

    # Shutdown.
    server.terminate()
    clerk.terminate()
    server.join()
    clerk.join()
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
    client = wsclient.WebsocketClient('ws://127.0.0.1:8080/websocket', 1)
    assert client.ping_clerk()

    # Instruct the server to spawn a Controller named 'Echo'. The call will
    # return the ID of the controller which must be '2' ('0' is invalid and '1'
    # was already given to the controller in the WS handler).
    objdesc = np.int64(1).tostring()
    ctrl_id, ok = client.spawn('Echo', objdesc, np.zeros(3))
    assert (ctrl_id, ok) == (int2id(2), True)

    # Shutdown.
    server.terminate()
    clerk.terminate()
    server.join()
    clerk.join()
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
    client = wsclient.WebsocketClient('ws://127.0.0.1:8080/websocket', 1)
    assert client.ping_clerk()

    # Instruct the server to spawn a Controller named 'Echo'. The call will
    # return the ID of the controller which must be '2' ('0' is invalid and '1'
    # was already given to the controller in the WS handler).
    objdesc = np.int64(1).tostring()
    client_id, ok = client.spawn('Echo', objdesc, np.zeros(3))
    assert (client_id, ok) == (int2id(2), True)

    # Dispatch the test message.
    msg_orig = 'test'.encode('utf8')
    ret, ok = client.sendMessage(client_id, msg_orig)
    assert ok

    # Fetch the response. The responses may not be immediate available so poll
    # a few times.
    for ii in range(5):
        src, msg_ret = client.getMessage()
        if src is not None:
            break
        time.sleep(0.1)
    assert src is not None

    # The source must be the newly created process and the resonse must be the
    # original messages prefixed with the controller ID.
    assert src == client_id
    assert client_id + msg_orig == msg_ret

    # Shutdown.
    server.terminate()
    clerk.terminate()
    server.join()
    clerk.join()
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
    client = wsclient.WebsocketClient('ws://127.0.0.1:8080/websocket', 1)
    assert client.ping_clerk()

    # Instruct the server to spawn a Controller named 'Echo'. The call will
    # return the ID of the controller which must be '2' ('0' is invalid and '1'
    # was already given to the controller in the WS handler).
    objdesc = np.int64(1).tostring()
    id_0, ok = client.spawn('Echo', objdesc, pos=np.ones(3), vel=-np.ones(3))
    assert (id_0, ok) == (int2id(2), True)

    sv, ok = client.getStateVariables(id_0)
    assert (len(sv), ok) == (1, True)
    assert id_0 in sv
    assert np.array_equal(sv[id_0].position, np.ones(3))
    assert np.array_equal(sv[id_0].velocityLin, -np.ones(3))

    sv, ok = client.getStateVariables(None)
    assert (len(sv), ok) == (1, True)
    assert id_0 in sv
    assert np.array_equal(sv[id_0].position, np.ones(3))
    assert np.array_equal(sv[id_0].velocityLin, -np.ones(3))

    # Spawn two more controllers and query their state variables all at once.
    id_1, ok = client.spawn('Echo', objdesc, pos=2 * np.ones(3), vel=-2 * np.ones(3))
    assert (id_1, ok) == (int2id(3), True)
    id_2, ok = client.spawn('Echo', objdesc, pos=3 * np.ones(3), vel=-3 * np.ones(3))
    assert (id_2, ok) == (int2id(4), True)
    sv, ok = client.getStateVariables(None)
    assert (len(sv), ok) == (3, True)
    for idx, ctrl_id in enumerate([id_0, id_1, id_2]):
        assert ctrl_id in sv

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
    ret, ok = client.setForce(ctrl_id, f, p)
    assert ok
    ret, ok = client.setForce(ctrl_id, f + 1, p + 1)
    assert ok

    # Set the suggested position.
    ret, ok = client.suggestPosition(ctrl_id, f)
    assert ok
    ret, ok = client.suggestPosition(ctrl_id, f + 1)
    assert ok
    del f

    # Shutdown.
    server.terminate()
    clerk.terminate()
    server.join()
    clerk.join()
    print('Test passed')


def test_create_raw_objects():
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

    # Instruct the server to spawn an invisible dummy object (objdesc=1) and
    # assicate an 'Echo' instance with it. The call will return the ID of the
    # controller which must be '2' ('0' is invalid and '1' was already given to
    # the controller in the WS handler).
    objdesc = np.int64(1).tostring()
    id_0, ok = client.spawn('Echo', objdesc, np.zeros(3))
    assert (id_0, ok) == (int2id(2), True)

    # Must return no geometery becaus the default object (objdesc=1) has none.
    geo_0, ok = client.getGeometry(objdesc)
    assert (geo_0, ok) == (b'', True)

    # Define a new raw object. The geometry data is arbitrary but its length
    # must be divisible by 9.
    geo_0_ref = bytes(range(0, 9))
    cs_0_ref = np.array([1, 1, 1, 1]).tostring()
    geo_1_ref = bytes(range(9, 18))
    cs_1_ref = np.array([3, 1, 1, 1]).tostring()
    id_0, ok = client.newRawObject(cs_0_ref, geo_0_ref)
    assert ok
    id_1, ok = client.newRawObject(cs_1_ref, geo_1_ref)
    assert ok

    # Check the geometries again.
    geo_0, ok = client.getGeometry(id_0)
    assert (geo_0, ok) == (geo_0_ref, True)
    geo_1, ok = client.getGeometry(id_1)
    assert (geo_1, ok) == (geo_1_ref, True)

    # Query the geometry of a non-existing object.
    ret, ok = client.getGeometry(np.int64(200).tostring())
    assert not ok

    # Shutdown.
    server.terminate()
    clerk.terminate()
    server.join()
    clerk.join()
    print('Test passed')


if __name__ == '__main__':
    test_create_raw_objects()
    test_spawn_one_controller()
    test_spawn_and_talk_to_one_controller()
    test_spawn_and_get_state_variables()
    test_server()
    test_connect()
    test_timeout()
    test_clerk_ping()
    test_websocket_getID()
