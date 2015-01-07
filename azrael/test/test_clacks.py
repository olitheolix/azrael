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
import azrael.config as config
import azrael.wscontroller as wscontroller
import azrael.controller as controller

from azrael.util import int2id, id2int
from azrael.test.test_leonard import startAzrael, stopAzrael

WSControllerBase = wscontroller.WSControllerBase

ipshell = IPython.embed


def test_ping_clacks():
    """
    Start services and send Ping to Clacks. Then terminate clacks and verify
    that the ping fails.
    """
    # Start the necessary services.
    clerk, ctrl, clacks = startAzrael('Websocket')

    # Ping the Clacks.
    assert ctrl.ping()

    # Shutdown the services.
    stopAzrael(clerk, clacks)

    # Connection must now be impossible.
    with pytest.raises(ConnectionRefusedError):
        WSControllerBase('ws://127.0.0.1:8080/websocket', 1)

    print('Test passed')


def test_ping_clerk():
    """
    Ping the Clerk instance via Clacks.
    """
    # Start the necessary services.
    clerk, ctrl, clacks = startAzrael('Websocket')

    # And send 'PING' command.
    assert ctrl.pingClacks()

    # Shutdown the services.
    stopAzrael(clerk, clacks)

    # And send 'PING' command.
    assert not ctrl.pingClacks()

    print('Test passed')


if __name__ == '__main__':
    test_ping_clacks()
    test_ping_clerk()
