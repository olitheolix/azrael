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
Azrael's API.

Clients can send commands to Clerk via ZeroMQ to influence the simulation, for
instance spawn new objects, query existing objects, their state variables
and more.

The ZeroMQ interface ensures a language agnostic interface. However, every
client must adhere to the binary protocol specified in the ``protocols``
module.

The ``ControllerBase`` class is a specimen client that can talk to
Clerk. Unlike ``Clerk`` there can be many ``Controller`` instances running at
the same time and and on multiple machines.
"""
import os
import sys
import zmq
import IPython
import cytoolz
import logging
import setproctitle
import multiprocessing

import numpy as np

import azrael.database
import azrael.util as util
import azrael.parts as parts
import azrael.config as config
import azrael.database as database
import azrael.protocol as protocol
import azrael.protocol_json as json
import azrael.physics_interface as physAPI
import azrael.bullet.bullet_data as bullet_data

from azrael.typecheck import typecheck

# Convenience.
ipshell = IPython.embed
RetVal = util.RetVal


class PythonInstance(multiprocessing.Process):
    """
    Replace existing process with pristine Python interpreter.

    This is a convenience wrapper to start an independently running
    Python script. It is usually used to spawn a Controller.

    This function workds as follows: Azrael forks itself when it
    triggers the 'start' method of this class instance. This duplicates
    Azrael including sockets etc which I would rather avoid. Therefore,
    I replace this copy with an entirely new Python process that runs
    the requested script.

    The called script receives the object ID as an argument.

    :param str name: name of Python script to start.
    :param bytes objID: object ID.
    :raises: None
    """
    @typecheck
    def __init__(self, name: str, objID: bytes):
        super().__init__()

        # Keep the variables around for after the fork.
        self.script_name = name
        self.objID = objID

    def run(self):
        # Convert objectID -> integer -> string so that it can be passed as a
        # command line argument.
        objID = '{}'.format(util.id2int(self.objID))

        # Replace the current process with a new Python process. The first
        # argument is the script name, followed by the command line
        # arguments. The first of those is 'python3' once more  because the
        # program name (ie. 'python3' in this case) is also the first argument
        # Bash would pass to any new program. We pass it because we want to
        # emulate the Bash convention here to ensure everything looks sound to
        # the called Python script.
        os.execlp('python3', 'python3', self.script_name, objID)


class Clerk(multiprocessing.Process):
    """
    Administrate the simulation.

    There can only be one instance of Clerk per machine because it binds 0MQ
    sockets. These sockets are the only way to interact with Clerk.

    Clerk will always inspect and sanity check the received data to reject
    invalid client requests.

    Clerk relies on the `protocol` module to convert the ZeroMQ byte strings
    to meaningful quantities.

    :raises: None
    """
    @typecheck
    def __init__(self):
        super().__init__()

        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

        # Specify the decoding-processing-encoding triplet functions for
        # (almost) every command supported by Clerk. The only exceptions are
        # administrative commands (eg. ping). This dictionary will be used
        # in the digest loop.
        self.codec = {
            'ping_clerk': (
                protocol.ToClerk_Ping_Decode,
                self.pingClerk,
                protocol.FromClerk_Ping_Encode),
            'spawn': (
                protocol.ToClerk_Spawn_Decode,
                self.spawn,
                protocol.FromClerk_Spawn_Encode),
            'remove': (
                protocol.ToClerk_Remove_Decode,
                self.removeObject,
                protocol.FromClerk_Remove_Encode),
            'get_statevar': (
                protocol.ToClerk_GetStateVariable_Decode,
                self.getStateVariables,
                protocol.FromClerk_GetStateVariable_Encode),
            'set_statevar': (
                protocol.ToClerk_AttributeOverride_Decode,
                self.setStateVariables,
                protocol.FromClerk_AttributeOverride_Encode),
            'get_geometry': (
                protocol.ToClerk_GetGeometry_Decode,
                self.getGeometry,
                protocol.FromClerk_GetGeometry_Encode),
            'update_geometry': (
                protocol.ToClerk_SetGeometry_Decode,
                self.updateGeometry,
                protocol.FromClerk_SetGeometry_Encode),
            'set_force': (
                protocol.ToClerk_SetForce_Decode,
                self.setForce,
                protocol.FromClerk_SetForce_Encode),
            'get_template': (
                protocol.ToClerk_GetTemplate_Decode,
                self.getTemplate,
                protocol.FromClerk_GetTemplate_Encode),
            'get_template_id': (
                protocol.ToClerk_GetTemplateID_Decode,
                self.getTemplateID,
                protocol.FromClerk_GetTemplateID_Encode),
            'add_template': (
                protocol.ToClerk_AddTemplate_Decode,
                self.addTemplate,
                protocol.FromClerk_AddTemplate_Encode),
            'get_all_objids': (
                protocol.ToClerk_GetAllObjectIDs_Decode,
                self.getAllObjectIDs,
                protocol.FromClerk_GetAllObjectIDs_Encode),
            'control_parts': (
                protocol.ToClerk_ControlParts_Decode,
                self.controlParts,
                protocol.FromClerk_ControlParts_Encode),
            }

        # Insert default objects. None of them has an actual geometry but
        # their collision shapes are: none, sphere, cube.
        self.addTemplate('_templateNone'.encode('utf8'),
                         np.array([0, 1, 1, 1], np.float64),
                         np.array([]), np.array([]), np.array([]),
                         [], [])
        self.addTemplate('_templateSphere'.encode('utf8'),
                         np.array([3, 1, 1, 1], np.float64),
                         np.array([]), np.array([]), np.array([]),
                         [], [])
        self.addTemplate('_templateCube'.encode('utf8'),
                         np.array([4, 1, 1, 1], np.float64),
                         np.array([]), np.array([]), np.array([]),
                         [], [])

    def runCommand(self, fun_decode, fun_process, fun_encode):
        """
        Wrapper function to process a client request.

        This wrapper will use ``fun_decode`` to convert the ZeroMQ byte stream
        into  Python data types, then pass these data types to ``fun_process``
        for processing, and encodes the return values (also Python types) with
        ``fun_encode`` so that they can be sent back via ZeroMQ.

        The main purpose of this function is to establish a clear
        decode-process-encode work flow that all commands adhere to.

        To add a new command it is therefore necessary to specify the necessary
        {en,de}coding functions (usually in the `protocol` module) and add a
        method to this class for the actual processing.

        To make this work it is mandatory that all processing methods return an
        `(ok, some_tuple)` tuple. The Boolean ``ok`` flag indicates the
        success, and the ``some_tuple`` can contain arbitrarily many return
        types. Note however that ``some_tuple`` *must* always be a tuple, even
        if it contains only one entry, or no entry at all.

        :param callable fun_decode: converter function (bytes --> Python)
        :param callable fun_process: processes the client request.
        :param callable fun_encode: converter function (Python --> bytes)
        :return: **None**
        """
        # Decode the binary data.
        ok, out = fun_decode(self.payload)
        if not ok:
            # Error during decoding.
            self.returnErr(self.last_addr, {}, out)
        else:
            # Decoding was successful. Pass all returned parameters directly
            # to the processing method.
            ret = fun_process(*out)

            if ret.ok:
                # Encode the output into a byte stream and return it.
                ok, ret = fun_encode(ret.data)
                self.returnOk(self.last_addr, ret, '')
            else:
                # The processing method encountered an error.
                self.returnErr(self.last_addr, {}, ret.msg)

    def run(self):
        """
        Initialise ZeroMQ and wait for client requests.

        This method will not return.

        :raises: None
        """
        # Rename this process to simplify finding it in the process table.
        setproctitle.setproctitle('killme Clerk')

        # Initialise ZeroMQ and create the command socket. All client request
        # will come through this socket.
        addr = config.addr_clerk
        self.logit.info('Attempt to bind <{}>'.format(addr))
        ctx = zmq.Context()
        self.sock_cmd = ctx.socket(zmq.ROUTER)
        self.sock_cmd.bind(addr)
        poller = zmq.Poller()
        poller.register(self.sock_cmd, zmq.POLLIN)
        self.logit.info('Listening on <{}>'.format(addr))
        del addr

        # Wait for socket activity.
        while True:
            sock = dict(poller.poll())
            if not self.sock_cmd in sock:
                continue

            # Read from ROUTER socket and perform sanity checks.
            data = self.sock_cmd.recv_multipart()
            assert len(data) == 3
            self.last_addr, empty, msg = data[0], data[1], data[2]
            assert empty == b''
            del data, empty

            # Decode the data.
            try:
                msg = json.loads(msg.decode('utf8'))
            except (ValueError, TypeError) as err:
                self.returnErr(self.last_addr, {},
                               'JSON decoding error in Clerk')
                continue

            # Sanity check: every message must contain at least a command byte.
            if not (('cmd' in msg) and ('payload' in msg)):
                self.returnErr(self.last_addr, {}, 'Invalid command format')
                continue

            # Extract the command word and payload.
            cmd, self.payload = msg['cmd'], msg['payload']

            # The command word determines the action...
            if cmd in self.codec:
                # Look up the decode-process-encode functions for the current
                # command. Then execute them.
                enc, proc, dec = self.codec[cmd]
                self.runCommand(enc, proc, dec)
            else:
                # Unknown command.
                self.returnErr(self.last_addr, {},
                               'Invalid command <{}>'.format(cmd))

    @typecheck
    def returnOk(self, addr, data: dict, msg: str=''):
        """
        Send affirmative reply.

        This is a convenience method to enhance readability.

        :param addr: ZeroMQ address as returned by the router socket.
        :param dict data: arbitrary data to pass back to client.
        :param str msg: text message to pass along.
        :return: None
        """
        try:
            ret = json.dumps({'ok': True, 'payload': data, 'msg': msg})
        except (ValueError, TypeError) as err:
            self.returnErr(addr, {}, 'JSON encoding error in Clerk')
            return

        self.sock_cmd.send_multipart([addr, b'', ret.encode('utf8')])

    @typecheck
    def returnErr(self, addr, data: dict, msg: str=''):
        """
        Send negative reply and log a warning message.

        This is a convenience method to enhance readability.

        :param addr: ZeroMQ address as returned by the router socket.
        :param dict data: arbitrary data to pass back to client.
        :param str msg: message to pass along.
        :return: None
        """
        try:
            # Convert the message to a byte string (if it is not already).
            ret = json.dumps({'ok': False, 'payload': msg, 'msg': msg})
        except (ValueError, TypeError) as err:
            ret = json.dumps({'ok': False, 'payload': {},
                              'msg': 'JSON encoding error in Clerk'})

        # For record keeping.
        if isinstance(msg, str):
            self.logit.warning(msg)

        # Send the message.
        self.sock_cmd.send_multipart([addr, b'', ret.encode('utf8')])

    def pingClerk(self):
        """
        Return a 'pong'.

        :return: simple string to acknowledge the ping.
        :rtype: str
        :raises: None
        """
        return RetVal(True, None, 'pong clerk')

    # ----------------------------------------------------------------------
    # These methods service Controller requests.
    # ----------------------------------------------------------------------
    @typecheck
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
        :return: **True** if no error occurred.
        :rtype: bool
        :raises: None
        """

        # Query the templateID for the current object.
        ret = self.getTemplateID(objID)
        if not ret.ok:
            self.logit.warning(ret.msg)
            return RetVal(False, ret.msg, None)

        # Fetch the template for the current object.
        templateID = ret.data
        template = self.getTemplate(templateID)
        if not template.ok:
            msg = 'Could not retrieve template for objID={}'.format(objID)
            self.logit.warning(msg)
            return RetVal(False, msg, None)
        else:
            template = template.data
            boosters, factories = template['boosters'], template['factories']
            del template

        # Fetch the SV for objID.
        sv_parent = self.getStateVariables([objID])
        if not sv_parent.ok:
            msg = 'Could not retrieve SV for objID={}'.format(objID)
            self.logit.warning(msg)
            return RetVal(False, msg, None)

        # Extract the parent's orientation from svdata.
        sv_parent = sv_parent.data[objID]
        parent_orient = sv_parent.orientation
        quat = util.Quaternion(parent_orient[3], parent_orient[:3])

        # Compile a list of all parts defined in the template.
        booster_t = dict(zip([int(_.partID) for _ in boosters], boosters))
        factory_t = dict(zip([int(_.partID) for _ in factories], factories))

        # Verify that all Booster commands have the correct type and specify
        # a valid Booster ID.
        for cmd in cmd_boosters:
            if not isinstance(cmd, parts.CmdBooster):
                msg = 'Invalid Booster type'
                self.logit.warning(msg)
                return RetVal(False, msg, None)
            if cmd.partID not in booster_t:
                msg = 'Template <{}> has no Booster ID <{}>'
                msg = msg.format(templateID, cmd.partID)
                self.logit.warning(msg)
                return RetVal(False, msg, None)

        # Verify that all Factory commands have the correct type and specify
        # a valid Factory ID.
        for cmd in cmd_factories:
            if not isinstance(cmd, parts.CmdFactory):
                msg = 'Invalid Factory type'
                self.logit.warning(msg)
                return RetVal(False, msg, None)
            if cmd.partID not in factory_t:
                msg = 'Template <{}> has no Factory ID <{}>'
                msg = msg.format(templateID, cmd.partID)
                self.logit.warning(msg)
                return RetVal(False, msg, None)

        # Ensure all booster- and factory parts receive at most one command
        # each.
        partIDs = [_.partID for _ in cmd_boosters]
        if len(set(partIDs)) != len(partIDs):
            msg = 'Same booster received multiple commands'
            self.logit.warning(msg)
            return RetVal(False, msg, None)
        partIDs = [_.partID for _ in cmd_factories]
        if len(set(partIDs)) != len(partIDs):
            msg = 'Same factory received multiple commands'
            self.logit.warning(msg)
            return RetVal(False, msg, None)
        del partIDs

        # Tally up the central force and torque exerted by all boosters.
        tot_torque = np.zeros(3, np.float64)
        tot_central_force = np.zeros(3, np.float64)
        for cmd in cmd_boosters:
            # Template for this very factory.
            this = booster_t[cmd.partID]

            # Booster position after taking the parent's orientation into
            # account. The position is relative to the parent, *not* an
            # absolute position in world coordinates.
            force_pos = quat * this.pos
            force_dir = quat * this.direction

            # Rotate the unit force vector into the orientation given by the
            # Quaternion.
            force = cmd.force_mag * force_dir

            # Accumulate torque and central force.
            tot_torque += np.cross(force_pos, force)
            tot_central_force += force

        # Apply the net- force and torque. Skip this step if booster commands
        # were supplied.
        if len(cmd_boosters) > 0:
            physAPI.setForceAndTorque(objID, tot_central_force, tot_torque)

        # Let the factories spawn the objects.
        objIDs = []
        for cmd in cmd_factories:
            # Template for this very factory.
            this = factory_t[cmd.partID]

            # Position (in world coordinates) where the new object will be
            # spawned.
            pos = quat * this.pos + sv_parent.position

            # Rotate the exit velocity according to the parent's orientation.
            velocityLin = cmd.exit_speed * (quat * this.direction)

            # Add the parent's velocity to the exit velocity.
            velocityLin += sv_parent.velocityLin

            # Create the state variables that encode the just determined
            # position and speed.
            sv = bullet_data.BulletData(position=pos, velocityLin=velocityLin,
                                        orientation=sv_parent.orientation)

            # Spawn the actual object that this factory can create. Retain
            # the objID as it will be returned to the caller.
            ret = self.spawn(this.templateID, sv)
            if ret.ok:
                objIDs.append(ret.data)

        # Success. Return the IDs of all spawned objects.
        return RetVal(True, None, objIDs)

    @typecheck
    def addTemplate(self, templateID: bytes, cshape: np.ndarray,
                    vertices: np.ndarray, UV: np.ndarray,
                    RGB: np.ndarray, boosters: (list, tuple),
                    factories: (list, tuple)):
        """
        Add a new ``templateID`` to the system.

        Henceforth it is possible to ``spawn`` ``templateID`` objects.

        Return an error if a template with name ``templateID`` already exists.

        :param bytes templateID: the name of the new template.
        :param bytes cshape: collision shape
        :param bytes vert: object vertices
        :param bytes UV: UV map for textures
        :param bytes RGB: texture
        :param parts.Booster boosters: list of Booster instances.
        :param parts.Factory boosters: list of Factory instances.
        :return: the ID of the newly added template
        :rtype: bytes
        :raises: None
        """
        # The number of vertices must be an integer multiple of 9 to constitute
        # a valid triangle mesh (every triangle has three edges and every edge
        # requires an (x, y, z) triplet to describe its position).
        if len(vertices) % 9 != 0:
            msg = 'Number of vertices must be a multiple of Nine'
            return RetVal(False, msg, None)

        # Determine the largest possible side length of the AABB. To find it,
        # just determine the largest spatial extent in any axis direction. That
        # is the side length of the AABB cube. Then multiply it with sqrt(3) to
        # ensure that any rotation angle of the object is covered. The slightly
        # larger value of sqrt(3.1) adds some slack.
        if len(vertices) == 0:
            # Empty geometries have a zero sized AABB.
            aabb = 0
        else:
            len_x = max(vertices[0::3]) - min(vertices[0::3])
            len_y = max(vertices[1::3]) - min(vertices[1::3])
            len_z = max(vertices[2::3]) - min(vertices[2::3])
            aabb = np.sqrt(3.1) * max(len_x, len_y, len_z)

        # Compile the Mongo document for the new template. This document
        # contains the collision shape and geometry...
        data = {'templateID': templateID,
                'cshape': cshape.tostring(),
                'vertices': vertices.tostring(),
                'UV': UV.tostring(),
                'RGB': RGB.tostring(),
                'AABB': float(aabb)}

        # ... as well as booster- and factory parts.
        for b in boosters:
            data['boosters.{0:03d}'.format(b.partID)] = b.tostring()
        for f in factories:
            data['factories.{0:03d}'.format(f.partID)] = f.tostring()

        return physAPI.addTemplate(templateID, data)

    @typecheck
    def getTemplate(self, templateID: bytes):
        """
        Return the template for ``templateID``.

        Templates describe the geometry, collision shape, and capabilities
        (eg. boosters and factories) of an object.
        parts like boo

        This method return (cs, geo, boosters, factories).

        A template object has the following structure in Mongo:
        {'_id': ObjectId('53eeb55062d05244dfec278f'),
        'boosters': {'000': b'', '001': b'', ..},
        'factories': {'000':b'', ...},
        'cshape': b'',
        'templateID': b'',
        'geometry': b''}

        :param bytes templateID: templateID
        :return: Dictionary with keys 'cshape', 'vert', 'uv', 'rgb', 'boosters'
                 'factories', and 'aabb'.
        :rtype: dict
        :raises: None
        """
        # Retrieve the template. Return immediately if it does not exist.
        ret = physAPI.getTemplate(templateID)
        if not ret.ok:
            self.logit.info(ret.msg)
            return ret

        # Extract the collision shape, geometry, UV- and texture map.
        doc = ret.data
        cs = np.fromstring(doc['cshape'], np.float64)
        vert = np.fromstring(doc['vertices'], np.float64)
        uv = np.fromstring(doc['UV'], np.float64)
        rgb = np.fromstring(doc['RGB'], np.uint8)
        aabb = float(doc['AABB'])

        # Extract the booster parts.
        if 'boosters' in doc:
            # Convert byte string to Booster objects.
            boosters = [parts.fromstring(_) for _ in doc['boosters'].values()]
        else:
            # Object has no boosters.
            boosters = []

        # Extract the factory parts.
        if 'factories' in doc:
            # Convert byte string to Factory objects.
            fac = [parts.fromstring(_) for _ in doc['factories'].values()]
        else:
            # Object has no factories.
            fac = []

        ret = {'cshape': cs, 'vert': vert, 'uv': uv,
               'rgb': rgb, 'boosters': boosters, 'factories': fac,
               'aabb': aabb}
        return RetVal(True, None, ret)

    @typecheck
    def spawn(self, templateID: bytes, sv: bullet_data.BulletData):
        """
        Spawn a new object based on ``templateID``.

        The new object will get ``sv`` as the initial state vector albeit the
        collision shape will be overwritten with that specified in the
        template.

        :param bytes templateID: template from which to spawn new object.
        :param bytes sv: State Variables of new object.
        :return: ID of new object
        :rtype: bytes
        """
        # Fetch the template for the new object.
        template = self.getTemplate(templateID)
        if not template.ok:
            return template
        template = template.data

        # Overwrite the supplied collision shape with the template
        # version. This has no effect on the other quantities including
        # position and speed. However, this all rather hackey at the moment.
        sv.cshape[:] = np.fromstring(template['cshape'])

        # Request unique object ID.
        # Obtain a new and unique work package ID.
        objID = azrael.database.getNewObjectID()
        if not objID.ok:
            self.logit.error(msg)
            return objID
        objID = util.int2id(objID.data)

        # To copy the template to the instance DB we first need to get the
        # template...
        ret = physAPI.getTemplate(templateID)
        if not ret.ok:
            self.logit.info(ret.msg)
            return ret
        else:
            self.logit.info('Added template <{}>'.format(templateID))

        # ... then add objID and geometry checksum to the document, remove the
        # _id field, and insert it into the instance DB.
        doc = ret.data
        doc['objID'] = objID
        doc['csGeo'] = 0
        doc['templateID'] = templateID
        del doc['_id']
        database.dbHandles['Templates'].insert(doc)
        del doc

        # Add the object to the physics simulation.
        physAPI.addCmdSpawn(objID, sv, template['aabb'])
        msg = 'Spawned template <{}> as objID=<{}> (0x{:0X})'
        msg = msg.format(templateID, objID, util.id2int(objID))
        self.logit.debug(msg)
        return RetVal(True, None, objID)

    @typecheck
    def removeObject(self, objID: bytes):
        """
        Remove ``objID`` from the physics simulation.

        :param bytes objID: ID of object to remove.
        :return: Success
        """
        ret = physAPI.addCmdRemoveObject(objID)
        database.dbHandles['Templates'].remove({'objID': objID}, mult=True)
        if ret.ok:
            return RetVal(True, None, None)
        else:
            return RetVal(False, ret.msg, None)

    @typecheck
    def getStateVariables(self, objIDs: (list, tuple)):
        """
        Return the State Variables for all ``objIDs`` in a dictionary.

        The dictionary keys will be the elements of ``objIDs``, whereas the
        values are either the State Variables (instance of ``BulletData``) or
        *None* (if the objID does not exist).

        :param list(bytes) objIDS: list of objects for which to returns the SV.
        :return: {objID_1: SV_k, ...}
        :rtype: dict
        """
        # Get the State Variables.
        ret = physAPI.getStateVariables(objIDs)
        if not ret.ok:
            return RetVal(False, 'One or more IDs do not exist', None)

        # Query the geometry checksums for all objects.
        docs = database.dbHandles['Templates'].find(
            {'objID': {'$in': objIDs}},
            {'csGeo': 1, 'objID': 1})

        # Convert the list of [{objID1: cs1}, {objID2: cs2}, ...] into
        # a simple {objID1: cs1, objID2: cs2, ...} dictionary.
        docs = {_['objID']: _['csGeo'] for _ in docs}

        # Manually update the geometry checksum field.
        sv = ret.data
        out = {}
        for objID in objIDs:
            if (objID in docs) and (sv[objID] is not None):
                out[objID] = sv[objID]._replace(checksumGeometry=docs[objID])
            else:
                out[objID] = None

        return RetVal(True, None, out)

    @typecheck
    def getGeometry(self, objID: bytes):
        """
        Return the vertices, UV map, and RGB map for ``objID``.

        All returned values are NumPy arrays.

        If the ID does not exist return an error.

        .. note::
           It is possible that an object has no geometry. An empty array will
           be returned in that case.

        :param bytes templateID: template ID
        :return: Vertices, UV, and RGB data for ``objID``.
        :rtype: {'vert': arr_float64, 'uv': arr_float64, 'rgb': arr_uint8}
        """
        # Retrieve the geometry. Return an error if the ID does not
        # exist. Note: an empty geometry field is valid.
        doc = database.dbHandles['Templates'].find_one({'objID': objID})
        if doc is None:
            return RetVal(False, 'ID <{}> does not exist'.format(objID), None)
        else:
            vert = np.fromstring(doc['vertices'], np.float64)
            uv = np.fromstring(doc['UV'], np.float64)
            rgb = np.fromstring(doc['RGB'], np.uint8)
