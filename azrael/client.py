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
Use ``Client`` to connect to ``Clerk``. There can be arbitrarily many ``Clerk``
and ``Client`` client instances connected to each other.

This moduel implement ZeroMQ version of the client. For a Websocket version
(eg. JavaScript developers) use ``WSClient`` from `wsclient.py` (their
feature set is identical).
"""

import zmq
import logging
import numpy as np

import azrael.util as util
import azrael.config as config
import azrael.protocol as protocol
import azrael.protocol_json as json

from azrael.util import RetVal
from azrael.typecheck import typecheck
from azrael.bullet.bullet_data import BulletDataOverride
from azrael.bullet.bullet_data import BulletData, _BulletData


class Client():
    """
    A Client for Clerk/Azrael.

    This class is little more than a collection of wrappers around the commands
    provided by Clerk. These wrappers may do some sanity checks on the input
    data but mostly they merely encode and send it Clerk, wait for a replay,
    decode the reply back to Python types, and pass the result back to the
    caller.

    :param str addr: Address of Clerk.
    :raises: None
    """
    @typecheck
    def __init__(self, addr_clerk: str=config.addr_clerk):
        super().__init__()

        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

        # Create ZeroMQ sockets and connect them to Clerk.
        self.ctx = zmq.Context()
        self.sock_cmd = self.ctx.socket(zmq.REQ)
        self.sock_cmd.linger = 0
        self.sock_cmd.connect(addr_clerk)

        # Associate the encoding and decoding functions for every command.
        self.codec = {
            'ping_clerk': (
                protocol.ToClerk_Ping_Encode,
                protocol.FromClerk_Ping_Decode),
            'get_geometry': (
                protocol.ToClerk_GetGeometry_Encode,
                protocol.FromClerk_GetGeometry_Decode),
            'set_geometry': (
                protocol.ToClerk_SetGeometry_Encode,
                protocol.FromClerk_SetGeometry_Decode),
            'spawn': (
                protocol.ToClerk_Spawn_Encode,
                protocol.FromClerk_Spawn_Decode),
            'remove': (
                protocol.ToClerk_Remove_Encode,
                protocol.FromClerk_Remove_Decode),
            'get_template_id': (
                protocol.ToClerk_GetTemplateID_Encode,
                protocol.FromClerk_GetTemplateID_Decode),
            'get_templates': (
                protocol.ToClerk_GetTemplates_Encode,
                protocol.FromClerk_GetTemplates_Decode),
            'add_templates': (
                protocol.ToClerk_AddTemplates_Encode,
                protocol.FromClerk_AddTemplates_Decode),
            'get_statevar': (
                protocol.ToClerk_GetStateVariable_Encode,
                protocol.FromClerk_GetStateVariable_Decode),
            'set_statevar': (
                protocol.ToClerk_SetStateVector_Encode,
                protocol.FromClerk_SetStateVector_Decode),
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
        if self.sock_cmd is not None:
            self.sock_cmd.close(linger=0)

    @typecheck
    def send(self, data: str):
        """
        Send ``data`` via the ZeroMQ socket.

        This method primarily exists to abstract away the underlying socket
        type. In this case, it is a ZeroMQ socket, in the case of
        ``WSClient`` it is a Websocket.

        :param str data: data in string format (usually a JSON string).
        :return: None
        """
        self.sock_cmd.send(data.encode('utf8'))

    def recv(self):
        """
        Read next message from ZeroMQ socket.

        This method primarily exists to abstract away the underlying socket
        type. In this case, it is a ZeroMQ socket, in the case of
        ``WSClient`` it is a Websocket.

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
        :return: Payload data in whatever form it arrives.
        :rtype: any
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
            return RetVal(False, 'JSON decoding error in Client', None)

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

        This is a convenience wrapper around the encode-send-receive-decode
        cycle that constitutes every request to Clerk.

        The value of ``cmd`` determines the encoding of ``args``. Note that
        this method accepts a variable number of parameters in ``args`` yet
        does not actually inspect them. Instead it passes them verbatim to
        the respective encoding function in the ``protocol`` module.

        :param str cmd: name of command.
        :return: deserialised reply.
        :rtype: any
        """
        # Sanity checks.
        assert cmd in self.codec

        # Convenience.
        ToClerk_Encode, FromClerk_Decode = self.codec[cmd]

        # Encode the arguments and send them to Clerk.
        ok, data = ToClerk_Encode(*args)
        if not ok:
            return RetVal(False, 'Protocol error', None)
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
        :return: reply from Clerk.
        :rtype: string
        """
        return self.serialiseAndSend('ping_clerk', None)

    @typecheck
    def getGeometry(self, objID: int):
        """
        Return the vertices, UV map, and RGB map for ``objID``.

        All returned values are NumPy arrays.

        :param int objID: return geometry for this object.
        :return: tupleof NumPy arrays: (vert, UV, RGB)
        :rtype: tuple(arrays)
        """
        return self.serialiseAndSend('get_geometry', objID)

    @typecheck
    def setGeometry(self, objID: int, vert: np.ndarray, uv: np.ndarray,
                    rgb: np.ndarray):
        """
        Change the geometry parameters of ``objID``.

        :param int objID: ID for which to return the geometry.
        :param bytes vert: object geometry
        :param bytes UV: UV map for textures
        :param bytes RGB: texture
        :return: Success
        """
        return self.serialiseAndSend('set_geometry', objID, vert, uv, rgb)

    @typecheck
    def spawn(self, new_objects: (tuple, list)):
        """
        Spawn new object from ``templateID`` and return its ID.

        The various function arguments modify the initial State Vector.
        fixme: paramter docu
        fixme: all other docu

        :param bytes templateID: template from which to spawn the object.
        :param 3-vec pos: object position
        :param 3-vec vel: initial velocity
        :param 4-vec orient: initial orientation
        :param float scale: scale entire object by this factor.
        :param float imass: (inverse) object mass.
        :return: object ID
        :rtype: int
        """
        reference = {
            'scale': 1,
            'imass': 1,
            'position': None,
            'orientation': np.array([0, 0, 0, 1]),
            'velocityLin': np.zeros(3),
            'axesLockLin': np.ones(3),
            'axesLockRot': np.ones(3),
            'template': None}

        payload = []
        for inp in new_objects:
            assert 'position' in inp
            assert 'template' in inp

            obj = dict(reference)
            for key in obj:
                obj[key] = inp[key] if key in inp else obj[key]

            assert isinstance(obj['scale'], (int, float))
            assert isinstance(obj['imass'], (int, float))
            assert isinstance(obj['position'], (list, np.ndarray))
            assert isinstance(obj['orientation'], (list, np.ndarray))
            assert isinstance(obj['velocityLin'], (list, np.ndarray))
            assert isinstance(obj['axesLockLin'], (list, np.ndarray))
            assert isinstance(obj['axesLockRot'], (list, np.ndarray))

            payload.append(obj)

        return self.serialiseAndSend('spawn', payload)

    @typecheck
    def removeObject(self, objID: int):
        """
        Remove ``objID`` from the physics simulation.

        ..note:: this method will succeed even if there is no ``objID``.

        :param int objID: request to remove this object.
        :return: Success
        """
        return self.serialiseAndSend('remove', objID)

    def controlParts(self, objID: int, cmd_boosters: (list, tuple),
                     cmd_factories: (list, tuple)):
        """
        Issue control commands to object parts.

        Boosters expect a scalar force which will apply according to their
        orientation. The commands themselves must be ``parts.CmdBooster``
        instances.

        Factories can spawn objects. Their command syntax is defined in the
        ``parts`` module. The commands themselves must be ``parts.CmdFactory``
        instances.

        :param int objID: object ID.
        :param list cmd_booster: booster commands.
        :param list cmd_factory: factory commands.
        :return: list of IDs of objects spawned by factories (if any).
        :rtype: list
        """
        return self.serialiseAndSend(
            'control_parts', objID, cmd_boosters, cmd_factories)

    @typecheck
    def getTemplateID(self, objID: int):
        """
        Return the template ID for ``objID``.

        Return an error if ``objID`` does not exist in the simulation.

        :param int objID: ID of spawned object.
        :return: template ID
        :rtype: bytes
        """
        return self.serialiseAndSend('get_template_id', objID)

    @typecheck
    def getTemplates(self, templateIDs: list):
        """
        Return the template data for all  ``templateIDs`` in a dictionary.

        Use ``getGeometry`` to just query the geometry.

        :param bytes templateID: return the description of this template.
        :return: (cs, geo, boosters, factories)
        """
        return self.serialiseAndSend('get_templates', templateIDs)

    @typecheck
    def addTemplates(self, templates: list):
        """
        Add all ``templates`` to Azrael.

        Return an error if one or more template names already exist.

        Every element in ``templates`` must comprise:

        * ``bytes`` templateID: the name of the new template.
        * ``bytes`` cs: collision shape
        * ``bytes`` vert: object geometry
        * ``bytes`` UV: UV map for textures
        * ``bytes`` RGB: texture
        * ``parts.Booster`` boosters: list of Booster instances.
        * ``parts.Factory`` boosters: list of Factory instances.

        :return: Success
        """
        return self.serialiseAndSend('add_templates', templates)

    @typecheck
    def getStateVariables(self, objIDs: (list, tuple, int)):
        """
        Return the State Variables for all ``objIDs`` in a dictionary.

        :param list/int objIDs: query the SV for these objects
        :return: dictionary of State Variables.
        :rtype: dict
        """
        # If the user requested only a single State Variable wrap it into a
        # list to avoid special case treatment.
        if isinstance(objIDs, int):
            objIDs = [objIDs]

        # Sanity check: all objIDs must be valid.
        for objID in objIDs:
            assert isinstance(objID, int)
            assert objID >= 0

        # Pass on the request to Clerk.
        ret = self.serialiseAndSend('get_statevar', objIDs)
        if not ret.ok:
            return ret

        # Convert the returned data back into a named tuple (_BulletData).
        out = {}
        for objID, v in ret.data.items():
            objID = int(objID)
            if v is not None:
                out[objID] = _BulletData(**v)
            else:
                out[objID] = None

        return RetVal(True, None, out)


    @typecheck
    def setStateVariable(self, objID: int, new_SV: BulletDataOverride):
        """
        Overwrite the the State Variables of ``objID`` with ``new_SV``.

        This method tells Leonard to manually set attributes like position and
        speed, irrespective of what the physics engine computes. The attributes
        will only be applied once.

        :param int objID: the object to move.
        :param BulletDataOverride new_SV: the object attributes to set.
        :return: Success
        """
        new_SV = tuple(new_SV)
        return self.serialiseAndSend('set_statevar', objID, new_SV)

    @typecheck
    def setForce(self, objID: int, force: np.ndarray):
        """
        Apply ``force`` to ``objID``.

        The ``force`` applies always at the centre of mass.

        :param int objID: apply ``force`` to this object
        :param ndarray force: the actual force vector (3 elements).
        :return: Success
        """
        assert len(force) == 3
        pos = np.zeros(3, np.float64)
        return self.serialiseAndSend('set_force', objID, force, pos)

    def getAllObjectIDs(self):
        """
        Return all object IDs currently in the simulation.

        :param bytes dummy: irrelevant
        :return: list of object IDs (integers)
        :rtype: list of int
        """
        return self.serialiseAndSend('get_all_objids')
