# Copyright 2015, Oliver Nagy <olitheolix@gmail.com>
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
and ``Client`` instances connected to each other.

This module implement ZeroMQ version of the ``Clerk``. For a Websocket version
(eg. JavaScript developers) use ``Clacks`` from `clacks.py` (their feature set
is identical).

"""
import io
import os
import sys
import zmq
import json
import cytoolz
import logging
import traceback
import subprocess

import numpy as np

import azrael.igor
import azrael.database
import azrael.util as util
import azrael.parts as parts
import azrael.config as config
import azrael.leo_api as leoAPI
import azrael.dibbler as dibbler
import azrael.database as database
import azrael.protocol as protocol
import azrael.rb_state as rb_state

from IPython import embed as ipshell
from azrael.types import typecheck, RetVal, Template, CollShapeMeta
from azrael.types import FragState, MetaFragment


class Clerk(config.AzraelProcess):
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

        # Create a Dibbler instance to gain access to the model database.
        self.dibbler = dibbler.Dibbler()

        # Igor instance.
        self.igor = azrael.igor.Igor()

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
            'get_body_states': (
                protocol.ToClerk_GetBodyState_Decode,
                self.getBodyStates,
                protocol.FromClerk_GetBodyState_Encode),
            'get_all_body_states': (
                protocol.ToClerk_GetAllBodyStates_Decode,
                self.getAllBodyStates,
                protocol.FromClerk_GetAllBodyStates_Encode),
            'set_body_state': (
                protocol.ToClerk_SetBodyState_Decode,
                self.setBodyState,
                protocol.FromClerk_SetBodyState_Encode),
            'get_fragment_geometries': (
                protocol.ToClerk_GetFragmentGeometries_Decode,
                self.getFragmentGeometries,
                protocol.FromClerk_GetFragmentGeometries_Encode),
            'set_fragment_geometries': (
                protocol.ToClerk_SetFragmentGeometry_Decode,
                self.setFragmentGeometries,
                protocol.FromClerk_SetFragmentGeometry_Encode),
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
            'set_fragment_states': (
                protocol.ToClerk_SetFragmentStates_Decode,
                self.setFragmentStates,
                protocol.FromClerk_SetFragmentStates_Encode),
            'add_constraints': (
                protocol.ToClerk_AddConstraints_Decode,
                self.addConstraints,
                protocol.FromClerk_AddConstraints_Encode),
            'get_constraints': (
                protocol.ToClerk_GetConstraints_Decode,
                self.getConstraints,
                protocol.FromClerk_GetConstraints_Encode),
            'get_all_constraints': (
                protocol.ToClerk_GetAllConstraints_Decode,
                self.getAllConstraints,
                protocol.FromClerk_GetAllConstraints_Encode),
            'delete_constraints': (
                protocol.ToClerk_DeleteConstraints_Decode,
                self.deleteConstraints,
                protocol.FromClerk_DeleteConstraints_Encode),
        }

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
            self.returnErr(self.last_addr, out)
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
                self.returnErr(self.last_addr, ret.msg)

    def run(self):
        """
        Initialise ZeroMQ and wait for client requests.

        This method will not return.

        :raises: None
        """
        # Call `run` method of `AzraelProcess` base class.
        super().run()

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
            if self.sock_cmd not in sock:
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
                self.returnErr(self.last_addr, 'JSON decoding error in Clerk')
                continue

            # Sanity check: every message must contain at least a command byte.
            if not (('cmd' in msg) and ('payload' in msg)):
                self.returnErr(self.last_addr, 'Invalid command format')
                continue

            # Extract the command word and payload.
            cmd, self.payload = msg['cmd'], msg['payload']

            # The command word determines the action...
            if cmd in self.codec:
                # Look up the decode-process-encode functions for the current
                # command.
                enc, proc, dec = self.codec[cmd]

                # Run the Clerk function. The try/except is to intercept any
                # errors and prevent Clerk from dying.
                try:
                    self.runCommand(enc, proc, dec)
                except Exception:
                    msg = 'Client data for <{}> raised an error in Clerk'
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
                    self.returnErr(self.last_addr, msg, addToLog=False)
                    del msg, buf, msg_st
            else:
                # Unknown command.
                self.returnErr(self.last_addr,
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
            self.returnErr(addr, 'JSON encoding error in Clerk')
            return

        self.sock_cmd.send_multipart([addr, b'', ret.encode('utf8')])

    @typecheck
    def returnErr(self, addr, msg: str='', addToLog: bool=True):
        """
        Send negative reply and log a warning message.

        This is a convenience method to enhance readability.

        :param addr: ZeroMQ address as returned by the router socket.
        :param bool addToLog: logs a Warning with ``msg`` if *True*
        :param str msg: error message.
        :return: None
        """
        # Convert the message to a byte string (if it is not already).
        ret = json.dumps({'ok': False, 'payload': {}, 'msg': msg})
        if addToLog:
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
        sv_parent = self.getBodyStates([objID])
        if not sv_parent.ok:
            msg = 'Could not retrieve SV for objID={}'.format(objID)
            self.logit.warning(msg)
            return RetVal(False, msg, None)

        # Return with an error if the requested objID does not exist.
        if sv_parent.data[objID] is None:
            msg = 'objID={} does not exits'.format(objID)
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
        leoAPI.addCmdBoosterForce(objID, force, torque)
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
            sv = rb_state.RigidBodyState(
                position=pos, velocityLin=velocityLin,
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
    def _isNameValid(self, name):
        """
        Return *True* if ``name`` is a valid template name.

        The template ``name`` is valid when it is a non-empty string, at most
        32 characters long, and contains only alphanumeric characters (ie
        [a-zA-Z0-9]) and '_'.

        :param str name: name to validate.
        :return: *True* if ``name`` is valid, *False* otherwise.
        """
        # Template name must be a string.
        if not isinstance(name, str):
            return False

        # Must contain at least one character and no more than 32.
        if not (0 < len(name) <= 32):
            return False

        # Compile the set of admissible characters.
        ref = 'abcdefghijklmnopqrstuvwxyz'
        ref += ref.upper()
        ref += '0123456789_'
        ref = set(ref)

        # Return true if ``name`` only consists of characters from the just
        # defined reference set.
        return set(name).issubset(ref)

    @typecheck
    def _verifyCollisionShapes(self, cshapes: (tuple, list)):
        """
        Return *True* if all Collision shapes in ``cshapes`` are valid.

        fixme: incomplete; untested; good enough for now until its merit is
        clear.
        """
        try:
            for cs in cshapes:
                cs = CollShapeMeta(*cs)
                assert isinstance(cs.aid, str)
                assert isinstance(cs.type, str)
                assert isinstance(cs.pos, (tuple, list))
                assert isinstance(cs.rot, (tuple, list))

                assert len(cs.pos) == 3
                assert len(cs.rot) == 4
                for _ in cs.pos:
                    assert isinstance(_, (float, int))
                for _ in cs.rot:
                    assert isinstance(_, (float, int))
            return RetVal(True, None, None)
        except (AssertionError, TypeError):
            msg = 'Invalid Collision shape'
            return RetVal(False, msg, None)

    @typecheck
    def addTemplates(self, templates: list):
        """
        Add all ``templates`` to the system so that they can be spawned.

        This method returns with an error if a template could not be added.

        ..note:: due to the primitive way the model files are stored
                 in the file system it is possible that model files were
                 written to disk yet Azrael does not know about them.

        The elements in ``templates`` are instances of
        :ref:``azrael.util.Template``.

        :param list templates: list of Template definitions.
        :return: success
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

            # The templates will be inserted with a single bulk operation.
            db = database.dbHandles['Templates']
            bulk = db.initialize_unordered_bulk_op()

            # Add each template to the bulk.
            for tt in templates:
                # Sanity check:
                if not isinstance(tt.fragments, list):
                    return RetVal(False, 'Fragments must be in a list', None)
                if not self._isNameValid(tt.aid):
                    return RetVal(False, 'Invalid template name', None)

                # Ensure all fragments have the correct type and their names
                # are both valid and unique.
                tmp = [_ for _ in tt.fragments if isinstance(_, MetaFragment)]
                tmp = [_ for _ in tmp if self._isNameValid(_.aid)]
                tmp = set([_.aid for _ in tmp])
                if len(set(tmp)) < len(tt.fragments):
                    msg = 'One or more fragment names are invalid',
                    return RetVal(False, msg, None)
                del tmp

                # Ensure all collision shapes are valid.
                ret = self._verifyCollisionShapes(tt.cshapes)
                if not ret.ok:
                    return RetVal(False, ret.msg, None)

                # Ensure all Boosters and Factories have a sane partID.
                try:
                    for booster in tt.boosters:
                        assert self._isNameValid(booster.partID)
                    for factory in tt.factories:
                        assert self._isNameValid(factory.partID)
                except AssertionError:
                    msg = 'One or more Booster/Factory names are invalid'
                    return RetVal(False, msg, None)

                # Ask Dibbler to add the template. Abort immediately if Dibbler
                # came back with an error (should be impossible, but just to
                # be sure).
                ret = self.dibbler.addTemplate(tt)
                if not ret.ok:
                    return ret

                # We already stored the geometry in Dibbler; here we only add
                # the meta data (mostly to avoid data duplication) which is why
                # we delete the 'data' attribute.
                frags = [frag._replace(data=None) for frag in tt.fragments]

                # Compile the Mongo document for the new template.
                data = {
                    'url': config.url_templates + '/' + tt.aid,
                    'aid': tt.aid,
                    'cshapes': tt.cshapes,
                    'aabb': float(ret.data['aabb']),
                    'boosters': tt.boosters,
                    'factories': tt.factories,
                    'fragments': frags}
                del frags

                # Add the template to the database.
                query = {'templateID': tt.aid}
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
        Return the meta data for all ``templateIDs`` as a dictionary.

        This method will return either return the templates for all specified
        `templateIDs`, or none. Furthermore, it will return each template only
        once, even if it was specified multiple times in `templateIDs`.

        For instance, ``getTemplates([name_1, name_2, name_1])`` is
        tantamount to calling ``getTemplates([name_1, name_2])``.

        The return value has the following structure::

          ret = {template_names[0]: {
                   fragment_name[0]: {
                      'cshapes': X, 'vert': X, 'uv': X, 'rgb': X,
                      'boosters': X, 'factories': X, 'aabb': X},
                   fragment_name[1]: {
                      'cshapes': X, 'vert': X, 'uv': X, 'rgb': X,
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
        :return: Dictionary with keys 'cshapes', 'vert', 'uv', 'rgb',
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

        where ``template_name_k`` is a string and ``sv_k`` is a
        ``RigidBodyState`` instance.

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
                assert isinstance(sv, rb_state._RigidBodyState)
                del templateID, sv
        except AssertionError:
            return RetVal(False, '<spawn> received invalid arguments', None)

        # Convenience: convert the list of tuples into a plain list, ie
        # [(t1, sv1), (t2, sv2), ...]  -->  [t1, t2, ...] and [sv1, sv2, ...].
        t_names = [_[0] for _ in newObjects]
        SVs = [_[1] for _ in newObjects]

        with util.Timeit('spawn:1 getTemplates') as timeit:
            # Fetch the raw templates for all ``t_names``.
            ret = self.getTemplates(t_names)
            if not ret.ok:
                self.logit.info(ret.msg)
                return ret
            templates = ret.data

        # Request unique IDs for the objects to spawn.
        ret = azrael.database.getUniqueObjectIDs(len(t_names))
        if not ret.ok:
            self.logit.error(ret.msg)
            return ret
        objIDs = ret.data

        with util.Timeit('spawn:2 createSVs') as timeit:
            # Make a copy of every template and endow it with the meta
            # information for an instantiated object. Then add it to the list
            # of objects to spawn.
            dbDocs = []
            for idx, name in enumerate(t_names):
                # Convenience.
                objID = objIDs[idx]

                # Make a copy of the current template dictionary and populate
                # it with the values that describe the template instance.
                doc = dict(templates[name])
                doc['objID'] = objID
                doc['version'] = 0
                doc['templateID'] = name

                # Copy the template files to the instance collection.
                ret = self.dibbler.spawnTemplate(name, str(objID))
                if not ret.ok:
                    # Skip this 'spawn' command because Dibbler and Clerk are
                    # out of sync; Clerk has found the template but Dibbler
                    # has not --> should not happen!
                    msg = 'Dibbler and Clerk are out of sync for template {}.'
                    msg = msg.format(name)
                    msg += ' Dibbler returned with this error: <{}>'
                    msg = msg.format(ret.msg)
                    self.logit.warning(msg)
                    continue
                else:
                    # URL where the instance data is available.
                    doc['url'] = ret.data['url']

                # Parse the geometry data to determine all fragment names.
                # Then compile a neutral initial state for each.
                doc['fragState'] = {}
                for f in doc['fragments']:
                    f = MetaFragment(*f)
                    doc['fragState'][f.aid] = FragState(
                        aid=f.aid,
                        scale=1,
                        position=[0, 0, 0],
                        orientation=[0, 0, 0, 1])

                # Add the new template document.
                dbDocs.append(doc)
                del idx, name, objID, doc

            # Return if no objects were spawned (eg the templates did not
            # exist).
            if len(dbDocs) == 0:
                return RetVal(True, None, tuple())

            # Insert all objects into the State Variable DB. Note: this does
            # not make Leonard aware of their existence (see next step).
            database.dbHandles['ObjInstances'].insert(dbDocs)

        with util.Timeit('spawn:3 addCmds') as timeit:
            # Sanity check: collision shapes.
            for name, sv, objID in zip(t_names, SVs, objIDs):
                cs = templates[name]['cshapes']
                ret = self._verifyCollisionShapes(cs)
                if not ret.ok:
                    return ret

            # Compile the list of spawn commands that will be sent to Leonard.
            objs = []
            for name, sv, objID in zip(t_names, SVs, objIDs):
                # Convenience.
                t = templates[name]

                # Overwrite the user supplied collision shape with the one
                # specified in the template. This is to enforce geometric
                # consistency with the template data as otherwise strange
                # things may happen (eg a space-ship collision shape in the
                # template database with a simple sphere collision shape when
                # it is spawned).
                sv.cshapes[:] = t['cshapes']

                # Add the object description to the list.
                objs.append((objID, sv, t['aabb']))

            # Queue the spawn commands so that Leonard can pick them up.
            ret = leoAPI.addCmdSpawn(objs)
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
        ret = leoAPI.addCmdRemoveObject(objID)
        database.dbHandles['ObjInstances'].remove({'objID': objID}, mult=True)
        if ret.ok:
            self.dibbler.deleteInstance(str(objID))
            return RetVal(True, None, None)
        else:
            return RetVal(False, ret.msg, None)

    @typecheck
    def getFragmentGeometries(self, objIDs: list):
        """
        Return information about the fragments of each object in ``objIDs``.

        This method returns a dictionary of the form

         {objID_1: {'type': 'raw', 'url': 'http:...'},
          objID_2: {'type': 'dae', 'url': 'http:...'},
          objID_3: None,
          ...
        }

        Every element in ``objIDs`` will be a key in the returned dictionary.
        However, the corresponding value will be *None* if the object does not
        exist in Azrael.

        :param list objIDs: return geometry information for all of them.
        :return: meta information about all fragment for each object.
        :rtype: dict
        """
        # Retrieve the geometry. Return an error if the ID does not exist.
        # Note: an empty geometry field is still valid object.
        db = database.dbHandles['ObjInstances']
        docs = list(db.find({'objID': {'$in': objIDs}}))

        # Initialise the output dictionary with a None value for every
        # requested object. The loop below will overwrite these values for all
        # those objects that actually exist.
        out = {_: None for _ in objIDs}

        # Determine the fragment- type (eg. 'raw' or 'dae') and URL and put it
        # into the output dictionary. This will create a dictionary of the form
        # {objID_1:
        #     {name_1: {'type': 'raw', 'url': 'http:...'},
        #      name_2: {'type': 'raw', 'url': 'http:...'},...
        #     }
        #  objID_2: {name_1: {'type': 'dae', 'url': 'http:...'},...
        # }
        pj = os.path.join
        for doc in docs:
            u = doc['url']
            f = [MetaFragment(*_) for _ in doc['fragments']]
            obj = {_.aid: {'type': _.type, 'url': pj(u, _.aid)} for _ in f}
            out[doc['objID']] = obj
        return RetVal(True, None, out)

    @typecheck
    def setFragmentGeometries(self, objID: int, fragments: list):
        """
        Update the ``vert``, ``uv`` and ``rgb`` data for ``objID``.

        Return with an error if ``objID`` does not exist.

        :param int objID: the object for which to update the geometry.
        :param list fragments: the new fragments for ``objID``.
        :return: Success
        """
        # Sanity check the names of all fragments.
        for frag in fragments:
            if not self._isNameValid(frag.aid):
                msg = 'Invalid fragment name <{}>'.format(frag.aid)
                return RetVal(False, msg, None)

        # Convenience.
        update = database.dbHandles['ObjInstances'].update

        # Update the fragment geometry in Dibbler.
        for frag in fragments:
            ret = self.dibbler.updateFragments(str(objID), fragments)
            if not ret.ok:
                return ret

            # If the fragment type is '_none_' then remove it altogether.
            if frag.type == '_none_':
                update({'objID': objID},
                       {'$unset': {'fragState.{}'.format(frag.aid): True}})

        # Update the fragment's meta data in the DB.
        new_frags = [frag._replace(data=None) for frag in fragments]

        # Update the 'version' flag in the database. All clients
        # automatically receive this flag with their state variables.
        db = database.dbHandles['ObjInstances']
        ret = db.update({'objID': objID},
                        {'$inc': {'version': 1},
                         '$set': {'fragments': new_frags}
                         })

        # Return the success status of the database update.
        if ret['n'] == 1:
            return RetVal(True, None, None)
        else:
            return RetVal(False, 'ID <{}> does not exist'.format(objID), None)

    @typecheck
    def setForce(self, objID: int, force: (tuple, list), rpos: (tuple, list)):
        """
        Apply ``force`` to ``objID``.

        The force will be applied at ``rpos`` relative to the center of mass.

        If ``objID`` does not exist return an error.

        :param int objID: object ID
        :return: Sucess
        """
        torque = np.cross(np.array(rpos, np.float64),
                          np.array(force, np.float64)).tolist()
        return leoAPI.addCmdDirectForce(objID, force, torque)

    @typecheck
    def setBodyState(self, objID: int,
                     data: rb_state.RigidBodyStateOverride):
        """
        Set the State Variables of ``objID`` to ``data``.

        For a detailed description see ``leoAPI.addCmdModifyBodyState``
        since this method is only a wrapper for it.

        :param int objID: object ID
        :param RigidBodyStateOverride data: new object attributes.
        :return: Success
        """
        # Sanity check.
        ret = self._verifyCollisionShapes(data.cshapes)
        if not ret.ok:
            return ret

        ret = leoAPI.addCmdModifyBodyState(objID, data)
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
        ret = leoAPI.getAllObjectIDs()
        if not ret.ok:
            return RetVal(False, ret.data, None)
        else:
            return RetVal(True, None, ret.data)

    def _packSVData(self, SVs: dict):
        """
        Compile the data structure returned by ``get{All}BodyStates``.

        This is a convenience function to remove code duplication.

        The returned dictionary has the following form:

          {objID_1: {'frag': [FragState(), ...], 'sv': _RigidBodyState()},
           objID_2: {'frag': [FragState(), ...], 'sv': _RigidBodyState()},
           ...}

        :param dict SVs: SV dictionary. Each key is an object ID and the
            corresponding value a ``RigidBodyState`` instance.
        """
        # Convenience: extract all objIDs from ``SVs``.
        objIDs = list(SVs.keys())

        # Query the version values for all objects.
        docs = database.dbHandles['ObjInstances'].find(
            {'objID': {'$in': objIDs}},
            {'version': 1, 'objID': 1, 'fragState': 1})
        docs = list(docs)

        # Convert the list of [{objID1: foo}, {objID2: bar}, ...] into two
        # dictionaries like {objID1: foo, objID2: bar, ...}. This is purely for
        # readability and convenience a few lines below.
        version = {_['objID']: _['version'] for _ in docs}
        fragState = {_['objID']: _['fragState'].values() for _ in docs}

        # Wrap the fragment states into their dedicated tuple type.
        fragState = {k: [FragState(*_) for _ in v]
                     for (k, v) in fragState.items()}

        # Add SV and fragment data for all objects. If we the objects do not
        # exist then set the data to *None*.  During that proces also update
        # the 'version' (this flag indicates geometry changes to the
        # client).
        out = {}
        for objID in objIDs:
            if (SVs[objID] is None) or (objID not in fragState):
                out[objID] = None
                continue

            # Update the 'version' field to the latest value.
            out[objID] = {
                'frag': fragState[objID],
                'sv': SVs[objID]._replace(version=version[objID])
            }
        return RetVal(True, None, out)

    @typecheck
    def getBodyStates(self, objIDs: (list, tuple)):
        """
        Return the State Variables for all ``objIDs`` in a dictionary.

        The dictionary keys will be the elements of ``objIDs``, whereas the
        values are ``RigidBodyState`` instances, or *None* if the corresponding
        objID did not exist.

        :param list(int) objIDs: list of objects for which to return the SV.
        :return: see :ref:``_packSVData``.
        :rtype: dict
        """
        with util.Timeit('leoAPI.getSV') as timeit:
            # Get the State Variables.
            ret = leoAPI.getBodyStates(objIDs)
            if not ret.ok:
                return RetVal(False, 'One or more IDs do not exist', None)
        return self._packSVData(ret.data)

    @typecheck
    def getAllBodyStates(self, dummy=None):
        """
        Return all State Variables in a dictionary.

        The dictionary will have the objIDs and State Variables as keys and
        values, respectively.

        .. note::
           The ``dummy`` argument is a placeholder because the ``runCommand``
           function assumes that every method takes at least one argument.

        :return: see :ref:``_packSVData``.
        :rtype: dict
        """
        with util.Timeit('leoAPI.getSV') as timeit:
            # Get the State Variables.
            ret = leoAPI.getAllBodyStates()
            if not ret.ok:
                return ret
        return self._packSVData(ret.data)

    @typecheck
    def setFragmentStates(self, fragData: dict):
        """
        Update the fragments states (pos, vel, etc) of one or more objects.

        This method can update one- or more fragment states in one- or
        more objects simultaneously. The updates are specified with the
        following structure::

          fragData = {
            objID_1: [state_1, state_2, ...],
            objID_2: [state_3, state_4, ...]
          }

        where each ``state_k`` entry is a :ref:``util.FragState`` tuple. Those
        tuples contain the actual state information like scale, position, and
        orientation.

        This method will not touch any fragments that were not explicitly
        specified. This means that it is possible to update only a subset of
        the fragments for any given object.

        This method will update all existing objects and silently skip
        non-existing ones. However, the fragments for any particular object
        will either be updated all at once, or not at all. This means that if
        one or more fragment IDs are invalid then none of the fragments in the
        respective object will be updated, not even those with a valid ID.

        :param dict fragData: new fragment data for each object.
        :return: success.
        """
        # Convenience.
        update = database.dbHandles['ObjInstances'].update

        # Sanity checks.
        try:
            # All objIDs must be integers and all values must be dictionaries.
            for objID, fragStates in fragData.items():
                assert isinstance(objID, int)
                assert isinstance(fragStates, (list, tuple))

                # Each fragmentID must be a stringified integer, and all
                # fragment data must be a list with three entries.
                for fragState in fragStates:
                    assert isinstance(fragState, FragState)
                    assert isinstance(fragState.aid, str)

                    # Verify the content of the ``FragState`` data:
                    # scale (float), position (3-element vector), and
                    # orientation (4-element vector).
                    assert isinstance(fragState.scale, (int, float))
                    assert len(fragState.position) == 3
                    assert len(fragState.orientation) == 4
                    for _ in fragState.position:
                        assert isinstance(_, (int, float))
                    for _ in fragState.orientation:
                        assert isinstance(_, (int, float))
        except (TypeError, AssertionError):
            return RetVal(False, 'Invalid data format', None)

        # Update the fragments. Process one object at a time.
        ok = True
        for objID, frag in fragData.items():
            # Compile the mongo query to find the correct object and ensure
            # that every fragment indeed exists. The final query will have the
            # following structure:
            #   {'objID': 2,
            #    'fragState.1': {'$exists': 1},
            #    'fragState.2': {'$exists': 1},
            #    ...}
            frag_name = 'fragState.{}'
            query = {frag_name.format(_.aid): {'$exists': 1} for _ in frag}
            query['objID'] = objID

            # Overwrite the specified partIDs. This will produce a dictionary
            # like this:
            #   {'fragState.1': (FragState-tuple),
            #    'fragState.2': (FragState-tuple)}
            newvals = {frag_name.format(_.aid): _ for _ in frag}

            # Issue the update command to Mongo.
            ret = update(query, {'$set': newvals})

            # Exactly one document will have been updated if everything went
            # well. Note that we must check 'n' instead of 'nModified'. The
            # difference is that 'n' tells us how many documents Mongo has
            # touched whereas 'nModified' refers to the number of documents
            # that are now different data. This distinction is important if
            # the old- and new fragment values are identical, because then
            # 'n=1' whereas 'nModified=0'.
            if ret['n'] != 1:
                ok = False
                msg = 'Could not update the fragment states for objID <{}>'
                msg = msg.format(objID)
                self.logit.warning(msg)

        if ok:
            return RetVal(True, None, None)
        else:
            return RetVal(False, 'Could not update all fragments', None)

    @typecheck
    def addConstraints(self, constraints: (tuple, list)):
        """
        Return the number of ``constraints`` actually added to the simulation.

        See ``Igor.addConstraints`` for details.

        :param list constraints: list of constraints to add.
        :return: number of newly added constraints (see ``Igor.addConstraints``
                 for details).
        """
        return self.igor.addConstraints(constraints)

    @typecheck
    def getConstraints(self, bodyIDs: (set, tuple, list)):
        """
        Return all constraints that feature any of the bodies in ``bodyIDs``.

        :param list[int] bodyIDs: list of body IDs.
        :return: List of ``ConstraintMeta`` instances.
        """
        self.igor.updateLocalCache()
        return self.igor.getConstraints(bodyIDs)

    @typecheck
    def getAllConstraints(self):
        """
        Return all currently known constraints.

        :return: List of ``ConstraintMeta`` instances.
        """
        self.igor.updateLocalCache()
        return self.igor.getAllConstraints()

    @typecheck
    def deleteConstraints(self, constraints: (tuple, list)):
        """
        Return the number of ``constraints`` actually deleted.

        See ``Igor.deleteConstraints`` for details.

        :param list constraints: list of `ConstraintMeta` tuples.
        :return: number of deleted entries.
        """
        return self.igor.deleteConstraints(constraints)
