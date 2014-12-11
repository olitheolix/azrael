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
import azrael.protocol_json as json
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

    :param bytes objID: ID of object to connect to.
    :param str addr: Address of Clerk.
    :raises: None
    """
    @typecheck
    def __init__(self, obj_id: bytes=None, addr_clerk: str=config.addr_clerk):
        super().__init__()

        # Declare the socket variable. This is necessary because the destructor
        # will use and depending on whether the Controller runs as a process
        # or in the main thread this variable may otherwise be unavailable.
        self.sock_cmd = None

        # The object ID associated with this controller.
        self.objID = obj_id

        # Address of Clerk (ZeroMQ sockets will connect to that address).
        self.addr_clerk = addr_clerk

        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

        # Associate the encoding and decoding functions for every command.
        self.codec = {
            'ping_clerk': (
                protocol.ToClerk_Ping_Encode,
                protocol.FromClerk_Ping_Decode),
            'get_id': (
                protocol.ToClerk_GetID_Encode,
                protocol.FromClerk_GetID_Decode),
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
            'remove': (
                protocol.ToClerk_Remove_Encode,
                protocol.FromClerk_Remove_Decode),
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
            'override_attributes': (
                protocol.ToClerk_AttributeOverride_Encode,
                protocol.FromClerk_AttributeOverride_Decode),
            'control_parts': (
                protocol.ToClerk_ControlParts_Encode,
                protocol.FromClerk_ControlParts_Decode),
            }

    def __del__(self):
        self.close()

    def setupZMQ(self):
        """
        Create ZeroMQ sockets and connect them to Clerk.
        """
        self.ctx = zmq.Context()
        self.sock_cmd = self.ctx.socket(zmq.REQ)
        self.sock_cmd.linger = 0
        self.sock_cmd.connect(self.addr_clerk)

    def close(self):
        """
        Close all ZeroMQ sockets.
        """
        if self.sock_cmd is not None:
            self.sock_cmd.close()
        self.logit.debug('Controller for <{}> has shutdown'.format(self.objID))
        self.sock_cmd = None

    @typecheck
    def send(self, data: str):
        """
        Send ``data`` via the ZeroMQ socket.

        This method primarily exists to abstract away the underlying socket
        type. In this case, it is a ZeroMQ socket, in the case of
        ``WSControllerBase`` it is a Websocket.

        :param str data: data in string format (usually a JSON string).
        :return: None
        """
        self.sock_cmd.send(data.encode('utf8'))

    def recv(self):
        """
        Read next message from ZeroMQ socket.

        This method primarily exists to abstract away the underlying socket
        type. In this case, it is a ZeroMQ socket, in the case of
        ``WSControllerBase`` it is a Websocket.

        :return: received data as a string (usuallay a JSON string).
        :rtype: ste
        """
        ret = self.sock_cmd.recv()
        return ret.decode('utf8')

    @typecheck
    def sendToClerk(self, cmd: str, data: dict):
        """
        Send data to Clerk and return the response.

        This method blocks until a response arrives. Upon a reply it inspects
        the response to determine whether the request succeeded or not. This is
        returned as the first argument in the 'ok' flag.

        .. note::
           JSON must be able to serialise the content of ``data``.

        :param str cmd: command word
        :param dict data: payload (must be JSON encodeable)
        :return: (ok, data)
        :rtype: (bool, dict)
        """
        try:
            payload = json.dumps({'cmd': cmd, 'payload': data})
        except (ValueError, TypeError) as err:
            return False, {}, 'JSON encoding error'

        # Send data and wait for response.
        self.send(payload)
        payload = self.recv()

        # Decode the response.
        try:
            ret = json.loads(payload)
        except (ValueError, TypeError) as err:
            return False, {}, 'JSON decoding error in Controller'

        # Returned JSON must always contain an 'ok' and 'payload' field.
        if not (('ok' in ret) and ('payload' in ret)):
            return False, {}, 'Invalid response from Clerk'

        # Extract the 'Ok' flag and return the rest verbatim.
        return ret['ok'], ret['payload'], ret['msg']

    def connectToClerk(self):
        """
        Obtain a unique object ID from Clerk.

        This command does nothing if the Controller already has an ID (ie. if
        its self.objID attribute is not *None*).

        .. note::
           Every object in the simulation should have at most one controller
           associated with it but this is currently not enforced. It is thus
           possible to create a Controller for a non-existing object. This is
           fine for debugging and demo purposes. In the long term this method
           will probably vanish.

        :return bytes: the ID of the object with which we are associated.
        :rtype: bytes
        """
        if self.objID is None:
            # Ask Clerk for a new ID.
            ok, objID = self.serialiseAndSend('get_id', None)
            if ok:
                self.objID = objID
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
        :return: (ok, data, msg)
        :rtype: (bool, bytes) or (bool, str)
        """
        # Sanity checks.
        assert cmd in self.codec

        # Convenience.
        ToClerk_Encode, FromClerk_Decode = self.codec[cmd]

        # Encode the arguments and send them to Clerk.
        ok, data = ToClerk_Encode(*args)
        ok, data, msg = self.sendToClerk(cmd, data)
        if not ok:
            # There was an error. The 'data' field will thus contain an error
            # message.
            return False, data

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
        return self.serialiseAndSend('ping_clerk', None)

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
        Return the vertices, UV map, and RGB map for ``templateID``.

        All returned values are NumPy arrays.

        .. note::
           This method will return the geometry for a particular *template*,
           *not* a particular object from the simulation. Use ``getTemplateID``
           to determine the template ID for a given object ID.

        :param bytes templateID: ID for which to return the geometry.
        :return: (ok, (vert, UV, RGB))
        :rtype: (bool, np.ndarray) or (bool, str)
        """
        return self.serialiseAndSend('get_geometry', templateID)

    @typecheck
    def spawn(self, name: bytes, templateID: bytes,
              pos: (np.ndarray, list)=np.zeros(3),
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

    @typecheck
    def deleteObject(self, objID: bytes):
        """
        Remove ``objID`` from the physics simulation.

        :param bytes objID: ID of object to remove.
        :return: (ok, (msg,))
        :rtype: tuple
        """
        return self.serialiseAndSend('remove', objID)

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
    def addTemplate(self, templateID: bytes, cs: (tuple, list, np.ndarray),
                    vert: np.ndarray, UV: np.ndarray, RGB: np.ndarray,
                    boosters: (list, tuple),
                    factories: (list, tuple)):
        """
        Add a new ``templateID`` to the system.

        Henceforth Clerk can spawn ``templateID`` objects.

        Return an error if ``templateID`` already exists.

        :param bytes templateID: the name of the new template.
        :param bytes cs: collision shape
        :param bytes vert: object geometry
        :param bytes UV: UV map for textures
        :param bytes RGB: texture
        :param parts.Booster boosters: list of Booster instances.
        :param parts.Factory boosters: list of Factory instances.
        :return: (ok, template ID)
        :rtype: (bool, bytes)
        :raises: None
        """
        cs = np.array(cs, np.float64)
        return self.serialiseAndSend(
            'add_template', templateID, cs, vert, UV, RGB, boosters, factories)

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
    def overrideAttributes(self, objID: bytes,
                           data: btInterface.PosVelAccOrient):
        """
        Request to override the attributes of ``objID`` with ``data``.

        This method tells Leonard to manually set attributes like position and
        speed, irrespective of what the physics engine computes. The attributes
        will be applied exactly once.

        :param bytes objID: the object to move.
        :param PosVelAccOrient data: the object attributes to set.
        :return: (ok, b'')
        :rtype: (bool, bytes)
        :raises: None
        """
        return self.serialiseAndSend('override_attributes', objID, data)

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
