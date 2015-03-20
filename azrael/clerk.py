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
import subprocess
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

from azrael.util import Template, Fragment, RetVal
from azrael.util import FragState, FragDae, FragRaw, MetaFragment

# Convenience.
ipshell = IPython.embed


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
        frags = [MetaFragment('NoName', 'raw', FragRaw(vert=[], uv=[], rgb=[]))]
        t1 = Template('_templateNone', [0, 1, 1, 1], frags, [], [])
        t2 = Template('_templateSphere', [3, 1, 1, 1], frags, [], [])
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
                # command.
                enc, proc, dec = self.codec[cmd]

                # Run the Clerk function. The try/except is to intercept any
                # errors and prevent Clerk from dying.
                try:
                    self.runCommand(enc, proc, dec)
                except Exception as err:
                    msg = 'Client data raised error in Clerk'
                    self.logit.error(msg)
                    self.returnErr(self.last_addr, {}, msg)
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
        # fixme: is this try/except still necessary?
        try:
            # Convert the message to a byte string (if it is not already).
            ret = json.dumps({'ok': False, 'payload': {}, 'msg': msg})
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
    def _isGeometrySane(self, frag: FragRaw):
        """
        Return *True* if the geometry is consistent.

        :param Fragment frag: a geometry Fragment
        :return: Sucess
        :rtype: bool
        """
        # The number of vertices must be an integer multiple of 9 to
        # constitute a valid triangle mesh (every triangle has three
        # edges and every edge requires an (x, y, z) triplet to
        # describe its position).
        try:
            assert len(frag.vert) % 9 == 0
            assert len(frag.uv) % 2 == 0
            assert len(frag.rgb) % 3 == 0
        except AssertionError:
            return False
        return True

    def _saveDaeFragment(self, frag_dir, frag):
        """
        fixme: docu
        fixme: rename to _saveModelDae
        """
        # Sanity checks.
        try:
            assert isinstance(frag.data, FragDae)
            assert isinstance(frag.data.dae, bytes)
            for v in frag.data.rgb.values():
                assert isinstance(v, bytes)
        except AssertionError as err:
            msg = 'Invalid fragment data types'
            return RetVal(False, msg, None)

        # Save the dae file to "templates/mymodel/name.dae".
        open(os.path.join(frag_dir, frag.name), 'wb').write(frag.data.dae)

        # Save the textures. These are stored as dictionaries with the texture
        # file name as key and the data as a binary stream, eg,
        # {'house.jpg': b';lj;lkj', 'tree.png': b'fdfu', ...}
        for name, rgb in frag.data.rgb.items():
            open(os.path.join(frag_dir, name), 'wb').write(rgb)

        return RetVal(True, None, 1.0)

    def _saveRawFragment(self, frag_dir, frag):
        """
        fixme: docu
        fixme: rename to _saveModelRaw
        """
        # Sanity checks.
        try:
            data = FragRaw(*frag.data)
            assert isinstance(data.vert, list)
            assert isinstance(data.uv, list)
            assert isinstance(data.rgb, list)
        except (AssertionError, TypeError):
            msg = 'Invalid fragment data types'
            return RetVal(False, msg, None)

        if not self._isGeometrySane(data):
            msg = 'Invalid geometry for template <{}>'
            return RetVal(False, msg.format(frag.name), None)

        # Write the fragment data as a JSON to eg "templates/mymodel/model".
        file_data = dict(zip(data._fields, data))
        file_data = json.dumps(file_data)
        open(os.path.join(frag_dir, 'model.json'), 'w').write(file_data)
        del file_data

        # Determine the largest possible side length of the
        # AABB. To find it, just determine the largest spatial
        # extent in any axis direction. That is the side length of
        # the AABB cube. Then multiply it with sqrt(3) to ensure
        # that any rotation angle of the object is covered. The
        # slightly larger value of sqrt(3.1) adds some slack.
        aabb = 0
        if len(data.vert) > 0:
            len_x = max(data.vert[0::3]) - min(data.vert[0::3])
            len_y = max(data.vert[1::3]) - min(data.vert[1::3])
            len_z = max(data.vert[2::3]) - min(data.vert[2::3])
            tmp = np.sqrt(3.1) * max(len_x, len_y, len_z)
            aabb = np.amax((aabb, tmp))

        return RetVal(True, None, aabb)

    @typecheck
    def addTemplates(self, templates: list):
        """
        Add all ``templates`` to the system so that they can be spawned.

        Return an error if one or more templates with the same name
        exists. However, all new and unique templates will be added
        regardless, whereas those with a name clash will be ignored.

        ``templates`` is a list of :ref:``azrael.util.Template`` instances.

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

            # The templates will be inserted in bulk for efficiency reasons.
            db = database.dbHandles['Templates']
            bulk = db.initialize_unordered_bulk_op()

            # Add each template to the bulk operation.
            aabb = 0
            for tt in templates:
                # Initial AABB size. We will expand it when we parse the
                # geometries to fit the largest one.
                assert isinstance(tt.name, str)
                assert isinstance(tt.fragments, list)

                # fixme: ensure tt.name is sane
                # fixme: double check the directory does not yet exist.
                # Build directory name for this template.
                model_dir = os.path.join(config.dir_template, tt.name)

                geo = {}
                aabb = 0

                # Store all fragment models for this template.
                for frag in tt.fragments:
                    # Ensure 'frag' is a MetaFragment instance.
                    # fixme: proper error handling.
                    assert isinstance(frag, MetaFragment)

                    frag_dir = os.path.join(model_dir, frag.name)

                    # Create the directory for this fragment:
                    # eg. "templates/mymodel/"
                    try:
                        os.makedirs(frag_dir, exist_ok=False)
                    except:
                        # fixme: This error should only be possible if two or
                        # more fragment have the same name. add a sanity check
                        # for this somewhere.
                        msg = 'Frag dir <{}> already exists'.format(frag_dir)
                        return RetVal(False, msg, None)

                    # fixme: remove aabb
                    # Save the Fragment in model_dir + tt.name
                    if frag.type == 'raw':
                        ret = self._saveRawFragment(frag_dir, frag)
                    elif frag.type == 'dae':
                        ret = self._saveDaeFragment(frag_dir, frag)
                    else:
                        # fixme: return a proper error
                        print('Unknown type <{}>'.format(frag.type))
                        assert False

                    if not ret.ok:
                        return ret

                    aabb = np.amax((ret.data, aabb))

                # Compile the Mongo document for the new template.
                data = {
                    'url': config.url_template + '/' + tt.name,
                    'name': tt.name,
                    'cshape': tt.cs,
                    'aabb': float(aabb),
                    'boosters': tt.boosters,
                    'factories': tt.factories,
                    'fragments': [MetaFragment(_.name, _.type, None)
                                  for _ in tt.fragments]}

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

        # Convenience: convert the list of tuples into to plain list, ie
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

                doc = dict(templates[name])
                doc['objID'] = objID
                doc['lastChanged'] = 0
                doc['templateID'] = name

                # Copy the model from the template- to the instance directory.
                src = os.path.join(config.dir_template, doc['name'], '*')
                dst = os.path.join(config.dir_instance, str(objID)) + '/'
                os.makedirs(dst)
                cmd = 'cp -r {} {}'.format(src, dst)
                subprocess.call(cmd, shell=True)
                doc['url'] = config.url_instance + '/{}/'.format(objID)

                # Parse the geometry data to determine all fragment names.
                # Then compile a neutral initial state for each.
                doc['fragState'] = {}
                for f in doc['fragments']:
                    f = MetaFragment(*f)
                    doc['fragState'][f.name] = FragState(
                        name=f.name,
                        scale=1,
                        position=[0, 0, 0],
                        orientation=[0, 0, 0, 1])

                # Add the new template document.
                dbDocs.append(doc)
                del idx, name, objID, doc

            # Insert all objects into the State Variable DB. Note: this does
            # not make Leonard aware of their existence (see next step).
            database.dbHandles['ObjInstances'].insert(dbDocs)

        with util.Timeit('spawn:3 addCmds') as timeit:
            # Compile the list of spawn commands that will be sent to Leonard.
            objs = []
            for objID, name, sv in zip(objIDs, t_names, SVs):
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
    def getGeometry(self, objIDs: list):
        """
        fixme: docu update; args; return type
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
        # Retrieve the geometry. Return an error if the ID does not exist.
        # Note: an empty geometry field is valid because Azrael supports dummy
        # objects without geometries.
        db = database.dbHandles['ObjInstances']
        docs = list(db.find({'objID': {'$in': objIDs}}))

        out = {_: None for _ in objIDs}
        for doc in docs:
            objID = doc['objID']
            assert objID in out

            obj = {}
            for f in doc['fragments']:
                f = MetaFragment(*f)
                obj[f.name] = {'type': f.type,
                               'url': os.path.join(doc['url'], f.name)}
            out[objID] = obj
        return RetVal(True, None, out)

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

        for frag in fragments:
            # fixme: code duplication with spawn
            frag_dir = os.path.join(config.dir_instance, str(objID)) + '/'
            frag_dir = os.path.join(frag_dir, frag.name)

            # Save the Fragment in model_dir + tt.name
            if frag.type == 'raw':
                ret = self._saveRawFragment(frag_dir, frag)
            elif frag.type == 'dae':
                ret = self._saveDaeFragment(frag_dir, frag)
            else:
                # fixme: return a proper error
                print('Unknown type <{}>'.format(frag.type))
                assert False

            if not ret.ok:
                return ret

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

    def _packSVData(self, SVs: dict):
        """
        Compile the data structure returned by ``get{All}StateVariables``.

        This is a convenience function to remove code duplication.

        The returned dictionary has the following form:

          {objID_1: {'frag': [FragState(), ...], 'sv': _BulletData()},
           objID_2: {'frag': [FragState(), ...], 'sv': _BulletData()},
           ...}

        :param dict SVs: SV dictionary. Each key is an object ID and the
            corresponding value a ``BulletData`` instance.
        """
        # Convenience: extract all objIDs from ``SVs``.
        objIDs = list(SVs.keys())

        # Query the lastChanged values for all objects.
        docs = database.dbHandles['ObjInstances'].find(
            {'objID': {'$in': objIDs}},
            {'lastChanged': 1, 'objID': 1, 'fragState': 1})
        docs = list(docs)

        # Convert the list of [{objID1: foo}, {objID2: bar}, ...] into two
        # dictionaries like {objID1: foo, objID2: bar, ...}. This is purely for
        # readability and convenience a few lines below.
        lastChanged = {_['objID']: _['lastChanged'] for _ in docs}
        fragState = {_['objID']: _['fragState'].values() for _ in docs}

        # Wrap the fragment states into their dedicated tuple type.
        fragState = {k: [FragState(*_) for _ in v]
                     for (k, v) in fragState.items()}

        # Add SV and fragment data for all objects. If we the objects do not
        # exist then set the data to *None*.  During that proces also update
        # the 'lastChanged' (this flag indicates geometry changes to the
        # client).
        out = {}
        for objID in objIDs:
            if (SVs[objID] is None) or (objID not in fragState):
                out[objID] = None
                continue

            # Update the 'lastChanged' field to the latest value.
            out[objID] = {
                'frag': fragState[objID],
                'sv': SVs[objID]._replace(lastChanged=lastChanged[objID])
            }
        return RetVal(True, None, out)

    @typecheck
    def getStateVariables(self, objIDs: (list, tuple)):
        """
        Return the State Variables for all ``objIDs`` in a dictionary.

        The dictionary keys will be the elements of ``objIDs``, whereas the
        values are ``BulletData`` instances, or *None* if the corresponding
        objID did not exist.

        :param list(int) objIDs: list of objects for which to return the SV.
        :return: see :ref:``_packSVData``.
        :rtype: dict
        """
        with util.Timeit('physAPI.getSV') as timeit:
            # Get the State Variables.
            ret = physAPI.getStateVariables(objIDs)
            if not ret.ok:
                return RetVal(False, 'One or more IDs do not exist', None)
        return self._packSVData(ret.data)

    @typecheck
    def getAllStateVariables(self, dummy=None):
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
        with util.Timeit('physAPI.getSV') as timeit:
            # Get the State Variables.
            ret = physAPI.getAllStateVariables()
            if not ret.ok:
                return ret
        return self._packSVData(ret.data)

    @typecheck
    def updateFragmentStates(self, fragData: dict):
        """
        Update one or more fragments in one or more objects.

        The ``fragData`` dictionary has the following structure::

          fragData = {
            objID_1: [state_1, state_2, ...],
            objID_2: [state_3, state_4, ...]
          }

        where each ``state_k`` entry is a :ref:``util.FragState`` tuple. Those
        tuplse contain the actual state information like scale, position, and
        orientation.

        This methos will updat all existing objects and silently skip
        non-existing ones. However, the fragments for any particular object
        will be updated all at once, or not at all. This means that if one or
        more fragment IDs are invalid then none of the fragments in that object
        will be updated, not even those with a valid ID.

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
                    assert isinstance(fragState.name, str)

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
            query = {frag_name.format(_.name): {'$exists': 1} for _ in frag}
            query['objID'] = objID

            # Overwrite the specified partIDs. This will produce a dictionary
            # like this:
            #   {'fragState.1': (FragState-tuple),
            #    'fragState.2': (FragState-tuple)}
            newvals = {frag_name.format(_.name): _ for _ in frag}

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

        if ok:
            return RetVal(True, None, None)
        else:
            return RetVal(False, 'Could not udpate all fragments', None)