#            width = int(doc['width'])
#            height = int(doc['height'])
            return RetVal(True, None, {'vert': vert, 'uv': uv, 'rgb': rgb})

    @typecheck
    def updateGeometry(self, objID: bytes, vert: np.ndarray,
                    uv: np.ndarray, rgb: np.ndarray):
        """
        Update the ``vert``, ``uv`` and ``rgb`` data for ``objID``.

        If the ID does not exist return an error.

        :param bytes templateID: template ID
        :return: Success
        """
        # Update the geometry entries.
        ret = database.dbHandles['Templates'].update(
            {'objID': objID},
            {'$set': {'vertices': (vert.astype(np.float64)).tostring(),
                      'UV': (uv.astype(np.float64)).tostring(),
                      'RGB': (rgb.astype(np.uint8)).tostring()},
             '$inc': {'csGeo': 1}})

        if ret['n'] == 1:
            return RetVal(True, None, None)
        else:
            return RetVal(False, 'ID <{}> does not exist'.format(objID), None)

    @typecheck
    def setForce(self, objID: bytes, force: np.ndarray, rpos: np.ndarray):
        """
        Apply ``force`` to ``objID``.

        The force will be applied at ``rpos`` relative to the center of mass.

        If ``objID`` does not exist return an error.

        :param bytes templateID: template ID
        :return: Sucess
        """
        ret = physAPI.setForce(objID, force, rpos)
        if ret.ok:
            return RetVal(True, None, None)
        else:
            return RetVal(False, ret.msg, None)

    @typecheck
    def setStateVariables(self, objID: bytes,
                          data: bullet_data.BulletDataOverride):
        """
        Set the State Variables of ``objID`` to ``data``.

        For a detailed description see ``physAPI.addCmdModifyStateVariable``
        since this method is only a wrapper for it.

        :param bytes objID: object ID
        :param BulletDataOverride data: new object attributes.
        :return: Success
        """
        ret = physAPI.addCmdModifyStateVariable(objID, data)
        if ret.ok:
            return RetVal(True, None, None)
        else:
            return RetVal(False, ret.msg, None)

    @typecheck
    def getTemplateID(self, objID: bytes):
        """
        Return the template ID from which ``objID`` was created.

        :param bytes objID: object ID.
        :return: templateID from which ``objID`` was created.
        """
        doc = database.dbHandles['Templates'].find_one({'objID': objID})
        if doc is None:
            msg = 'Could not find template for objID {}'.format(objID)
            return RetVal(False, msg, None)
        else:
            return RetVal(True, None, doc['templateID'])

    @typecheck
    def getAllObjectIDs(self, dummy=None):
        """
        Return all ``objIDs`` in the simulation.

        .. note::
           The ``dummy`` argument is a placeholder because the ``runCommand``
           function assumes that every method takes at least one argument.

        :param bytes dummy: irrelevant
        :return: list of objIDs
        :rtype: list(bytes)
        """
        ret = physAPI.getAllObjectIDs()
        if not ret.ok:
            return RetVal(False, ret.data, None)
        else:
            return RetVal(True, None, ret.data)
