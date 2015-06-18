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

This module implements the ZeroMQ version of the client. For a Websocket
version (eg. JavaScript developers) use ``WSClient`` from `wsclient.py` (their
feature set is identical).
"""

import io
import zmq
import json
import base64
import logging
import traceback
import urllib.request

import numpy as np

import azrael.parts as parts
import azrael.config as config
import azrael.protocol as protocol

from azrael.types import typecheck, RetVal, Template
from azrael.types import FragState, FragDae, FragRaw, MetaFragment
from azrael.rb_state import RigidBodyStateOverride, _RigidBodyState


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
    def __init__(self, ip: str=config.addr_clerk, port: int=config.port_clerk):
        super().__init__()

        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

        # Create ZeroMQ sockets and connect them to Clerk.
        self.ctx = zmq.Context()
        self.sock_cmd = self.ctx.socket(zmq.REQ)
        self.sock_cmd.linger = 0
        self.sock_cmd.connect('tcp://{}:{}'.format(ip, port))

        # Some methods need to know the address of the server.
        self.ip, self.port = ip, port

        # Associate the encoding and decoding functions for every command.
        self.codec = {
            'ping_clerk': (
                protocol.ToClerk_Ping_Encode,
                protocol.FromClerk_Ping_Decode),
            'get_fragment_geometries': (
                protocol.ToClerk_GetFragmentGeometries_Encode,
                protocol.FromClerk_GetFragmentGeometries_Decode),
            'set_fragment_geometries': (
                protocol.ToClerk_SetFragmentGeometry_Encode,
                protocol.FromClerk_SetFragmentGeometry_Decode),
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
            'get_body_states': (
                protocol.ToClerk_GetBodyState_Encode,
                protocol.FromClerk_GetBodyState_Decode),
            'get_all_body_states': (
                protocol.ToClerk_GetAllBodyStates_Encode,
                protocol.FromClerk_GetAllBodyStates_Decode),
            'set_body_state': (
                protocol.ToClerk_SetBodyState_Encode,
                protocol.FromClerk_SetBodyState_Decode),
            'set_force': (
                protocol.ToClerk_SetForce_Encode,
                protocol.FromClerk_SetForce_Decode),
            'get_all_objids': (
                protocol.ToClerk_GetAllObjectIDs_Encode,
                protocol.FromClerk_GetAllObjectIDs_Decode),
            'control_parts': (
                protocol.ToClerk_ControlParts_Encode,
                protocol.FromClerk_ControlParts_Decode),
            'set_fragment_states': (
                protocol.ToClerk_SetFragmentStates_Encode,
                protocol.FromClerk_SetFragmentStates_Decode),
            'add_constraints': (
                protocol.ToClerk_AddConstraints_Encode,
                protocol.FromClerk_AddConstraints_Decode),
            'get_constraints': (
                protocol.ToClerk_GetConstraints_Encode,
                protocol.FromClerk_GetConstraints_Decode),
            'get_all_constraints': (
                protocol.ToClerk_GetAllConstraints_Encode,
                protocol.FromClerk_GetAllConstraints_Decode),
            'delete_constraints': (
                protocol.ToClerk_DeleteConstraints_Encode,
                protocol.FromClerk_DeleteConstraints_Decode),
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
            msg = 'JSON encoding error for Client command <{}>'.format(cmd)
            self.logit.warning(msg)
            return RetVal(False, msg, None)

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

        try:
            # Encode the arguments and send them to Clerk.
            ret = ToClerk_Encode(*args)
            if not ret.ok:
                msg = 'ToClerk_Encode_* error for <{}>'.format(cmd)
                msg += '\n ' + ret.err
                self.logit.error(msg)
                return RetVal(False, msg, None)
            ret = self.sendToClerk(cmd, ret.data)
            if not ret.ok:
                return ret

            # Command completed without error. Return the decode output.
            return FromClerk_Decode(ret.data)
        except Exception:
            msg = 'Error during (de)serialisation on Client for cmd <{}>'
            msg = msg.format(cmd)

            # Get stack trace as string.
            buf = io.StringIO()
            traceback.print_exc(file=buf)
            buf.seek(0)
            msg_st = [' -> ' + _ for _ in buf.readlines()]
            msg_st = msg + '\n' + ''.join(msg_st)

            # Log the error message with stack trace, but return only
            # the error message.
            self.logit.error(msg_st)
            return RetVal(False, msg_st, None)

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
    def getFragmentGeometries(self, objIDs: list):
        """
        Return links to the models for the objects in ``objIDs``.

        {objID_1:
            {name_1: {'type': 'raw', 'url': 'http:...'},
             name_2: {'type': 'raw', 'url': 'http:...'},...
            }
         objID_2: {name_1: {'type': 'dae', 'url': 'http:...'},...
        }

        :param int objIDs: list of objIDs to query.
        :return: links to model data for all ``objIDs``.
        :rtype: dict
        """
        return self.serialiseAndSend('get_fragment_geometries', objIDs)

    @typecheck
    def setFragmentGeometries(self, objID: int, frags: list):
        """
        Change the geometry parameters of ``objID``.

        :param int objID: ID for which to return the geometry.
        :param list frags: list of ``Fragment`` instances.
        :return: Success
        """
        try:
            frags = [MetaFragment(*_) for _ in frags]
        except TypeError:
            return RetVal(False, 'Invalid fragment data types', None)

        return self.serialiseAndSend('set_fragment_geometries', objID, frags)

    @typecheck
    def spawn(self, new_objects: (tuple, list)):
        """
        Spawn the objects described in ``new_objects`` and return their IDs.

        The elements of the ``new_objects`` list must comprise the following
        parameters:

        * bytes templateID: template from which to spawn the object.
        * 3-vec pos: object position
        * 3-vec vel: initial velocity
        * 4-vec orient: initial orientation
        * float scale: scale entire object by this factor.
        * float imass: (inverse) object mass.

        :param list new_objects: description of all objects to spawn.
        :return: object IDs
        :rtype: tuple(int)
        """
        # Reference dictionary with default values.
        template = {
            'scale': 1,
            'imass': 1,
            'position': None,
            'orientation': [0, 0, 0, 1],
            'velocityLin': [0, 0, 0],
            'axesLockLin': [1, 1, 1],
            'axesLockRot': [1, 1, 1],
            'template': None}

        # Create valid object descriptions by copying the 'template' and
        # overwriting its defaults with the values provided in
        # ``new_objects``.
        payload = []
        for inp in new_objects:
            assert 'position' in inp
            assert 'template' in inp

            # Copy the template and replace the provided keys with the provided
            # values.
            obj = dict(template)
            for key in obj:
                obj[key] = inp[key] if key in inp else obj[key]

                # Replace all NumPy arrays with Python lists to ensure JSON
                # compatibility.
                if isinstance(obj[key], np.ndarray):
                    obj[key] = obj[key].tolist()

            # Sanity checks.
            assert isinstance(obj['scale'], (int, float))
            assert isinstance(obj['imass'], (int, float))
            assert isinstance(obj['position'], list)
            assert isinstance(obj['orientation'], list)
            assert isinstance(obj['velocityLin'], list)
            assert isinstance(obj['axesLockLin'], list)
            assert isinstance(obj['axesLockRot'], list)

            # Add the description to the list of objects to spawn.
            payload.append(obj)

        # Send to Clerk.
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
        # Sanity checks.
        for cmd in cmd_boosters:
            assert isinstance(cmd, parts.CmdBooster)
        for cmd in cmd_factories:
            assert isinstance(cmd, parts.CmdFactory)

        # Every object can have at most 256 parts.
        assert len(cmd_boosters) < 256
        assert len(cmd_factories) < 256

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

        Use ``getFragmentGeometries`` to query just the geometry.

        :param bytes templateID: return the description of this template.
        :return: (cs, geo, boosters, factories)
        """
        return self.serialiseAndSend('get_templates', templateIDs)

    @typecheck
    def getTemplateGeometry(self, template):
        """
        Return the ``template`` geometry.

        The return value is a dictionary. The keys are the fragment names and
        the values are ``Fragment`` instances:

            {'frag_1': FragRaw(...), 'frag_2': FragDae(...), ...}

        :param str url: template URL
        :return: fragments.
        :rtype: dict
        """
        # Compile the URL.
        base_url = 'http://{ip}:{port}{url}'.format(
            ip=self.ip, port=config.port_clacks, url=template.url)

        # Fetch the geometry from the web server and decode it.
        out = {}
        for frag in template.fragments:
            frag = MetaFragment(*frag)
            url = base_url + '/' + frag.aid + '/model.json'
            data = urllib.request.urlopen(url).readall()
            out = json.loads(data.decode('utf8'))

            # Wrap the fragments into their dedicated tuple type.
            out[frag.aid] = FragRaw(**out)
        return RetVal(True, None, out)

    @typecheck
    def addTemplates(self, templates: list):
        """
        Add the ``templates`` to Azrael.

        Return an error if one or more template names already exist.

        * ``list`` templates: list of ``Template`` objects.

        :return: Success
        """
        # Return an error unless all templates pass the sanity checks.
        try:
            # Sanity check each template.
            for idx, temp in enumerate(templates):
                # Sanity checks.
                assert isinstance(temp, Template)
                assert isinstance(temp.aid, str)
                assert isinstance(temp.cshapes, (tuple, list, np.ndarray))
                assert isinstance(temp.fragments, (tuple, list))

                # Check and Base64 encode each individual fragment.
                frags = []
                for frag in temp.fragments:
                    # Check the Fragment header.
                    assert isinstance(frag, MetaFragment)
                    frags.append(MetaFragment(*frag))

                # Sanity checks for boosters and factories.
                assert isinstance(temp.boosters, list)
                assert isinstance(temp.factories, list)
                for b in temp.boosters:
                    assert isinstance(b, parts.Booster)
                for f in temp.factories:
                    assert isinstance(f, parts.Factory)

                # fixme: verify the Collision Shape is valid.
                cs = list(temp.cshapes)

                # Replace the original entry with a new one where CS is
                # definitively a list.
                templates[idx] = Template(
                    temp.aid, cs, frags, temp.boosters, temp.factories)
        except AssertionError as err:
            return RetVal(False, 'Data type error', None)
        return self.serialiseAndSend('add_templates', templates)

    @typecheck
    def _unpackSVData(self, raw: dict):
        """
        Return unpacked SV data.

        This is a convenience function only to avoid code duplication in
        ``get{All}BodyStates``.

        The returned dictionary has the format:
          {objID_1: {'frag': [FragState(), ...], 'sv': RigidBodyState()},
           objID_2: {'frag': [FragState(), ...], 'sv': RigidBodyState()},
           ...
        }

        :param dict raw: output from protocol module.
        :return: unpacked SV data.
        """
        # Iterate over all objects.
        out = {}
        for objID, v in raw.items():
            # Convert the object ID to an integer because JSON will convert all
            # dictionary keys to strings.
            objID = int(objID)

            # Add a None value if there is no data (typically happens if one
            # or more of the objects for which SV data was requested did not
            # exist).
            if v is None:
                out[objID] = None
                continue

            # Fill in the SV and fragment state data.
            out[objID] = {'frag': [FragState(**_) for _ in v['frag']],
                          'sv': _RigidBodyState(**v['sv'])}
        return RetVal(True, None, out)

    @typecheck
    def getBodyStates(self, objIDs: (list, tuple, int)):
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
        ret = self.serialiseAndSend('get_body_states', objIDs)
        if not ret.ok:
            return ret
        return self._unpackSVData(ret.data)

    @typecheck
    def getAllBodyStates(self):
        """
        Return the State Variables for all objects in the simulation.

        :return: dictionary of State Variables.
        :rtype: dict
        """
        # Pass on the request to Clerk.
        ret = self.serialiseAndSend('get_all_body_states')
        if not ret.ok:
            return ret
        return self._unpackSVData(ret.data)

    @typecheck
    def setBodyState(self, objID: int, new: RigidBodyStateOverride):
        """
        Overwrite the the State Variables of ``objID`` with ``new``.

        This method tells Leonard to manually set attributes like position and
        speed, irrespective of what the physics engine computes. The attributes
        will only be applied once.

        :param int objID: the object to move.
        :param RigidBodyStateOverride new: the object attributes to set.
        :return: Success
        """
        new = tuple(new)
        return self.serialiseAndSend('set_body_state', objID, new)

    @typecheck
    def setForce(self, objID: int, force: (tuple, list, np.ndarray)):
        """
        Apply ``force`` to ``objID``.

        The ``force`` applies always at the centre of mass.

        :param int objID: apply ``force`` to this object
        :param ndarray force: the actual force vector (3 elements).
        :return: Success
        """
        force = tuple(np.array(force).tolist())
        assert len(force) == 3

        # fixme: position should be an optional parameter.
        pos = (0, 0, 0)
        return self.serialiseAndSend('set_force', objID, force, pos)

    def getAllObjectIDs(self):
        """
        Return all object IDs currently in the simulation.

        :return: list of object IDs (integers)
        :rtype: list of int
        """
        return self.serialiseAndSend('get_all_objids')

    def setFragmentStates(self, fragStates: dict):
        """
        Modify the fragment states specified in ``fragStates``.

        Fragment states specify the size, position, and orientation of
        individual fragment. They do not specify the geometry.

        Each key in ``fragStates`` must be an object ID and each value a
        ``FragState`` instance, eg.

           {objID: [FragState('bar', 2.2, [1, 2, 3], [1, 0, 0, 0])]}

        :param dict fragStates: new fragment states.
        :return: Success
        :rtype:
        """
        return self.serialiseAndSend('set_fragment_states', fragStates)

    @typecheck
    def addConstraints(self, constraints: (tuple, list)):
        """
        Install the ``constraints``.

        Each element in ``constraints`` must be a `ConstraintMeta` instance.

        :param list constraints: the constraints to install.
        :return: number of newly added constraints.
        """
        return self.serialiseAndSend('add_constraints', constraints)

    @typecheck
    def getConstraints(self, bodyIDs: (set, tuple, list)):
        """
        Return all constraints that feature any of the bodies in ``bodyIDs``.

        :param list[int] bodyIDs: list of body IDs.
        :return: List of ``ConstraintMeta`` instances.
        """
        return self.serialiseAndSend('get_constraints', bodyIDs)

    @typecheck
    def getAllConstraints(self):
        """
        Return all currently known constraints.

        :return: List of ``ConstraintMeta`` instances.
        """
        return self.serialiseAndSend('get_all_constraints', None)

    @typecheck
    def deleteConstraints(self, constraints: (tuple, list)):
        """
        Remove the ``constraints``.

        Each element in ``constraints`` must be a `ConstraintMeta` instance.
        Invalid constraints are ignored.

        :param list constraints: the constraints to remove.
        :return: number of newly added constraints.
        """
        return self.serialiseAndSend('delete_constraints', constraints)
