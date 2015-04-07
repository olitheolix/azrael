import sys
import time
import pytest
import logging
import websocket
import subprocess
import numpy as np

import azrael.clerk
import azrael.clacks
import azrael.vectorgrid
import azrael.wsclient
import azrael.config as config

from IPython import embed as ipshell

WSClient = azrael.wsclient.WSClient


def test_ping_clacks():
    """
    Start services and send Ping to Clacks. Then terminate clacks and verify
    that the ping fails.
    """
    ip, port = config.addr_clacks, config.port_clacks

    # Start the services.
    clerk = azrael.clerk.Clerk()
    clacks = azrael.clacks.ClacksServer()
    clerk.start()
    clacks.start()

    # Create a Websocket client.
    client = azrael.wsclient.WSClient(ip=ip, port=port, timeout=1)

    # Ping Clerk via Clacks.
    assert client.ping()
    assert client.pingClacks().ok

    # Terminate the services.
    clerk.terminate()
    clacks.terminate()
    clerk.join()
    clacks.join()

    # Ping must now be impossible.
    with pytest.raises(ConnectionRefusedError):
        WSClient(ip=ip, port=port, timeout=1)

    assert not client.pingClacks().ok
    
    print('Test passed')
