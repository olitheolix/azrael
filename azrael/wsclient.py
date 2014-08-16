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

import azrael.util as util
import azrael.config as config
import azrael.bullet.btInterface as btInterface

ipshell = IPython.embed


class WebsocketClient:
    """
    The timeout value is unimportant until the connection is actually
    established. Then it determines how long the 'send' and 'recv'
    methods will block until they raise an error. The timeout is in
    seconds.
    """
    def __init__(self, url, timeout=20):
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

    def __del__(self):
        if self.ws is not None:
            self.ws.close()

    def sendToClacks(self, data):
        """
        Send ``data`` through Websocket.
        """
        assert isinstance(data, bytes)
        self.ws.send_binary(data)

    def recvFromClacks(self):
        """
        Read from Websocket and analyse the error status.
        """
        ret = self.ws.recv()
        assert isinstance(ret, bytes)
        if len(ret) == 0:
            return 'Invalid response from Clacks', False

        if ret[0] == 0:
            return True, ret[1:]
        else:
            return False, ret[1:]

    def ping(self):
        """
        Ping Clacks.
        """
        self.sendToClacks(config.cmd['ping_clacks'])
        ok, msg = self.recvFromClacks()
        if not ok:
            return False
        else:
            return (msg.decode('utf8') == 'pong clacks')

    def ping_clerk(self):
        """
        Ping Clerk.
        """
        self.sendToClacks(config.cmd['ping_clerk'])
        ok, msg = self.recvFromClacks()
        if not ok:
            return False
        else:
            return (msg.decode('utf8') == 'pong clerk')

    def getID(self):
        """
        Get controller ID associated with this connection.
        """
        self.sendToClacks(config.cmd['get_id'])
        return self.recvFromClacks()

    def spawn(self, name: str, templateID: bytes, pos: np.ndarray,
              vel=np.zeros(3), scale=1, radius=1, imass=1):
        """
        Spawn the ``templateID`` object at ``pos`` and launch the associated
        ``name``controller for it.

        The new object will have initial velocity ``vel``.
        """
        assert isinstance(name, str)
        assert isinstance(pos, np.ndarray)
        assert isinstance(vel, np.ndarray)
        assert pos.dtype == np.float64
        assert vel.dtype == np.float64

        cshape = [0, 1, 1, 1]
        cmd = config.cmd['spawn']
        cmd += bytes([len(name.encode('utf8'))]) + name.encode('utf8')
        sv = btInterface.defaultData(position=pos, vlin=vel, cshape=cshape,
                                     scale=scale, radius=radius, imass=imass)
        cmd += templateID + btInterface.pack(sv).tostring()
        self.sendToClacks(cmd)
        return self.recvFromClacks()

    def setForce(self, target: bytes, force: np.ndarray, relpos: np.ndarray):
        """
        Apply ``force`` to ``target``.
        """
        assert isinstance(target, bytes)
        assert isinstance(force, np.ndarray)
        assert isinstance(relpos, np.ndarray)
        assert len(force) == len(relpos) == 3
        force = force.astype(np.float64).tostring()
        relpos = relpos.astype(np.float64).tostring()
        cmd = config.cmd['set_force'] + target + force + relpos
        self.sendToClacks(cmd)
        return self.recvFromClacks()

    def suggestPosition(self, target: bytes, pos: np.ndarray):
        """
        Suggest to move ``target`` instantly to ``position``.
        """
        assert isinstance(target, bytes)
        assert isinstance(pos, np.ndarray)
        assert len(pos) == 3

        pos = pos.astype(np.float64)
        pos = pos.tostring()
        cmd = config.cmd['suggest_pos'] + target + pos
        self.sendToClacks(cmd)
        return self.recvFromClacks()

    def newObjectTemplate(self, cshape: bytes, geometry: bytes):
        """
        Create a new raw object with ``geometry`` and collision shape ``cs``. 

        The length of the ``geometry`` byte stream must be a multiple of 9 or
        the server will reject it. The reason is that ever triangle has three
        vertices and every vertex has a 3-dimensional position in space. A
        single triangle thus consists of exactly 9 floating point values.
        """
        assert isinstance(cshape, bytes)
        assert isinstance(geometry, bytes)
        assert len(geometry) % 9 == 0

        cmd = config.cmd['new_template'] + cshape + geometry
        self.sendToClacks(cmd)
        return self.recvFromClacks()

    def getGeometry(self, target: bytes):
        """
        Return the geometry for ``target``.
        """
        assert isinstance(target, bytes)
        self.sendToClacks(config.cmd['get_geometry'] + target)
        return self.recvFromClacks()

    def sendMessage(self, target, msg):
        """
        Dispatch a message to another controller.

        The WS handler will use its own Controller object to do the clerk.
        """
        self.sendToClacks(config.cmd['send_msg'] + target + msg)
        return self.recvFromClacks()

    def recvMessage(self):
        """
        Check for new messages.

        The WS handler will use its own Controller to do the fetch.
        """
        self.sendToClacks(config.cmd['get_msg'])
        ok, ret = self.recvFromClacks()

        if ok:
            if len(ret) < config.LEN_ID:
                src, data = None, b''
            else:
                # Protocol: sender ID, data
                src, data = ret[:config.LEN_ID], ret[config.LEN_ID:]
        else:
            src, data = None, b''

        # Return message- source and body.
        return src, data

    def getStateVariables(self, ctrl_ids):
        """
        Return the state variables for all ``ctrl_ids``.
        """
        if isinstance(ctrl_ids, (list, tuple)):
            ctrl_ids = b''.join(ctrl_ids)
            
        assert isinstance(ctrl_ids, bytes)
        self.sendToClacks(config.cmd['get_statevar'] + ctrl_ids)
        ok, ret = self.recvFromClacks()
        if not ok:
            return False, {}

        # The available data must be an integer multiple of an ID plus SV.
        l = config.LEN_ID + config.LEN_SV_BYTES
        assert (len(ret) % l) == 0

        # Return a dictionary of SV variables. The dictionary key is the
        # object ID (the state variables - incidentally - are another
        # dictionary).
        out = {}
        for data in cytoolz.partition(l, ret):
            data = bytes(data)
            sv = np.fromstring(data[config.LEN_ID:])
            out[data[:config.LEN_ID]] = btInterface.unpack(sv)
        return True, out

    def getAllObjectIDs(self):
        """
        Return all object IDs in the simulation.
        """
        self.sendToClacks(config.cmd['get_all_objids'])
        ok, ret = self.recvFromClacks()
        if not ok:
            return False, []

        # The available data must be an integer multiple of an ID plus SV.
        assert (len(ret) % config.LEN_ID) == 0

        # Split the byte string into a list of object IDs.
        out = [bytes(_) for _ in cytoolz.partition(config.LEN_ID, ret)]
        return True, out

    def getTemplateID(self, ctrl_id):
        """
        Return the state variables for ``ctrl_id``.
        """
        assert isinstance(ctrl_id, bytes)
        self.sendToClacks(config.cmd['get_template_id'] + ctrl_id)
        ok, ret = self.recvFromClacks()
        if not ok:
            return False, None
        else:
            return True, ret
