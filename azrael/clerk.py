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
Primary gateway into Azrael.

``Clerk`` is a stateless class that arbitrates between clients on the network
and the various Azrael services. It also acts as a prudent sanity checker that
will verify all incoming data. In turn, the other Azrael services mostly forgoe
sanity checks for performance reasons.

``Clerk`` is meant to run as an independent process. Its stateless design
implies that there can be many ``Clerk`` processes (eg behind an NginX
server) running simultaneously. Furthermore, not all ``Clerk`` processes need
to run on the same machine since Azrael's collective memory is contained
entirely within a database -- ``Clerk`` has no state.

``Clerk`` uses ZeroMQ sockets for the communication with clients. ZeroMQ has
bindings for virtually every language except JavaScript, which is why
``Clacks`` implements a web server bridge. In both cases the data exchange is
plain JSON; no Python specific data types are used to keep the interface
language agnostic.

"""
import io
import os
import sys
import zmq
import json
import logging
import traceback
import subprocess

import numpy as np

import azrael.igor
import azrael.database
import azrael.util as util
import azrael.types as types
import azrael.config as config
import azrael.leo_api as leoAPI
import azrael.dibbler as dibbler
import azrael.database as database
import azrael.protocol as protocol

from IPython import embed as ipshell
from azrael.types import typecheck, RetVal, Template, CollShapeMeta, CollShapeEmpty
from azrael.types import FragState, FragMeta, _FragMeta


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

        # Dibbler is the interface to the geometry database.
        self.dibbler = dibbler.Dibbler()

        # Dibbler is the interface to the constraints database.
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

        # Digest loop.
        while True:
            # Wait for socket activity.
            sock = dict(poller.poll())
            if self.sock_cmd not in sock:
                continue

            # Read from ROUTER socket and perform sanity checks.
            data = self.sock_cmd.recv_multipart()
            assert len(data) == 3
            self.last_addr, empty, msg = data[0], data[1], data[2]
            if empty != b'':
                self.logit.error('Expected empty frame')
                continue
            del data, empty

            # The payload must be a valid JSON string.
            try:
                msg = json.loads(msg.decode('utf8'))
            except (ValueError, TypeError) as err:
                self.returnErr(self.last_addr, 'JSON decoding error in Clerk')
                continue

            # Sanity check: every message must contain at least a command word.
            if not (('cmd' in msg) and ('payload' in msg)):
                self.returnErr(self.last_addr, 'Invalid command format')
                continue

            # Extract the command word and payload.
            cmd, self.payload = msg['cmd'], msg['payload']

            # The command word determines the action...
            if cmd in self.codec:
                # Look up the decode-process-encode functions for the current
                # command word. The 'decode' part will interpret the JSON
                # string we just received, the 'process' part is a handle to a
                # method in this very Clerk instance, and 'encode' will convert
                # the values to a valid JSON string that will be returned to
                # the Client.
                dec, proc, enc = self.codec[cmd]

                # Run the Clerk function. The try/except is to intercept any
                # errors and prevent Clerk from dying.
                try:
                    self.runCommand(dec, proc, enc)
                except Exception:
                    # Basic error message.
                    msg = 'Client data for <{}> raised an error in Clerk'
                    msg = msg.format(cmd)

                    # Get the Python stack trace as string (this will be added
                    # to the log for reference).
                    buf = io.StringIO()
                    traceback.print_exc(file=buf)
                    buf.seek(0)
                    msg_st = [' -> ' + _ for _ in buf.readlines()]
                    msg_st = msg + '\n' + ''.join(msg_st)

                    # Log the error message with stack trace. However, only
                    # the basic error message to the client.
                    self.logit.error(msg_st)
                    self.returnErr(self.last_addr, msg, addToLog=False)
                    del msg, buf, msg_st
            else:
                # Unknown command word.
                self.returnErr(
                    self.last_addr, 'Invalid command <{}>'.format(cmd))

    @typecheck
    def returnOk(self, addr, data: dict, msg: str=''):
        """
        Send affirmative reply.

        This is a convenience method to enhance readability.

        :param addr: ZeroMQ address as returned by the ROUTER socket.
        :param dict data: the payload to send back to the client.
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

        :param addr: ZeroMQ address as returned by the ROUTER socket.
        :param bool addToLog: logs a 'Warning' with ``msg`` if *True*
        :param str msg: the error message to send back.
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

        :return: the string 'pong' to acknowledge the ping.
        :rtype: str
        :raises: None
        """
        return RetVal(True, None, 'pong clerk')

    # ----------------------------------------------------------------------
    # These methods service Client requests.
    # ----------------------------------------------------------------------
    @typecheck
    def addTemplates(self, templates: list):
        """
        Add all ``templates`` to Azrael so that they can be spawned.

        The elements in ``templates`` must be ``Template`` instances.

        This method will abort immediately when it encounters an invalid
        Template. If that happens then no templates will be added at all.

        It will also return with an error if a template with the same  name
        already exists. However, it will still add all the other templates that
        have unique names.

        :param list[Template]: the templates to add.
        :return: success
        :raises: None
        """
        # Return immediately if ``templates`` is empty.
        if len(templates) == 0:
            return RetVal(True, None, None)

        with util.Timeit('clerk.addTemplates') as timeit:
            # Verify that all templates contain valid data.
            try:
                templates = [Template(*_) for _ in templates]
            except TypeError:
                return RetVal(False, 'Invalid template data', None)

            # The templates will be inserted with a single bulk operation.
            db = database.dbHandles['Templates']
            bulk = db.initialize_unordered_bulk_op()

            # Add each template to the bulk. Dibbler handles the (possibly
            # large) geometry data, whereas the template database itself
            # contains only meta information (eg the type of geometry, but not
            # geometry itself).
            for template in templates:
                # Convenience.
                frags = template.fragments

                # Ensure the AIDs of all fragments are unique.
                if len(set([_.aid for _ in frags])) < len(frags):
                    msg = 'Not all fragment IDs in template <{}> are unique'
                    msg = msg.format(template.aid)
                    return RetVal(False, msg, None)

                # Dibbler administrates the geometry data. Abort immediately if
                # it returns an error (should be impossible, but just to be
                # sure).
                ret = self.dibbler.addTemplate(template)
                if not ret.ok:
                    return ret

                # Dibbler must have returned the URL where the fragments are
                # available.
                url_frag = ret.data['url_frag']

                # Only retain the meta data for the geometries to save space
                # and avoid data duplication (Dibbler handles the actual
                # geometry data).
                frags = [_._replace(fragdata=None) for _ in frags]
                template = template._replace(fragments=frags)

                # Compile the template data that will go into the database. The
                # template will be stored as an explicit dictionary.
                data = {'url_frag': url_frag,
                        'template': template._asdict(),
                        'templateID': template.aid}
                del frags

                # Add the template to the database.
                query = {'templateID': template.aid}
                bulk.find(query).upsert().update({'$setOnInsert': data})

        with util.Timeit('clerk.addTemplates_db') as timeit:
            # Run the database query.
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

        This method will either return all the templates specified in
        `templateIDs` or none.

        Each template will only be returned once, no matter how many times it
        was specified in `templateIDs`. For instance, these two calls will both
        return the same two templates::
            getTemplates([name_1, name_2, name_1])
            getTemplates([name_1, name_2])

        This method returns a dictionary with the `templateIDs` as keys::

          ret = {templateIDs[0]: {'template': Template(),
                                  'url_frag': URL for geometries},
                 templateIDs[1]: {...}, }.

        ..note:: The template data only contains meta information about the
            geometry. The geometry itself is available at the URL specified in
            the return value.

        :param list[str] templateIDs: template IDs
        :return dict: raw template data (the templateID is the key).
        """
        # Sanity check: all template IDs must be strings.
        try:
            for tid in templateIDs:
                assert isinstance(tid, str)
        except AssertionError:
            return RetVal(False, 'All template IDs must be strings', None)

        # Remove all duplicates from the list of templateIDs.
        templateIDs = tuple(set(templateIDs))

        # Fetch all requested templates and place them into a dictonary where
        # the template ID is the key. Use a projection operator to suppress
        # Mongo's "_id" field.
        db = database.dbHandles['Templates']
        cursor = db.find({'templateID': {'$in': templateIDs}}, {'_id': False})

        # Compile the output dictionary and compile the `Template` instances.
        out = {}
        try:
            for doc in cursor:
                out[doc['templateID']] = {
                    'url_frag': doc['url_frag'],
                    'template': Template(**doc['template']),
                }
        except TypeError:
            msg = 'Inconsistent Template data'
            self.logit.error(msg)
            return RetVal(False, msg, None)

        # Return immediately if we received fewer templates than requested
        # (simply means that not all requested template names were valid).
        if len(out) < len(templateIDs):
            msg = 'Could not find all templates'
            self.logit.info(msg)
            return RetVal(False, msg, None)

        # Return the templates.
        return RetVal(True, None, out)

    @typecheck
    def spawn(self, newObjects: (tuple, list)):
        """
        Spawn all ``newObjects`` and return their IDs in a tuple.

        The ``newObjects`` variable mut be a list of dictionaries. Each
        dictionary *must* contain an 'templateID' and *may* contain an 'rbs'
        key. The 'templateID' specify which template should be used for the new
        object, and the 'rbs' value, which is a dictionary itself, specifies
        the values to override in the rigid body structure. For instance, a
        valid `newObjects` argument would be::

        newObjects = [
            {'templateID': 'foo'},
            {'templateID': 'foo', 'rbs': {'imass': 5}},
            {'templateID': 'bar', 'rbs': {'position': (1, 2, 3)},
        ]
        
        This will spawn three objects. The first one is a verbatim copy of
        `foo`, the second will also be an instance of `foo` but with an `imass`
        of 5, whereas the third object is an instance of `bar` that is spawned
        at position (1, 2, 3).

        This method will either spawn all objects, or return with an error
        without spawning a single one.

        ..note:: Note to myself: ``newObjects`` cannot be a dictionary because
            the client may want to spawn the same template ID (which would be
            the keys) several times with different initial states, for instance
            to create a chain of spheres. It is possible to store the initial
            states in a list but then there is still the problem for the client
            to uniquely map every templateID and initials state to a particular
            object ID.

        :param list[dict] newObjects: template IDs (key) and body parameters to
            override (value).
        :return: IDs of spawned objects
        :rtype: tuple of int
        """
        # Sanity checks.
        try:
            assert len(newObjects) > 0
            for tmp in newObjects:
                assert isinstance(tmp, dict)
                assert 'templateID' in tmp
        except AssertionError:
            return RetVal(False, '<spawn> received invalid arguments', None)

        # Convenience: convert the list of tuples into a plain list, ie
        # [(t1, s1), (t2, s2), ...]  -->  [t1, t2, ...] and [s1, s2, ...].
        t_names = [_['templateID'] for _ in newObjects]
