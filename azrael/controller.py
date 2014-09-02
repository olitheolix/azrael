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
Python interface for Clerk/Azrael.

You should inherit this class and overload the ``run`` method with your own
version to intelligently control the object based on its position, speed, and
other objects in the vicinity.

There can be arbitrarily many Controller instances connected to the same Clerk
yet they need not run on the same machine.

The controller implemented in this file uses ZeroMQ. If you want/need a
Websocket version (eg. JavaScript developers) then use the version provided in
`wscontroller.py`. Their feature set is identical.
"""

import sys
import zmq
import time
import logging
import setproctitle
import multiprocessing
import numpy as np

import azrael.util as util
import azrael.parts as parts
import azrael.config as config
import azrael.protocol as protocol
import azrael.bullet.btInterface as btInterface
import azrael.bullet.bullet_data as bullet_data

from azrael.typecheck import typecheck


class ControllerBase(multiprocessing.Process):
    """
    A Client for Clerk/Azrael.

    This class is little more than a collection of wrappers around the commands
    provided by Clerk. These wrappers may do some sanity checks on the input
    data, but mostly they merely encode the data to binary format, send the
    result to Clerk, wait for a replay, decode the reply back to Python types,
    and pass that back to the caller.

    :param str name: name of Python script to start.
    :param bytes objID: ID of object with which this controller is associated.
    :raises: None
    """
    @typecheck
    def __init__(self, obj_id: bytes=None):
        super().__init__()

        # The object ID with which this controller is associated.
        self.objID = obj_id

        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

        # Associate the encoding and decoding functions for every command.
        self.codec = {
            'send_msg': (
                protocol.ToClerk_SendMsg_Encode,
                protocol.FromClerk_SendMsg_Decode),
            'recv_msg': (
                protocol.ToClerk_RecvMsg_Encode,
                protocol.FromClerk_RecvMsg_Decode),
            'get_geometry': (
                protocol.ToClerk_GetGeometry_Encode,
                protocol.FromClerk_GetGeometry_Decode),
            'spawn': (
                protocol.ToClerk_Spawn_Encode,
                protocol.FromClerk_Spawn_Decode),
            'get_template_id': (
                protocol.ToClerk_GetTemplateID_Encode,
                protocol.FromClerk_GetTemplateID_Decode),
            'get_template': (
                protocol.ToClerk_GetTemplate_Encode,
                protocol.FromClerk_GetTemplate_Decode),
            'add_template': (
                protocol.ToClerk_AddTemplate_Encode,
                protocol.FromClerk_AddTemplate_Decode),
            'get_statevar': (
                protocol.ToClerk_GetStateVariable_Encode,
                protocol.FromClerk_GetStateVariable_Decode),
            'set_force': (
                protocol.ToClerk_SetForce_Encode,
                protocol.FromClerk_SetForce_Decode),
            'get_all_objids': (
                protocol.ToClerk_GetAllObjectIDs_Encode,
                protocol.FromClerk_GetAllObjectIDs_Decode),
            'suggest_pos': (
                protocol.ToClerk_SuggestPosition_Encode,
                protocol.FromClerk_SuggestPosition_Decode),
            'control_parts': (
                protocol.ToClerk_ControlParts_Encode,
                protocol.FromClerk_ControlParts_Decode),
            }

    def setupZMQ(self):
        """
        Create and connect ZeroMQ sockets.
        """
        self.ctx = zmq.Context()
        self.sock_cmd = self.ctx.socket(zmq.REQ)
        self.sock_cmd.linger = 0
        self.sock_cmd.connect(config.addr_clerk)

    def close(self):
        """
        Close all ZeroMQ sockets.
        """
        self.sock_cmd.close()
        self.logit.debug('Controller for <{}> has shutdown'.format(self.objID))

    @typecheck
    def sendToClerk(self, data: bytes):
        """
        Send data to Clerk and return the response.

        This method blocks until a response arrives. Upon a reply it inspects
        the response to determine whether the request succeeded or not. This is
        returned as the first argument in the 'ok' flag.

        :param bytes data: this will be sent verbatim to Clerk.
        :return: (ok, data)
        :rtype: (bool, bytes)
        """
        # Send data and wait for response.
        self.sock_cmd.send(data)
        ret = self.sock_cmd.recv()

        # We should always receive at least one byte to indicate whether the
        # command was successful or not.
        if len(ret) == 0:
            return False, 'Invalid response from Clerk'

        if ret[0] == 0:
            # Command was successful.
            return True, ret[1:]
        else:
            # Command was unsuccessful.
            return False, ret[1:]

    def connectToClerk(self):
        """
        Obtain a unique object ID from Clerk.

        This command does nothing if the Controller already has an ID (ie. if
        its self.objID attribute is not *None*).

        .. note::
           Every object in the simulation should have at most one controller
           associated with it but this is currently not enforced. It is thus
           currently possible via this method to create a Controller for a
           non-existing object. This is fine for debugging and demo
           purposes. In the long term this method will probably vanish.

        :return bytes: the ID of the object with which we are associated.
        :rtype: bytes
        """
        if self.objID is None:
            # Ask Clerk for a new ID.
            ok, ret = self.sendToClerk(config.cmd['get_id'])
            if ok:
                self.objID = ret
        return self.objID

    @typecheck
    def serialiseAndSend(self, cmd: str, *args):
        """
        Serialise ``args``, send it to Clerk, and return de-serialised reply.

        This method is a convenience wrapper around the
        encode-send-receive-decode cycle that constitutes every request to
        Clerk.

        The value of ``cmd`` determines the encoding of ``args``. Note that
        this method accepts a variable number of parameters in ``args`` yet
        does not actually inspect them. Instead it passes them on verbatim to
        the respective encoding function in the ``protocol`` module.

        The method returns an (ok, data) tuple. If the `ok` flag is **True**
        then `data` will contain the de-serialised content in terms of
        Python/NumPy types. Otherwise it contains an error message.

        :param str cmd: name of command.
        :return: (ok, data)
        :rtype: (bool, bytes) or (bool, str)
        """
        # Sanity checks.
        assert cmd in config.cmd
        assert cmd in self.codec

        # Convenience.
        ToClerk_Encode, FromClerk_Decode = self.codec[cmd]

        # Encode the arguments and send them to Clerk.
        ok, data = ToClerk_Encode(*args)
        ok, data = self.sendToClerk(config.cmd[cmd] + data)
        if not ok:
            # There was an error. The 'data' field will thus contain an error
            # message.
            return False, data
        else:
            # Command completed without error. Return the decode output.
            return FromClerk_Decode(data)

    def ping(self):
        """
        Send a Ping to Clerk.

        This method will block if there is no Clerk process.

        :param str cmd: name of command.
        :return: (ok, data)
        :rtype: (bool, bytes) or (bool, str)
        """
        return self.sendToClerk(config.cmd['ping_clerk'])

    @typecheck
    def sendMessage(self, target: bytes, msg: bytes):
        """
        Send ``msg`` to ``target``.

        There is no guarantee that ``target`` will actually receive the
        message.

        This method does not verify that ``target`` even exists.

        :param str cmd: name of command.
        :return: (ok, data)
        :rtype: (bool, bytes) or (bool, str)
        """
        # Sanity checks.
        assert len(target) == config.LEN_ID
        return self.serialiseAndSend('send_msg', self.objID, target, msg)

    def recvMessage(self):
        """
        Return the next message posted to us.

        If there is no message for us then return an empty message (the 'ok'
        flag will still be **True**).

        :return: (ok, data)
        :rtype: (bool, bytes) or (bool, str)
        """
        # Sanity check.
        assert len(self.objID) == config.LEN_ID
        return self.serialiseAndSend('recv_msg', self.objID)

    @typecheck
    def getGeometry(self, templateID: bytes):
        """
        Return the geometry for ``templateID`` as a NumPy array.

        .. note::
           This method will return the geometry for a particular *template*,
           *not* a particular object. Use ``getTemplateID`` to determine the
           template ID for a given object ID.

        :param bytes templateID: ID for which to return the geometry.
        :return: (ok, data)
        :rtype: (bool, np.ndarray) or (bool, str)
        """
        return self.serialiseAndSend('get_geometry', templateID)

    @typecheck
    def spawn(self, name: bytes, templateID: bytes,
              pos: (np.ndarray, list),
              vel: (np.ndarray, list)=np.zeros(3),
              orient: (np.ndarray, list)=[0, 0, 0, 1],
              scale=1, radius=1, imass=1):
        """
        Spawn the ``templateID`` object at ``pos`` with velocity ``vel``.

        If ``name`` is not **None** then Clerk will launch a Controller process
        for the newly create object. If it cannot find the correct program then
        no object is spawned and the command returns with an error.

        To only spawn an object but not create a new Controller process pass
        **None** for the ``name`` argument.

        :param bytes name: specify the Controller process to launch.
        :param bytes templateID: template from which to spawn the object.
        :param 3-vec pos: object position
        :param 3-vec vel: initial velocity
        :param 4-vec orient: initial orientation
        :param float scale: scale entire object by this factor.
        :param float radius: specify the bounding sphere radius of the object.
        :param float imass: inverse of object mass.
        :return: (ok, data)
        :rtype: (bool, np.ndarray) or (bool, str)
        """
        cshape = [0, 1, 1, 1]
        sv = bullet_data.BulletData(position=pos, velocityLin=vel,
                                    cshape=cshape, scale=scale,
                                    radius=radius, imass=imass,
                                    orientation=orient)
        return self.serialiseAndSend('spawn', name, templateID, sv)

    def controlParts(self, objID: bytes, cmd_boosters: (list, tuple),
                     cmd_factories: (list, tuple)):
        """
        Issue control commands to object parts.

        Boosters can be activated with a scalar force that will apply according
        to their orientation. The commands themselves must be
        ``parts.CmdBooster`` instances.

        Factories can spawn objects. Their command syntax is defined in the
        ``parts`` module. The commands themselves must be
        ``parts.CmdFactory`` instances.

        :param bytes objID: object ID.
        :param list cmd_booster: booster commands.
        :param list cmd_factory: factory commands.
        :return: (True, (b'',)) or (False, error-message)
        :rtype: (bool, (bytes, )) or (bool, str)
        :raises: None
        """
        return self.serialiseAndSend(
            'control_parts', objID, cmd_boosters, cmd_factories)

    @typecheck
    def getTemplateID(self, objID: bytes):
        """
        Return the template ID from which ``objID`` was spawned.

        If ``objID`` does not exist in the simulation then return an error.

        :param bytes objID: ID of spawned object.
        :return: (ok, objID)
        :rtype: (bool, np.ndarray) or (bool, str)
        """
        return self.serialiseAndSend('get_template_id', objID)

    @typecheck
    def getTemplate(self, templateID: bytes):
        """
        Return the entire template data for ``templateID``.

        If you are only interested in the geometry then use ``getGeometry``
        instead.

        :param bytes templateID: return the description of this template.
        :return: (ok, (cs, geo, boosters, factories))
        """
        return self.serialiseAndSend('get_template', templateID)

    @typecheck
    def addTemplate(self, templateID: bytes, cs: np.ndarray, geo: np.ndarray,
                    boosters: (list, tuple), factories: (list, tuple)):
        """
        Add a new ``templateID`` to the system.

        Henceforth Clerk can spawn ``templateID`` objects.

        Return an error if ``templateID`` already exists.

        :param bytes templateID: the name of the new template.
        :param bytes cs: collision shape
        :param bytes geo: object geometry
        :param parts.Booster boosters: list of Booster instances.
        :param parts.Factory boosters: list of Factory instances.
        :return: (ok, template ID)
        :rtype: (bool, bytes)
        :raises: None
        """
        return self.serialiseAndSend(
            'add_template', templateID, cs, geo, boosters, factories)

    @typecheck
    def getStateVariables(self, objIDs: (list, tuple, bytes)):
        """
        Return the State Variables for all ``objIDs`` as a dictionary.

        :param list objIDs: object ID (or list thereof)
        :return: (ok, dict)
        :rtype: (bool, bytes)
        :raises: None
        """
        if isinstance(objIDs, bytes):
            # Wrap a single objID into a list for uniformity.
            objIDs = [objIDs]

        # Sanity check: every objID in the list must have the correct type and
        # length.
        for objID in objIDs:
            assert isinstance(objID, bytes)
            assert len(objID) == config.LEN_ID

        # Pass on the request to Clerk.
        return self.serialiseAndSend('get_statevar', objIDs)

    @typecheck
    def suggestPosition(self, objID: bytes, pos: np.ndarray):
        """
        Suggest to move ``objID`` instantly to ``pos``.

        .. note::
           This is a debug function. The physics engine may not heed this
           request.

        :param bytes objID: the object to move.
        :return: (ok, b'')
        :rtype: (bool, bytes)
        :raises: None
        """
        assert len(pos) == 3
        return self.serialiseAndSend('suggest_pos', objID, pos)

    @typecheck
    def setForce(self, objID: bytes, force: np.ndarray):
        """
        Apply ``force`` to ``objID``.

        The force is always applied at the centre of mass.

        :param bytes objID: the object for which to apply a force.
        :param ndarray force: force vector.
        :return: (ok, b'')
        :rtype: (bool, bytes)
        :raises: None
        """
        assert len(force) == 3
        pos = np.zeros(3, np.float64)
        return self.serialiseAndSend('set_force', objID, force, pos)

    def getAllObjectIDs(self):
        """
        Return all ``objIDs`` in the simulation.

        :param bytes dummy: irrelevant
        :return: (ok, list-of-objIDs)
        :rtype: (bool, list)
        """
        return self.serialiseAndSend('get_all_objids')

    def run(self):
        """
        Wait for messages sent to us and bounce them back.

        This method is a stub. Override it with our own functionality to
        control the associated object in an intelligent way.
        """
        # Initialise ZeroMQ and obtain an ID (no ID will be obtained if one
        # the constructor already received one).
        self.setupZMQ()
        self.connectToClerk()

        # Rename the process. I cannot do this earlier because objID may change
        # in the `connectToClerk` call.
        name = 'killme Controller {}'.format(util.id2int(self.objID))
        setproctitle.setproctitle(name)

        # Wait for messages, prefix them with our own controller ID, then send
        # them back.
        while True:
            # Wait for the next message.
            ok, data = self.recvMessage()
            if ok and data[0] is not None:
                sender, msg = data

                # Prefix the message with our ID and return to sender.
                self.sendMessage(sender, self.objID + msg)
            time.sleep(0.1)
