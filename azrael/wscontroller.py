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
Websocket version of ``ControllerBase``.

This version of the `Controller` exists as a proof-of-concept to demonstrate
that web browser (ie JavaScript) can interact with Azrael.

The class itself behaves like the original ``ControllerBase`` which is why the
same unit tests run on both versions. However, it also requires a running
``Clacks`` server to handle the Websocket connection.

For Python users it makes little sense to use this library as it first sends
all commands via a Websocket to ``Clacks`` which will then relay the command
via ZeroMQ to ``Clerk``.

This client uses the Websocket library from
https://github.com/liris/websocket-client
"""
import time
import IPython
import websocket
import numpy as np

import azrael.controller
import azrael.config as config

from azrael.typecheck import typecheck

ipshell = IPython.embed


class WSControllerBase(azrael.controller.ControllerBase):
    """
    Websocket version of ``ControllerBase``.

    To use this class a ``Clacks`` instance must be running.

    :param str url: address of ``Clacks`` (eg 'ws://127.0.0.1:8080/websocket')
    :param float timeout: Websocket timeout.
    """
    @typecheck
    def __init__(self, url: str, timeout: (int, float)=20, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # URL of Clacks server.
        self.url = url

        # Websocket handle (will be initialised below).
        self.ws = None

        # Make several attempts to establish the connection before giving up.
        for ii in range(5):
            try:
                self.ws = websocket.create_connection(url, timeout)
                break
            except ConnectionRefusedError as err:
                if ii >= 3:
                    raise err
                else:
                    time.sleep(0.1)

        # Retrieve the object ID. Fixme: if user has specified an ID via the
        # constructor then the Controller instance in Clacks must heed it.
        ok, self.objID = self.sendToClacks(config.cmd['get_id'])
        
    def __del__(self):
        """
        Shutdown the Websocket when this object is garbage collected.
        """
        if self.ws is not None:
            self.ws.close()

    @typecheck
    def sendToClerk(self, data: bytes):
        """
        Proxy all communication via the Controller in Clerk.

        This method replaces the original ``sendToClerk`` method and relays the
        data to ``sendToClacks`` instead.

        :param bytes data: this data will be sent to Clacks server.
        :return: see ``sendToClacks``.
        """
        return self.sendToClacks(data)

    @typecheck
    def sendToClacks(self, data: bytes):
        """
        Send ``data`` to Clacks, wait for reply and return its content.

        :param bytes data: the payload
        :return: (ok, data)
        :rtype: (bool, bytes)
        """
        # Send payload to Clacks and wait for reply.
        self.ws.send_binary(data)
        ret = self.ws.recv()

        # Check for errors.
        assert isinstance(ret, bytes)
        if len(ret) == 0:
            return 'Invalid response from Clacks', False

        # Extract the 'Ok' flag and return the rest verbatim.
        if ret[0] == 0:
            return True, ret[1:]
        else:
            return False, ret[1:]

    def pingClerk(self):
        """
        Ping Clerk.

        This method return **True** if the Ping was successful. Otherwise the
        Websocket library will (most likely) raise a Timeout error.

        :return: ok flag.
        :rtype: bool
        """
        ok, msg = self.sendToClacks(config.cmd['ping_clerk'])
        if not ok:
            return False
        else:
            return (msg.decode('utf8') == 'pong clerk')
