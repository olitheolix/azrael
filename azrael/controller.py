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
import azrael.parts as parts
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

        # Associate the encoding and decoding functions for every command.
        self.codec = {
            'send_msg': (protocol.ToClerk_SendMsg_Encode,
                         protocol.FromClerk_SendMsg_Decode),
            'recv_msg': (protocol.ToClerk_RecvMsg_Encode,
                        protocol.FromClerk_RecvMsg_Decode),
            'get_geometry': (protocol.ToClerk_GetGeometry_Encode,
                        protocol.FromClerk_GetGeometry_Decode),
            'spawn': (protocol.ToClerk_Spawn_Encode,
                        protocol.FromClerk_Spawn_Decode),
            'get_template_id': (protocol.ToClerk_GetTemplateID_Encode,
                        protocol.FromClerk_GetTemplateID_Decode),
            'get_template': (protocol.ToClerk_GetTemplate_Encode,
                        protocol.FromClerk_GetTemplate_Decode),
            'add_template': (protocol.ToClerk_AddTemplate_Encode,
                        protocol.FromClerk_AddTemplate_Decode),
            'get_statevar': (protocol.ToClerk_GetStateVariable_Encode,
                        protocol.FromClerk_GetStateVariable_Decode),
            'set_force': (protocol.ToClerk_SetForce_Encode,
                        protocol.FromClerk_SetForce_Decode),
            'get_all_objids': (protocol.ToClerk_GetAllObjectIDs_Encode,
                        protocol.FromClerk_GetAllObjectIDs_Decode),
            'suggest_pos': (protocol.ToClerk_SuggestPosition_Encode,
                        protocol.FromClerk_SuggestPosition_Decode),
            }

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

    @typecheck
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

    def serialiseAndSend(self, cmd, *args):
        assert cmd in config.cmd
        assert cmd in self.codec

        ToClerk_Encode, FromClerk_Decode = self.codec[cmd]

        ok, data = ToClerk_Encode(*args)
        ok, data = self.sendToClerk(config.cmd[cmd] + data)
        if not ok:
            return ok, data
        else:
            return FromClerk_Decode(data)

    @typecheck
    def sendMessage(self, target: bytes, msg: bytes):
        """
        Send ``msg`` to ``target``.

        There is no guarantee that ``target`` will actually receive the
        message, or that it even exists.
        """
        # Sanity checks.
        assert isinstance(target, bytes)
        assert isinstance(msg, bytes)
        assert len(target) == config.LEN_ID

        return self.serialiseAndSend('send_msg', self.objID, target, msg)

    def recvMessage(self):
        """
        Return next message for us from Clerk.

        This method is non-blocking and will return the message- source and
        body together.
        """
        # Sanity check.
        assert len(self.objID) == config.LEN_ID

        return self.serialiseAndSend('recv_msg', self.objID)

    def ping(self):
        """
        Send ping to Clerk.

        This method will block if there is no Clerk process.
        """
        return self.sendToClerk(config.cmd['ping_clerk'])

    @typecheck
    def getGeometry(self, target: bytes):
        """
        Fetch geometry for ``target``.
        """
        assert isinstance(target, bytes)

        return self.serialiseAndSend('get_geometry', target)

    @typecheck
    def spawn(self, name: bytes, templateID: bytes, pos: (np.ndarray, list),
              vel: (np.ndarray, list)=np.zeros(3), scale=1, radius=1, imass=1):
        """
        Spawn the ``templateID`` object at ``pos`` and launch the associated
        ``name``controller for it.
        """
        cshape = [0, 1, 1, 1]
        sv = btInterface.defaultData(position=pos, vlin=vel, cshape=cshape,
                                     scale=scale, radius=radius, imass=imass)

        return self.serialiseAndSend('spawn', name, templateID, sv)

    @typecheck
    def getTemplateID(self, objID: bytes):
        """
        Retrieve the template ID for ``objID``.
        """
        return self.serialiseAndSend('get_template_id', objID)

    @typecheck
    def getTemplate(self, templateID: bytes):
        """
        Retrieve the data for ``templateID``.
        """
        return self.serialiseAndSend('get_template', templateID)

    @typecheck
    def addTemplate(self, templateID: bytes, cs: np.ndarray, geo: np.ndarray,
                    boosters: (list, tuple), factories: (list, tuple)):
        """
        Retrieve the data for ``templateID``.
        """
        return self.serialiseAndSend(
            'add_template', templateID, cs, geo, boosters, factories)

    @typecheck
    def getStateVariables(self, objIDs: (list, tuple, bytes)):
        """
        Retrieve the state vector for all ``objIDs``.
        """
        if isinstance(objIDs, bytes):
            objIDs = [objIDs]

        for objID in objIDs:
            assert isinstance(objID, bytes)
            assert len(objID) == config.LEN_ID

        return self.serialiseAndSend('get_statevar', objIDs)

    @typecheck
    def suggestPosition(self, target: bytes, pos: np.ndarray):
        """
        Suggest to move ``target`` instantly to ``position``.
        """
        assert isinstance(target, bytes)
        assert isinstance(pos, np.ndarray)
        assert len(pos) == 3

        return self.serialiseAndSend('suggest_pos', target, pos)

    @typecheck
    def setForce(self, ctrl_id: bytes, force: np.ndarray):
        """
        Set the ``force`` for ``ctrl_id``.
        """
        assert len(force) == 3
        assert isinstance(force, np.ndarray)

        pos = np.zeros(3, np.float64)

        return self.serialiseAndSend('set_force', ctrl_id, force, pos)

    def getAllObjectIDs(self):
        """
        Set the ``force`` for ``ctrl_id``.
        """
        return self.serialiseAndSend('get_all_objids')

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
            self.sendMessage(src, self.objID + msg)
