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
``WebServer`` implements a web server bridge. In both cases the data exchange is
plain JSON; no Python specific data types are used to keep the interface
language agnostic.

"""
import io
import os
import zmq
import copy
import json
import jsonschema
import base64
import traceback

import numpy as np

import azrael.igor
import azrael.database
import azrael.util as util
import azrael.aztypes as aztypes
import azrael.config as config
import azrael.leo_api as leoAPI
import azrael.dibbler as dibbler
import azrael.database as database
import azrael.protocol as protocol
import azrael.azschemas as azschemas

from IPython import embed as ipshell
from azrael.aztypes import typecheck, RetVal, Template, FragMeta, _FragMeta


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
            'add_templates': (
                protocol.ToClerk_AddTemplates_Decode,
                self.addTemplates,
                protocol.FromClerk_AddTemplates_Encode),
            'get_templates': (
                protocol.ToClerk_GetTemplates_Decode,
                self.getTemplates,
                protocol.FromClerk_GetTemplates_Encode),
            'get_template_id': (
                protocol.ToClerk_GetTemplateID_Decode,
                self.getTemplateID,
                protocol.FromClerk_GetTemplateID_Encode),
            'spawn': (
                protocol.ToClerk_Spawn_Decode,
                self.spawn,
                protocol.FromClerk_Spawn_Encode),
            'remove_object': (
                protocol.ToClerk_RemoveObject_Decode,
                self.removeObject,
                protocol.FromClerk_RemoveObject_Encode),
            'get_all_objids': (
                protocol.ToClerk_GetAllObjectIDs_Decode,
                self.getAllObjectIDs,
                protocol.FromClerk_GetAllObjectIDs_Encode),
            'get_object_states': (
                protocol.ToClerk_GetObjectStates_Decode,
                self.getObjectStates,
                protocol.FromClerk_GetObjectStates_Encode),
            'get_rigid_bodies': (
                protocol.ToClerk_GetRigidBodies_Decode,
                self.getRigidBodies,
                protocol.FromClerk_GetRigidBodies_Encode),
            'set_rigid_bodies': (
                protocol.ToClerk_SetRigidBodies_Decode,
                self.setRigidBodies,
                protocol.FromClerk_SetRigidBodies_Encode),
            'set_fragments': (
                protocol.ToClerk_SetFragments_Decode,
                self.setFragments,
                protocol.FromClerk_SetFragments_Encode),
            'get_fragments': (
                protocol.ToClerk_GetFragments_Decode,
                self.getFragments,
                protocol.FromClerk_GetFragments_Encode),
            'set_force': (
                protocol.ToClerk_SetForce_Decode,
                self.setForce,
                protocol.FromClerk_SetForce_Encode),
            'control_parts': (
                protocol.ToClerk_ControlParts_Decode,
                self.controlParts,
                protocol.FromClerk_ControlParts_Encode),
            'add_constraints': (
                protocol.ToClerk_AddConstraints_Decode,
                self.addConstraints,
                protocol.FromClerk_AddConstraints_Encode),
            'get_constraints': (
                protocol.ToClerk_GetConstraints_Decode,
                self.getConstraints,
                protocol.FromClerk_GetConstraints_Encode),
            'delete_constraints': (
                protocol.ToClerk_DeleteConstraints_Decode,
                self.deleteConstraints,
                protocol.FromClerk_DeleteConstraints_Encode),
            'set_custom': (
                protocol.ToClerk_SetCustomData_Decode,
                self.setCustomData,
                protocol.FromClerk_SetCustomData_Encode),
            'get_custom': (
                protocol.ToClerk_GetCustomData_Decode,
                self.getCustomData,
                protocol.FromClerk_GetCustomData_Encode),
        }

    def runCommand(self, cmd, payload, fun_decode, fun_process, fun_encode):
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

        :param str cmd: the command word
        :param dict payload: the data from the client.
        :param callable fun_decode: converter function (bytes --> Python)
        :param callable fun_process: processes the client request.
        :param callable fun_encode: converter function (Python --> bytes)
        :return: **None**
        """
        # The try/except is to keep Clerk from dying due to malformed client
        # request or processing errors.
        try:
            # Convert the JSON data to Python/Azrael types.
            out = fun_decode(payload)

            # Call the respective Clerk method with exactly the arguments supplied
            # in the JSON dictionary. If ``out`` is not a JSON dictionary then this
            # will raise an exception that the caller handles.
            ret = fun_process(**out)

            # If the Clerk method succeeded then encode the result to JSON.
            if ret.ok:
                tmp_json = fun_encode(ret.data)
                ret = ret._replace(data=tmp_json)

            # Send the response to the client.
            self.returnToClient(self.last_addr, ret)
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
            ret = RetVal(False, msg, None)
            self.returnToClient(self.last_addr, ret, addToLog=False)
            del msg, buf, msg_st, ret

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
            with util.Timeit('clerk.runCmd:1'):
                try:
                    msg = json.loads(msg.decode('utf8'))
                except (ValueError, TypeError):
                    ret = RetVal(False, 'JSON decoding error in Clerk', None)
                    self.returnToClient(self.last_addr, ret)
                    del ret
                    continue

            # Sanity check: every message must contain at least a command word.
            if not (('cmd' in msg) and ('data' in msg)):
                ret = RetVal(False, 'Invalid command format', None)
                self.returnToClient(self.last_addr, ret)
                del ret
                continue

            # Extract the command word and payload.
            cmd, payload = msg['cmd'], msg['data']

            with util.Timeit('clerk.runCmd:2-{}'.format(cmd)):
                # The command word determines the action...
                if cmd in self.codec:
                    # Look up the decode-process-encode functions for the current
                    # command word. The 'decode' part will interpret the JSON
                    # string we just received, the 'process' part is a handle to a
                    # method in this very Clerk instance, and 'encode' will convert
                    # the values to a valid JSON string that will be returned to
                    # the Client.
                    dec, proc, enc = self.codec[cmd]

                    # Run the Clerk function.
                    self.runCommand(cmd, payload, dec, proc, enc)
                else:
                    # Unknown command word.
                    ret = RetVal(False, 'Invalid command <{}>'.format(cmd), None)
                    self.returnToClient(self.last_addr, ret)

    @typecheck
    def returnToClient(self, addr, ret: RetVal, addToLog: bool=True):
        """
        Send ``ret`` to back to Client via ZeroMQ.

        This is a convenience method to enhance readability.

        :param addr: ZeroMQ address as returned by the ROUTER socket.
        :param bool addToLog: logs a 'Warning' with ``msg`` if *True*
        :param str msg: the error message to send back.
        :return: None
        """
        if addToLog and (ret.msg is not None):
            self.logit.warning(ret.msg)

        # Convert the message to JSON.
        try:
            ret = json.dumps(ret._asdict())
        except (ValueError, TypeError):
            msg = 'Could not convert Clerk return value to JSON'
            ret = json.dumps(RetVal(False, msg, None)._asdict())

        # Send the message via ZeroMQ.
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

        This method will abort immediately when one or more templates are
        invalid. If that happens then no templates will be added at all.

        It will also return an error if a template name already exists in the
        database. However, it will still add all the other templates that
        have unique names.

        :param list[Template]: the templates to add.
        :return: success
        :raises: None
        """
        # Return immediately if ``templates`` is empty.
        if len(templates) == 0:
            return RetVal(True, None, None)

        with util.Timeit('clerk.addTemplates'):
            # Verify that all templates contain valid data.
            try:
                templates = [Template(*_) for _ in templates]
            except TypeError:
                return RetVal(False, 'Invalid template data', None)

            # The templates will be inserted with a single bulk operation.
            db = database.dbHandles['Templates']
            bulk = db.initialize_unordered_bulk_op()

            # Insert each template into the database (only queue it in the bulk
            # operation, actually).
            for template in templates:
                # Convenience.
                b64dec = base64.b64decode

                # Store all fragment files in Dibbler under the following URL
                # prefix (eg. 'templates/template_name/'). The final URL for
                # each fragment will look something like this:
                # templates/template_name/fragment_name/fragfile_name_1'.
                url_frag = '{url}/{aid}'.format(url=config.url_templates, aid=template.aid)
                for fragname, frag in template.fragments.items():
                    # Create the url prefix for the current fragment name.
                    prefix = '{url}/{name}/'.format(url=url_frag, name=fragname)

                    # Attach the url prefix to each file in the fragment.
                    files = {prefix + k: v for k, v in frag.files.items()}

                    # Base64 encode the data (cannot be binary because it will
                    # be served up via HTTP).
                    files = {k: b64dec(v.encode('utf8')) for k, v in files.items()}

                    # Put the files into Dibbler. Abort the entire method if an
                    # error occurs.
                    # fixme: either delete all templates that may have already
                    # been added, or skip only this template and proceed to the
                    # next (prefered option). Then update the doc string.
                    ret = self.dibbler.put(files)
                    if not ret.ok:
                        return ret
                    del fragname, frag, prefix, files

                # Mangle all fragment file names to make them compatible with
                # Mongo.
                template_json = self._mangleFileNames(template._asdict())

                # Compile the template data that will go into the database. The
                # template will be stored as an explicit dictionary.
                data = {'url_frag': url_frag,
                        'template': template_json,
                        'templateID': template.aid}

                # Add the template to the database.
                query = {'templateID': template.aid}
                bulk.find(query).upsert().update({'$setOnInsert': data})

        with util.Timeit('clerk.addTemplates_db'):
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
                # Undo the file name mangling.
                template_json = self._unmangleFileNames(doc['template'])

                # Parse the document into a Template structure and add it to
                # the list of templates.
                template = Template(**template_json)
                out[doc['templateID']] = {
                    'url_frag': doc['url_frag'],
                    'template': template,
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

    def _mangleFileNamesHelper(self, template_json: dict, char_src, char_dst):
        """
        Return 'template_json' where all file names were mangled.

        The mangling simply replaces all occurrences of ``char_src`` with
        ``char_dst``. Example: if ``char_src`` is '.' and ``char_dst`` is ';'
        then 'foo.bar' will become 'foo;bar;.

        The returned dictionary will be identical to``template_json`` except
        for the mangled file names.

        :param dict template_json: dictionary version of ``Template`` data
            structure.
        :param str char_src: the character(s) to replace
        :param str char_dst: the character(s) with which to replace
            ``char_src``.
        :return: dict
        """
        # Convert the template to JSON but remove the fragment data;
        # retain only names of the fragment files. The actual geometry
        # content is managed by Dibbler.
        for fragname, metafrag in template_json['fragments'].items():
            # Replace the 'files' dictionary with one where all values
            # are empty. Then mangle all file names (replace all
            # dots with semicolons) because Mongo would not accept dots
            # in any of the keys.
            fnames = metafrag['files']
            tmp = {fname.replace(char_src, char_dst): None for fname in fnames}
            metafrag['files'] = tmp
        return template_json
        
    def _mangleFileNames(self, template_json: dict):
        """
        Return ``template_json`` with mangled file names.

        This is a convenience function because eg Mongo does not allow dots in
        file names, yet virtually every file name has them.

        :param dict template_json: dictionary version of ``Template`` data
            structure.
        :return: dict
        """
        return self._mangleFileNamesHelper(template_json, '.', ';')

    def _unmangleFileNames(self, template_json: dict):
        """
        Return ``template_json`` with unmangled file names.

        This method is the inverse of ``_mangleFileNames``.

        :param dict template_json: dictionary version of ``Template`` data
            structure.
        :return: dict
        """
        return self._mangleFileNamesHelper(template_json, ';', '.')

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
        # Sanity checks: newObjects must be a list of dictionaries, and each
        # dictionary must contain at least a 'templateID' field that contains a
        # string. If an RBS field is present it must contain a valid rigid body
        # state.
        try:
            assert len(newObjects) > 0
            for tmp in newObjects:
                assert isinstance(tmp, dict)
                assert isinstance(tmp['templateID'], str)
                if 'rbs' in tmp:
                    aztypes.DefaultRigidBody(**tmp['rbs'])
        except (AssertionError, KeyError, TypeError):
            return RetVal(False, '<spawn> received invalid arguments', None)

        # Fetch the specified templates so that we can duplicate them in
        # the instance database afterwards.
        with util.Timeit('spawn:1 getTemplates'):
            t_names = [_['templateID'] for _ in newObjects]
            ret = self.getTemplates(t_names)
            if not ret.ok:
                self.logit.info(ret.msg)
                return ret
            templates = ret.data
            del t_names, ret

        # Request unique IDs for the new objects.
        ret = azrael.database.getUniqueObjectIDs(len(newObjects))
        if not ret.ok:
            self.logit.error(ret.msg)
            return ret
        newObjectIDs = ret.data

        with util.Timeit('spawn:2 createStates'):
            # Make a copy of every template and endow it with the meta
            # information for an instantiated object. Then add it to the list
            # of objects to spawn.
            dbDocs = []
            bodyStates = {}
            for newObj, objID in zip(newObjects, newObjectIDs):
                # Convenience: 'template' is a Template instance converted to
                # a dictionary (see types.py for the detailed layout).
                templateID = newObj['templateID']
                template = templates[templateID]['template']

                # Selectively overwrite the rigid body state stored in the
                # template with the values provided by the client.
                body = template.rbs
                if 'rbs' in newObj:
                    body = body._replace(**newObj['rbs'])
                template = template._replace(rbs=body)

                # Copy all fragment files from the template to a new
                # location dedicated to the object instance.
                url_src = '{src}/{aid}'.format(src=config.url_templates, aid=template.aid)
                url_dst = '{dst}/{aid}'.format(dst=config.url_instances, aid=objID)
                ret = RetVal(True, None, None)
                for fragname in template.fragments:
                    fnames = template.fragments[fragname].files

                    # Compile the names of the source and target files.
                    pre_src = '{url}/{name}/'.format(url=url_src, name=fragname)
                    pre_dst = '{url}/{name}/'.format(url=url_dst, name=fragname)
                    fnames = {pre_src + k: pre_dst + k for k in fnames}
                    del pre_src, pre_dst, fragname

                    # Copy the files. Abort the loop if an error occurs.
                    ret = self.dibbler.copy(fnames)
                    if not ret.ok:
                        break
                    del fnames

                # If the last Dibbler operation failed then delete all
                # fragments that would have been associated with the
                # object. Then skip to the next object.
                if not ret.ok:
                    # Clean up any fragment files from this object that may
                    # have been copied before the error occurred.
                    self.dibbler.removeDirs([url_dst])

                    # Log an error message.
                    msg = ('Dibbler could not copy the fragments from '
                           'the template <{}> because of this error: <{}>.'
                           ' This template will not be spawned')
                    msg = msg.format(templateID, ret.msg)
                    self.logit.error(msg)
                    continue
                
                # Mangle all fragment file names to make them compatible with
                # Mongo.
                template_json = self._mangleFileNames(template._asdict())

                # Compile the database document. Each entry must be an explicit
                # dictionary (eg 'template'). The document contains the
                # original template plus additional meta information,
                # for instance 'objID' and 'version'.
                doc = {
                    'objID': objID,
                    'url_frag': url_dst,
                    'version': 0,
                    'templateID': templateID,
                    'template': template_json,
                }

                # Track the rigid body state separately. These will be sent to
                # Leonard later.
                bodyStates[objID] = template.rbs

                # Add the new template document.
                dbDocs.append(doc)
                del templateID, objID, doc

            # Return immediately if there are no objects to spaw.
            if len(dbDocs) == 0:
                return RetVal(True, None, tuple())

            # Insert all objects into the State Variable DB. Note: this does
            # not make Leonard aware of their existence (see next step).
            database.dbHandles['ObjInstances'].insert(dbDocs)

        with util.Timeit('spawn:3 addCmds'):
            # Compile the list of spawn commands that will be sent to Leonard.
            objs = tuple(bodyStates.items())

            # Queue the spawn commands. Leonard will fetch them at its leisure.
            ret = leoAPI.addCmdSpawn(objs)
            if not ret.ok:
                return ret
            self.logit.debug('Spawned {} new objects'.format(len(objs)))

        return RetVal(True, None, newObjectIDs)

    @typecheck
    def updateBoosterForces(self, objID: int, cmds: dict):
        """
        Update the Booster values for an object and return the new net force.

        This method returns the torque and linear force that each booster would
        apply at object's center. A typical return value is::

            {'foo': ([force_x, force_y, force_z],
                     [torque_x, torque_y, torque_z]),
             'bar': ([force_x, force_y, force_z],
                     [torque_x, torque_y, torque_z]),
             ...}

        where 'foo' and 'bar' are the names of the boosters.

        :param int objID: object ID
        :param dict cmds: Booster commands.
        :return: (linear force, torque) that the Booster apply to the object.
        :rtype: tuple(vec3, vec3)
        """
        # Convenience.
        db = database.dbHandles['ObjInstances']

        # Query the object's booster information.
        query = {'objID': objID}
        doc = db.find_one(query, {'template.boosters': True})
        if doc is None:
            msg = 'Object <{}> does not exist'.format(objID)
            return RetVal(False, msg, None)
        instance = doc['template']
        del doc

        # Put the Booster entries from the database into Booster tuples.
        try:
            b = aztypes.Booster
            boosters = {k: b(**v)for (k, v) in instance['boosters'].items()}
            del b
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
                boosters[partID] = booster._replace(force=cmds[partID].force)
                booster = boosters[partID]
                del cmds[partID]

            # Convenience.
            b_pos = np.array(booster.pos)
            b_dir = np.array(booster.direction)

            # Update the central force and torque.
            force += booster.force * b_dir
            torque += booster.force * np.cross(b_pos, b_dir)
            del booster

        # If we have not consumed all commands yet then at least one partID did
        # not exist --> return with an error.
        if len(cmds) > 0:
            return RetVal(False, 'Some Booster partIDs were invalid', None)

        # Update the new Booster values (and only the Booster values) in the
        # instance database. To this end convert them back to dictionaries and
        # issue the update.
        boosters = {k: v._asdict() for (k, v) in boosters.items()}
        db.update(query, {'$set': {'template.boosters': boosters}})

        # Return the final force- and torque as a tuple of 2-tuples.
        out = (force.tolist(), torque.tolist())
        return RetVal(True, None, out)

    @typecheck
    def controlParts(self, objID: int, cmd_boosters: dict, cmd_factories: dict):
        """
        Issue commands to individual parts of the ``objID``.

        Boosters can be activated with a scalar force. The force automatically
        applies in the direction of the booster (taking the rotation of the
        parent into account).

        Both, ``cmd_booster`` and ``cmd_factories`` are dictionaries that use
        the part ID as the key. The values are ``CmdBooster`` and
        ``CmdFactory`` instances, respectively.

        :param int objID: object ID.
        :param dict cmd_booster: booster commands.
        :param dict cmd_factory: factory commands.
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

        # Fetch the SV for objID (we need this to determine the rotation of
        # the base object to which the parts are attached).
        sv_parent = self.getRigidBodies([objID])
        if not sv_parent.ok:
            msg = 'Could not retrieve body state for objID={}'.format(objID)
            self.logit.warning(msg)
            return RetVal(False, msg, None)

        # Return with an error if the requested objID does not exist.
        if sv_parent.data[objID] is None:
            msg = 'objID={} does not exits'.format(objID)
            self.logit.warning(msg)
            return RetVal(False, msg, None)

        # Extract the parent's rotation from its rigid body state.
        sv_parent = sv_parent.data[objID]['rbs']
        parent_orient = sv_parent.rotation
        quat = util.Quaternion(parent_orient[3], parent_orient[:3])

        # Sanity check the Booster- and Factory commands.
        try:
            b, f = aztypes.CmdBooster, aztypes.CmdFactory
            cmd_boosters = {k: b(*v) for (k, v) in cmd_boosters.items()}
            cmd_factories = {k: f(*v) for (k, v) in cmd_factories.items()}
            del b, f
        except TypeError:
            msg = 'Invalid booster- or factory command'
            self.logit.warning(msg)
            return RetVal(False, msg, None)

        # Verify that the Booster commands reference existing Boosters.
        for partID, cmd in cmd_boosters.items():
            # Verify the referenced booster exists.
            if partID not in instance.boosters:
                msg = 'Object <{}> has no Booster with AID <{}>'
                msg = msg.format(objID, partID)
                self.logit.warning(msg)
                return RetVal(False, msg, None)

        # Verify that the Factory commands reference existing Factories.
        for partID, cmd in cmd_factories.items():
            # Verify that the referenced factory exists.
            if partID not in instance.factories:
                msg = 'Object <{}> has no Factory with AID <{}>'
                msg = msg.format(objID, partID)
                self.logit.warning(msg)
                return RetVal(False, msg, None)
            del partID, cmd

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
        for partID, cmd in cmd_factories.items():
            # Template for this very factory.
            this = instance.factories[partID]

            # Position (in world coordinates) where the new object will be
            # spawned.
            pos = quat * this.pos + sv_parent.position

            # Align the exit velocity vector with the parent's rotation.
            velocityLin = cmd.exit_speed * (quat * this.direction)

            # Add the parent's velocity to the exit velocity.
            velocityLin += sv_parent.velocityLin

            # The body state of the new object must align with the factory unit
            # in terms of position, rotation, and velocity.
            init = {
                'templateID': this.templateID,
                'rbs': {
                    'position': tuple(pos),
                    'velocityLin': tuple(velocityLin),
                    'rotation': tuple(sv_parent.rotation),
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
    def removeObject(self, objID: int):
        """
        Remove ``objID`` from the physics simulation.

        :param int objID: ID of object to remove.
        :return: Success
        """
        # Announce that an object was removed.
        ret = leoAPI.addCmdRemoveObject(objID)

        # Remove the master record for the object.
        database.dbHandles['ObjInstances'].remove({'objID': objID})

        if ret.ok:
            url = '{dst}/{aid}'.format(dst=config.url_instances, aid=objID)
            self.dibbler.removeDirs([url])
            return RetVal(True, None, None)
        else:
            return RetVal(False, ret.msg, None)

    @typecheck
    def getFragments(self, objIDs: list):
        """
        Return information about the fragments of each object in ``objIDs``.

        This method returns a dictionary of the form::

            {objID_1: {'fragtype': 'raw', 'scale': 1, 'position': (1, 2, 3),
                       'rotation': (0, 1, 0, 0,), 'url_frag': 'http://',
                       'files': ['file1.json', 'file2.jpg', ...]},
             objID_2: {'fragtype': 'dae', 'scale': 1, 'position': (4, 5, 6),
                       'rotation': (0, 0, 0, 1), 'url_frag': 'http://',
                       'files': ['file1.json', 'file2.jpg', ...]},
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
        db = database.dbHandles['ObjInstances']
        docs = list(db.find({'objID': {'$in': objIDs}}))

        # Initialise the output dictionary with a None value for every
        # requested object. The loop below will overwrite these values for
        # those objects that we have actually found in the database.
        out = {_: None for _ in objIDs}

        # Determine the fragment- type (eg. 'raw' or 'dae') and URL and put it
        # into the output dictionary.
        pjoin = os.path.join
        try:
            # Create a dedicated dictionary for each object.
            for doc in docs:
                # It is well possible that (parts of) the document are being
                # deleted by another client while we query it here. The try/except
                # block ensures that we will skip documents that have become
                # (partially) invalid because one or more keys have gone missing.
                try:
                    # Restore the original fragment file names.
                    template_json = self._unmangleFileNames(doc['template'])

                    # Compile each fragment into a `FragMeta` type.
                    frags = template_json['fragments']
                    frags = {k: FragMeta(**v) for (k, v) in frags.items()}

                    # Compile the dictionary with all the geometries that comprise
                    # the current object, including where to download the geometry
                    # data itself (we only provide the meta information).
                    out[doc['objID']] = {
                        k: {
                            'scale': v.scale,
                            'position': v.position,
                            'rotation': v.rotation,
                            'fragtype': v.fragtype,
                            'url_frag': pjoin(doc['url_frag'], k),
                            'files': list(v.files.keys()),
                        } for (k, v) in frags.items()}
                except KeyError:
                    continue
        except TypeError:
            msg = 'Inconsistent Fragment data'
            self.logit.error(msg)
            return RetVal(False, msg, None)
        return RetVal(True, None, out)

    @typecheck
    def setFragments2(self, fragments: dict):
        """
        Fixme: copy docu from 'setFragments'

        Missing:
          - verify the type of objID and frags
          - specify behaviour when data is corrupt for a sub-set of objects
        """
        db = database.dbHandles['ObjInstances']
        num_updated = 0

        # Determine what data to update in each object. The database query runs
        # for every object individually.
        for objID, frags in fragments.items():
            # fixme: verify the type of `objID` and `frags`

            # The following variables are work lists.
            # db_set: overwrite these DB keys with the new values
            # db_del: delete these DB keys (pertains to geometry files)
            # db_exists: these keys must exist or the entire update does not
            #            got ahead
            # file_put: files to add/overwrite in Dibbler (and their content).
            # file_del: files to delete in Dibbler.
            db_set = {}
            db_del = {}
            db_exists = {}
            file_put = {}
            file_del = []

            # If any of the files were modified then the object needs a new
            # version.
            new_version = False

            # Path prefix for all the files that Dibbler has on this object.
            pre = '{dst}/{aid}'.format(dst=config.url_instances, aid=objID)

            # Compile the query to update the instance data.
            for fragname, fragdata in frags.items():
                try:
                    jsonschema.validate(fragdata, azschemas.setFragments)
                except jsonschema.exceptions.ValidationError:
                    self.logit.warning('Input failed to validate')
                    continue

                # The fragment must exist.
                dbkey = 'template.fragments.{}'.format(fragname)
                db_exists[dbkey] = True
                
                # Determine the state variables to update.
                if 'state' in fragdata:
                    # Compile the list of all states that should be changed.
                    # The logic below will silently ignore all those keys that
                    # do not denote a state.
                    ref = {k: None for k in aztypes.FragMeta._fields}
                    ref = {k: fragdata['state'].get(k, None) for k in ref}

                    # Remove all keys for which we did not get new values.
                    ref = {k: v for k, v in ref.items() if v is not None}

                    # Compile a dictionary where the key denotes the position
                    # of the state variable in the database document hierarchy.
                    for field, value in ref.items():
                        db_set['{}.{}'.format(dbkey, field)] = value

                # If the user wants to change the fragment type then we must
                # update the corresponding field in the database as well.
                if 'fragtype' in fragdata:
                    db_set['{}.fragtype'.format(dbkey)] = fragdata['fragtype']
                    new_version = True

                # Files to delete. This entails deleting the actual file in
                # Dibbler, as well as the reference to it in the instance database.
                url = '{pre}/{fragname}'.format(pre=pre, fragname=fragname)
                for fname in fragdata.get('del', []):
                    # The file to delete in Dibbler.
                    file_del.append('{url}/{filename}'.format(url=url, filename=fname))

                    # Mangle the file names (fixme: put this in dedicated method).
                    fname = fname.replace('.', ';')

                    # Specify which key to remove in the database.
                    tmp = '{}.files.{}'.format(dbkey, fname)
                    db_del[tmp] = True
                    new_version = True

                # Files to add/update. As above, we need to delete the files in
                # Dibbler and remove the corresponding keys in the instance database.
                for fname, fdata in fragdata.get('put', {}).items():
                    fdata = base64.b64decode(fdata.encode('utf8'))
                    # The file to add/overwrite in Dibbler.
                    file_put['{url}/{filename}'.format(url=url, filename=fname)] = fdata

                    # Mangle the file names (fixme: put this in dedicated method).
                    fname = fname.replace('.', ';')

                    # Specify which key to add in the database.
                    tmp = '{}.files.{}'.format(dbkey, fname)
                    db_set[tmp] = None
                    new_version = True

            # Compile the database query and issue it.
            ret = RetVal(True, None, None)
            if not (db_set == {} and db_del == {}):
                # The operations for MongoDB will be stored in this dictionary.
                op = {}

                # Increment the version if at least one geometry file changed,
                # or the fragment type changed.
                # fixme: must also increase the version when only the fragment
                #        type changes (needs a test).
                if new_version:
                    op['$inc'] = {'version': 1}

                # Specify the fields to add/overwrite, as well as their values.
                if len(db_set) > 0:
                    op['$set'] = db_set

                # Specify the fields to unset.
                if len(db_del) > 0:
                    op['$unset'] = db_del

                query = {'objID': objID}
                for k, v in db_exists.items():
                    if v is not True:
                        continue
                    query[k] = {'$exists': True}
                ret = db.update_one(query, op)
                if ret.modified_count > 1:
                    self.logit.error('Too many documents were udpated')
                    num_updated += 1
                else:
                    num_updated += ret.modified_count

            # Issue the Dibbler queries.
            self.dibbler.remove(file_del)
            self.dibbler.put(file_put)

            del objID, frags

        return RetVal(True, None, {'updated': num_updated})

    @typecheck
    def setFragments(self, fragments: dict):
        """
        Update the fragments in the database with the new ``fragments`` data.

        This will update existing objects. Non-existing objects will be
        skipped.

        Returns with an error unless *all* fragments in *all* objects could be
        updated.

        :param dict[str: ``FragMeta``] fragments: new fragments.
        :return: Success
        """
        # Preserve the caller's state of ``fragments`` because we are going to
        # modify and refactor it heavily.
        fragments = copy.deepcopy(fragments)

        # Compile- and sanity check the fragments.
        try:
            # Valid default values for a FragMeta types.
            ref_1 = {'fragtype': '_DEL_',
                     'scale': 1,
                     'position': (0, 0, 0),
                     'rotation': (0, 0, 0, 1),
                     'files': {}}

            # Same as ref_1 but all values are None.
            ref_2 = {k: None for k in ref_1}

            # Compile dictionary with all fragments to update. This is mostly
            # to sanitise data. It will also create valid FragMeta data from
            # the partial FragMeta data it receives. The partial FragMeta
            # coming from the client is valid in this case because all missing
            # fields mean they should not be modified (eg if the 'position'
            # field is missing then it means to not update the position field
            # of the fragment.)
            fragments_dibbler = {}
            for objID, frags in fragments.items():
                fragments_dibbler[objID] = {}
                for fragID, fragdata in frags.items():
                    # Create a valid FragMeta instance from the data that has
                    # valid default values for all those keys that the Client
                    # did not provide.
                    # This will sanity check the input data.
                    tmp = dict(ref_1)
                    tmp.update(fragdata)
                    fragments_dibbler[objID][fragID] = FragMeta(**tmp)

                    # Now that we know the input data is valid we can put it
                    # into a '_FragMeta' instance. We do *not* put it into a
                    # 'FragMeta' instance (note the missing underscore). This
                    # circumvents the sanity checks because our new object
                    # may well contain None values.
                    tmp = dict(ref_2)
                    tmp.update(fragdata)
                    fragments[objID][fragID] = _FragMeta(**tmp)

                    # Remove this from Dibbler's fragment list if the user did
                    # not provide a fragment type and fragment data (ie the
                    # user does not want us to touch the geometry itself).
                    f = fragments[objID][fragID]
                    if None in (f.fragtype, f.files):
                        del fragments_dibbler[objID][fragID]

                    del fragID, fragdata, tmp, f
                del objID, frags
            del ref_1, ref_2
        except TypeError:
            return RetVal(False, 'Not all fragment data sets are valid', None)

        # Convenience.
        db = database.dbHandles['ObjInstances']
        ok, msg = True, []

        # Update the objects (one by one) in the instance database.
        for objID, frags in fragments.items():
            # Update the fragment geometry in Dibbler (if there are any to
            # update). If an error occurs skip immediately to the next object.
            if len(fragments_dibbler[objID]) > 0:
                # Convenience.
                b64dec = base64.b64decode

                # Compile the location prefix for this object instance. The
                # overwrite all the fragments for which we got new data.
                url_dst = '{dst}/{aid}'.format(dst=config.url_instances, aid=objID)
                for fragname, frag in fragments_dibbler[objID].items():
                    # Final location of model file.
                    prefix = '{url}/{name}/'.format(url=url_dst, name=fragname)

                    # Either delete the model file or overwrite it, depending
                    # on what the user specified.
                    if frag.fragtype.upper() == '_DEL_':
                        assert self.dibbler.removeDirs([prefix])
                    else:
                        # Compile all file names and encode them properly.
                        fnames = frag.files
                        files = {prefix + k: v for k, v in fnames.items()}
                        files = {k: b64dec(v.encode('utf8')) for k, v in files.items()}

                        # Update all files in dibbbler.
                        self.dibbler.put(files)
                        del fnames, files
                    del fragname, prefix
                del url_dst

            # Remove all '_DEL_' fragments in the instance database.
            to_remove = set()
            new_version = False
            for fragID, frag in frags.items():
                # Skip fragments that have not type (ie Client does not want to
                # update the geometry for this fragment).
                if frag.fragtype is None:
                    continue

                # If we get to here then the geometry of at least one fragment
                # will be modified. This demands an update of the 'version'
                # flag (the version remains stable if we will merely update eg
                # scale/position because the client does not have to download
                # new geometry data in that case).
                new_version = True

                # Remove the fragment from the instance database if so
                # requested by the user.
                if frag.fragtype.upper() == '_DEL_':
                    db.update({'objID': objID},
                              {'$unset': {'template.fragments.{}'.format(fragID): True}})
                    to_remove.add(fragID)

            # Remove all those fragments from the fragment dictionary that the
            # client wanted removed, because we have already dealt with them.
            frags = {k: v for (k, v) in frags.items() if k not in to_remove}

            # Strip the geometry data because the instance database only
            # contains meta information; Dibbler contains the geometry.
            frags = {k: v._replace(files={}) for (k, v) in frags.items()}

            # Convert the fragments to dictionaries.
            frags = {k: v._asdict() for (k, v) in frags.items()}

            # Compile JSON hierarchy for the geometries to update without
            # touching the ones we do not want to update. This will result in a
            # dictionary like:
            #
            #     data = {'
            #         'template.fragments.foo.position': (1, 2, 3),
            #         'template.fragments.bar.scale': 2,
            #          ...
            #     }
            data = {}
            q_find = {'objID': objID}
            new_geometry = False
            for fragID, fragdata in frags.items():
                for field, value in fragdata.items():
                    # Skip the field if its value is None because it means the
                    # Client did not specify it (None values are otherwise not
                    # allowed and would not have passed the sanity check at the
                    # beginning of this method.
                    if value is None:
                        continue
                    key = 'template.fragments.{}.{}'.format(fragID, field)
                    data[key] = value

                    # If the fragment was not fully specified then it must
                    # already exist, as a partial update would otherwise not be
                    # possible. The next few lines will modify the Mongo query
                    # to enforce the existence of the fields unless *all* of
                    # them were specified, which means Dibbler must have
                    # processed (and accepted) it, and all other fields must
                    # not be None.
                    if fragID in fragments_dibbler:
                        if None not in fragments_dibbler[objID][fragID]:
                            q_find[key] = False
                    else:
                        q_find[key] = {'$exists': True}

            # Update the fragment state. Also update the 'version' if at least
            # one of the underlying geometries was changed.
            if new_version:
                ret = db.update(q_find, {'$inc': {'version': 1}, '$set': data})
            else:
                ret = db.update(q_find, {'$set': data})

            # Save the current objID if an error occured.
            if ret['n'] != 1:
                ok = False
                msg.append(objID)

        if ok:
            # No error occurred.
            return RetVal(True, None, None)
        else:
            # Return with an error and list all objIDs that did not update
            # correctly.
            tmp = '{' + str(set(msg)) + '}'
            msg = 'objIDs {} do not exist'.format(tmp)
            return RetVal(False, msg, None)

    @typecheck
    def getRigidBodies(self, objIDs: (list, tuple)):
        """
        Return the rigid body data for all ``objIDs`` in a dictionary.

        If ``objIDs`` is *None* then all bodies will be returned.

        The dictionary keys will be the elements of ``objIDs`` and the
        associated  values are ``RigidBodyData`` instances, or *None*
        if the corresponding objID did not exist.

        Return value example::

            ret = {
                id_1: {'rbs': RigidBodyData(...)},
                id_2: {'rbs': RigidBodyData(...)},
            }

        ..note:: the inner 'rbs' dictionary is currently redundant since it
            contains only a single hard coded key, but this will make it easy
            to pass along other values in the future, should the need arise.

        :param list[int] objIDs: list of objects to query.
        :return: see example above
        :rtype: dict
        """
        # Create the MongoDB query. If `objID` is None then the client wants
        # the state for all objects.
        if objIDs is None:
            query = {}
        else:
            query = {'objID': {'$in': objIDs}}
        prj = {
            'version': True,
            'objID': True,
            'template.rbs': True
        }

        # Query object states and compile them into a dictionary.
        db = database.dbHandles['ObjInstances']

        # Compile the data from the database into a simple dictionary that
        # contains the fragment- and body state.
        out = {}
        RBS = aztypes._RigidBodyData
        for doc in db.find(query, prj):
            # Compile the rigid body data and overwrite the version tag with
            # one stored in the database.
            rbs = RBS(**doc['template']['rbs'])
            out[doc['objID']] = {'rbs': rbs._replace(version=doc['version'])}

        # If the user requested a particular set of objects then make sure each
        # one is in the output dictionary. If one is missing (eg it does not
        # exist) then its value is None.
        if objIDs is not None:
            out = {_: out[_] if _ in out else None for _ in objIDs}
        return RetVal(True, None, out)

    @typecheck
    def setRigidBodies(self, bodies: dict):
        """
        Set the rigid body state of ``objID`` to ``body``.

        This method supports partial updates of rigid body data. To skip an
        attribute simply set it to *None* in the `_RigidBodyData` structure.

        This method always succeeds. However, the 'data' field in the return
        value contains a list of all object IDs that could not be updated for
        whatever reason. If an error occurs this method will simply skip to the
        next object and not announce the creation of a new object.

        :param dict[objID: RigidBodyData] bodies: new object attributes.
        :return: Success
        """
        # Convenience.
        db = azrael.database.dbHandles['ObjInstances']
        invalid_objects = []

        for objID, body in bodies.items():
            # Backup the key names the user wants us to update.
            modify_keys = set(body.keys())

            # Compile- and sanity check ``body``.
            try:
                body = aztypes.DefaultRigidBody(**body)._asdict()
            except TypeError:
                return RetVal(False, 'Invalid body data', None)

            # Only retain those keys the user wanted us to update (the
            # DefaultRigidBody constructed a complete body with *all*
            # attributes).
            body = {k: v for (k, v) in body.items() if k in modify_keys}

            # Update the respective entries in the database. The keys already have
            # the correct names but require the 'template.rbs' to match the
            # position in the master record.
            tmp = {'template.rbs.' + k: v for (k, v) in body.items()}
            ret = db.update({'objID': objID}, {'$set': tmp})
            if ret['n'] == 0:
                invalid_objects.append(objID)
                continue

            # Notify Leonard.
            ret = leoAPI.addCmdModifyBodyState(objID, body)
            if not ret.ok:
                return ret

        return RetVal(True, None, invalid_objects)

    @typecheck
    def getObjectStates(self, objIDs: list):
        """
        Return the object states (eg position of the body and its fragments).

        If ``objIDs`` is *None* then the states of all objects are returned.

        The returned dictionary contains the scale, position and rotation of
        every fragment and the rigid body, as well as the linear- and angular
        velocity of the body. The dictionary does not contain any collision
        shapes, fragment geometries, or other specialised data.

        The purpose of this method is to make it easy to query the salient
        information about an object in a bandwidth efficient way.::

            out = {
                objID_1: {
                    'frag': {
                        'a': {'scale': x, 'position': [...], 'rotation': [...],},
                        'b': {'scale': y, 'position': [...], 'rotation': [...],},
                    },
                    'rbs': _RigidBodyData(),
                },
                objID_2: {
                    'frag': {
                        'a': {'scale': x, 'position': [...], 'rotation': [...],},
                        'b': {'scale': y, 'position': [...], 'rotation': [...],},
                    },
                    'rbs': _RigidBodyData(...),
                },
            }

        :param list objIDs: the objIDs for which to compile the data.
        :return: see example above.
        """
        # Create the MongoDB query. If `objID` is None then the client wants
        # the state for all objects.
        if objIDs is None:
            query = {}
        else:
            query = {'objID': {'$in': objIDs}}

        # Query object states and compile them into a dictionary.
        db = database.dbHandles['ObjInstances']

        # Specify the fields we are really interested in here.
        prj = {
            'version': True,
            'objID': True,
            'template.fragments': True,
            'template.rbs.scale': True,
            'template.rbs.position': True,
            'template.rbs.rotation': True,
            'template.rbs.velocityLin': True,
            'template.rbs.velocityRot': True,
        }

        # Compile the data from the database into a simple dictionary that
        # contains the fragment- and body state.
        out = {}
        for doc in db.find(query, prj):
            # It is well possible that (parts of) the document are being
            # deleted by another client while we query it here. The try/except
            # block ensures that we will skip documents that have become
            # (partially) invalid because one or more keys have gone missing.
            try:
                # Convenience: fragments of current object.
                frags = doc['template']['fragments']

                # Compile the state data for each fragment of the current object.
                fs = {k: {'scale': v['scale'],
                          'position': v['position'],
                          'rotation': v['rotation']}
                      for (k, v) in frags.items()}

                # Add the current version to the rigid body data.
                rbs = doc['template']['rbs']
                rbs['version'] = doc['version']

                # Construct the return value.
                out[doc['objID']] = {'frag': fs, 'rbs': rbs}
            except KeyError as err:
                continue

        # If the user requested a particular set of objects then make sure each
        # one is in the output dictionary. If one is missing (eg it does not
        # exist) then its value is None.
        if objIDs is not None:
            out = {_: out[_] if _ in out else None for _ in objIDs}
        return RetVal(True, None, out)

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

        Return all contraints if ``bodyIDs`` is *None*.

        :param list[int] bodyIDs: list of body IDs.
        :return: List of ``ConstraintMeta`` instances.
        """
        self.igor.updateLocalCache()
        return self.igor.getConstraints(bodyIDs)

    @typecheck
    def deleteConstraints(self, constraints: (tuple, list)):
        """
        Return the number of ``constraints`` actually deleted.

        See ``Igor.deleteConstraints`` for details.

        :param list[ConstraintMeta] constraints: the constraints to remove.
        :return: number of deleted entries.
        """
        return self.igor.deleteConstraints(constraints)

    @typecheck
    def setCustomData(self, data: dict):
        """
        Update the `custom` field with the information in ``data``.

        ``Data`` is a dictionary, eg::
            {1: 'foo', 25: 'bar'}

        Non-existing objects are silently ignored, but their ID will be
        returned to the caller.

        All entries must be strings with less than 16k characters.

        :param dict[int: str] data: new content for 'custom' field in object.
        :return: List of invalid object IDs.
        """
        db = database.dbHandles['ObjInstances']

        # Update the 'custom' field of the specified object IDs.
        invalid_objects = []
        for objID, value in data.items():
            try:
                assert isinstance(value, str)
                assert len(value) < 2 ** 16

                ret = db.update({'objID': objID},
                                {'$set': {'template.custom': value}})

                # If the update did not work then add the current object ID to
                # the list.
                assert ret['n'] > 0
            except AssertionError:
                invalid_objects.append(objID)

        # Return the list of objects that could not be updated.
        return RetVal(True, None, invalid_objects)

    @typecheck
    def getCustomData(self, objIDs: (tuple, list)):
        """
        Return the `custom` data for all ``objIDs`` in a dictionary.

        The return value may look like:: {1: 'foo', 25: 'bar'}

        :param dict[int: str] data: new content for 'custom' field in object.
        :return: dictionary of 'custom' data.
        """
        db = database.dbHandles['ObjInstances']

        if objIDs is None:
            # Query all objects.
            query = {'template.custom': {'$exists': True}}
            out = {}
        else:
            # Only query the specified objects. Return a *None* value for all
            # those objects not found in the database.
            query = {'objID': {'$in': objIDs}, 'template.custom': {'$exists': True}}
            out = {_: None for _ in objIDs}

        # Prjection operator.
        prj = {'template.custom': True, '_id': False, 'objID': True}

        # Unpack the data. For some unknown reason (read: bug) the database
        # record is sometimes incomplete. Therefore extract the entries
        # one-by-one protected by a try/except.
        for doc in db.find(query, prj):
            try:
                objID = doc['objID']
                tag = doc['template']['custom']
                out[objID] = tag
            except KeyError:
                pass

        return RetVal(True, None, out)
