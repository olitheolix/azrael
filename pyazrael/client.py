# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

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
import copy
import base64
import logging
import requests
import traceback
import netifaces

import numpy as np
import pyazrael.util as util
import pyazrael.aztypes as aztypes

from IPython import embed as ipshell

typecheck = aztypes.typecheck
RetVal = aztypes.RetVal
Template = aztypes.Template
ConstraintMeta = aztypes.ConstraintMeta


def getNetworkAddress():
    """
    Return the IP address of the first configured network interface.

    The search order is 'eth*', 'wlan*', and localhost last.
    """
    # Find all interface names.
    eth = [_ for _ in netifaces.interfaces() if _.lower().startswith('eth')]
    wlan = [_ for _ in netifaces.interfaces() if _.lower().startswith('wlan')]
    lo = [_ for _ in netifaces.interfaces() if _.lower().startswith('lo')]

    # Search through all interfaces until a configured one (ie one with an IP
    # address) was found. Return that one to the user, or abort with an error.
    host_ip = None
    for iface in eth + wlan + lo:
        try:
            host_ip = netifaces.ifaddresses(iface)[2][0]['addr']
            break
        except (ValueError, KeyError):
            pass
    if host_ip is None:
        logger.critical('Could not find a valid network interface')
        sys.exit(1)

    return host_ip