#        initStates = [_[1] for _ in newObjects]

        with util.Timeit('spawn:1 getTemplates') as timeit:
            # Fetch the raw templates for all ``t_names``.
            ret = self.getTemplates(t_names)
            if not ret.ok:
                self.logit.info(ret.msg)
                return ret
            templates = ret.data

        # Request unique IDs for the objects to spawn.
        ret = azrael.database.getUniqueObjectIDs(len(newObjects))
        if not ret.ok:
            self.logit.error(ret.msg)
            return ret
        objIDs = ret.data

        with util.Timeit('spawn:2 createStates') as timeit:
            # Make a copy of every template and endow it with the meta
            # information for an instantiated object. Then add it to the list
            # of objects to spawn.
            dbDocs = []
            bodyStates = {}
            for newObj, objID in zip(newObjects, objIDs):
                # Convenience.
                # fixme: explain that 'templates' is a dictionary with keys
                # like 'template' and 'templateID' (anything else), and that
                # the entries under 'template' are Template instances?
                templateID = newObj['templateID']
                template = templates[templateID]['template']
                frags = template.fragments

                # fixme: explain, protect with try/except or sanity check
                # earlier on (probably a better idea).
                body = template.rbs
                if 'rbs' in newObj:
                    body = body._replace(**newObj['rbs'])
                template = template._replace(rbs=body)

                # Tell Dibbler to duplicate the template data into the instance
                # location.
                ret = self.dibbler.spawnTemplate(templateID, objID)
                if not ret.ok:
                    # Dibbler and Clerk are out of sync because Clerk found
                    # a template that Dibbler does not know about. This really
                    # should not happen, so skip this object and do not spawn
                    # it.
                    msg = 'Dibbler and Clerk are out of sync for template {}.'
                    msg = msg.format(templateID)
                    msg += ' Dibbler returned this error: <{}>'
                    msg = msg.format(ret.msg)
                    self.logit.error(msg)
                    continue
                else:
                    # URL where the instance geometry is available.
                    geo_url = ret.data['url_frag']

                # Give all geometries a neutral initial state in terms of
                # scale, position, and orientation.
                fs = FragState(aid='',
                               scale=1,
                               position=(0, 0, 0),
                               orientation=(0, 0, 0, 1))
                fragStates = {_.aid: fs._replace(aid=_.aid) for _ in frags}

                # Serialise the template and add additional meta information
                # that is specific to this instance, for instance the 'objID'
                # and 'version'.
                doc = {
                    'objID': objID,
                    'url_frag': geo_url,
                    'version': 0,
                    'templateID': templateID,
                    'template': template._asdict(),
                    'fragState': {k: v._asdict() for (k, v) in fragStates.items()},
                }

                # Overwrite the user supplied collision shape with the one
                # specified in the template. This is to enforce geometric
                # consistency with the template data as otherwise strange
                # things may happen (eg a space-ship collision shape in the
                # template database with a simple sphere collision shape when
                # it is spawned).
