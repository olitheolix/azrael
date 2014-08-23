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
import azrael.wscontroller as wscontroller
import azrael.controller as controller

from azrael.util import int2id, id2int

WSControllerBase = wscontroller.WSControllerBase

ipshell = IPython.embed


def killall():
    subprocess.call(['pkill', 'killme'])


def startAzrael(ctrl_type):
    killall()
    
    # Start Clerk and instantiate Controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()

    if ctrl_type == 'ZeroMQ':
        ctrl = ControllerBase()
        ctrl.setupZMQ()
        ctrl.connectToClerk()
        server = None
    elif ctrl_type == 'Websocket':
        server = clacks.ClacksServer()
        server.start()

        ctrl = WSControllerBase('ws://127.0.0.1:8080/websocket', 1)
        assert ctrl.ping()
    else:
        print('Unknown controller type <{}>'.format(ctrl_type))
        assert False
    return clerk, ctrl, server


def stopAzrael(clerk, server):
    # Terminate the Clerk.
    clerk.terminate()
    clerk.join(timeout=3)

    # Terminate the Server (if one was started).
    if server is not None:
        server.terminate()
        server.join(timeout=3)

    # Forcefully terminate everything.
    killall()


def test_ping_clacks():
    """
    Start services and send Ping to Clacks. Then terminate clacks and verify
    that the ping fails.
    """
    # Start the necessary services.
    clerk, ctrl, server = startAzrael('Websocket')

    # Ping the server.
    assert ctrl.ping()

    # Shutdown the services.
    stopAzrael(clerk, server)

    # Connection must now be impossible.
    with pytest.raises(ConnectionRefusedError):
        WSControllerBase('ws://127.0.0.1:8080/websocket', 1)

    print('Test passed')


def test_ping_clerk():
    """
    Ping the Clerk instance via Clacks.
    """
    # Start the necessary services.
    clerk, ctrl, server = startAzrael('Websocket')

    # And send 'PING' command.
    assert ctrl.pingClerk()

    # Shutdown the services.
    stopAzrael(clerk, server)

    print('Test passed')


def test_timeout():
    """
    WS connection must timeout if it is inactive for too long.
    """
    # Start the necessary services.
    clerk, ctrl, server = startAzrael('Websocket')

    # Read from the WS. Since the server is not writing to that socket the call
    # will block and must raise a timeout eventually.
    with pytest.raises(websocket.WebSocketTimeoutException):
        ctrl.sendToClacks(b'')

    # Shutdown the services.
    stopAzrael(clerk, server)

    print('Test passed')


def test_websocket_getID():
    """
    Query the controller ID associated with this WebSocket.
    """
    # Start the necessary services.
    clerk, ctrl, server = startAzrael('Websocket')

    # Make sure we are connected.
    assert ctrl.objID == int2id(1)

    # Shutdown the services.
    stopAzrael(clerk, server)

    print('Test passed')


if __name__ == '__main__':
    test_ping_clacks()
    test_ping_clerk()
    test_timeout()
    test_websocket_getID()
