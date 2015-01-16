import sys
import time
import pytest
import logging
import IPython
import websocket
import subprocess
import numpy as np

import azrael.clerk
import azrael.clacks
import azrael.vectorgrid
import azrael.wsclient
import azrael.config as config

WSClient = azrael.wsclient.WSClient

ipshell = IPython.embed


def killAzrael():
    subprocess.call(['pkill', 'killme'])

    # Delete all grids used in this test.
    assert azrael.vectorgrid.deleteAllGrids().ok

    azrael.database.init(reset=True)


def startAzrael(client_type):
    """
    Start all Azrael services and return their handles.

    ``client_type`` may be  either 'ZeroMQ' or 'Websocket'. The only difference
    this makes is that the 'Websocket' version will also start a Clacks server,
    whereas for 'ZeroMQ' the respective handle will be **None**.

    :param str client_type: the client type ('ZeroMQ' or 'Websocket').
    :return: handles to (clerk, client, clacks)
    """
    killAzrael()

    # Start Clerk and instantiate a Client.
    clerk = azrael.clerk.Clerk()
    clerk.start()

    if client_type == 'ZeroMQ':
        # Instantiate the ZeroMQ version of the Client.
        client = azrael.client.Client()
        client.setupZMQ()

        # Do not start a Clacks process.
        clacks = None
    elif client_type == 'Websocket':
        # Start a Clacks process.
        clacks = azrael.clacks.ClacksServer()
        clacks.start()

        # Instantiate the Websocket version of the Client.
        client = azrael.wsclient.WSClient(
            'ws://127.0.0.1:8080/websocket', 1)
        assert client.ping()
    else:
        print('Unknown protocol type <{}>'.format(client_type))
        assert False
    return clerk, client, clacks


def stopAzrael(clerk, clacks):
    """
    Kill all processes related to Azrael.

    :param clerk: handle to Clerk process.
    :param clacks: handle to Clacks process.
    """
    # Terminate the Clerk.
    clerk.terminate()
    clerk.join(timeout=3)

    # Terminate Clacks (if one was started).
    if clacks is not None:
        clacks.terminate()
        clacks.join(timeout=3)

    # Forcefully terminate everything.
    killAzrael()


def test_ping_clacks():
    """
    Start services and send Ping to Clacks. Then terminate clacks and verify
    that the ping fails.
    """
    # Start the necessary services.
    clerk, client, clacks = startAzrael('Websocket')

    # Ping the Clacks.
    assert client.ping()

    # Shutdown the services.
    stopAzrael(clerk, clacks)

    # Connection must now be impossible.
    with pytest.raises(ConnectionRefusedError):
        WSClient('ws://127.0.0.1:8080/websocket', 1)

    print('Test passed')


def test_ping_clerk():
    """
    Ping the Clerk instance via Clacks.
    """
    # Start the necessary services.
    clerk, client, clacks = startAzrael('Websocket')

    # And send 'PING' command.
    assert client.pingClacks().ok

    # Shutdown the services.
    stopAzrael(clerk, clacks)

    # And send 'PING' command.
    assert not client.pingClacks().ok

    print('Test passed')


if __name__ == '__main__':
    test_ping_clacks()
    test_ping_clerk()
