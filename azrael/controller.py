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
import multiprocessing
import numpy as np

import azrael.util as util
import azrael.parts as parts
import azrael.config as config
import azrael.protocol as protocol
import azrael.protocol_json as json
import azrael.physics_interface as physAPI
import azrael.bullet.bullet_data as bullet_data

from azrael.typecheck import typecheck

RetVal = util.RetVal


class ControllerBase():
    """
    A Client for Clerk/Azrael.

    This class is little more than a collection of wrappers around the commands
    provided by Clerk. These wrappers may do some sanity checks on the input
    data, but mostly they merely encode the data to binary format, send the
    result to Clerk, wait for a replay, decode the reply back to Python types,
    and pass that back to the caller.

    :param str addr: Address of Clerk.
    :raises: None
    """
    @typecheck
    def __init__(self, addr_clerk: str=config.addr_clerk):
        super().__init__()

        # Declare the socket variable. This is necessary because the destructor
        # will use and depending on whether the Controller runs as a process
        # or in the main thread this variable may otherwise be unavailable.
        self.sock_cmd = None

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
            'get_geometry': (
                protocol.ToClerk_GetGeometry_Encode,
                protocol.FromClerk_GetGeometry_Decode),
            'update_geometry': (
                protocol.ToClerk_UpdateGeometry_Encode,
                protocol.FromClerk_UpdateGeometry_Decode),
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
            'set_statevar': (
                protocol.ToClerk_AttributeOverride_Encode,
                protocol.FromClerk_AttributeOverride_Decode),
            'set_force': (
                protocol.ToClerk_SetForce_Encode,
                protocol.FromClerk_SetForce_Decode),
            'get_all_objids': (
                protocol.ToClerk_GetAllObjectIDs_Encode,
                protocol.FromClerk_GetAllObjectIDs_Decode),
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
            return RetVal(False, 'JSON encoding error', None)

        # Send data and wait for response.
        self.send(payload)
        payload = self.recv()

        # Decode the response.
        try:
            ret = json.loads(payload)
        except (ValueError, TypeError) as err:
            return RetVal(False, 'JSON decoding error in Controller', None)

        # Returned JSON must always contain an 'ok' and 'payload' field.
        if not (('ok' in ret) and ('payload' in ret)):
            return RetVal(False, 'Invalid response from Clerk', None)

        # Extract the 'Ok' flag and return the rest verbatim.
        if not ret['ok']:
            return RetVal(False, ret['msg'], ret['payload'])
        else:
            return RetVal(True, ret['msg'], ret['payload'])

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
        ret = self.sendToClerk(cmd, data)
        if not ret.ok:
            return ret

        # Command completed without error. Return the decode output.
        return FromClerk_Decode(ret.data)

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
    def getGeometry(self, objID: int):
        """
        Return the vertices, UV map, and RGB map for ``objID``.

        All returned values are NumPy arrays.

        :param int objID: ID for which to return the geometry.
        :return: (ok, (vert, UV, RGB))
        :rtype: (bool, np.ndarray) or (bool, str)
        """
        return self.serialiseAndSend('get_geometry', objID)

    @typecheck
    def updateGeometry(self, objID: int, vert: np.ndarray, uv: np.ndarray,
                       rgb: np.ndarray):
        """
        Change the geometry parameters of ``objID``.

        :param int objID: ID for which to return the geometry.
        :param bytes vert: object geometry
        :param bytes UV: UV map for textures
        :param bytes RGB: texture
        :return: (ok, ())
        :rtype: (bool, tuple) or (bool, str)
        """
        return self.serialiseAndSend('update_geometry', objID, vert, uv, rgb)

    @typecheck
    def spawn(self, templateID: bytes,
              pos: (np.ndarray, list)=np.zeros(3),
              vel: (np.ndarray, list)=np.zeros(3),
              orient: (np.ndarray, list)=[0, 0, 0, 1],
              scale=1, imass=1,
              axesLockLin: (list, np.ndarray)=[1, 1, 1],
              axesLockRot: (list, np.ndarray)=[1, 1, 1]):
        """
        Spawn a new object based on the template ``templateID``.

        The new object will spawn at ``pos`` with velocity ``vel``,
        orientation ``orient``.

        :param bytes templateID: template from which to spawn the object.
        :param 3-vec pos: object position
        :param 3-vec vel: initial velocity
        :param 4-vec orient: initial orientation
        :param float scale: scale entire object by this factor.
        :param float imass: inverse of object mass.
        :return: (ok, data)
        :rtype: (bool, np.ndarray) or (bool, str)
        """
        cshape = [0, 1, 1, 1]
        sv = bullet_data.BulletData(
            position=pos, velocityLin=vel, cshape=cshape,
            scale=scale, imass=imass,
            orientation=orient, axesLockLin=axesLockLin,
            axesLockRot=axesLockRot)
        return self.serialiseAndSend('spawn', templateID, sv)

    @typecheck
    def removeObject(self, objID: int):
        """
        Remove ``objID`` from the physics simulation.

        :param int objID: ID of object to remove.
        :return: (ok, (msg,))
        :rtype: tuple
        """
        return self.serialiseAndSend('remove', objID)

    def controlParts(self, objID: int, cmd_boosters: (list, tuple),
                     cmd_factories: (list, tuple)):
        """
        Issue control commands to object parts.

        Boosters can be activated with a scalar force that will apply according
        to their orientation. The commands themselves must be
        ``parts.CmdBooster`` instances.

        Factories can spawn objects. Their command syntax is defined in the
        ``parts`` module. The commands themselves must be
        ``parts.CmdFactory`` instances.

        :param int objID: object ID.
        :param list cmd_booster: booster commands.
        :param list cmd_factory: factory commands.
        :return: (True, (b'',)) or (False, error-message)
        :rtype: (bool, (int, )) or (bool, str)
        :raises: None
        """
        return self.serialiseAndSend(
            'control_parts', objID, cmd_boosters, cmd_factories)

    @typecheck
    def getTemplateID(self, objID: int):
        """
        Return the template ID from which ``objID`` was spawned.

        If ``objID`` does not exist in the simulation then return an error.

        :param int objID: ID of spawned object.
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
    def getStateVariables(self, objIDs: (list, tuple, int)):
        """
        Return the State Variables for all ``objIDs`` as a dictionary.

        :param list objIDs: object ID (or list thereof)
        :return: (ok, dict)
        :rtype: (bool, bytes)
        :raises: None
        """
        if isinstance(objIDs, int):
            # Wrap a single objID into a list for uniformity.
            objIDs = [objIDs]

        # Sanity check: every objID in the list must have the correct type and
        # length.
        for objID in objIDs:
            assert isinstance(objID, int)
            assert objID >= 0

        # Pass on the request to Clerk.
        return self.serialiseAndSend('get_statevar', objIDs)

    @typecheck
    def setStateVariables(self, objID: int,
                          new_SV: bullet_data.BulletDataOverride):
        """
        Overwrite the the State Variables of ``objID`` with ``data``.

        This method tells Leonard to manually set attributes like position and
        speed, irrespective of what the physics engine computes. The attributes
        will be applied exactly once.

        :param int objID: the object to move.
        :param BulletDataOverride new_SV: the object attributes to set.
        :return: (ok, b'')
        :rtype: (bool, bytes)
        :raises: None
        """
        return self.serialiseAndSend('set_statevar', objID, new_SV)

    @typecheck
    def setForce(self, objID: int, force: np.ndarray):
        """
        Apply ``force`` to ``objID``.

        The force is always applied at the centre of mass.

        :param int objID: the object for which to apply a force.
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