class Client():
    """
    A Client for Clerk/Azrael.

    This class is little more than a collection of wrappers around the commands
    provided by Clerk. These wrappers may do some sanity checks on the input
    data but mostly they merely encode and send it Clerk, wait for a replay,
    decode the reply back to Python types, and pass the result back to the
    caller.

    :param str ip: Address of Clerk.
    :param int port_clerk: Port of Clerk.
    :param int port_webapi: Port of Azrael's web API.
    :raises: None
    """
    @typecheck
    def __init__(self, addr_clerk: str=None,
                 port_clerk: int=5555,
                 port_webapi: int=8080):
        super().__init__()

        # If no IP address was given for Azrael then try to determine it
        # automatically.
        if addr_clerk is None:
            self.addr_clerk = getNetworkAddress()
        else:
            self.addr_clerk = addr_clerk
        self.port_clerk = port_clerk
        self.port_webapi = port_webapi

        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

        # Create ZeroMQ sockets and connect them to Clerk.
        self.ctx = zmq.Context()
        self.sock_cmd = self.ctx.socket(zmq.REQ)
        self.sock_cmd.linger = 0
        addr = 'tcp://{}:{}'.format(self.addr_clerk, self.port_clerk)
        self.logit.info('Connecing to <{}>'.format(addr))
        self.sock_cmd.connect(addr)

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
        type. In the case of this very Client this is a ZeroMQ socket. In the
        case of ``WSClient`` (a subclass of this one) it would be a Websocket.

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
        with util.Timeit('client.sendToClerk:{}:1'.format(cmd)):
            try:
                payload = json.dumps({'cmd': cmd, 'data': data})
            except (ValueError, TypeError):
                msg = 'JSON encoding error for Client command <{}>'.format(cmd)
                self.logit.warning(msg)
                return RetVal(False, msg, None)

        # Send data and wait for response.
        with util.Timeit('client.sendToClerk:{}:2'.format(cmd)):
            self.send(payload)
            payload = self.recv()

        util.logMetricQty('client.recv:{}'.format(cmd), len(payload))

        # Decode the response and wrap it into a RetVal tuple.
        with util.Timeit('client.sendToClerk:{}:3'.format(cmd)):
            try:
                ret = json.loads(payload)
                ret = RetVal(**ret)
            except (ValueError, TypeError):
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
        b64enc = base64.b64encode
        # Return an error unless all templates pass the sanity checks.
        try:
            # Sanity check each template and Base64 encode all fragment files.
            templates = [Template(*_)._asdict() for _ in templates]
            for template in templates:
                for fragname in template['fragments']:
                    files = template['fragments'][fragname]['files']
                    files = {k: b64enc(v).decode('utf8') for k, v in files.items()}
                    template['fragments'][fragname]['files'] = files

        except AssertionError:
            return RetVal(False, 'Data type error', None)

        return self.serialiseAndSend('add_templates', {'templates': templates})

    @typecheck
    def getTemplates(self, templateIDs: list):
        """
        Return the template data for all  ``templateIDs`` in a dictionary.

        Use ``getFragments`` to query just the geometry.

        :param list[str] templateIDs: return the Template for these IDs.
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

    def controlParts(self, objID: str, cmd_boosters: dict, cmd_factories: dict):
        """
        Issue control commands to object parts.

        Boosters expect a scalar force which will apply according to their
        rotation. The commands themselves must be ``types.CmdBooster``
        instances.

        Factories can spawn objects. Their command syntax is defined in the
        ``parts`` module. The commands themselves must be ``types.CmdFactory``
        instances.

        :param str objID: object ID.
        :param dict cmd_booster: booster commands.
        :param dict cmd_factory: factory commands.
        :return: list of IDs of objects spawned by factories (if any).
        :rtype: list
        """
        # Sanity checks.
        for partID, cmd in cmd_boosters.items():
            assert isinstance(cmd, aztypes.CmdBooster)
        for partID, cmd in cmd_factories.items():
            assert isinstance(cmd, aztypes.CmdFactory)

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
    def removeObjects(self, objIDs: list):
        """
        Remove ``objIDs`` from the physics simulation.

        ..note:: this method will succeed even if one or more of the ``objIDs``
            do not exist.

        :param list[str] objIDs: request to remove this object.
        :return: Success
        """
        return self.serialiseAndSend('remove_objects', {'objIDs': objIDs})

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

        :param list[str] objIDs: list of ``objIDs``.
        :return: Meta data for all fragments of all ``objIDs``.
        :rtype: dict

        """
        ret = self.serialiseAndSend('get_fragments', {'objIDs': objIDs})
        if not ret.ok:
            return ret

        # Unpack the response: convert all objIDs to integers becauseJSON
        # always converts integer keys in hash maps to strings.
        data = {k: v for (k, v) in ret.data.items()}
        return ret._replace(data=data)

    @typecheck
    def setFragments(self, cmd: dict):
        """
        Modify the fragments according to ``cmd``.

        The format of ``cmd`` is defined in `azschema.setFragments`. Basically
        it looks like this::

            {objID: {
                'scale': num_nonneg,
                'position': vec3,
                'rotation': vec4,
                'fragtype': {'type': 'string'},
                'del': [file_1, file_2, ...]
                'put': {{file_1: content, file_2: content, ...},
                'op': {'type': 'string', 'pattern': "put|mod|del"},
            }}

        :param dict cmd: fragment update information.
        :return: Success
        """
        def enc(filedata):
            return base64.b64encode(filedata).decode('utf8')

        # Copy the input data because we will replace the binary file data with
        # Base64 encoded versions thereof.
        cmd = copy.deepcopy(cmd)

        for objID in cmd:
            for fragname, fragdata in cmd[objID].items():
                if 'del' in fragdata:
                    fragdata['del'] = [enc(v) for v in fragdata['del']]
                if 'put' in fragdata:
                    fragdata['put'] = {k: enc(v) for k, v in fragdata['put'].items()}

        return self.serialiseAndSend('set_fragments', {'fragupdates': cmd})

    @typecheck
    def getRigidBodies(self, objIDs: (str, list, tuple)):
        """
        Return the State Variables for all ``objIDs`` in a dictionary.

        :param list/str objIDs: query the bodies for these objects
        :return: dictionary of State Variables.
        :rtype: dict
        """
        # If the user requested only a single State Variable wrap it into a
        # list to avoid special case treatment.
        if objIDs is not None:
            if isinstance(objIDs, str):
                objIDs = [objIDs]

            # Sanity check: all objIDs must be valid.
            for objID in objIDs:
                assert isinstance(objID, str)
                assert objID != ''

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
                out[objID] = None
                continue

            # Replace the original 'rbs' and 'frag' entries with the new ones.
            out[objID] = {'rbs': aztypes.RigidBodyData(**data['rbs'])}
        return ret._replace(data=out)

    @typecheck
    def setRigidBodies(self, bodies: dict):
        """
        Overwrite the body data for all bodies specified in ``bodies``.

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
    def getObjectStates(self, objIDs: (list, tuple, str)):
        """
        Return the object states for all ``objIDs`` in a dictionary.

        :param list[int] objIDs: query the states for these objects.
        :return: dictionary with state data about body and its fragments.
        :rtype: dict
        """
        # If the user requested only a single State Variable wrap it into a
        # list to avoid special case treatment.
        if objIDs is not None:
            if isinstance(objIDs, str):
                objIDs = [objIDs]

            # Sanity check: all objIDs must be valid.
            for objID in objIDs:
                assert isinstance(objID, str)
                assert objID != ''

        # Pass on the request to Clerk.
        payload = {'objIDs': objIDs}
        ret = self.serialiseAndSend('get_object_states', payload)
        if not ret.ok:
            return ret
        return ret

    @typecheck
    def getTemplateID(self, objID: str):
        """
        Return the template ID from which ``objID`` was spawned.

        Return an error if ``objID`` does not exist in the simulation.

        :param str objID: ID of spawned object.
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
                 objID: str,
                 force: (tuple, list),
                 position: (tuple, list)=(0, 0, 0)):
        """
        Apply ``force`` to ``objID`` at ``position``.

        The ``position`` is relative to the object's center of mass.

        :param str objID: apply ``force`` to this object
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
    def removeConstraints(self, constraints: (tuple, list)):
        """
        Remove the ``constraints``.

        Each element in ``constraints`` must be a `ConstraintMeta` instance.
        Invalid constraints are ignored.

        :param list constraints: the constraints to remove.
        :return: number of newly added constraints.
        """
        payload = {'constraints': [_._asdict() for _ in constraints]}
        return self.serialiseAndSend('remove_constraints', payload)

    @typecheck
    def getTemplateGeometry(self, template):
        """
        Return the model files for ``template``.

        The return value is a dictionary of dictionaries::

            ret = {
                fragname1: {
                    filename_1: binary, ..., filename_n: binary
                },
                ...,
                fragnameN: {
                    filename_1: binary, ..., filename_n: binary
                }
            }

        :param dict template: template URL
        :return: fragments.
        :rtype: dict[dict]
        """
        # Compile the URL.
        base_url = 'http://{ip}:{port}{url}'.format(
            ip=self.addr_clerk, port=self.port_webapi, url=template['url_frag'])

        # Fetch all the model files for each fragment.
        out = {}
        for fragname, frag in template['template'].fragments.items():
            out[fragname] = {}

            # Download each model for the current fragment.
            for fname in frag.files:
                url = base_url + '/' + fragname + '/' + fname
                geo = requests.get(url).content
                out[fragname][fname] = geo.decode('utf8')
        return RetVal(True, None, out)

    @typecheck
    def setCustomData(self, data: dict):
        """
        Update the `custom` field with the information in ``data``.

        ``Data`` is a dictionary, eg::
            {1: 'foo', 25: 'bar'}

        Non-existing objects are silently ignored, but their ID will be
        returned to the caller.

        :param dict[str: str] data: new content for 'custom' field in object.
        :return: List of invalid object IDs.
        """
        # Sanity checks.
        for k, v in data.items():
            assert isinstance(k, str)
            assert isinstance(v, str)

        return self.serialiseAndSend('set_custom', {'data': data})

    @typecheck
    def getCustomData(self, objIDs: (tuple, list)):
        """
        Return the `custom` data for all ``objIDs`` in a dictionary.

        The return value may look like:: {1: 'foo', 25: 'bar'}

        :param dict[int: str] data: new content for 'custom' field in object.
        :return: dictionary of 'custom' data.
        """
        # Sanity checks: all object IDs must be integers.
        if objIDs is not None:
            for objID in objIDs:
                assert isinstance(objID, str)

        # Send to Clerk and wait for response.
        ret = self.serialiseAndSend('get_custom', {'objIDs': objIDs})
        if not ret.ok:
            return ret
        return ret
