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

Use ``Client`` to connect to ``Clerk``. There can be arbitrarily many ``Clerk``
and ``Client`` client instances connected to each other.

This moduel implement ZeroMQ version of the ``Clerk``. For a Websocket version
(eg. JavaScript developers) use ``Clacks`` from `clacks.py` (their feature set
is identical).

"""
import os
import sys
import zmq
import pickle
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

from collections import namedtuple
from azrael.typecheck import typecheck

# Convenience.
ipshell = IPython.embed
RetVal = util.RetVal
Template = azrael.util.Template


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
                protocol.ToClerk_SetStateVector_Decode,
                self.setStateVariable,
                protocol.FromClerk_SetStateVector_Encode),
            'get_geometry': (
                protocol.ToClerk_GetGeometry_Decode,
                self.getGeometry,
                protocol.FromClerk_GetGeometry_Encode),
            'set_geometry': (
                protocol.ToClerk_SetGeometry_Decode,
                self.setGeometry,
                protocol.FromClerk_SetGeometry_Encode),
            'set_force': (
                protocol.ToClerk_SetForce_Decode,
                self.setForce,
                protocol.FromClerk_SetForce_Encode),
            'get_templates': (
                protocol.ToClerk_GetTemplates_Decode,
                self.getTemplates,
                protocol.FromClerk_GetTemplates_Encode),
            'get_template_id': (
                protocol.ToClerk_GetTemplateID_Decode,
                self.getTemplateID,
                protocol.FromClerk_GetTemplateID_Encode),
            'add_templates': (
                protocol.ToClerk_AddTemplates_Decode,
                self.addTemplates,
                protocol.FromClerk_AddTemplates_Encode),
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
        t1 = Template('_templateNone',
                      np.array([0, 1, 1, 1], np.float64),
                      [], [], [],
                      [], [])
        t2 = Template('_templateSphere',
                      np.array([3, 1, 1, 1], np.float64),
                      [], [], [],
                      [], [])
        t3 = Template('_templateCube',
                      np.array([4, 1, 1, 1], np.float64),
                      [], [], [],
                      [], [])
        self.addTemplates([t1, t2, t3])

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
    # These methods service Client requests.
    # ----------------------------------------------------------------------
    @typecheck
    def controlParts(self, objID: int, cmd_boosters: (list, tuple),
                     cmd_factories: (list, tuple)):
        """
        Issue commands to individual parts of the ``objID``.

        Boosters can be activated with a scalar force that will apply according
        to their orientation. The commands themselves must be
        ``parts.CmdBooster`` instances.

        Factories can spawn objects. Their command syntax is defined in the
        ``parts`` module. The commands themselves must be
        ``parts.CmdFactory`` instances.

        :param int objID: object ID.
        :param list cmd_booster: booster commands.
        :param list cmd_factory: factory commands.
        :return: **True** if no error occurred.
        :rtype: bool
        :raises: None
        """
        # Fetch the instance data for ``objID``.
        ret = self.getObjectInstance(objID)
        if not ret.ok:
            self.logit.warning(ret.msg)
            return RetVal(False, ret.msg, None)
        else:
            boosters = ret.data['boosters']
            factories = ret.data['factories']
            del ret

        # Fetch the SV for objID (we need this to determine the orientation of
        # the base object to which the parts are attached).
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
                msg = 'Object <{}> has no Booster ID <{}>'
                msg = msg.format(objID, cmd.partID)
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
                msg = 'Object <{}> has no Factory ID <{}>'
                msg = msg.format(objID, cmd.partID)
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
        tot_force = np.zeros(3, np.float64)
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
            tot_force += force

        # The physAPI expects Python types, not NumPy arrays.
        tot_force = tot_force.tolist()
        tot_torque = tot_torque.tolist()

        # Apply the net- force and torque. Skip this step if booster commands
        # were supplied.
        if len(cmd_boosters) > 0:
            physAPI.addCmdSetForceAndTorque(objID, tot_force, tot_torque)
        del tot_force, tot_torque

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
            ret = self.spawn([(this.templateID, sv)])
            if ret.ok:
                objIDs.append(ret.data[0])
            else:
                self.logit.info('Factory could not spawn objects')

        # Success. Return the IDs of all spawned objects.
        return RetVal(True, None, objIDs)

    @typecheck
    def _isGeometrySane(self, vert: list, uv: list, rgb: list):
        """
        Return *True* if the geometry is consistent.

        :param np.ndarray vert: vertices
        :param np.ndarray uv: UV values
        :param np.ndarray rgb: RGB values
        :return: Sucess
        :rtype: bool
        """
        # The number of vertices must be an integer multiple of 9 to
        # constitute a valid triangle mesh (every triangle has three
        # edges and every edge requires an (x, y, z) triplet to
        # describe its position).
        try:
            assert len(vert) % 9 == 0
            assert len(uv) % 2 == 0
            assert len(rgb) % 3 == 0
        except AssertionError:
            return False
        return True

    @typecheck
    def addTemplates(self, templates: list):
        """
        Add all the templates specified in ``templates`` to the system.

        Henceforth it will be possible to ``spawn`` any of them.

        Return an error if one or more template with the same name exists. All
        non-existing templates will be added but none of the existing ones will
        be modified.

        The elements in ``templates`` are ``Template`` instances.

        :param str templateID: the name of the new template.
        :param np.ndarray cshape: collision shape
        :param list vert: object vertices
        :param list UV: UV map for textures
        :param list RGB: texture
        :param parts.Booster boosters: list of Booster instances.
        :param parts.Factory boosters: list of Factory instances.
        :return: the ID of the newly added template
        :rtype: bytes
        :raises: None
        """
        # Return immediately if ``templates`` is empty.
        if len(templates) == 0:
            return RetVal(True, None, None)

        with util.Timeit('clerk.addTemplates') as timeit:
            # Sanity checks.
            tmp = [_ for _ in templates if not isinstance(_, Template)]
            if len(tmp) > 0:
                return RetVal(False, 'Invalid arguments', None)

            db = database.dbHandles['Templates']
            bulk = db.initialize_unordered_bulk_op()
            for tt in templates:
                assert isinstance(tt.name, str)
                vertices = tt.vert

                # Sanity checks.
                try:
                    assert isinstance(vertices, list)
                    assert isinstance(tt.uv, list)
                    assert isinstance(tt.rgb, list)
                except AssertionError:
                    msg = 'addTemplates Parameters must be lists'
                    return RetVal(False, msg, None)

                if not self._isGeometrySane(vertices, tt.uv, tt.rgb):
                    msg = 'Invalid geometry for template <{}>'.format(tt.name)
                    return RetVal(False, msg, None)

                # Determine the largest possible side length of the AABB. To
                # find it, just determine the largest spatial extent in any
                # axis direction. That is the side length of the AABB
                # cube. Then multiply it with sqrt(3) to ensure that any
                # rotation angle of the object is covered. The slightly larger
                # value of sqrt(3.1) adds some slack.
                if len(vertices) == 0:
                    # Empty geometries have a zero sized AABB.
                    aabb = 0
                else:
                    len_x = max(vertices[0::3]) - min(vertices[0::3])
                    len_y = max(vertices[1::3]) - min(vertices[1::3])
                    len_z = max(vertices[2::3]) - min(vertices[2::3])
                    aabb = np.sqrt(3.1) * max(len_x, len_y, len_z)

                # Compile the Mongo document for the new template. This
                # document contains the collision shape and geometry...
                data = {'cshape': tt.cs.tostring(),
                        'AABB': float(aabb),
                        'boosters': {},
                        'factories': {}}
                geo = {'vertices': vertices,
                       'UV': tt.uv,
                       'RGB': tt.rgb}

                # ... as well as booster- and factory parts.
                for b in tt.boosters:
                    tmp = b.tostring()
                    data['boosters']['{0:03d}'.format(b.partID)] = tmp
                for f in tt.factories:
                    tmp = f.tostring()
                    data['factories']['{0:03d}'.format(f.partID)] = tmp

                # Add the template to the database.
                query = {'templateID': tt.name}
                data['geo'] = pickle.dumps(geo)
                bulk.find(query).upsert().update({'$setOnInsert': data})

        with util.Timeit('clerk.addTemplates_db') as timeit:
            ret = bulk.execute()

        if ret['nMatched'] > 0:
            # A template with name ``templateID`` already existed --> failure.
            msg = 'At least one template already existed'
            return RetVal(False, msg, None)
        else:
            # No template name existed before the insertion --> success.
            return RetVal(True, None, None)

    @typecheck
    def getRawTemplate(self, templateIDs: list):
        """
        Return the raw data for all ``templateIDs`` as a dictionary.

        This method will return either all templates or none. However, if the
        same template is specified multiple times in ``templateIDs`` then it
        will only return unique names.

        For instance, ``getRawTemplate([name_1, name_2, name_1])`` is
        tantamount to calling ``getRawTemplate([name_1, name_2])``.

        :param list(str) templateIDs: template IDs
        :return dict: raw template data (the templateID is the key).
        """
        # Sanity check
        tmp = [_ for _ in templateIDs if not isinstance(_, str)]
        if len(tmp) > 0:
            return RetVal(False, 'All template IDs must be strings', None)

        # Remove all duplicates from templateIDs.
        templateIDs = list(set(list(templateIDs)))

        # Retrieve the template. Return immediately if one does not exist.
        db = database.dbHandles['Templates']
        docs = list(db.find({'templateID': {'$in': templateIDs}}))
        if len(docs) < len(templateIDs):
            msg = 'Not all template IDs were valid'
            self.logit.info(msg)
            return RetVal(False, msg, None)

        # Compile a dictionary of all the templates.
        docs = {_['templateID']: _ for _ in docs}

        # Delete the '_id' field.
        for name in docs:
            del docs[name]['_id']
        return RetVal(True, None, docs)

    @typecheck
    def getTemplates(self, names: list):
        """
        Return the templates specified in ``names`` as a dictionary.

        Templates describe the geometry, collision shape, and capabilities
        (eg. boosters and factories) of an object.

        Internally, this method calls ``_unpackTemplateData`` to unpack the
        data. The output of that method will then be returned verbatim by this
        method (see ``_unpackTemplateData`` for details on that output).

        :param list names: list of template names.
        :return: {names[0]: {'cshape': *, 'vert': *, 'uv': *, 'rgb':*,
                             'boosters': *, 'factories': *, 'aabb': *},
                  names[1]: {*},
                  ...}.
        :rtype: dict
        :raises: None
        """
        # Retrieve the template. Return immediately if it does not exist.
        ret = self.getRawTemplate(names)
        if not ret.ok:
            self.logit.info(ret.msg)
            return ret

        # Convenience.
        fun = self._unpackTemplateData

        # Unpack the raw templates and insert them into a dictionary where the
        # template names correspond to its keys.
        out = {k: fun(v).data for (k, v) in ret.data.items()}
        return RetVal(True, None, out)

    @typecheck
    def getObjectInstance(self, objID: int):
        """
        Return the instance data for ``objID``.

        This function is almost identical to ``getTemplates`` except that it
        queries the `Instance` database, not the `Template` database (the data
        structure are identical in both databases).

        Internally, this method calls ``_unpackTemplateData`` to unpack the
        data. The output of that method will then be returned verbatim by this
        method (see ``_unpackTemplateData`` for details on that output).

        :param int objID: objID
        :return: Dictionary with keys 'cshape', 'vert', 'uv', 'rgb',
                 'boosters', 'factories', and 'aabb'.
        :rtype: dict
        :raises: None
        """
        # Retrieve the instance template. Return immediately if no such
        # template exists.
        doc = database.dbHandles['ObjInstances'].find_one({'objID': objID})
        if doc is None:
            msg = 'Could not find instance data for objID <{}>'.format(objID)
            self.logit.info(msg)
            return RetVal(False, msg, None)

        return self._unpackTemplateData(doc)

    def _unpackTemplateData(self, doc: dict):
        """
        Return unpacked template data.

        This method assumes that ``doc`` describes a template (or object
        instance) and decompiles it into its constituents (boosters, factories,
        geometry, etc).

        .. note:: This method also unpacks instance objects as they their
                  format is identical.

        The return value is a dictionary like this:
          {'cshape': cs, 'vert': vert, 'uv': uv, 'rgb': rgb,
           'boosters': boosters, 'factories': fac, 'aabb': aabb}

        :param dict doc: raw data from the DB.
        :returns: decompiled objects
        :rtype: dict
        """
        geo = pickle.loads(doc['geo'])

        # Extract the collision shape, geometry, UV- and texture map.
        cs = np.fromstring(doc['cshape'], np.float64)
        vert = geo['vertices']
        uv = geo['UV']
        rgb = geo['RGB']
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
    def spawn(self, newObjects: (tuple, list)):
        """
        Spawn all ``newObjects`` and return their object IDs in a tuple.

        The ``newObjects`` must have the following format:
          newObjects = [(template_name_1, sv_1), (template_name_2, sv_2), ...]
        where ``template_name_k`` is a string and ``sv_k`` is a ``BulletData``
        instance.

        The new object will get ``sv_k`` as the initial state vector. However,
        the provided collision shape will be ignored and *always* replaced with
        the collision shape specified in the template ``template_name_k``.

        This method will return with an error (without spawning a single
        object) if one or more argument are invalid.

        :param list/tuple newObjects: list of template names and SVs.
        :return: IDs of spawned objects
        :rtype: tuple of int
        """
        # Sanity checks.
        try:
            assert len(newObjects) > 0
            for ii in newObjects:
                assert len(ii) == 2
                templateID, sv = ii
                assert isinstance(templateID, str)
                assert isinstance(sv, bullet_data._BulletData)
                del templateID, sv
        except AssertionError:
            return RetVal(False, '<spawn> received invalid arguments', None)

        # Convenience.
        names = [_[0] for _ in newObjects]
        SVs = [_[1] for _ in newObjects]

        with util.Timeit('spawn:1 getRawTemplate') as timeit:
            # Fetch the raw templates for all ``names``.
            ret = self.getRawTemplate(names)
            if not ret.ok:
                self.logit.info(ret.msg)
                return ret
            templates = ret.data

        # Request unique IDs for the objects to spawn.
        ret = azrael.database.getUniqueObjectIDs(len(names))
        if not ret.ok:
            self.logit.error(ret.msg)
            return ret
        objIDs = ret.data

        with util.Timeit('spawn:2 createSVs') as timeit:
            # Make a copy of every template and endow it with the meta
            # information for an instantiated object. Then add it to the list
            # of objects to spawn.
            dbDocs = []
            for idx, name in enumerate(names):
                tmp = dict(templates[name])
                tmp['objID'] = objIDs[idx]
                tmp['lastChanged'] = 0
                tmp['templateID'] = name
                dbDocs.append(tmp)

            # Insert all objects into the State Variable DB. Note: this does
            # not make Leonard aware of their existend (see next step).
            database.dbHandles['ObjInstances'].insert(dbDocs)

        with util.Timeit('spawn:3 addCmds') as timeit:
            # Compile the list of spawn commands that will be sent to Leonard.
            objs = []
            for objID, name, sv in zip(objIDs, names, SVs):
                # Convenience.
                t = templates[name]

                # Overwrite the user supplied collision shape with the one
                # specified in the template. This is to enforce geometric
                # consistency with the template data as otherwise strange
                # things may happen (eg a space-ship collision shape in the
                # template database with a simple sphere collision shape when
                # it is spawned).
                sv.cshape[:] = np.fromstring(t['cshape']).tolist()

                # Add the object description to the list.
                objs.append((objID, sv, t['AABB']))

            # Queue the spawn commands so that Leonard can pick them up.
            ret = physAPI.addCmdSpawn(objs)
            if not ret.ok:
                return ret
            self.logit.debug('Spawned {} new objects'.format(len(objs)))

        return RetVal(True, None, objIDs)

    @typecheck
    def removeObject(self, objID: int):
        """
        Remove ``objID`` from the physics simulation.

        :param int objID: ID of object to remove.
        :return: Success
        """
        ret = physAPI.addCmdRemoveObject(objID)
        database.dbHandles['ObjInstances'].remove({'objID': objID}, mult=True)
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

        :param list(int) objIDs: list of objects for which to returns the SV.
        :return: {objID_1: SV_k, ...}
        :rtype: dict
        """
        with util.Timeit('physAPI.getSV') as timeit:
            # Get the State Variables.
            ret = physAPI.getStateVariables(objIDs)
            if not ret.ok:
                return RetVal(False, 'One or more IDs do not exist', None)

        # Query the lastChanged values for all objects.
        docs = database.dbHandles['ObjInstances'].find(
            {'objID': {'$in': objIDs}},
            {'lastChanged': 1, 'objID': 1})

        # Convert the list of [{objID1: cs1}, {objID2: cs2}, ...] into
        # a simple {objID1: cs1, objID2: cs2, ...} dictionary.
        docs = {_['objID']: _['lastChanged'] for _ in docs}

        # Overwrite the 'lastChanged' field in the State Variable with the
        # current value so that the user automatically gets the latest value.
        sv = ret.data
        out = {}
        for objID in objIDs:
            if (objID in docs) and (sv[objID] is not None):
                out[objID] = sv[objID]._replace(lastChanged=docs[objID])
            else:
                out[objID] = None

        return RetVal(True, None, out)

    @typecheck
    def getGeometry(self, objID: int):
        """
        Return the vertices, UV map, and RGB map for ``objID``.

        All returned values are NumPy arrays.

        If the ID does not exist return an error.

        .. note::
           It is possible that an object has no geometry. An empty array will
           be returned in that case.

        :param int objID: object ID
        :return: Vertices, UV, and RGB data for ``objID``.
        :rtype: {'vert': arr_float64, 'uv': arr_float64, 'rgb': arr_uint8}
        """
        # Retrieve the geometry. Return an error if the ID does not
        # exist. Note: an empty geometry field is valid because Azrael supports
        # dummy objects.
        doc = database.dbHandles['ObjInstances'].find_one({'objID': objID})
        if doc is None:
            return RetVal(False, 'ID <{}> does not exist'.format(objID), None)
        else:
            geo = pickle.loads(doc['geo'])
            vert = geo['vertices']
            uv = geo['UV']
            rgb = geo['RGB']
            return RetVal(True, None, {'vert': vert, 'uv': uv, 'rgb': rgb})

    @typecheck
    def setGeometry(self, objID: int, vert: list, uv: list, rgb: list):
        """
        Update the ``vert``, ``uv`` and ``rgb`` data for ``objID``.

        Return with an error if ``objID`` does not exist.

        :param int objID: the object for which to update the geometry.
        :param list vert: list of vertices.
        :param list uv: list of UV coordinate pairs.
        :param list RGB: list of RGB values for every UV pair.
        :return: Success
        """
        if not self._isGeometrySane(vert, uv, rgb):
            msg = 'Invalid geometry for objID <{}>'.format(objID)
            return RetVal(False, msg, None)

        geo = {'vertices': vert, 'UV': uv, 'RGB': rgb}

        ret = database.dbHandles['ObjInstances'].update(
            {'objID': objID},
            {'$set': {'geo': pickle.dumps(geo)},
             '$inc': {'lastChanged': 1}})

        if ret['n'] == 1:
            return RetVal(True, None, None)
        else:
            return RetVal(False, 'ID <{}> does not exist'.format(objID), None)

    @typecheck
    def setForce(self, objID: int, force: list, rpos: list):
        """
        Apply ``force`` to ``objID``.

        The force will be applied at ``rpos`` relative to the center of mass.

        If ``objID`` does not exist return an error.

        :param int objID: object ID
        :return: Sucess
        """
        torque = np.cross(np.array(rpos, np.float64),
                          np.array(force, np.float64)).tolist()
        return physAPI.addCmdSetForceAndTorque(objID, force, torque)

    @typecheck
    def setStateVariable(self, objID: int,
                         data: bullet_data.BulletDataOverride):
        """
        Set the State Variables of ``objID`` to ``data``.

        For a detailed description see ``physAPI.addCmdModifyStateVariable``
        since this method is only a wrapper for it.

        :param int objID: object ID
        :param BulletDataOverride data: new object attributes.
        :return: Success
        """
        ret = physAPI.addCmdModifyStateVariable(objID, data)
        if ret.ok:
            return RetVal(True, None, None)
        else:
            return RetVal(False, ret.msg, None)

    @typecheck
    def getTemplateID(self, objID: int):
        """
        Return the template ID from which ``objID`` was created.

        :param int objID: object ID.
        :return: templateID from which ``objID`` was created.
        """
        doc = database.dbHandles['ObjInstances'].find_one({'objID': objID})
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

        :param dummy: irrelevant
        :return: list of objIDs
        :rtype: list(int)
        """
        ret = physAPI.getAllObjectIDs()
        if not ret.ok:
            return RetVal(False, ret.data, None)
        else:
            return RetVal(True, None, ret.data)

    @typecheck
    def getAllStateVariables(self):
        """
        Return all State Variables in a dictionary.

        The dictionary will have the objIDs and State Variables as keys and
        values, respectively.

        :return: {objID_1: SV_k, ...}
        :rtype: dict
        """
        with util.Timeit('physAPI.getSV') as timeit:
            # Get the State Variables.
            ret = physAPI.getAllStateVariables()
            if not ret.ok:
                return ret
        sv = ret.data

        # Query the lastChanged values for all objects.
        docs = database.dbHandles['ObjInstances'].find(
            {'objID': {'$in': list(ret.data.keys())}},
            {'lastChanged': 1, 'objID': 1})

        # Convert the list of [{objID1: cs1}, {objID2: cs2}, ...] into
        # a simple {objID1: cs1, objID2: cs2, ...} dictionary.
        docs = {_['objID']: _['lastChanged'] for _ in docs}

        # Overwrite the 'lastChanged' field in the State Variable. This ensures
        # the user gets the most up-to-date value on when the object geometry
        # last changed.
        out = {}
        for objID in sv:
            if objID in docs:
                out[objID] = sv[objID]._replace(lastChanged=docs[objID])
        return RetVal(True, None, out)
