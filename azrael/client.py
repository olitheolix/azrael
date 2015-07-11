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
import logging
import traceback
import urllib.request

import numpy as np
import azrael.types as types
import azrael.config as config

from azrael.types import typecheck, RetVal, Template, FragRaw, ConstraintMeta


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
            payload = json.dumps({'cmd': cmd, 'data': data})
        except (ValueError, TypeError) as err:
            msg = 'JSON encoding error for Client command <{}>'.format(cmd)
            self.logit.warning(msg)
            return RetVal(False, msg, None)

        # Send data and wait for response.
        self.send(payload)
        payload = self.recv()

        # Decode the response and wrap it into a RetVal tuple.
        try:
            ret = json.loads(payload)
            ret = RetVal(**ret)
        except (ValueError, TypeError) as err:
            return RetVal(False, 'JSON decoding error in Client', None)

        return ret

    @typecheck
    def serialiseAndSend(self, cmd: str, payload):
        """
        Serialise ``payload``, send it to Clerk, and return the reply.

        This is a convenience wrapper around the encode-send-receive-decode
        cycle that constitutes every request to Clerk.

        The value of ``cmd`` determines the encoding of ``payload``. Note that
        this method accepts a variable number of parameters in ``payload`` yet
        does not actually inspect them. Instead it passes them verbatim to the
        respective encoding function in the ``protocol`` module.

        :param str cmd: name of command.
        :return: deserialised reply.
        :rtype: any
        """
        try:
            # Send the data to Clerk.
            return self.sendToClerk(cmd, payload)
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

        :return: reply from Clerk.
        :rtype: string
        """
        return self.serialiseAndSend('ping_clerk', {})

    @typecheck
    def addTemplates(self, templates: list):
        """
        Add the ``templates`` to Azrael.

        Return an error if one or more template names already exist.

        :param list templates: list of ``Template`` instances.
        :return: Success
        """
        # Return an error unless all templates pass the sanity checks.
        try:
            # Sanity check each template.
            templates = [Template(*_)._asdict() for _ in templates]
        except AssertionError as err:
            return RetVal(False, 'Data type error', None)

        return self.serialiseAndSend('add_templates', {'templates': templates})

    @typecheck
    def getTemplates(self, templateIDs: list):
        """
        Return the template data for all  ``templateIDs`` in a dictionary.

        Use ``getFragments`` to query just the geometry.

        :param list templateIDs: return the Template for these IDs.
        :return: Template data and the URL of the fragments.
        :rtype: dict
        """
        payload = {'templateIDs': templateIDs}
        ret = self.serialiseAndSend('get_templates', payload)
        if not ret.ok:
            return ret

        # Unpack the response.
        out = {}
        for objID, data in ret.data.items():
            out[objID] = {'url_frag': data['url_frag'],
                          'template': Template(**data['template'])}

        return ret._replace(data=out)

    @typecheck
    def spawn(self, new_objects: (tuple, list)):
        """
        Spawn the objects described in ``new_objects`` and return their IDs.

        See `Clerk.spawn` for details.

        :param list new_objects: description of all objects to spawn.
        :return: object IDs
        :rtype: tuple(int)
        """
        # Send to Clerk.
        return self.serialiseAndSend('spawn', {'newObjects': new_objects})

    def controlParts(self, objID: int, cmd_boosters: dict, cmd_factories: dict):
        """
        Issue control commands to object parts.

        Boosters expect a scalar force which will apply according to their
        rotation. The commands themselves must be ``types.CmdBooster``
        instances.

        Factories can spawn objects. Their command syntax is defined in the
        ``parts`` module. The commands themselves must be ``types.CmdFactory``
        instances.

        :param int objID: object ID.
        :param dict cmd_booster: booster commands.
        :param dict cmd_factory: factory commands.
        :return: list of IDs of objects spawned by factories (if any).
        :rtype: list
        """
        # Sanity checks.
        for partID, cmd in cmd_boosters.items():
            assert isinstance(cmd, types.CmdBooster)
        for partID, cmd in cmd_factories.items():
            assert isinstance(cmd, types.CmdFactory)

        # Every object can have at most 256 parts.
        assert len(cmd_boosters) < 256
        assert len(cmd_factories) < 256

        payload = {
            'objID': objID,
            'cmd_boosters': {k: v._asdict() for (k, v) in cmd_boosters.items()},
            'cmd_factories': {k: v._asdict() for (k, v) in cmd_factories.items()}
        }
        return self.serialiseAndSend('control_parts', payload)

    @typecheck
    def removeObject(self, objID: int):
        """
        Remove ``objID`` from the physics simulation.

        ..note:: this method will succeed even if there is no ``objID``.

        :param int objID: request to remove this object.
        :return: Success
        """
        return self.serialiseAndSend('remove_object', {'objID': objID})

    @typecheck
    def getFragments(self, objIDs: list):
        """
        Return meta data for all fragments in all ``objIDs``.

        Example::

            {objID_1:
                {name_1: {'fragtype': 'raw', 'url_frag': 'http:...'},
                 name_2: {'fragtype': 'raw', 'url_frag': 'http:...'},
                }
             objID_2:
                {name_1: {'fragtype': 'dae', 'url_frag': 'http:...'}},
                {name_2: {'fragtype': 'dae', 'url_frag': 'http:...'}},
            }

        :param list[int] objIDs: list of ``objIDs``.
        :return: Meta data for all fragments of all ``objIDs``.
        :rtype: dict

        """
        ret = self.serialiseAndSend('get_fragments', {'objIDs': objIDs})
        if not ret.ok:
            return ret

        # Unpack the response: convert all objIDs to integers becauseJSON
        # always converts integer keys in hash maps to strings.
        data = {int(k): v for (k, v) in ret.data.items()}
        return ret._replace(data=data)

    @typecheck
    def setFragments(self, fragments: dict):
        """
        Change the ``fragments``.

        The format of ``fragments`` is::

            fragments = {objID_0: {fragID_0: {'scale': 2}, ...},
                         objID_1: {fragID_0: {'position': (1, 2, 3), ...},}

        :param dict fragments: nested dictionary to (partially) update fragments.
        :return: Success
        """
        return self.serialiseAndSend('set_fragments', {'fragments': fragments})

    @typecheck
    def getRigidBodies(self, objIDs: (int, list, tuple)):
        """
        Return the State Variables for all ``objIDs`` in a dictionary.

        :param list/int objIDs: query the bodies for these objects
        :return: dictionary of State Variables.
        :rtype: dict
        """
        # If the user requested only a single State Variable wrap it into a
        # list to avoid special case treatment.
        if objIDs is not None:
            if isinstance(objIDs, int):
                objIDs = [objIDs]

            # Sanity check: all objIDs must be valid.
            for objID in objIDs:
                assert isinstance(objID, int)
                assert objID >= 0

        # Pass on the request to Clerk.
        payload = {'objIDs': objIDs}
        ret = self.serialiseAndSend('get_rigid_bodies', payload)
        if not ret.ok:
            return ret

        # Unpack the response.
        out = {}
        for objID, data in ret.data.items():
            if data is None:
                # Clerk could not find this particular object.
                out[int(objID)] = None
                continue

            # Replace the original 'rbs' and 'frag' entries with the new ones.
            out[int(objID)] = {'rbs': types.RigidBodyData(**data['rbs'])}
        return ret._replace(data=out)

    @typecheck
    def setRigidBodies(self, bodies: dict):
        """
        Overwrite the the body data for all bodies specified in ``bodies``.

        This method tells Leonard to manually set attributes like position and
        speed, irrespective of what the physics engine computes. The attributes
        will only be applied once.

        :param dict bodies: the object attributes to set.
        :return: Success
        """
        for objID, body in bodies.items():
            if 'cshapes' in body:
                bodies[objID]['cshapes'] = {
                    k: v._asdict() for (k, v) in body['cshapes'].items()
                }

        payload = {'bodies': bodies}
        return self.serialiseAndSend('set_rigid_bodies', payload)

    @typecheck
    def getObjectStates(self, objIDs: (list, tuple, int)):
        """
        Return the object states for all ``objIDs`` in a dictionary.

        :param list[int] objIDs: query the states for these objects.
        :return: dictionary with state data about body and its fragments.
        :rtype: dict
        """
        # If the user requested only a single State Variable wrap it into a
        # list to avoid special case treatment.
        if objIDs is not None:
            if isinstance(objIDs, int):
                objIDs = [objIDs]

            # Sanity check: all objIDs must be valid.
            for objID in objIDs:
                assert isinstance(objID, int)
                assert objID >= 0

        # Pass on the request to Clerk.
        payload = {'objIDs': objIDs}
        ret = self.serialiseAndSend('get_object_states', payload)
        if not ret.ok:
            return ret

        # Unpack the response and convert all keys to integers.
        data = {int(k): v for (k, v) in ret.data.items()}
        return ret._replace(data=data)

    @typecheck
    def getTemplateID(self, objID: int):
        """
        Return the template ID from which ``objID`` was spawned.

        Return an error if ``objID`` does not exist in the simulation.

        :param int objID: ID of spawned object.
        :return: template ID
        :rtype: bytes
        """
        return self.serialiseAndSend('get_template_id', {'objID': objID})

    def getAllObjectIDs(self):
        """
        Return all object IDs currently in the simulation.

        :return: object IDs
        :rtype: list[int]
        """
        return self.serialiseAndSend('get_all_objids', {})

    @typecheck
    def setForce(self,
                 objID: int,
                 force: (tuple, list),
                 position: (tuple, list)=(0, 0, 0)):
        """
        Apply ``force`` to ``objID`` at ``position``.

        The ``position`` is relative to the object's center of mass.

        :param int objID: apply ``force`` to this object
        :param vec3 force: the actual force vector (3 elements).
        :param vec3 position: position of the force relative to body.
        :return: Success
        """
        # Sanity check force and position (both must be 3-vectors).
        for var in (force, position):
            tmp = np.array(var, np.float64)
            assert tmp.ndim == 1
            assert len(tmp) == 3

        # Construct the payload.
        force = tuple(force)
        position = tuple(position)
        payload = {'objID': objID, 'force': force, 'rpos': position}

        return self.serialiseAndSend('set_force', payload)

    @typecheck
    def addConstraints(self, constraints: (tuple, list)):
        """
        Install the ``constraints``.

        Each element in ``constraints`` must be a `ConstraintMeta` instance.

        :param list constraints: the constraints to install.
        :return: number of newly added constraints.
        """
        payload = {'constraints': [_._asdict() for _ in constraints]}
        return self.serialiseAndSend('add_constraints', payload)

    @typecheck
    def getConstraints(self, bodyIDs: (set, tuple, list)):
        """
        Return all constraints that feature any of the bodies in ``bodyIDs``.

        Return all constraints if ``bodyIDs`` is *None*.

        :param list[int] bodyIDs: list of body IDs.
        :return: List of ``ConstraintMeta`` instances.
        """
        payload = {'bodyIDs': bodyIDs}
        ret = self.serialiseAndSend('get_constraints', payload)
        if not ret.ok:
            return ret

        # Unpack the response.
        data = [ConstraintMeta(**_) for _ in ret.data]
        return ret._replace(data=data)

    @typecheck
    def deleteConstraints(self, constraints: (tuple, list)):
        """
        Remove the ``constraints``.

        Each element in ``constraints`` must be a `ConstraintMeta` instance.
        Invalid constraints are ignored.

        :param list constraints: the constraints to remove.
        :return: number of newly added constraints.
        """
        payload = {'constraints': [_._asdict() for _ in constraints]}
        return self.serialiseAndSend('delete_constraints', payload)

    @typecheck
    def getTemplateGeometry(self, template):
        """
        Return the geometries for ``template``.

        The return value is a dictionary. The keys are the fragment names and
        the values are ``Fragment`` instances:

            {'frag_1': FragRaw(...), 'frag_2': FragDae(...), ...}

        :param dict template: template URL
        :return: fragments.
        :rtype: dict
        """
        # Compile the URL.
        base_url = 'http://{ip}:{port}{url}'.format(
            ip=self.ip, port=config.port_clacks, url=template['url_frag'])

        # Fetch the geometry from the web server and decode it.
        out = {}
        for aid, frag in template['template'].fragments.items():
            url = base_url + '/' + aid + '/model.json'
            geo = urllib.request.urlopen(url).readall()
            geo = json.loads(geo.decode('utf8'))

            # Wrap the fragments into their dedicated tuple type.
            out[aid] = FragRaw(**geo)
        return RetVal(True, None, out)
