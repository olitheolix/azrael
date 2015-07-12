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
Websocket version of ``Client``.

This version of the `Client` exists as a proof-of-concept to demonstrate
that web browser (ie JavaScript) can interact with Azrael.

The class itself behaves like the original ``Client`` which is why the
same unit tests run on both versions. However, it also requires a running
``WebServer`` server to handle the Websocket connection.

For Python users it makes little sense to use this library as it first sends
all commands via a Websocket to ``WebServer`` which will then relay the command
via ZeroMQ to ``Clerk``.

This client uses the Websocket library from
https://github.com/liris/websocket-client
"""
import time
import websocket

import azrael.util
import azrael.client

from azrael.types import typecheck, RetVal


class WSClient(azrael.client.Client):
    """
    Websocket version of ``Client``.

    To use this class a ``WebServer`` instance must be running.

    :param str ip: IP of ``WebServer`` (eg '127.0.0.1')
    :param int port: port of ``WebServer`` (eg '8080')
    :param float timeout: Websocket timeout.
    """
    @typecheck
    def __init__(self, ip: str, port: int, timeout: (int, float)=20):
        super().__init__()

        # URL of WebServer server.
        self.url = 'ws://{ip}:{port}/websocket'.format(ip=ip, port=port)

        # Websocket handle (will be initialised below).
        self.ws = None

        # Make several attempts to establish the connection before giving up.
        for ii in range(5):
            try:
                self.ws = websocket.create_connection(self.url, timeout)
                break
            except ConnectionRefusedError as err:
                if ii >= 3:
                    raise err
                else:
                    time.sleep(0.1)

    def __del__(self):
        """
        Shutdown the Websocket when this object is garbage collected.
        """
        if self.ws is not None:
            self.ws.close()

    @typecheck
    def send(self, data: str):
        """
        Overloaded method to write to the Websocket instead.

        :param str data: data in string format (usually a JSON string).
        :return: None
        """
        self.ws.send(data)

    def recv(self):
        """
        Overloaded method to read from the Websocket instead.

        :return: received data as a string (usuallay a JSON string).
        :rtype: ste
        """
        return self.ws.recv()

    def pingWebserver(self):
        """
        Ping WebServer.

        This method returns **True** if WebServer responds. If WebServer does not
        respond then the Websocket will (most likely) raise a Timeout error
        because it does not receive anything.

        :return: **True** if Ping was successful.
        :rtype: bool
        """
        try:
            ret = self.sendToClerk('ping_webserver', None)
        except websocket.WebSocketConnectionClosedException:
            return RetVal(False, 'Websocket Error', None)

        if not ret.ok:
            return ret
        else:
            return RetVal(True, None, 'pong webserver')
