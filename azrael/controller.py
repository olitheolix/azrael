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

import sys
import time
import cytoolz
import logging
import setproctitle
import multiprocessing
import zmq.eventloop.zmqstream
import numpy as np

import azrael.json as json
import azrael.util as util
import azrael.types as types
import azrael.config as config
import azrael.protocol as protocol
import azrael.bullet.btInterface as btInterface

from azrael.typecheck import typecheck

class ControllerBase(multiprocessing.Process):
    def __init__(self, obj_id=None):
        super().__init__()
        self.objID = obj_id

        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

    def setupZMQ(self):
        """
        Create and connect 0MQ sockets.
        """
        self.ctx = zmq.Context()
        self.sock_cmd = self.ctx.socket(zmq.REQ)
        self.sock_cmd.linger = 0
        self.sock_cmd.connect(config.addr_clerk)

    def close(self):
        """
        Close all sockets.
        """
        self.sock_cmd.close()
        self.logit.debug('Controller for <{}> has shutdown'.format(self.objID))

    def sendToClerk(self, data: bytes):
        """
        Send data to Clerk and return the response.
        """
        assert isinstance(data, bytes)
        self.sock_cmd.send(data)
        ret = self.sock_cmd.recv()
        if len(ret) == 0:
            return False, 'Invalid response from Clerk'

        if ret[0] == 0:
            return True, ret[1:]
        else:
            return False, ret[1:]

    def connectToClerk(self):
        """
        Obtain controller ID from Clerk.
        """
        if self.objID is None:
            ok, ret = self.sendToClerk(config.cmd['get_id'])
            if ok:
                self.objID = ret
        return self.objID

    def _sendMessage(self, data: bytes):
        """
        Send ``msg`` to ``target``.

        There is no guarantee that ``target`` will actually receive the
        message, or that it even exists.
        """
        # Sanity checks.
        assert isinstance(data, bytes)
        assert len(self.objID) == config.LEN_ID
        return self.sendToClerk(config.cmd['send_msg'] + self.objID + data)

    def sendMessage(self, target, msg):
        """
        Send ``msg`` to ``target``.

        There is no guarantee that ``target`` will actually receive the
        message, or that it even exists.
        """
        # Sanity checks.
        assert isinstance(target, bytes)
        assert isinstance(msg, bytes)
        assert len(target) == config.LEN_ID

        ok, data = protocol.ToClerk_SendMsg_Encode(self.objID, target, msg)
        ok, data = self.sendToClerk(config.cmd['send_msg'] + data)
        if not ok:
            return ok, data
        else:
            return protocol.FromClerk_SendMsg_Decode(data)

    def _recvMessage(self):
        return self.sendToClerk(config.cmd['get_msg'] + self.objID)

    def recvMessage(self):
        """
        Return next message for us from Clerk.

        This method is non-blocking and will return the message- source and
        body together.
        """
        # Sanity check.
        assert len(self.objID) == config.LEN_ID

        ok, data = protocol.ToClerk_RecvMsg_Encode(self.objID)
        ok, data = self.sendToClerk(config.cmd['get_msg'] + data)
        if not ok:
            return ok, data
        else:
            return protocol.FromClerk_RecvMsg_Decode(data)

    def ping(self):
        """
        Send ping to Clerk.

        This method will block if there is no Clerk process.
        """
        return self.sendToClerk(config.cmd['ping_clerk'])

    @typecheck
    def _newObjectTemplate(self, data: bytes):
        return self.sendToClerk(config.cmd['new_template'] + data)

    @typecheck
    def newObjectTemplate(self, cshape: np.ndarray, geometry: np.ndarray):
        """
        Create a new object template with ``geometry`` and collision shape
        ``cs``.
        """
        a, b = cshape.tostring(), geometry.tostring()
        ret = self._newObjectTemplate(a + b)
        return ret

    def _getGeometry(self, data: bytes):
        assert isinstance(data, bytes)
        return self.sendToClerk(config.cmd['get_geometry'] + data)

    def getGeometry(self, target: bytes):
        """
        Fetch geometry for ``target``.
        """
        assert isinstance(target, bytes)
        return self._getGeometry(target)

    def _spawn(self, data: bytes):
        assert isinstance(data, bytes)
        assert len(data) == data[0] + 1 + 8 + config.LEN_SV_BYTES
        return self.sendToClerk(config.cmd['spawn'] + data)

    def spawn(self, name: str, templateID: bytes, pos: np.ndarray,
              vel=np.zeros(3), scale=1, radius=1, imass=1):
        """
        Spawn the ``templateID`` object at ``pos`` and launch the associated
        ``name``controller for it.
        """
        cshape = [0, 1, 1, 1]
        sv = btInterface.defaultData(position=pos, vlin=vel, cshape=cshape,
                                     scale=scale, radius=radius, imass=imass)

        ok, data = protocol.ToClerk_Spawn_Encode(name, templateID, sv)
        ok, data = self.sendToClerk(config.cmd['spawn'] + data)
        if not ok:
            return ok, data
        else:
            return protocol.FromClerk_Spawn_Decode(data)

    def _getTemplateID(self, data: bytes):
        return self.sendToClerk(config.cmd['get_template_id'] + data)

    def getTemplateID(self, ctrl_id: bytes):
        """
        Retrieve the template ID  for ``ctrl_id``.
        """
        return self._getTemplateID(ctrl_id)

    def _getTemplateEncode(self, data):
        return data

    def _getTemplateDecode(self, data: bytes): 
        import collections
        data = json.loads(data)
        boosters = [types.booster(*_) for _ in data['boosters']]
        factories = [types.factory(*_) for _ in data['factories']]
        nt = collections.namedtuple('Generic', 'cs geo boosters factories')
        ret = nt(np.fromstring(bytes(data['cs'])),
                 np.fromstring(bytes(data['geo'])),
                 boosters, factories)
        return ret

    def getTemplate(self, templateID: bytes):
        """
        Retrieve the data for ``templateID``.
        """
        ok, data = protocol.ToClerk_GetTemplate_Encode(templateID)
        ok, data = self.sendToClerk(config.cmd['get_template'] + data)
        if not ok:
            return ok, data
        else:
            return protocol.FromClerk_GetTemplate_Decode(data)

    def _addTemplate(self, data: bytes): 
        return self.sendToClerk(config.cmd['add_template'] + data)

    @typecheck
    def addTemplate(self, cs: np.ndarray, geo: np.ndarray, boosters, factories):
        """
        Retrieve the data for ``templateID``.
        """
        ok, data = protocol.ToClerk_AddTemplate_Encode(cs, geo, boosters, factories)
        ok, data = self.sendToClerk(config.cmd['add_template'] + data)
        if not ok:
            return ok, data
        else:
            return protocol.FromClerk_AddTemplate_Decode(data)

    def _getStateVariables(self, data: bytes):
        return self.sendToClerk(config.cmd['get_statevar'] + data)

    def getStateVariables(self, ctrl_id):
        """
        Retrieve the state vector for ``ctrl_id``.
        """
        return self._getStateVariables(ctrl_id)

    def _suggestPosition(self, data: bytes):
        assert isinstance(data, bytes)
        return self.sendToClerk(config.cmd['suggest_pos'] + data)

    def _setStateVariables(self, data: bytes):
        assert isinstance(data, bytes)
        return self.sendToClerk(config.cmd['set_force'] + data)

    def setStateVariables(self, ctrl_id, force):
        """
        Set the ``force`` for ``ctrl_id``.
        """
        assert len(force) == 3
        assert isinstance(force, np.ndarray)

        pos = np.zeros(3, np.float64).tostring()
        force = force.astype(np.float64).tostring()

        return self._setStateVariables(ctrl_id + force + pos)

    def getAllObjectIDs(self):
        """
        Set the ``force`` for ``ctrl_id``.
        """
        ok, data = protocol.ToClerk_GetAllObjectIDs_Encode()
        ok, data = self.sendToClerk(config.cmd['get_all_objids'] + data)
        if not ok:
            return ok, data
        else:
            return protocol.FromClerk_GetAllObjectIDs_Decode(data)

    def run(self):
        """
        Prefix incoming message with our ID and return it to sender.
        """
        # Setup.
        self.setupZMQ()
        self.connectToClerk()

        # Rename the process. I cannot do this earlier because the
        # ``connectToClerk`` method will update self.objID from None to the
        # actual ID assigned to us.
        name = 'killme Controller {}'.format(util.id2int(self.objID))
        setproctitle.setproctitle(name)

        while True:
            # See if we got any messages.
            ok, data = self.recvMessage()
            if ok:
                src, msg = data
            else:
                src, msg = None, None

            # If not, wait a bit and then ask again.
            if src is None:
                time.sleep(0.1)
                continue

            # Prefix the message with our ID and return to sender.
            print('Ctrl (received, sent): ', msg, self.objID + msg)
            self.sendMessage(src, self.objID + msg)
