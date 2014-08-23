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
A simple Websocket client in Python.

The client uses the Websocket library from
https://github.com/liris/websocket-client

As a standalone script it will connect to the Clacks server, send
a message, and then retrieve it again.

The WebsocketClient class only deals with bytes and will raise an assertion
error if you pass anything else to its 'send' method, or 'recv' receives
anything but bytes (usually because the server assumes a non-binary socket).
"""
import time
import cytoolz
import IPython
import websocket
import numpy as np

import azrael.controller
import azrael.util as util
import azrael.config as config
import azrael.bullet.btInterface as btInterface

ipshell = IPython.embed


class ControllerBaseWS(azrael.controller.ControllerBase):
    def __init__(self, url, timeout=20, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.url = url
        self.ws = None

        # Try a few times to establish the connection.
        for ii in range(5):
            try:
                self.ws = websocket.create_connection(url, timeout)
                break
            except ConnectionRefusedError as err:
                if ii >= 3:
                    raise err
                else:
                    time.sleep(0.1)
        ok, self.objID = self.sendToClacks(config.cmd['get_id'])
        
    def __del__(self):
        if self.ws is not None:
            self.ws.close()

    def sendToClerk(self, data):
        """
        Proxy all communication via the Controller in Clerk.
        """
        return self.sendToClacks(data)

    def sendToClacks(self, data):
        """
        Read from Websocket and analyse the error status.
        """
        assert isinstance(data, bytes)

        self.ws.send_binary(data)
        ret = self.ws.recv()

        assert isinstance(ret, bytes)
        if len(ret) == 0:
            return 'Invalid response from Clacks', False

        if ret[0] == 0:
            return True, ret[1:]
        else:
            return False, ret[1:]

    def pingClerk(self):
        """
        Ping Clerk.
        """
        ok, msg = self.sendToClacks(config.cmd['ping_clerk'])
        if not ok:
            return False
        else:
            return (msg.decode('utf8') == 'pong clerk')

