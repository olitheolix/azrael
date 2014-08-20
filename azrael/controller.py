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
        return self._sendMessage(target + msg)

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
        ok, ret = self._recvMessage()
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

    def ping(self):
        """
        Send ping to Clerk.

        This method will block if there is no Clerk process.
        """
        return self.sendToClerk(config.cmd['ping_clerk'])

    def _newObjectTemplate(self, data: bytes):
        assert isinstance(data, bytes)
        return self.sendToClerk(config.cmd['new_template'] + data)

    def newObjectTemplate(self, cshape: bytes, geometry: bytes):
        """
        Create a new object template with ``geometry`` and collision shape
        ``cs``.
        """
        assert isinstance(cshape, bytes)
        assert isinstance(geometry, bytes)
        return self._newObjectTemplate(cshape + geometry)

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
        cmd = bytes([len(name.encode('utf8'))]) + name.encode('utf8')
        cshape = [0, 1, 1, 1]
        sv = btInterface.defaultData(position=pos, vlin=vel, cshape=cshape,
                                     scale=scale, radius=radius, imass=imass)
        cmd += templateID + btInterface.pack(sv).tostring()
        return self._spawn(cmd)

    def _getTemplateID(self, data: bytes):
        return self.sendToClerk(config.cmd['get_template_id'] + data)

    def getTemplateID(self, ctrl_id: bytes):
        """
        Retrieve the template ID  for ``ctrl_id``.
        """
        return self._getTemplateID(ctrl_id)

    def _getTemplate(self, data: bytes): 
        ok, data = self.sendToClerk(config.cmd['get_template'] + data)
        if ok:
            import collections
            data = json.loads(data)
            boosters = [types.booster(*_) for _ in data['boosters']]
            factories = [types.factory(*_) for _ in data['factories']]
            nt = collections.namedtuple('Generic', 'cs geo boosters factories')
            ret = nt(np.fromstring(bytes(data['cs'])),
                     np.fromstring(bytes(data['geo'])),
                     boosters, factories)
            return True, ret
        else:
            return ok, data

    def getTemplate(self, templateID: bytes):
        """
        Retrieve the data for ``templateID``.
        """
        return self._getTemplate(templateID)

    def _addTemplate(self, data: bytes): 
        return self.sendToClerk(config.cmd['add_template'] + data)

    @typecheck
    def addTemplate(self, cs: np.ndarray, geo: np.ndarray, boosters, factories):
        """
        Retrieve the data for ``templateID``.
        """
        cs = cs.tostring()
        geo = geo.tostring()
        d = {'cs': cs, 'geo': geo, 'boosters': boosters,
             'factories': factories}
        d = json.dumps(d).encode('utf8')

        return self._addTemplate(d)

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

    def _getAllObjectIDs(self):
        return self.sendToClerk(config.cmd['get_all_objids'])

    def getAllObjectIDs(self):
        """
        Set the ``force`` for ``ctrl_id``.
        """
        ok, data = self._getAllObjectIDs()
        if not ok:
            return ok, data

        data = [bytes(_) for _ in cytoolz.partition(config.LEN_ID, data)]
        return True, data

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
            src, data = self.recvMessage()

            # If not, wait a bit and then ask again.
            if src is None:
                time.sleep(0.1)
                continue

            # Prefix the message with our ID and return to sender.
            self.sendMessage(src, self.objID + data)
