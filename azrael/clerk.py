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
import json
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
import azrael.physics_interface as physAPI
import azrael.bullet.bullet_data as bullet_data

from collections import namedtuple
from azrael.typecheck import typecheck

# Convenience.
ipshell = IPython.embed
RetVal = util.RetVal
Template = azrael.util.Template
Fragment = azrael.util.Fragment


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
            'get_all_statevars': (
                protocol.ToClerk_GetAllStateVariables_Decode,
                self.getAllStateVariables,
                protocol.FromClerk_GetAllStateVariables_Encode),
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
            'update_fragment_states': (
                protocol.ToClerk_UpdateFragmentStates_Decode,
                self.updateFragmentStates,
                protocol.FromClerk_UpdateFragmentStates_Encode),
            }

        # Insert default objects. None of them has an actual geometry but
        # their collision shapes are: none, sphere, cube.
        frags = [Fragment(name='NoName', vert=[], uv=[], rgb=[])]
        t1 = Template('_templateNone', [0, 1, 1, 1], frags, [], [])
        t2 = Template('_templateSphere', [3, 1, 1, 1],frags, [], [])
        t3 = Template('_templateCube', [4, 1, 1, 1], frags, [], [])
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
        addr = 'tcp://{}:{}'.format(config.addr_clerk, config.port_clerk)
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

        # Compile a list of all parts defined in the template.
        booster_t = [parts.Booster(*_) for _ in ret.data['boosters']]
        booster_t = {_.partID: _ for _ in booster_t}
        factory_t = [parts.Factory(*_) for _ in ret.data['factories']]
        factory_t = {_.partID: _ for _ in factory_t}

        # Fetch the SV for objID (we need this to determine the orientation of
        # the base object to which the parts are attached).
        sv_parent = self.getStateVariables([objID])
        if not sv_parent.ok:
            msg = 'Could not retrieve SV for objID={}'.format(objID)
            self.logit.warning(msg)
            return RetVal(False, msg, None)

        # Extract the parent's orientation from svdata.
        sv_parent = sv_parent.data[objID]['sv']
        parent_orient = sv_parent.orientation
        quat = util.Quaternion(parent_orient[3], parent_orient[:3])

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
        del booster_t

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

        # Ensure all boosters/factories receive at most one command each.
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

        ret = self.updateBoosterForces(objID, cmd_boosters)
        if not ret.ok:
            return ret

        # Apply the net- force and torque exerted by the boostes.
        force, torque = ret.data
        physAPI.addCmdBoosterForce(objID, force, torque)
        del ret, force, torque

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
    def updateBoosterForces(self, objID: int, cmds: list):
        """
        Return forces and update the Booster values in the instance DB.

        A typical return value looks like this::

          {1: ([1, 0, 0], [0, 2, 0]), 2: ([1, 2, 3], [4, 5, 6]), ...}

        :param int objID: object ID
        :param list cmds: list of Booster commands.
        :return: dictionary with objID as key and force/torque as values.
        :rtype: dict
        """
        # Convenience.
        db = database.dbHandles['ObjInstances']

        # Put the new force values into a dictionary for convenience later on.
        cmds = {_.partID: _.force_mag for _ in cmds}

        # Query the instnace template for ``objID``. Return with an error if it
        # does not exist.
        query = {'objID': objID}
        doc = db.find_one(query, {'boosters': 1})
        if doc is None:
            msg = 'Object <{}> does not exist'.format(objID)
            return RetVal(False, msg, None)

        # Put the Booster entries from the database into Booster tuples.
        boosters = [parts.Booster(*_) for _ in doc['boosters']]
        boosters = {_.partID: _ for _ in boosters}

        # Tally up the forces exerted by all Boosters on the object.
        force, torque = np.zeros(3), np.zeros(3)
        for partID, booster in boosters.items():
            # Update the Booster value if the user specified a new one.
            if partID in cmds:
                boosters[partID] = booster._replace(force=cmds[partID])
                booster = boosters[partID]
                del cmds[partID]

            # Convenience.
            b_pos = np.array(booster.pos)
            b_dir = np.array(booster.direction)

            # Update the central force and torque.
            force += booster.force * b_dir
            torque += booster.force * np.cross(b_pos, b_dir)

        # If we have not consumed all commands then at least one partID did not
        # exist --> return with an error in that case.
        if len(cmds) > 0:
            return RetVal(False, 'Some Booster partIDs were invalid', None)

        # Update the new Booster values in the instance DB. To this end convert
        # the dictionary back to a list because Mongo does not like it if
        # dictionary keys are integers.
        boosters = list(boosters.values())
        db.update(query, {'$set': {'boosters': boosters}})

        # Return the final force and torque as a tuple of tuples.
        out = (force.tolist(), torque.tolist())
        return RetVal(True, None, out)

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

        fixme: explain the structure of ``templates``.

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

            # The templates will be inserted in bulk for efficiency reasons.
            db = database.dbHandles['Templates']
            bulk = db.initialize_unordered_bulk_op()

            # Add each template to the bulk operation.
            for tt in templates:
                # Initial AABB size. We will expand it when we parse the
                # geometries to fit the largest one.
                aabb = 0
                assert isinstance(tt.name, str)
                assert isinstance(tt.fragments, list)

                # Sanity check all fragment geometries.
                for frag in tt.fragments:
                    # Sanity checks.
                    try:
                        assert isinstance(frag, Fragment)
                        assert isinstance(frag.vert, list)
                        assert isinstance(frag.uv, list)
                        assert isinstance(frag.rgb, list)
                    except AssertionError:
                        msg = 'Parameters for addTemplates must be lists'
                        return RetVal(False, msg, None)

                    if not self._isGeometrySane(frag.vert, frag.uv, frag.rgb):
                        msg = 'Invalid geometry for template <{}>'.format(tt.name)
                        return RetVal(False, msg, None)

                    # Determine the largest possible side length of the AABB. To
                    # find it, just determine the largest spatial extent in any
                    # axis direction. That is the side length of the AABB
                    # cube. Then multiply it with sqrt(3) to ensure that any
                    # rotation angle of the object is covered. The slightly larger
                    # value of sqrt(3.1) adds some slack.
                    if len(frag.vert) > 0:
                        len_x = max(frag.vert[0::3]) - min(frag.vert[0::3])
                        len_y = max(frag.vert[1::3]) - min(frag.vert[1::3])
                        len_z = max(frag.vert[2::3]) - min(frag.vert[2::3])
                        tmp = np.sqrt(3.1) * max(len_x, len_y, len_z)
                        aabb = np.amax((aabb, tmp))
                    del frag

                # Compile the Mongo document for the new template.
                data = {
                    'name': tt.name,
                    'cshape': tt.cs,
                    'aabb': float(aabb),
                    'boosters': tt.boosters,
                    'factories': tt.factories}

                # Compile the geometry data.
                geo = {_.name: Fragment(*_) for _ in tt.fragments}

                # Compile file name for geometry data and add that name to the
                # template dictionary.
                base_name = tt.name + '_geo'
                data['file_geo'] = os.path.join(config.dir_template, base_name)
                data['url_geo'] = '/templates/' + base_name

                # Abort if the template already exists.
                # Note: the following condition can fall prey to the race
                # condition where a file is created after checking but before
                # the file is written. For templates this is relatively
                # harmless and therefore ignored here.
                if os.path.exists(data['file_geo']):
                    # A template with name ``templateID`` already existed -->
                    # failure.
                    msg = 'Template <{}> already exists'.format(data['name'])
                    return RetVal(False, msg, None)

                # Save the geometry data.
                geo = json.dumps(geo)
                open(data['file_geo'], 'wb').write(geo.encode('utf8'))
                del geo

                # Add the template to the database.
                query = {'templateID': tt.name}
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
    def getTemplates(self, templateIDs: list):
        """
        Return the raw data for all ``templateIDs`` as a dictionary.

        This method will return either all templates or none. However, if the
        same template is specified multiple times in ``templateIDs`` then it
        will only return unique names.

        For instance, ``getTemplates([name_1, name_2, name_1])`` is
        tantamount to calling ``getTemplates([name_1, name_2])``.

        The return value has the following structure::

          ret = {template_names[0]: {
                   fragment_name[0]: {
                      'cshape': X, 'vert': X, 'uv': X, 'rgb': X,
                      'boosters': X, 'factories': X, 'aabb': X},
                   fragment_name[1]: {
                      'cshape': X, 'vert': X, 'uv': X, 'rgb': X,
                      'boosters': X, 'factories': X, 'aabb': X}},
                 template_names[1]: {}, }.

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

        # Load geometry data and add it to template.
        return RetVal(True, None, doc)

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

        with util.Timeit('spawn:1 getTemplates') as timeit:
            # Fetch the raw templates for all ``names``.
            ret = self.getTemplates(names)
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

                # Copy the geometry from the template- to the instance
                # directory and update the 'file_geo' field to point to it.
                geodata = open(tmp['file_geo'], 'rb').read()
                tmp['file_geo'] = os.path.join(config.dir_instance,
                                               str(tmp['objID']) + '_geo')
                open(tmp['file_geo'], 'wb').write(geodata)

                # Parse the geometry data to determine the names of all
                # fragments. Then create an initial fragment state for each
                # name.
                # fixme: use named tuple for frag_init_state
                geodata = json.loads(geodata.decode('utf8'))
                frag_init_state = (1, [0, 0, 0], [0, 0, 0, 1])
                tmp['fragState'] = {_: frag_init_state for _ in geodata}
                del frag_init_state, geodata

                # Add the new template document.
                dbDocs.append(tmp)

            # Insert all objects into the State Variable DB. Note: this does
            # not make Leonard aware of their existence (see next step).
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
                sv.cshape[:] = t['cshape']

                # Add the object description to the list.
                objs.append((objID, sv, t['aabb']))

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

        :param list(int) objIDs: list of objects for which to return the SV.
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
            {'lastChanged': 1, 'objID': 1, 'fragState': 1})

        # Convert the list of [{objID1: cs1}, {objID2: cs2}, ...] into
        # a simple {objID1: cs1, objID2: cs2, ...} dictionary.
        # fixme: split into two dictionaries for readability.
        docs = {_['objID']: (_['lastChanged'], _['fragState']) for _ in docs}

        # Overwrite the 'lastChanged' field in the State Variable with the
        # current value so that the user automatically gets the latest value.
        sv = ret.data
        out = {}
        for objID in objIDs:
            if (objID in docs) and (sv[objID] is not None):
                tmp = sv[objID]._replace(lastChanged=docs[objID][0])
                out[objID] = {'sv': tmp, 'frag': docs[objID][1]}
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
        # dummy objects without geometries.
        doc = database.dbHandles['ObjInstances'].find_one({'objID': objID})
        if doc is None:
            return RetVal(False, 'ID <{}> does not exist'.format(objID), None)
        else:
            geo = open(doc['file_geo'], 'rb').read()
            geo = json.loads(geo.decode('utf8'))
            geo = {_: Fragment(*geo[_]) for _ in geo}
            return RetVal(True, None, geo)

    @typecheck
    def setGeometry(self, objID: int, fragments: list):
        """
        Update the ``vert``, ``uv`` and ``rgb`` data for ``objID``.

        Return with an error if ``objID`` does not exist.
        fixup: docu update due to new signature

        :param int objID: the object for which to update the geometry.
        :param list vert: list of vertices.
        :param list uv: list of UV coordinate pairs.
        :param list RGB: list of RGB values for every UV pair.
        :return: Success
        """
        # Fetch the instance data for ``objID`` to find out where the current
        # geometry is stored.
        db = database.dbHandles['ObjInstances']
        doc = db.find_one({'objID': objID})
        if doc is None:
            return RetVal(False, 'ID <{}> does not exist'.format(objID), None)

        # Sanity check for geometry.
        # fixme: isGeometrySane must exped a 'Fragment' instance.
        for frag in fragments:
            if not self._isGeometrySane(frag.vert, frag.uv, frag.rgb):
                msg = 'Invalid geometry for objID <{}>'.format(objID)
                return RetVal(False, msg, None)

        # Overwrite the geometry file with the new one.
        # fixme: add same sanity check as in addTemplate
        geo = json.loads(open(doc['file_geo'], 'rb').read().decode('utf8'))
        for frag in fragments:
            if frag.name not in geo:
                msg = 'Unknown fragment <{}>'.format(frag.name),
                return RetVal(False, msg, None)
            geo[frag.name] = frag
        geo = json.dumps(geo)
        open(doc['file_geo'], 'wb').write(geo.encode('utf8'))
        del geo

        # Update the 'lastChanged' flag. Any clients will automatically receive
        # this flag whenever they query state variables.
        ret = db.update({'objID': objID}, {'$inc': {'lastChanged': 1}})

        # Verify the update worked.
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
        return physAPI.addCmdDirectForce(objID, force, torque)

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
    def getAllStateVariables(self, dummy=None):
        """
        Return all State Variables in a dictionary.

        The dictionary will have the objIDs and State Variables as keys and
        values, respectively.

        .. note::
           The ``dummy`` argument is a placeholder because the ``runCommand``
           function assumes that every method takes at least one argument.

        fixme: remove/reduce code duplication with getStateVariables

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
            {'lastChanged': 1, 'objID': 1, 'fragState': 1})

        # Convert the list of [{objID1: cs1}, {objID2: cs2}, ...] into
        # a simple {objID1: cs1, objID2: cs2, ...} dictionary.
        docs = {_['objID']: (_['lastChanged'], _['fragState']) for _ in docs}

        # Overwrite the 'lastChanged' field in the State Variable. This ensures
        # the user gets the most up-to-date value on when the object geometry
        # last changed.
        out = {}
        for objID in sv:
            if objID in docs:
                tmp = sv[objID]._replace(lastChanged=docs[objID][0])
                out[objID] = {'sv': tmp, 'frag': docs[objID][1]}
        return RetVal(True, None, out)

    @typecheck
    def updateFragmentStates(self, fragData: dict):
        """
        Update one or more fragments in one or more objects.

        The ``fragData`` dictionary has the following structure:

          fragData = {
            objID_1: {
              '1': [5, [5, 5, 5], [5, 5, 5, 5]],
              '3': [5, [5, 5, 5], [5, 5, 5, 5]]
            },
            objID_2: {
              '1': [2, [3, 3, 3], [4, 4, 4, 4]]
            }
        }

        where an entry like {'1': [2, [3, 3, 3], [4, 4, 4, 4]]} means
        to update fragment '1'. Specifically, set its scale to 2, its position
        to [2, 2, 2], and its orientation (Quaternion) to [4, 4, 4, 4].

        fixme docu: only updates existing objects; for any given object either
        all fragments are updated, or none.

        :param dict fragData: new fragment data for each object.
        :return: success.
        """
        # Convenience.
        update = database.dbHandles['ObjInstances'].update

        # Sanity checks.
        try:
            # All objIDs must be integers and all values must be dictionaries.
            for k1, v1 in fragData.items():
                assert isinstance(k1, int)
                assert isinstance(v1, dict)

                # Each fragmentID must be a stringified integer, and all
                # fragment data must be a list with three entries.
                for k2, v2 in v1.items():
                    assert isinstance(k2, str)
                    assert isinstance(v2, list)

                    # Every fragment must receive three pieces of information:
                    # scale (scalar), position (3-element vector), and
                    # orientation (4-element vector).
                    assert len(v2) == 3
                    assert isinstance(v2[0], (int, float))
                    assert len(v2[1]) == 3
                    assert len(v2[2]) == 4
                    for _ in v2[1]:
                        assert isinstance(_, (int, float))
                    for _ in v2[2]:
                        assert isinstance(_, (int, float))
        except (TypeError, AssertionError):
            return RetVal(False, 'Invalid data format', None)

        # Update the fragments one objects at a time.
        ok = True
        for objID, frag in fragData.items():
            # Mongo query: ensure every part ID actually exists. The result of
            # the code below will be a dictionary like this:
            #   {'fragState.1': {'$exists': 1},
            #    'fragState.2': {'$exists': 1},
            #    'objID': 2}
            query = {'fragState.{}'.format(k): {'$exists': 1} for k in frag}
            query['objID'] = objID

            # Overwrite the specified partIDs. This will produce a dictionary
            # like this:
            #   {'fragState.1': [7, [7, 7, 7], [7, 7, 7, 7]],
            #    'fragState.2': [8, [8, 8, 8], [8, 8, 8, 8]]}
            newvals = {'fragState.{}'.format(k): frag[k] for k in frag}

            # Issue the update command to Mongo.
            ret = update(query, {'$set': newvals})

            # Exactly one document was updated if everything went well. Note
            # that we must check 'n', not 'nModified'. The difference is that
            # 'n' tells us how many documents Mongo has modified,
            # whereas 'nModified' refers to the number of documents that are
            # now different. This distinction is important if the new fragment
            # values are the same as the old ones, because 'n'=1 whereas
            # 'nModified'=0.
            if ret['n'] != 1:
                ok = False
        return RetVal(ok, None, None)
