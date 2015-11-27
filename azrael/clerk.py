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
import traceback

import numpy as np

import azrael.igor
import azrael.util as util
import azrael.aztypes as aztypes
import azrael.config as config
import azrael.leo_api as leoAPI
import azrael.dibbler as dibbler
import azrael.protocol as protocol
import azrael.datastore as datastore
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
            'remove_objects': (
                protocol.ToClerk_RemoveObjects_Decode,
                self.removeObjects,
                protocol.FromClerk_RemoveObjects_Encode),
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
            try:
                sock = dict(poller.poll())
            except KeyboardInterrupt:
                break
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
        self.logit.warning('Clerk was aborted')

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
        Add all ``templates`` to Azrael and return the success.

        The elements in ``templates`` must be ``Template`` instances.

        If a template with the same name already exists in the data store then
        it will not be added.

        The returned dictionary contains a key for each template AID and a
        Boolean value to indicate whether the template was successfully added.
        Example::

            addTemplates(...) == (True, None, {'foo': True, 'bar': False})

        :param list[Template]: the templates to add.
        :return: success
        :raises: None
        """
        # Return immediately if ``templates`` is empty.
        if len(templates) == 0:
            return RetVal(True, None, None)

        with util.Timeit('clerk.addTemplates'):
            # Verify that all `templates` are valid.
            try:
                templates = [Template(*_) for _ in templates]
            except TypeError:
                return RetVal(False, 'Invalid template data', None)

            # Handle to data store.
            db = datastore.dbHandles['Templates']

            # Prepare each template and compile the database operations.
            dib_files, ds_ops = {}, {}
            for template in templates:
                aid = template.aid
                dib_files[aid] = {}

                # Store all fragment files in Dibbler under the following URL
                # prefix (eg. 'templates/template_name/'). The final URL for
                # each fragment will look something like this:
                # templates/template_name/fragment_name/fragfile_name_1'.
                url_frag = '{url}/{aid}'.format(url=config.url_templates, aid=aid)
                for fragname, frag in template.fragments.items():
                    # Create the url prefix for the current fragment name and
                    # prefix each file name with it.
                    pre = '{url}/{name}/'.format(url=url_frag, name=fragname)
                    files = {pre + k: v for k, v in frag.files.items()}

                    dib_files[aid].update(files)
                    del fragname, frag, pre, files

                # Mangle the name of all fragment files to avoid problems with
                # indexing the document hierarchy (ie. replace all dots '.').
                template_json = self._mangleTemplate(template._asdict())

                # Compile the template data that will go into the database. The
                # template will be stored as an explicit dictionary.
                data = {'url_frag': url_frag,
                        'template': template_json,
                        'templateID': aid}

                # Compile the data store ops for this template.
                ds_ops[template.aid] = {'data': data}

        # Insert the templates. Since this will overwrite existing templates
        # with the same name we need to determine which templates were actually
        # added.
        ret = db.put(ds_ops)
        if ret.ok is False:
            return ret
        valid = [k for k, v in ret.data.items() if v is True]

        # For every successfully added template we will now put the
        # corresponding fragment files into Dibbler.
        for aid in valid:
            if not self.dibbler.put(dib_files[aid]).ok:
                msg = 'Dibbler could not add the files {} for template <{}>'
                fnames = list(dib_files[aid].keys())
                self.logit.warning(msg.format(fnames, aid))
        return ret

    @typecheck
    def getTemplates(self, templateIDs: list):
        """
        Return the meta data for all ``templateIDs`` as a dictionary.

        The data for for non-existing templates will be None.

        Note that each template will be returned only once, no matter
        how many times it was specified in `templateIDs`. For instance,
        these two calls will both return the same two templates::

            getTemplates([name_1, name_2, name_1])
            getTemplates([name_1, name_2])

        The keys in the returned dictionary are the entries of `templateIDs`::

            ret = {templateIDs[0]: {'template': Template(),
                                    'url_frag': URL for geometries},
                   templateIDs[1]: {...}, }.

        ..note:: The template data only contains meta information about the
            geometry. The geometry itself is available at the URL specified in
            the return value.

        :param list[Template] templateIDs: template IDs
        :return dict: raw template data with templateID as key.
        """
        # Sanity check: all template IDs must be strings.
        try:
            for tid in templateIDs:
                assert isinstance(tid, str)
        except AssertionError:
            return RetVal(False, 'All template IDs must be strings', None)

        # Remove all duplicates from the list of templateIDs.
        templateIDs = tuple(set(templateIDs))

        # Fetch the requested templates.
        db = datastore.dbHandles['Templates']
        ret = db.getMulti(templateIDs)
        if not ret.ok:
            return ret

        # Guard against corrupt data in the data store.
        try:
            # Compile all templates into the 'out' dictionary.
            out = {}
            for aid, doc in ret.data.items():
                # The template data for non-existing objects is None.
                if doc is None:
                    out[aid] = None
                    continue

                # Undo the file name mangling.
                template_json = self._unmangleTemplate(doc['template'])

                # Parse the document into a Template structure.
                out[aid] = {
                    'url_frag': doc['url_frag'],
                    'template': Template(**template_json),
                }
        except TypeError:
            # This is a serious error because it means the data in the data
            # store is corrupt.
            msg = 'Inconsistent Template data'
            self.logit.critical(msg)
            return RetVal(False, msg, None)

        # Return the templates.
        return RetVal(True, None, out)

    def _mangleFileName(self, fname: str, unmangle: bool):
        """
        Return the (un)mangled version of ``fname``.
        """
        if unmangle:
            return fname.replace(';', '.')
        else:
            return fname.replace('.', ';')

    def _mangleTemplate(self, template_json: dict):
        """
        Return ``template_json`` with mangled file names.

        This is a convenience function because eg Mongo does not allow dots in
        file names, yet virtually every file name has them.

        :param dict template_json: dictionary version of ``Template`` data
            structure.
        :return: dict
        """
        # Iterate over all fragments in the template and mangle the geometry
        # file names.
        for fragname, metafrag in template_json['fragments'].items():
            fnames = metafrag['files']
            tmp = {self._mangleFileName(fname, unmangle=False): None
                   for fname in fnames}
            metafrag['files'] = tmp
        return template_json

    def _unmangleTemplate(self, template_json: dict):
        """
        Return ``template_json`` with unmangled file names.

        This method is the inverse of ``_mangleTemplate``.

        :param dict template_json: dictionary version of ``Template`` data
            structure.
        :return: dict
        """
        # Iterate over all fragments in the template and mangle the geometry
        # file names.
        for fragname, metafrag in template_json['fragments'].items():
            fnames = metafrag['files']
            tmp = {self._mangleFileName(fname, unmangle=True): None
                   for fname in fnames}
            metafrag['files'] = tmp
        return template_json

    @typecheck
    def spawn(self, newObjects: (tuple, list)):
        """
        Spawn all ``newObjects`` and return their IDs in a tuple.

        The ``newObjects`` variable mut be a list of dictionaries. Each
        dictionary *must* contain a 'templateID'. It *may* contain an 'rbs'
        key. The 'templateID' specifies which template should be used for the
        new object. The 'rbs' value, which is a dictionary itself,
        specifies the values to override in the rigid body structure. For
        instance, a valid `newObjects` argument would be::

            newObjects = [
                {'templateID': 'foo'},
                {'templateID': 'foo', 'rbs': {'imass': 5}},
                {'templateID': 'bar', 'rbs': {'position': (1, 2, 3)},
            ]

        This will spawn three objects. The first one is a verbatim copy of
        `foo`. The second will also be an instance of `foo` but with an `imass`
        of 5, whereas the third object is an instance of `bar` that is spawned
        at position (1, 2, 3).

        This method will either spawn all objects, or return with an error
        without spawning a single one.

        :param list[dict] newObjects: template IDs (key) and body parameters to
            override (value).
        :return: IDs of spawned objects
        :rtype: tuple of int
        """
        # Sanity checks: newObjects must be a list of dictionaries. Each must
        # contain at least a 'templateID' field that contains a string. If the
        # RBS field is present it must contain a valid rigid body state.
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
        # the instance database afterwards. Return with an error unless all
        # requested templates were found.
        with util.Timeit('spawn:1 getTemplates'):
            t_names = [_['templateID'] for _ in newObjects]
            ret = self.getTemplates(t_names)
            if not ret.ok:
                return ret
            del t_names

            # Could not find all templates. Abort without spawning anything.
            if None in ret.data.values():
                msg = 'Could not find all templates'
                self.logit.info(msg)
                return RetVal(False, msg, None)

            # These are the templates to spawn.
            templates = ret.data

        # Request unique IDs for the new objects.
        ret = datastore.getUniqueObjectIDs(len(newObjects))
        if not ret.ok:
            self.logit.error(ret.msg)
            return ret
        newObjectIDs = ret.data

        db = datastore.dbHandles['ObjInstances']
        with util.Timeit('spawn:2 createStates'):
            # Copy every template, endow it with the meta information for an
            # instance object, and add it to the list of objects to spawn.
            ds_ops, dib_files = {}, {}
            bodyStates = {}
            for newObj, objID in zip(newObjects, newObjectIDs):
                # Unpack the template name and its data (convenience).
                templateID = newObj['templateID']
                template = templates[templateID]['template']

                # ------------------------------------------------------------
                # Overwrite the initial state with the provided values (eg
                # initial position).
                # ------------------------------------------------------------
                body = template.rbs
                if 'rbs' in newObj:
                    body = body._replace(**newObj['rbs'])
                template = template._replace(rbs=body)
                del body

                # The new bodies will be published once the objects exist in
                # the database. Until then, store them.
                bodyStates[objID] = template.rbs

                # ------------------------------------------------------------
                # Compile the copy operations for Dibbler. This means
                # duplicating all fragment files from the template data store
                # to the instance data store.
                # ------------------------------------------------------------
                # Duplicate the fragment files to the instance URL.
                url_src = '{src}/{aid}'.format(src=config.url_templates,
                                               aid=template.aid)
                url_dst = '{dst}/{aid}'.format(dst=config.url_instances,
                                               aid=objID)
                dib_files[objID] = {}
                for fragname in template.fragments:
                    fnames = template.fragments[fragname].files

                    # Compile the names of the source and target files.
                    pre_src = '{url}/{name}/'.format(url=url_src, name=fragname)
                    pre_dst = '{url}/{name}/'.format(url=url_dst, name=fragname)
                    fnames = {pre_src + k: pre_dst + k for k in fnames}
                    dib_files[objID].update(fnames)
                    del fragname, fnames, pre_src, pre_dst
                del url_src

                # ------------------------------------------------------------
                # Compile the data store commands to insert the objects into
                # the instance store.
                # ------------------------------------------------------------
                # Mangle the name of all fragment files to avoid problems with
                # indexing the document hierarchy (ie. replace all dots '.').
                template_json = self._mangleTemplate(template._asdict())

                # Compile the database document. Each entry must be an explicit
                # dictionary (eg 'template'). The document contains the
                # original template plus additional meta information, for
                # instance the AID of the template from which it was spawned,
                # or the current 'version'.
                doc = {
                    'url_frag': url_dst,
                    'version': 0,
                    'templateID': templateID,
                    'template': template_json,
                }

                # Compile the datastore command to add the template to the
                # instance database.
                ds_ops[objID] = {'data': doc}
                del templateID, template, newObj, objID, doc

            # -----------------------------------------------------------------
            # Run the actual datastore- and Dibbler queries.
            # -----------------------------------------------------------------
            # Return immediately if there are no objects to spaw.
            if len(ds_ops) == 0:
                return RetVal(True, 'No objects to spawn', tuple())

            # Insert the objects. Since this will overwrite existing templates
            # with the same name we need to determine which templates were
            # actually added.
            ret = db.put(ds_ops)
            if not ret.ok:
                return ret
            valid = [k for k, v in ret.data.items() if v is True]
            self.logit.debug('Spawned {} new objects'.format(len(valid)))

            # For every successfully added objects we will now tell Dibbler to
            # duplicate the fragment files and make them available at the
            # instance URL for the respective object.
            for aid in valid:
                if not self.dibbler.copy(dib_files[aid]).ok:
                    msg = 'Dibbler could not copy the files {} for template <{}>'
                    fnames = list(dib_files[aid].keys())
                    self.logit.warning(msg.format(fnames, aid))

        # Publish the existence of the new objects.
        with util.Timeit('spawn:3 addCmds'):
            # Queue the spawn commands. Leonard will fetch them at its leisure.
            objs = tuple(bodyStates.items())
            ret = leoAPI.addCmdSpawn(objs)
            if not ret.ok:
                return ret
            self.logit.debug('Announced {} newly spawned objects'.format(len(objs)))

        return RetVal(True, None, newObjectIDs)

    @typecheck
    def updateBoosterForces(self, objID: str, cmds: dict):
        """
        Update the Booster values for ``objID`` and return the new net force.

        This method returns the torque and linear force that each booster would
        apply at object's center. A typical return value is::

            {'foo': ([force_x, force_y, force_z],
                     [torque_x, torque_y, torque_z]),
             'bar': ([force_x, force_y, force_z],
                     [torque_x, torque_y, torque_z]),
             ...}

        where 'foo' and 'bar' are the booster names.

        :param str objID: object ID
        :param dict cmds: Booster commands.
        :return: (linear force, torque) that the Booster apply to the object.
        :rtype: tuple(vec3, vec3)
        """
        # Convenience.
        db = datastore.dbHandles['ObjInstances']

        # Query the object's booster information.
        ret = db.getOne(objID, [['template', 'boosters']])
        if not ret.ok:
            return ret

        # Return with an error if `objID` does not exists.
        if ret.data is None:
            msg = 'Object <{}> does not exist'.format(objID)
            return RetVal(False, msg, None)
        instance = ret.data['template']

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

        # Compile modification op.
        ops = {
            objID: {
                'inc': {},
                'set': {('template', 'boosters'): boosters},
                'unset': [],
                'exists': {('template', 'boosters'): True},
            }
        }
        ret = db.modify(ops)
        if ret.ok:
            # Return the final force- and torque as a tuple of 2-tuples.
            out = (force.tolist(), torque.tolist())
            return RetVal(True, None, out)
        else:
            # The object was probably deleted in between querying it earlier
            # and now that we want to update it.
            return ret

    @typecheck
    def controlParts(self, objID: str, cmd_boosters: dict, cmd_factories: dict):
        """
        Issue commands to individual parts of the ``objID``.

        Boosters can be activated with a scalar force. The force automatically
        applies in the direction of the booster (taking the rotation of the
        parent into account).

        Both, ``cmd_booster`` and ``cmd_factories`` are dictionaries that use
        the part ID as the key. The values are ``CmdBooster`` and
        ``CmdFactory`` instances, respectively.

        :param str objID: object ID.
        :param dict cmd_booster: booster commands.
        :param dict cmd_factory: factory commands.
        :return: **True** if no error occurred.
        :rtype: bool
        :raises: None
        """
        # Fetch the instance data and return immediately if it does not exist.
        db = datastore.dbHandles['ObjInstances']
        ret = db.getOne(objID, [['template']])
        if not ret.ok:
            return ret

        # Return with an error if ``objID`` does not exist.
        if ret.data is None:
            msg = 'Could not find instance data for objID <{}>'.format(objID)
            self.logit.info(msg)
            return RetVal(False, msg, None)

        # Compile the instance information (it is a `Template` data structure).
        doc = ret.data
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
    def removeObjects(self, objIDs: (tuple, list)):
        """
        Remove all ``objIDs`` from the physics simulation.

        This method will silently ignore non-existing objIDs.

        :param list[str] objIDs: ID of object to remove.
        :return: Success
        """
        # Announce that an object was removed.
        for objID in objIDs:
            leoAPI.addCmdRemoveObject(objID)

        # Fetch the documents before deleting them (need later).
        db = datastore.dbHandles['ObjInstances']
        docs = db.getMulti(objIDs).data

        # Remove the objects from the instance data store.
        ret = db.remove(objIDs)
        if not ret.ok:
            return ret

        # Delete the fragments for all those objects that actually existed.
        ops = [_['url_frag'] for _ in docs.values() if _ is not None]
        self.dibbler.removeDirs(ops)
        return RetVal(True, None, None)

    @typecheck
    def getFragments(self, objIDs: list):
        """
        Return fragments information for all ``objIDs``.

        The returned dictionary has the following form::

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

        ..note:: This method does not actually return any geometries; it only
            returns the URLs from where they can be downloaded.

        :param list objIDs: return geometry information for all of them.
        :return: meta information about all fragment for each object.
        :rtype: dict
        """
        # Retrieve the geometry. Return an error if the ID does not exist.
        db = datastore.dbHandles['ObjInstances']
        ret = db.getMulti(objIDs)
        if not ret.ok:
            return ret

        # Initialise the output dictionary with a None value for every
        # requested object. The loop below will overwrite these values for
        # those objects that we have actually found in the database.
        out = {_: None for _ in objIDs}

        # Guard against corrupt data. This really should not happen and means
        # there is a serious bug somewhere.
        try:
            # Compile the fragment info for the requested AIDs into a dictionary.
            docs = ret.data
            pjoin = os.path.join
            for aid, doc in docs.items():
                # The fragment data for non-existing objects is None.
                if doc is None:
                    continue

                # Restore the original fragment file names.
                template_json = self._unmangleTemplate(doc['template'])

                # Compile each fragment into a `FragMeta` type.
                frags = template_json['fragments']
                frags = {k: FragMeta(**v) for (k, v) in frags.items()}

                # The fragment information includes the state (scale/pos/rot)
                # and fragment type. It also includes the prefix URL for all
                # the files, as well as the file names themselves.
                out[aid] = {
                    fragname: {
                        'scale': frag.scale,
                        'position': frag.position,
                        'rotation': frag.rotation,
                        'fragtype': frag.fragtype,
                        'url_frag': pjoin(doc['url_frag'], fragname),
                        'files': list(frag.files.keys()),
                    } for (fragname, frag) in frags.items()}
        except TypeError:
            msg = 'Inconsistent fragment data'
            self.logit.critical(msg)
            return RetVal(False, msg, None)
        return RetVal(True, None, out)

    def _setFragOps(self, objID, fragkey, url, fragop, op_db, op_file):
        """
        Compile meta commands for database and return success.

        This is an auxiliary function for `setFragments`. It parses the
        provided ``fragop`` and determine which database fields need to be
        set, modified, or deleted. The results are added to ``op_db``.

        Similarly, it determine which files have to be
        added, overwritten, or removed into Dibbler. The results are added to
        ``op_file``.

        This method modifies the ``op_db`` and ``op_file`` dictionaries
        directly. It returns True if ``fragop`` specifies a valid operation,
        otherwise it returns False.

        ..note:: This method is database agnostic. The caller is responsible
            for compiling ``op_db`` into actual database commands.
        """
        # Determine if the fragments needs to be overwritten ('put'), modified
        # ('mod'), or deleted ('del').
        if fragop['op'] == 'del':
            # Delete a fragment: remove the top level key from the
            # database. Recursively delete all its files starting at the
            # top-level directory.
            # This operation must update the version number.
            op_db['inc'] = {('version', ): 1}
            op_db['unset'].append(fragkey)
            op_file['rmdir'].append(url)
        elif fragop['op'] == 'put':
            # New fragment: this will delete the old fragment and then insert a
            # new one. This operation only goes ahead if a complete fragment is
            # specified. If one or more keys (eg. 'position') are missing then
            # nothing happens and the old fragment remains intact.
            try:
                # The JSON hierarchy for the new fragment.
                doc = {
                    'scale': fragop['scale'],
                    'position': fragop['position'],
                    'rotation': fragop['rotation'],
                    'fragtype': fragop['fragtype'],
                    'files': [fname.replace('.', ';') for fname in fragop['put']]
                }

                # Specify the files that should go into Dibbler.
                files = {}
                for fname, fdata in fragop['put'].items():
                    files['{url}/{filename}'.format(url=url, filename=fname)] = fdata
            except KeyError:
                # PUT operation is inconsistent. Notify the caller.
                msg = 'New fragment for object <{}> is incomplete'.format(objID)
                self.logit.info(msg)
                return False

            # The fragment is valid. Specify the new document hierarchy.
            op_db['set'][fragkey] = doc
            op_db['inc'] = {('version', ): 1}

            # Specify the files to go into Dibbler (this could not happen
            # earlier because we needed to ensure the whole fragment was
            # valid).
            op_file['put'] = files

            # Delete the original fragment. 'setFragments' will always delete
            # files and directories first before adding new files.
            op_file['rmdir'].append(url)
        elif fragop['op'] == 'mod':
            # Only existing keys can be updated.
            op_db['exists'][fragkey] = True

            # Overwrite the state variables (if there are any).
            for state in ('scale', 'position', 'rotation'):
                if state not in fragop:
                    continue
                op_db['set'][fragkey + (state,)] = fragop[state]

            # A new fragment types must trigger a version increase.
            if 'fragtype' in fragop:
                op_db['set'][fragkey + ('fragtype',)] = fragop['fragtype']
                op_db['inc'] = {('version', ): 1}

            # Delete geometry files for the current fragment.
            for fname in fragop.get('del', []):
                # The file to delete in Dibbler.
                absname = '{url}/{filename}'.format(url=url, filename=fname)
                op_file['del'].append(absname)

                # Mangle the file names to make them compatible with Mongo.
                fname = self._mangleFileName(fname, unmangle=False)

                # Remove the keys that list the file names.
                op_db['unset'].append(fragkey + ('files', fname))
                op_db['inc'] = {('version', ): 1}

            # Overwrite these files.
            for fname, fdata in fragop.get('put', {}).items():
                # The file to add/overwrite in Dibbler.
                absname = '{url}/{filename}'.format(url=url, filename=fname)
                op_file['put'][absname] = fdata

                # Mangle the file names to make them compatible with Mongo.
                fname = self._mangleFileName(fname, unmangle=False)

                # Update the keys that list the file names.
                op_db['set'][fragkey + ('files', fname)] = None
                op_db['inc'] = {('version', ): 1}
        else:
            # Impossible to reach because the JSON schema validated the
            # possible options already. However, just to be sure, let's handle
            # the case anyway.
            msg = 'Invalid update operation type <{}>'.format(fragop['op'])
            self.logit.critical()
            return False

        # Tell the caller that the operation is valid.
        return True

    @typecheck
    def setFragments(self, fragupdates: dict):
        """
        Modify the ``fragupdates`` and return the success status for each.

        The ``fragupdates`` dictionary specifies operations. For
        instance, assume we want to modify the three fragments 'foo_frag',
        'bar_frag', and 'foobar_frag' in the following way:

        * 'foo_frag': modify (op='mod') the scale to 5, and add/replace the
          geometry file 'myfile.txt' with the content b'aaa'.
        * 'bar_frag': replace (op='put') completely. Operation *must* specify
           scale, position, rotation, and fragtype
        * 'foobar_frag': delete (op='del').

        The update command for this would be::

            fragupdates = {
                'foo_obj': {
                    'foo_frag': {
                        'op': 'mod',
                        'scale': 5,
                        'put': {'myfile.txt': b'aaa'},
                    },
                    'bar_frag': {
                        'op': 'put',
                        'scale': 2,
                        'position': [1, 2, 3],
                        'rotation': [1, 0, 0, 1],
                        'fragtype': 'CUSTOM',
                        'put': {'myfile.txt': b'aaa'},
                    },
                    'foobar_frag': {
                        'op': 'del',
                    }
                }
            }

        :param dict fragupdates: update operations.
        :return: dict[aid]: bool to state which ones were successfully updated.
        """
        db = datastore.dbHandles['ObjInstances']

        # Compile the data store ops for all objects (no actual data store
        # querie take place in this loop.
        ops_db, ops_file = {}, {}
        for objID, frags in fragupdates.items():
            # The following variables are work lists for the database (op_db)
            # and Dibbler (op_file). The keys in op_db mean:
            #    set: overwrite these DB keys with the new values
            #    unset: delete these DB keys
            #    exists: this key must exist for the update to go ahead
            #
            # The keys in op_file mean:
            #    put: files to add/overwrite in Dibbler (and their content).
            #    del: files to delete in Dibbler.
            #    rmdir: directories to delete in Dibbler.
            op_db = {
                'inc': {},
                'set': {},
                'unset': [],
                'exists': {},
            }
            op_file = {
                'put': {},
                'del': [],
                'rmdir': []
            }

            # Path prefix for all the files that Dibbler has on this object.
            pre = '{dst}/{aid}'.format(dst=config.url_instances, aid=objID)

            # Compile the query to update the instance data.
            for fragname, fragop in frags.items():
                # Check input data against schema.
                try:
                    jsonschema.validate(fragop, azschemas.setFragments)
                except jsonschema.exceptions.ValidationError:
                    msg = 'Invalid input data for AID {} and fragment {}'
                    msg = msg.format(objID, fragname)
                    self.logit.warning(msg)
                    return RetVal(False, msg, None)

                # Define the prefix key in the JSON hierarchy for current fragment, and
                # the file name prefix in Dibbler.
                fragkey = ('template', 'fragments', fragname)
                url = '{pre}/{fragname}'.format(pre=pre, fragname=fragname)

                # Determine the necessary database operations (will update the
                # 'op_db' and 'op_file' dictionaries).
                sfo = self._setFragOps
                if not sfo(objID, fragkey, url, fragop, op_db, op_file):
                    return RetVal(False, 'Invalid operation', None)
                del fragkey, url

            # Add the ops for the data store and Igor.
            ops_db[objID] = op_db
            ops_file[objID] = op_file
            del op_db, op_file, pre
        del objID, frags

        # -----------------------------------------------------------------
        # Apply the updates.
        # -----------------------------------------------------------------
        ret = db.modify(ops_db)
        if not ret.ok:
            return ret

        # Determine the AIDs for which the update succeeded.
        updated = ret.data
        valid = [k for k, v in updated.items() if v is True]

        # Issue the Dibbler update for each object that could be successfully
        # updated in the data store.
        for aid in valid:
            op_file = ops_file[aid]
            self.dibbler.removeDirs(op_file['rmdir'])
            self.dibbler.remove(op_file['del'])
            self.dibbler.put(op_file['put'])

        # Return update status for each object.
        return RetVal(True, None, {'updated': updated})

    @typecheck
    def getRigidBodies(self, objIDs: (list, tuple)):
        """
        Return the rigid body data for all ``objIDs`` in a dictionary.

        If ``objIDs`` is *None* then all bodies will be returned.

        The dictionary are ``objIDs`` and the values the associated
        ``RigidBodyData`` data (or *None* if the objID did not exist).

        Return value example::

            ret = {
                id_1: {'rbs': RigidBodyData(...)},
                id_2: {'rbs': RigidBodyData(...)},
            }

        ..note:: The inner 'rbs' dictionary is currently redundant since it
            contains only a single hard coded key. However, this will make it
            easy to pass along other values in the future, should the need
            arise.

        :param list[int] objIDs: list of objects to query.
        :return: see example above
        :rtype: dict
        """
        # Fetch the specified objects, or fetch all if none were specified.
        db = datastore.dbHandles['ObjInstances']
        prj = [['version'], ['objID'], ['template', 'rbs']]
        if objIDs is None:
            ret = db.getAll(prj)
        else:
            ret = db.getMulti(objIDs, prj)
        if not ret.ok:
            return ret

        # Compile a dictionary containing the fragment- and body states.
        out = {}
        RBS = aztypes._RigidBodyData
        for aid, doc in ret.data.items():
            if doc is None:
                # The requested object does not exist.
                out[aid] = None
            else:
                # Compile the rigid body data and overwrite the version tag
                # with the one stored in the database.
                rbs = RBS(**doc['template']['rbs'])
                out[aid] = {'rbs': rbs._replace(version=doc['version'])}
        return RetVal(True, None, out)

    @typecheck
    def setRigidBodies(self, bodies: dict):
        """
        Set the rigid body state of ``objID`` to ``body``.

        This method supports partial updates of rigid body data. To skip an
        attribute simply set it to *None* in the `_RigidBodyData` structure.

        This method always succeeds. However, the 'data' field in the return
        value contains a list of all object IDs that could not be updated for
        whatever reason.

        This this method will publish an object modification announcment for
        all those objects that could be updated in the database.

        :param dict[objID: RigidBodyData] bodies: new object attributes.
        :return: Success
        """
        # Get handle to datastore.
        db = datastore.dbHandles['ObjInstances']

        # Compile the data store ops to modify all the objects.
        ops = {}
        for objID, body in bodies.items():
            # Backup the attribute names the user wants us to modify.
            modify_keys = set(body.keys())

            # Compile- and sanity check ``body``. This will return a complete
            # RigidBody object with defaults for all the values the user did
            # not specify. We will remove these default values later.
            try:
                body = aztypes.DefaultRigidBody(**body)._asdict()
            except TypeError:
                return RetVal(False, 'Invalid body data', None)

            # Remove the default values and retain only those the user wants to
            # explicitly update.
            body = {k: v for (k, v) in body.items() if k in modify_keys}

            # Update the respective entries in the database. The keys already have
            # the correct names but require the 'template.rbs' prefix to match the
            # position in the document hierarchy.
            ops[objID] = {
                'inc': {},
                'set': {('template', 'rbs',  k): v for (k, v) in body.items()},
                'unset': [],
                'exists': {},
            }

        # Update all the objects.
        ret = db.modify(ops)
        if not ret.ok:
            return ret

        # Announce the modification for each object that was successfully
        # updated. Furthermore, compile a list of all objects that could not be
        # updated for whatever reason.
        invalid_objects = []
        for aid, valid in ret.data.items():
            if valid:
                # Notify Leonard.
                leoAPI.addCmdModifyBodyState(objID, body)
            else:
                invalid_objects.append(aid)
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
        information about an object in a (more) bandwidth efficient way.::

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
        # Get handle to datastore.
        db = datastore.dbHandles['ObjInstances']
        
        # Projection operator to reduce the amount of network traffic.
        prj = [
            ('version', ),
            ('objID', ),
            ('template', 'fragments'),
            ('template', 'rbs', 'scale'),
            ('template', 'rbs', 'position'),
            ('template', 'rbs', 'rotation'),
            ('template', 'rbs', 'velocityLin'),
            ('template', 'rbs', 'velocityRot'),
        ]

        # Fetch the specified `objIDs`. Fetch all if `objIDs` is None.
        if objIDs is None:
            ret = db.getAll(prj)
        else:
            ret = db.getMulti(objIDs, prj)
        if not ret.ok:
            return ret

        # Compile the data from the database into a simple dictionary that
        # contains the fragment- and body state.
        out = {}
        docs = ret.data
        for aid, doc in docs.items():
            # The returned state is None for all non-existing objects.
            if doc is None:
                out[aid] = None
                continue

            # Convenience: fragments of current object.
            frags = doc['template']['fragments']

            # Compile the state for each fragment of the current object.
            fs = {k: {'scale': v['scale'],
                      'position': v['position'],
                      'rotation': v['rotation']}
                  for (k, v) in frags.items()}

            # Add the current version to the rigid body data.
            rbs = doc['template']['rbs']
            rbs['version'] = doc['version']

            # Construct the return value.
            out[aid] = {'frag': fs, 'rbs': rbs}
        return RetVal(True, None, out)

    @typecheck
    def getTemplateID(self, objID: str):
        """
        Return the template ID from which ``objID`` was created.

        :param str objID: object ID.
        :return: templateID from which ``objID`` was created.
        """
        # Get handle to datastore and query for the specified ``objID``.
        db = datastore.dbHandles['ObjInstances']
        ret = db.getOne(objID)

        # Return the template (or an error).
        if ret.ok and ret.data is not None:
            return RetVal(True, None, ret.data['templateID'])
        else:
            msg = 'Could not find template for objID {}'.format(objID)
            return RetVal(False, msg, None)

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
        return datastore.dbHandles['ObjInstances'].allKeys()

    @typecheck
    def setForce(self, objID: str, force: (tuple, list), rpos: (tuple, list)):
        """
        Apply ``force`` to ``objID`` at position ``rpos``.

        The ``force`` applies at ``rpos`` relative to the center of mass.

        If ``objID`` does not exist return an error.

        :param str objID: object ID
        :param vec3 forceID: force vector
        :param vec3 rpos: force position relative to object's center of mass.
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
        # Get handle to datastore.
        db = datastore.dbHandles['ObjInstances']

        # Will hold the database operations and AIDs of objects that could not
        # be updatd.
        ops = {}
        invalid_objects = []

        # Compile the data store operations to update the 'custom' field of the
        # specified objects.
        for objID, value in data.items():
            if isinstance(value, str) and (len(value) < 2 ** 16):
                ops[objID] = {
                    'inc': {},
                    'set': {('template', 'custom'): value},
                    'unset': [],
                    'exists': {('template', 'custom'): True},
                }
            else:
                # Either the AID is invalid or the custom data is too big.
                invalid_objects.append(objID)

        # Run the query and determine which objects were not updated.
        ret = db.modify(ops)
        not_updated = [k for k, v in ret.data.items() if v is False]

        # Return the list of objects that could not be updated.
        return RetVal(True, None, invalid_objects + not_updated)

    @typecheck
    def getCustomData(self, objIDs: (tuple, list)):
        """
        Return the `custom` data for all ``objIDs`` in a dictionary.

        The return value looks like this:: {1: 'foo', 25: 'bar'}

        The returned dictionary will only contain keys for objects that were
        actually found.

        :param dict[int: str] data: new content for 'custom' field in object.
        :return: dictionary of 'custom' data.
        """
        # Get handle to datastore.
        db = datastore.dbHandles['ObjInstances']

        # Fetch the specified objects. Fetch all if `objID` is None.
        prj = [('template', 'custom')]
        if objIDs is None:
            ret = db.getAll(prj)
        else:
            ret = db.getMulti(objIDs, prj)
        if not ret.ok:
            return ret

        # Compile the return dictionary with the custom data.
        out = {k: v['template']['custom'] if v is not None else None
               for k, v in ret.data.items()}
        return RetVal(True, None, out)