#                state.cshapes[:] = template.cshapes
                bodyStates[objID] = template.rbs

                # Add the new template document.
                dbDocs.append(doc)
                del templateID, objID, doc, fs

            # Return immediately if there are no objects to spaw.
            if len(dbDocs) == 0:
                return RetVal(True, None, tuple())

            # Insert all objects into the State Variable DB. Note: this does
            # not make Leonard aware of their existence (see next step).
            database.dbHandles['ObjInstances'].insert(dbDocs)

        with util.Timeit('spawn:3 addCmds') as timeit:
            # Compile the list of spawn commands that will be sent to Leonard.
            objs = tuple(bodyStates.items())

            # Queue the spawn commands. Leonard will fetch them at its leisure.
            ret = leoAPI.addCmdSpawn(objs)
            if not ret.ok:
                return ret
            self.logit.debug('Spawned {} new objects'.format(len(objs)))

        return RetVal(True, None, objIDs)

    @typecheck
    def controlParts(self, objID: int, cmd_boosters: (tuple, list),
                     cmd_factories: (tuple, list)):
        """
        Issue commands to individual parts of the ``objID``.

        Boosters can be activated with a scalar force. The force automatically
        applies in the direction of the booster (taking the orientation of the
        parent into account).

        The commands for Boosters and Factories must be instances of
        ``CmdBooster`` or ``CmdFactory``, respectively.

        :param int objID: object ID.
        :param list cmd_booster: booster commands.
        :param list cmd_factory: factory commands.
        :return: **True** if no error occurred.
        :rtype: bool
        :raises: None
        """
        # Fetch the instance data and return immediately if it does not exist.
        db = database.dbHandles['ObjInstances']
        doc = db.find_one({'objID': objID}, {'template': True, '_id': False})
        if doc is None:
            msg = 'Could not find instance data for objID <{}>'.format(objID)
            self.logit.info(msg)
            return RetVal(False, msg, None)

        # Compile the instance information (it is a `Template` data structure).
        try:
            instance = Template(**doc['template'])
        except TypeError:
            msg = 'Inconsistent Template data'
            self.logit.error(msg)
            return RetVal(False, msg, None)

        # Compile a list of all Boosters and Factories defined for the object.
        boosters = {_.partID: _ for _ in instance.boosters}
        factories = {_.partID: _ for _ in instance.factories}
        del instance

        # Fetch the SV for objID (we need this to determine the orientation of
        # the base object to which the parts are attached).
        sv_parent = self.getBodyStates([objID])
        if not sv_parent.ok:
            msg = 'Could not retrieve body state for objID={}'.format(objID)
            self.logit.warning(msg)
            return RetVal(False, msg, None)

        # Return with an error if the requested objID does not exist.
        if sv_parent.data[objID] is None:
            msg = 'objID={} does not exits'.format(objID)
            self.logit.warning(msg)
            return RetVal(False, msg, None)

        # Extract the parent's orientation from its rigid body state.
        sv_parent = sv_parent.data[objID]['rbs']
        parent_orient = sv_parent.orientation
        quat = util.Quaternion(parent_orient[3], parent_orient[:3])

        # Sanity check the Booster- and Factory commands.
        try:
            cmd_boosters = [types.CmdBooster(*_) for _ in cmd_boosters]
            cmd_factories = [types.CmdFactory(*_) for _ in cmd_factories]
        except TypeError:
            msg = 'Invalid booster- or factory command'
            self.logit.warning(msg)
            return RetVal(False, msg, None)

        # Verify that the Booster commands reference existing Boosters.
        for cmd in cmd_boosters:
            # Verify the referenced booster exists.
            if cmd.partID not in boosters:
                msg = 'Object <{}> has no Booster with AID <{}>'
                msg = msg.format(objID, cmd.partID)
                self.logit.warning(msg)
                return RetVal(False, msg, None)
        del boosters

        # Verify that the Factory commands reference existing Factories.
        for cmd in cmd_factories:
            # Verify the referenced factory exists.
            if cmd.partID not in factories:
                msg = 'Object <{}> has no Factory with AID <{}>'
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

        # Update the booster forces in the database. This will only update the
        # values for record keeping, but Leonard will never look at them (it
        # does not even know that data exists). Instead, we need to queue a
        # command with Leonard and tell it to apply the correct force and
        # torque that those booster generate.
        ret = self.updateBoosterForces(objID, cmd_boosters)
        if not ret.ok:
            return ret
        force, torque = ret.data
        leoAPI.addCmdBoosterForce(objID, force, torque)
        del ret, force, torque

        # Factories will spawn their objects.
        objIDs = []
        for cmd in cmd_factories:
            # Template for this very factory.
            this = factories[cmd.partID]

            # Position (in world coordinates) where the new object will be
            # spawned.
            pos = quat * this.pos + sv_parent.position

            # Align the exit velocity vector with the parent's orientation.
            velocityLin = cmd.exit_speed * (quat * this.direction)

            # Add the parent's velocity to the exit velocity.
            velocityLin += sv_parent.velocityLin

            # fixme: docu
            init = {
                'templateID': this.templateID,
                'rbs': {
                    'position': tuple(pos),
                    'velocityLin': tuple(velocityLin),
                    'orientation': tuple(sv_parent.orientation),
                }
            }

            # Spawn the actual object that this factory can create. Retain
            # the objID as it will be returned to the caller.
            ret = self.spawn([init])
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

        This method returns the torque and linear force that each booster would
        apply at object's center. A typical return value for boosters with IDs
        'for' and 'bar' would like this::

            {'foo': ([1, 0, 0], [0, 2, 0]),
             'bar': ([1, 2, 3], [4, 5, 6]),
             ...}

        :param int objID: object ID
        :param list cmds: list of Booster commands.
        :return: (linear force, torque) that the Booster apply to the object.
        :rtype: tuple
        """
        # Convenience.
        db = database.dbHandles['ObjInstances']

        # Put the new force values into a dictionary for convenience later on.
        cmds = {_.partID: _.force_mag for _ in cmds}

        # Query the object's booster information.
        query = {'objID': objID}
        doc = db.find_one(query, {'template.boosters': 1})
        if doc is None:
            msg = 'Object <{}> does not exist'.format(objID)
            return RetVal(False, msg, None)
        instance = doc['template']
        del doc

        # Put the Booster entries from the database into Booster tuples.
        try:
            boosters = [types.Booster(**_) for _ in instance['boosters']]
            boosters = {_.partID: _ for _ in boosters}
        except TypeError:
            msg = 'Inconsistent Template data'
            self.logit.error(msg)
            return RetVal(False, msg, None)

        # Tally up the forces exerted by all Boosters on the object.
        force, torque = np.zeros(3), np.zeros(3)
        for partID, booster in boosters.items():
            # Update the Booster value if the user specified a new one. Then
            # remove the command (irrelevant for this loop but necessary for
            # the sanity check that follows after the loop).
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

        # Update the new Booster values (and only the Booster values) in the
        # instance database. To this end convert them back to dictionaries and
        # issue the update.
        boosters = [_._asdict() for _ in boosters.values()]
        db.update(query, {'$set': {'template.boosters': boosters}})

        # Return the final force- and torque as a tuple of 2-tuples.
        out = (force.tolist(), torque.tolist())
        return RetVal(True, None, out)

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
            self.dibbler.deleteInstance(objID)
            return RetVal(True, None, None)
        else:
            return RetVal(False, ret.msg, None)

    @typecheck
    def getFragmentGeometries(self, objIDs: list):
        """
        Return information about the fragments of each object in ``objIDs``.

        This method returns a dictionary of the form::

            {objID_1: {'fragtype': 'raw', 'url_frag': 'http:...'},
             objID_2: {'fragtype': 'dae', 'url_frag': 'http:...'},
             objID_3: None,
             ...
            }

        Every element in ``objIDs`` will be a key in the returned dictionary.
        However, the corresponding value will be *None* if the object does not
        exist in Azrael.

        ..note:: This method does not actually return any geometries, only URLs
            from where they can be downloaded.

        :param list objIDs: return geometry information for all of them.
        :return: meta information about all fragment for each object.
        :rtype: dict
        """
        # Retrieve the geometry. Return an error if the ID does not exist.
        # Note: an empty geometry field is still valid object.
        db = database.dbHandles['ObjInstances']
        docs = list(db.find({'objID': {'$in': objIDs}}))

        # Initialise the output dictionary with a None value for every
        # requested object. The loop below will overwrite these values for the
        # objects we actually found in the database.
        out = {_: None for _ in objIDs}

        # Determine the fragment- type (eg. 'raw' or 'dae') and URL and put it
        # into the output dictionary.
        pjoin = os.path.join
        try:
            # Create a dedicated dictionary for each object.
            for doc in docs:
                # Unpack and compile geometry data for the current object.
                frags = doc['template']['fragments']
                frags = [FragMeta(**_) for _ in frags]

                # Compile the dictionary with all the geometries that comprise
                # the current object, including where to download the geometry
                # data itself (we only provide the meta information).
                out[doc['objID']] = {
                    _.aid: {
                        'fragtype': _.fragtype,
                        'url_frag': pjoin(doc['url_frag'], _.aid)
                    } for _ in frags}
        except TypeError:
            msg = 'Inconsistent Fragment data'
            self.logit.error(msg)
            return RetVal(False, msg, None)
        return RetVal(True, None, out)

    @typecheck
    def setFragmentGeometries(self, objID: int, fragments: list):
        """
        Update the geometries of ``objID``.

        Return with an error if ``objID`` does not exist.

        :param int objID: the object for which to update the geometry.
        :param list fragments: the new fragments for ``objID``.
        :return: Success
        """
        # Compile- and sanity check the fragments.
        try:
            fragments = [FragMeta(*_) for _ in fragments]
        except TypeError:
            return RetVal(False, 'Received invalid fragment data', None)

        # Convenience.
        db = database.dbHandles['ObjInstances']

        # Update the fragment geometry in Dibbler.
        for frag in fragments:
            ret = self.dibbler.updateFragments(objID, fragments)
            if not ret.ok:
                return ret

            # If the fragment type is '_NONE_' then remove it altogether.
            if frag.fragtype.upper() == '_NONE_':
                db.update({'objID': objID},
                          {'$unset': {'fragState.{}'.format(frag.aid): True}})

        # To update the fragment's meta data in the DB we first need to remove
        # the actual geometry data from the fragments because the instance DB
        # only stores meta information (Dibbler contains the actual
        # geometries).
        new_frags = [frag._replace(fragdata=None) for frag in fragments]

        # ------------------------------------------------------------------
        # Here we update/remove the specified fragments. This would be a
        # simple (atomic) MongoDB update if the object Template would store
        # its fragments in a dictionary. Alas, it stores it in a list. We
        # therefore need to fetch the entire template, parse its fragment
        # list to remove/update them as specified, and then write them back.
        # This is a design error and must be rectified. ie. Template must
        # store its fragments (and CShapes, for that matter) in
        # dictionaries.
        # ------------------------------------------------------------------

        # Compile the set of all fragments AIDs that should be either removed
        # or modified.
        aid_del = [_.aid for _ in new_frags if _.fragtype.upper() == '_NONE_']
        aid_mod = [_.aid for _ in new_frags if _.fragtype.upper() != '_NONE_']
        aid_del = set(aid_del)
        aid_mod = set(aid_mod)

        # Compile a list of fragments that should be modified but not removed.
        frag_mod = [_ for _ in new_frags if _.aid in aid_mod]

        # Retrieve the original template for the current objID.
        old_template = db.find_one({'objID': objID})
        if old_template is None:
            return RetVal(False, 'ID <{}> does not exist'.format(objID), None)

        # Compile its list of fragments.
        old_frags = old_template['template']['fragments']
        old_frags = [FragMeta(**_) for _ in old_frags]

        # Remove all those fragments from the template that the user has asked
        # us to update/delete.
        frags = [_ for _ in old_frags if _.aid not in aid_del.union(aid_mod)]

        # Add all those fragments the user wanted modifed (but not removed).
        frags.extend(frag_mod)

        # Convert the updated list of fragments to dictionaries so that they
        # can be saved in the database.
        frags = [_._asdict() for _ in frags]

        # Update the 'version' flag in the database. All clients
        # automatically receive this flag with their state variables.
        ret = db.update({'objID': objID},
                        {'$inc': {'version': 1},
                         '$set': {'template.fragments': frags}
                         })

        # Return the success status of the database update.
        if ret['n'] == 1:
            return RetVal(True, None, None)
        else:
            return RetVal(False, 'ID <{}> does not exist'.format(objID), None)

    @typecheck
    def setFragmentStates(self, fragData: dict):
        """
        Update the fragments states (pos, vel, etc) of one or more objects.

        This method can update one- or more fragment states in one- or
        more objects simultaneously. The updates are specified in ``fragData``
        as follows::

          fragData = {
            objID_1: [state_1, state_2, ...],
            objID_2: [state_3, state_4, ...]
          }

        where each ``state_k`` entry is a :ref:``FragState`` tuple. Those
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

        :param dict[list[FragData]] fragData: the new fragment states
        :return: success.
        """
        # Convenience.
        db_update = database.dbHandles['ObjInstances'].update

        # Sanity checks.
        try:
            # All objIDs must be integers and all values must be dictionaries.
            for objID, fragStates in fragData.items():
                assert isinstance(objID, int)
                fragData[objID] = [FragState(*_) for _ in fragStates]
        except (TypeError, AssertionError):
            return RetVal(False, 'Invalid data format', None)

        # Update the fragments. Process one object at a time.
        ok = True
        for objID, fragstate in fragData.items():
            # Convenience: string that represents the Mongo key for the
            # respective fragment name.
            key = 'fragState.{}'

            # Compile the MongoDB query to find the correct object and ensure
            # that every fragment indeed exists. The final query will have the
            # following structure:
            #   {'objID': 2,
            #    'fragState.1': {'$exists': 1},
            #    'fragState.2': {'$exists': 1},
            #    ...}
            query_find = {key.format(_.aid): {'$exists': 1} for _ in fragstate}
            query_find['objID'] = objID

            # Exactly the same query, except that instead of checking existince
            # we specify the FragState values. This will be the update query
            # and has the following structure:
            #   {'fragState.1': FragState,
            #    'fragState.2': FragState}
            query_update = {key.format(_.aid): _._asdict() for _ in fragstate}

            # Issue the update command to Mongo.
            ret = db_update(query_find, {'$set': query_update})

            # Exactly one document will have been updated if everything went
            # well. Note that we must check 'n' instead of 'nModified'. The
            # difference is that 'n' tells us how many documents Mongo has
            # touched whereas 'nModified' refers to the number of documents
            # that are now *different*. This distinction is important if
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

    def _packBodyState(self, objIDs: list):
        """
        Compile the data structure returned by ``get{All}BodyStates``.

        This is a convenience function to remove code duplication in
        ``getBodyStates`` and ``getAllBodyStates``.

        The input to this function is the output from ``leoAPI.getBodyStates``
        or ``leoAPI.getAllBodyStates``, which both return a dictionary. The
        keys in that dictionary denote objIDs and the values contain the
        rigid body state. This method adds the fragment states to that data
        structure.

        The returned dictionary has the following form::

        {
            objID_1: {
                'frag': [FragState(), ...],
                'rbs': _RigidBodyState(...),
            },
            objID_2: {
                'frag': [FragState(), ...],
                'rbs': _RigidBodyState(...),
            },
        }

        :param dict bodyStates: Each key is an object ID and the
            corresponding value a ``RigidBodyState`` instance.
        """
        # Convenience: extract all objIDs from ``bodyStates``.
        if objIDs is None:
            query = {}
        else:
            query = {'objID': {'$in': objIDs}}

        # Query the version values for all objects.
        db = database.dbHandles['ObjInstances']
        cursor = db.find(query,
                         {'version': True,
                          'objID': True,
                          'fragState': True,
                          'template.rbs': True})
        docs = {_['objID']: _ for _ in cursor}

        out = {}
        RBS = types._RigidBodyState
        for objID, doc in docs.items():
            fs = [FragState(**_) for _ in doc['fragState'].values()]
            rbs = RBS(**doc['template']['rbs'])
            rbs = rbs._replace(version=doc['version'])

            out[objID] = {'frag': fs, 'rbs': rbs}
        return RetVal(True, None, out)

    @typecheck
    def getBodyStates(self, objIDs: (list, tuple)):
        """
        Return the state variables for all ``objIDs`` in a dictionary.

        The dictionary keys will be the elements of ``objIDs`` and the
        associated  values are ``RigidBodyState`` instances, or *None*
        if the corresponding objID did not exist.

        :param list[int] objIDs: list of objects to query.
        :return: see :ref:``_packBodyState``.
        :rtype: dict
        """
        with util.Timeit('clerk.getBodyStates') as timeit:
            out = {_: None for _ in objIDs}
            ret = self._packBodyState(objIDs)
            if ret.ok:
                out.update(ret.data)
                return RetVal(True, None, out)
            else:
                return ret

    @typecheck
    def getAllBodyStates(self, dummy=None):
        """
        Return all State Variables in a dictionary.

        The dictionary will have the objIDs and state-variables as keys and
        values, respectively.

        .. note::
           The ``dummy`` argument is a placeholder because the ``runCommand``
           function assumes that every method takes at least one argument.

        :return: see :ref:``_packBodyState``.
        :rtype: dict
        """
        with util.Timeit('clerk.getAllBodyStates') as timeit:
            ret = self._packBodyState(None)
            if ret.ok:
                return RetVal(True, None, ret.data)
            else:
                return ret

    @typecheck
    def setBodyState(self, objID: int, state: dict):
        """
        Set the state variables of ``objID`` to ``state``.

        For a detailed description see ``leoAPI.addCmdModifyBodyState``
        since this method is only a wrapper for it.

        :param int objID: object ID
        :param dict state: new object attributes.
        :return: Success
        """
        db = azrael.database.dbHandles['ObjInstances']

        # Backup the original state because addCmdModify will need.
        state_bak = dict(state)

        try:
            state = types.DefaultRigidBody(**state)
        except TypeError:
            return RetVal(False, 'Invalid body state data', None)
        state = state._asdict()

        # Convert the collision shapes.
        try:
            if 'cshapes' in state:
                state['cshapes'] = [_._asdict() for _ in state['cshapes']]
        except TypeError:
            return RetVal(False, 'Invalid collision shape', None)

        # Update the respective entries in the data base. The keys already have
        # the correct names but must be saved under 'template.rbs'.
        body = {'template.rbs.' + k: v for (k, v) in state.items()}
        query = {'objID': objID}
        db.update(query, {'$set': body})

        # Notify Leonard.
        state = types.RigidBodyStateOverride(**state_bak)
        ret = leoAPI.addCmdModifyBodyState(objID, state)
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
        Return the list of ``objIDs`` currently in the simulation.

        .. note::
           The ``dummy`` argument is a placeholder because the ``runCommand``
           function assumes that every method takes at least one argument.

        :param dummy: irrelevant
        :return: list of objIDs
        :rtype: list(int)
        """
        db = database.dbHandles['ObjInstances']
        return RetVal(True, None, db.distinct('objID'))

    @typecheck
    def setForce(self, objID: int, force: (tuple, list), rpos: (tuple, list)):
        """
        Apply ``force`` to ``objID`` at position ``rpos``.

        The force will be applied at ``rpos`` relative to the center of mass.

        If ``objID`` does not exist return an error.

        :param int objID: object ID
        :return: Sucess
        """
        # Compute the torque and then queue a command for Leonard to apply the
        # specified force- and torque values to this object.
        torque = np.cross(np.array(rpos, np.float64),
                          np.array(force, np.float64)).tolist()
        return leoAPI.addCmdDirectForce(objID, force, torque)

    @typecheck
    def addConstraints(self, constraints: (tuple, list)):
        """
        Add ``constraints`` to the physics simulation.

        See ``Igor.addConstraints`` for details.

        :param list[ConsraintMeta] constraints: the constraints to add.
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

        :param list[ConstraintMeta] constraints: the constraints to remove.
        :return: number of deleted entries.
        """
        return self.igor.deleteConstraints(constraints)
