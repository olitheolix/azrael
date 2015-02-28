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
Test the Websocket version of the Client.

The tests for ``Client`` automatically test the Websocket
version. However, some tests, especially for the initial connection are
specific to this client type. Only these are covered here.
"""

import sys
import pytest
import IPython

import azrael.client
import azrael.wsclient

from azrael.test.test_clerk import killAzrael

ipshell = IPython.embed

Client = azrael.client.Client
WSClient = azrael.wsclient.WSClient


def test_custom_objid():
    """
    Create two clients. The first automatically gets an ID assigned,
    whereas the second one specifies one explicitly.

    This behaviour matches that of `Client`` but is not automatically
    inherited because the ``WSClient`` is not a client itself but a
    wrapper to communicate with the client instance in Clacks.
    """
    killAzrael()

    # Start Clerk.
    clerk = azrael.clerk.Clerk()
    clerk.start()

    # Start Clacks.
    clacks = azrael.clacks.ClacksServer()
    clacks.start()

    ip, port = '127.0.0.1', 8080

    # Instantiate a WSClient without specifiying an object ID.
    client_0 = azrael.wsclient.WSClient(ip, port)

    # Ping Clerk to verify the connection is live.
    ret = client_0.ping()
    assert (ret.ok, ret.data) == (True, 'pong clerk')

    # Instantiate another WSClient. This time specify an ID. Note: the ID
    # need not exist albeit object specific commands will subsequently fail.
    client_1 = azrael.wsclient.WSClient(ip, port)

    # Ping Clerk again to verify the connection is live.
    ret = client_1.ping()
    assert (ret.ok, ret.data) == (True, 'pong clerk')

    # Shutdown the system.
    clerk.terminate()
    clacks.terminate()
    clerk.join(timeout=3)
    clacks.join(timeout=3)

    # Shutdown the services.
    killAzrael()
    print('Test passed')


if __name__ == '__main__':
    test_custom_objid()
