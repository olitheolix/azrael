# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

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

import pyazrael.client
import azutils as util

from pyazrael.aztypes import typecheck, RetVal


class WSClient(pyazrael.client.Client):
    """
    Websocket version of ``Client``.

    To use this class a ``WebServer`` instance must be running.

    :param str addr_webapi: IP of ``WebServer`` (eg '127.0.0.1')
    :param int port_webapi: port of ``WebServer`` (eg '8080')
    :param float timeout: Websocket timeout.
    """
    @typecheck
    def __init__(self, addr_webapi: str, port_webapi: int, timeout: (int, float)=20):
        super().__init__()

        # URL of WebServer server.
        self.url = 'ws://{ip}:{port}/websocket'.format(ip=addr_webapi, port=port_webapi)

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
