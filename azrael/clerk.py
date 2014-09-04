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
import cytoolz
import logging
import pymongo
import setproctitle
import multiprocessing

import numpy as np

import azrael.util as util
import azrael.parts as parts
import azrael.config as config
import azrael.protocol as protocol
import azrael.bullet.btInterface as btInterface
import azrael.bullet.bullet_data as bullet_data

from azrael.typecheck import typecheck


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

    :param bool reset: flush the database.
    :raises: None
    """
    @typecheck
    def __init__(self, reset: bool):
        super().__init__()

        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

        # Specify all database collections for Azrael.
        client = pymongo.MongoClient()
        self.db_msg = client['azrael']['msg']
        self.db_admin = client['azrael']['admin']
        self.db_templateID = client['azrael']['templateID']

        if reset:
            # Flush the database.
            client.drop_database('azrael')

            # Reset the object counter. This counter will guarantee unique
            # object IDs.
            self.db_admin.insert({'name': 'objcnt', 'cnt': 0})

        # Specify the decoding-processing-encoding triplet functions for
        # (almost) every command supported by Clerk. The only exceptions are
        # administrative commands (eg. ping). This dictionary will be used
        # in the digest loop.
        self.codec = {
            config.cmd['send_msg']: (
                protocol.ToClerk_SendMsg_Decode,
                self.sendMessage,
                protocol.FromClerk_SendMsg_Encode),
            config.cmd['recv_msg']: (
                protocol.ToClerk_RecvMsg_Decode,
                self.recvMessage,
                protocol.FromClerk_RecvMsg_Encode),
            config.cmd['spawn']: (
                protocol.ToClerk_Spawn_Decode,
                self.spawn,
                protocol.FromClerk_Spawn_Encode),
            config.cmd['get_statevar']: (
                protocol.ToClerk_GetStateVariable_Decode,
                self.getStateVariables,
                protocol.FromClerk_GetStateVariable_Encode),
            config.cmd['get_geometry']: (
                protocol.ToClerk_GetGeometry_Decode,
                self.getGeometry,
                protocol.FromClerk_GetGeometry_Encode),
            config.cmd['set_force']: (
                protocol.ToClerk_SetForce_Decode,
                self.setForce,
                protocol.FromClerk_SetForce_Encode),
            config.cmd['suggest_pos']: (
                protocol.ToClerk_SuggestPosition_Decode,
                self.suggestPosition,
                protocol.FromClerk_SuggestPosition_Encode),
            config.cmd['get_template']: (
                protocol.ToClerk_GetTemplate_Decode,
                self.getTemplate,
                protocol.FromClerk_GetTemplate_Encode),
            config.cmd['get_template_id']: (
                protocol.ToClerk_GetTemplateID_Decode,
                self.getTemplateID,
                protocol.FromClerk_GetTemplateID_Encode),
            config.cmd['add_template']: (
                protocol.ToClerk_AddTemplate_Decode,
                self.addTemplate,
                protocol.FromClerk_AddTemplate_Encode),
            config.cmd['get_all_objids']: (
                protocol.ToClerk_GetAllObjectIDs_Decode,
                self.getAllObjectIDs,
                protocol.FromClerk_GetAllObjectIDs_Encode),
            config.cmd['control_parts']: (
                protocol.ToClerk_ControlParts_Decode,
                self.controlParts,
                protocol.FromClerk_ControlParts_Encode),
            }

        # Insert default objects. None of them has an actual geometry but
        # their collision shapes are: none, sphere, cube.
        self.addTemplate('_templateNone'.encode('utf8'),
                         np.array([0, 1, 1, 1], np.float64),
                         np.array([]), [], [])
        self.addTemplate('_templateSphere'.encode('utf8'),
                         np.array([3, 1, 1, 1], np.float64),
                         np.array([]), [], [])
        self.addTemplate('_templateCube'.encode('utf8'),
                         np.array([4, 1, 1, 1], np.float64),
                         np.array([]), [], [])

        # Initialise the SV database.
        btInterface.initSVDB(reset)

        # A dictionary of all controllers launched by this Clerk. The object ID
        # is the dictionary key and the Unise PID the value.
        self.processes = {}

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
            # Decoding was successfull. Pass all returned parameters directly
            # to the processing method.
            ok, out = fun_process(*out)

            if ok:
                # Encode the out into a byte stream and return it.
                ok, out = fun_encode(*out)
                self.returnOk(self.last_addr, out)
            else:
                # The processing method encountered an error.
                self.returnErr(self.last_addr, out)

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
        ctx = zmq.Context()
        self.sock_cmd = ctx.socket(zmq.ROUTER)
        self.sock_cmd.bind(config.addr_clerk)
        poller = zmq.Poller()
        poller.register(self.sock_cmd, zmq.POLLIN)

        # Wait for socket activity.
        while True:
            sock = dict(poller.poll())
            if not self.sock_cmd in sock:
                continue

            # Read from ROUTER socket and perform sanity checks.
            msg = self.sock_cmd.recv_multipart()
            assert len(msg) == 3
            self.last_addr, empty, msg = msg[0], msg[1], msg[2]
            assert empty == b''

            # Sanity check: every message must contain at least a command byte.
            if len(msg) == 0:
                self.returnErr(self.last_addr, 'Did not receive command word.')
                return

            # Split message into command word and payload.
            cmd, self.payload = msg[:1], msg[1:]

            # Determine the command.
            if cmd == config.cmd['ping_clerk']:
                # Return a hard coded 'pong' message.
                self.returnOk(self.last_addr, 'pong clerk'.encode('utf8'))
            elif cmd == config.cmd['get_id']:
                # Return a new and unique Controller ID to client.
                new_id = util.int2id(self.getUniqueID())
                self.returnOk(self.last_addr, new_id)
            elif cmd in self.codec:
                # Look up the decode-process-encode functions for the current
                # command and execute them.
                enc, proc, dec = self.codec[cmd]
                self.runCommand(enc, proc, dec)
            else:
                # Unknown command.
                self.returnErr(self.last_addr, 'Invalid Command')

    @typecheck
    def getControllerClass(self, ctrl_name: bytes):
        """
        Return the full path name of the Python script for ``ctrl_name``.

        Return **None** if no Python script corresponds to ``ctrl_name``.

        .. note::
           This function is currently only a proof-of-concept to automatically
           launch controller processes. As such it makes certain assumptions
           (eg. location of controller scripts).

        :param str ctrl_name: Controller name (eg. 'Echo').
        :return: Name (with full path) to Python script.
        :rtype: str
        :raises: None
        """

        # Build the path to the Controller scripts (hard coded for now).
        this_dir = os.path.dirname(os.path.abspath(__file__))
        p = os.path.join(this_dir, '..', 'controllers')

        # Pick the correct script.
        if ctrl_name == 'Echo'.encode('utf8'):
            return os.path.join(p, 'controller_cube.py')
        elif ctrl_name == 'EchoBoost'.encode('utf8'):
            return os.path.join(p, 'controller_cube_with_booster.py')
        else:
            return None

    def getUniqueID(self):
        """
        Return unique object ID.

        All returned IDs are guarenteed unique within all of Azrael.

        :returns: a unique object ID
        :rtype: int
        :raises: None
        """
        # Atomically increment the object counter to obtain a unique ID.
        new_id = self.db_admin.find_and_modify(
            {'name': 'objcnt'}, {'$inc': {'cnt': 1}}, new=True)

        if new_id is None:
            # This must not happen. If it does then the DB is corrupt.
            self.logit.critical('Could not fetch counter - this is a bug!')
            sys.exit(1)

        # Return the ID.
        return new_id['cnt']

    @typecheck
    def returnOk(self, addr, data: (bytes, str)=b''):
        """
        Send positive reply.

        This is a convenience method to enhance readability.

        :param addr: ZeroMQ address as returned by the router socket.
        :param bytes data: arbitrary data that should be passed back as well.
        :return: None
        """
        # Convert the data to a byte string if necessary.
        if isinstance(data, str):
            data = data.encode('utf8')

        # The first \x00 bytes tells the receiver that everything is ok.
        self.sock_cmd.send_multipart([addr, b'', b'\x00' + data])

    def returnErr(self, addr, msg: (bytes, str)=b''):
        """
        Send negative reply and log a warning message.

        This is a convenience method to enhance readability.

        :param addr: ZeroMQ address as returned by the router socket.
        :param bytes msg: message to pass along.
        :return: None
        """
        # Convert the message to a byte string if it is not already.
        if isinstance(msg, str):
            msg = msg.encode('utf8')

        # For record keeping.
        self.logit.warning(msg)

        # The first \x01 bytes tells the receiver that something went wrong.
        self.sock_cmd.send_multipart([addr, b'', b'\x01' + msg])

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
        :return: (ok, (cs, geo, boosters, factories))
        :rtype: (True, tuple) or (False, str)
        :raises: None
        """
        # Retrieve the template. Return immediately if it does not exist.
        doc = self.db_templateID.find_one({'templateID': templateID})
        if doc is None:
            msg = 'Invalid template ID <{}>'.format(templateID)
            self.logit.info(msg)
            return False, msg

        # Extract the collision shape and object geometry.
        cs, geo = np.fromstring(doc['cshape']), np.fromstring(doc['geometry'])

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

        return True, (cs, geo, boosters, fac)

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
        :return: (True, (b'',)) or (False, error-message)
        :rtype: (bool, (bytes, )) or (bool, str)
        :raises: None
        """

        # Query the templateID for the current object.
        ok, templateID = btInterface.getTemplateID(objID)
        if not ok:
            msg = 'Could not retrieve templateID for objID={}'.format(objID)
            self.logit.warning(msg)
            return False, msg

        # Fetch the template for the current object.
        ok, data = self.getTemplate(templateID)
        if not ok:
            msg = 'Could not retrieve template for objID={}'.format(objID)
            self.logit.warning(msg)
            return False, msg
        else:
            cshape, geo, boosters, factories = data

        # Fetch the SV for objID.
        ok, svdata = self.getStateVariables([objID])
        if not ok:
            msg = 'Could not retrieve SV for objID={}'.format(objID)
            self.logit.warning(msg)
            return False, msg

        # Extract the parent's orientation from svdata.
        sv_parent = svdata[1][0]
        parent_orient = sv_parent.orientation
        quat = util.Quaternion(parent_orient[3], parent_orient[:3])
        del svdata

        # Compile a list of all parts defined in the template.
        booster_t = dict(zip([int(_.partID) for _ in boosters], boosters))
        factory_t = dict(zip([int(_.partID) for _ in factories], factories))

        # Verify that all Booster commands have the correct type and are
        # directed to an existing Booster ID.
        for cmd in cmd_boosters:
            if not isinstance(cmd, parts.CmdBooster):
                msg = 'Invalid Booster type'
                self.logit.warning(msg)
                return False, msg
            if cmd.partID not in booster_t:
                msg = 'Template <{}> has no Booster ID <{}>'
                msg = msg.format(templateID, cmd.partID)
                self.logit.warning(msg)
                return False, msg

        # Verify that all Factory commands have the correct type and are
        # directed to an existing Factory ID.
        for cmd in cmd_factories:
            if not isinstance(cmd, parts.CmdFactory):
                msg = 'Invalid Factory type'
                self.logit.warning(msg)
                return False, msg
            if cmd.partID not in factory_t:
                msg = 'Template <{}> has no Factory ID <{}>'
                msg = msg.format(templateID, cmd.partID)
                self.logit.warning(msg)
                return False, msg

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
            btInterface.setForceAndTorque(objID, tot_central_force, tot_torque)

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
            ok, (objID, ) = self.spawn(None, this.templateID, sv)
            if ok:
                objIDs.append(objID)

        # Success. Return the IDs of all spawned objects.
        return True, (objIDs, )

    @typecheck
    def addTemplate(self, templateID: bytes, cshape: np.ndarray,
                    geometry: np.ndarray, boosters: (list, tuple),
                    factories: (list, tuple)):
        """
        Add a new ``templateID`` to the system.

        Henceforth it is possible to ``spawn`` ``templateID`` objects.

        Return an error if a template with name ``templateID`` already exists.

        :param bytes templateID: the name of the new template.
        :param bytes cshape: collision shape
        :param bytes geometry: object geometry
        :param parts.Booster boosters: list of Booster instances.
        :param parts.Factory boosters: list of Factory instances.
        :return: (ok, template ID)
        :rtype: (bool, bytes)
        :raises: None
        """
        # Compile the Mongo document for the new template. This document
        # contains the collision shape and geometry...
        data = {'templateID': templateID,
                'cshape': cshape.tostring(), 'geometry': geometry.tostring()}

        # ... as well as booster- and factory parts.
        for b in boosters:
            data['boosters.{0:03d}'.format(b.partID)] = b.tostring()
        for f in factories:
            data['factories.{0:03d}'.format(f.partID)] = f.tostring()

        # Insert the document only if it does not exist already. The return
        # value contains the old document, ie. **None** if the document
        # did not yet exist.
        ret = self.db_templateID.find_and_modify(
            {'templateID': templateID}, {'$setOnInsert': data}, upsert=True)

        if ret is None:
            # No template with name ``templateID`` existed --> success.
            return True, (templateID, )
        else:
            # A template with name ``templateID`` already existed --> failure.
            msg = 'Template ID <{}> already exists'.format(templateID)
            return False, msg

    @typecheck
    def sendMessage(self, src: bytes, dst: bytes, data: bytes):
        """
        Queue a new message with content ``data`` for ``dst`` from ``src``.

        :param bytes src: object ID of sender.
        :param bytes dst: object ID of receiver.
        :param bytes data: message to pass along.
        :return: Always (**True**, ())
        :rtype: (bool, tuple)
        """
        # Add the message to the DB.
        doc = {'src': src, 'dst': dst, 'msg': data}
        self.db_msg.insert(doc)
        return True, tuple()

    @typecheck
    def recvMessage(self, objID: bytes):
        """
        Return the next message for ``objID``.

        If no message is available for ``objID`` then return an empty message.

        :param bytes objID: object ID.
        :return: (ok, (src, message))
        :rtype: (bool, (bytes, bytes))
        """
        # Fetch/remove the next available message for ``objID``.
        doc = self.db_msg.find_and_modify({'dst': objID}, remove=True)

        if doc is None:
            # No message was available.
            return True, (b'', b'')
        else:
            # Return the message- origin and content.
            return True, (doc['src'], doc['msg'])

    @typecheck
    def spawn(self, ctrl_name: bytes, templateID: bytes,
              sv: bullet_data.BulletData):
        """
        Spawn a new object based on ``templateID``.

        Automatically launch a new ``ctrl_name`` process.

        The new object will get ``sv`` as the initial state vector albeit the
        collision shape will be overwritten with that specified in the
        template.

        :param bytes src: object ID of sender.
        :param bytes dst: object ID of receiver.
        :param bytes data: message to pass along.
        :return: (ok, (object ID, ))
        :rtype: (bool, (bytes, ))
        """
        # Retrieve the template.
        ok, data = self.getTemplate(templateID)
        if not ok:
            return False, 'Invalid Template ID'
        else:
            cshape, geo, boosters, factories = data

        # Overwrite the supplied collision shape with the template
        # version. This will the other quantities, most notably position and
        # speed intact. However, this all rather hackey at the moment.
        sv.cshape[:] = np.fromstring(cshape)

        # Determine the full path to the Controller script. Return with an
        # error if no matching script was found.
        if ctrl_name is not None:
            prog = self.getControllerClass(ctrl_name)
            if prog is None:
                return False, 'Unknown Controller Name'
        else:
            # No dedicated Controller process was requested. Do nothing.
            prog = None

        # Request unique object ID.
        new_id = util.int2id(self.getUniqueID())

        if prog is not None:
            # Start the Python Controller.
            self.processes[new_id] = PythonInstance(prog, new_id)
            self.processes[new_id].start()

        # Add the object to the physics simulation.
        btInterface.spawn(new_id, sv, templateID)
        return True, (new_id, )

    @typecheck
    def getStateVariables(self, objIDs: (list, tuple)):
        """
        Return the current state variables for all ``objIDs``.

        :param bytes src: object ID of sender.
        :param bytes dst: object ID of receiver.
        :param bytes data: message to pass along.
        :return: (ok, (object ID, SV))
        :rtype: (bool, (bytes, ))
        """
        # Get the State Variables.
        ok, sv = btInterface.getStateVariables(objIDs)
        if not ok:
            return False, 'One or more IDs do not exist'
        else:
            return True, (objIDs, sv)

    @typecheck
    def getGeometry(self, templateID: bytes):
        """
        Return the geometry for the template ``templateID``.

        If the ID does not exist return an error.

        .. note::
           It is possible that an object has no geometry. An empty array will
           be returned in that case.

        :param bytes templateID: template ID
        :return: (ok, (object ID, ))
        :rtype: (bool, (bytes, np.ndarray))
        """
        # Retrieve the geometry. Return an error if the ID does not
        # exist. Note: an empty geometry field is valid.
        doc = self.db_templateID.find_one({'templateID': templateID})
        if doc is None:
            return False, 'ID does not exist'
        else:
            geo = np.fromstring(doc['geometry'], np.float64)
            return True, (geo,)

    @typecheck
    def setForce(self, objID: bytes, force: np.ndarray, rpos: np.ndarray):
        """
        Apply ``force`` to ``objID``.

        The force will be applied at ``rpos`` relative to the center of mass.

        If the ID does not exist return an error.

        :param bytes templateID: template ID
        :return: (ok, (b'', ))
        :rtype: (bool, (bytes, ))
        """
        ok = btInterface.setForce(objID, force, rpos)
        if ok:
            return True, ('', )
        else:
            return False, 'ID does not exist'

    @typecheck
    def suggestPosition(self, objID: bytes, position: np.ndarray):
        """
        Suggest ``position`` for ``objID``.

        This is purely a suggestion that the physics engine may ignore. This is
        for debugging purposes only.

        :param bytes objID: object ID
        :param ndarray position: suggested position
        :return: (ok, (b'', ))
        :rtype: (bool, (bytes, ))
        """
        ok = btInterface.setSuggestedPosition(objID, position)
        if ok:
            return True, ('', )
        else:
            return False, 'ID does not exist'

    @typecheck
    def getTemplateID(self, objID: bytes):
        """
        Return the template ID from which ``objID`` was created.

        :param bytes objID: object ID
        :return: (ok, (templateID, ))
        :rtype: (bool, (bytes, ))
        """
        ok, templateID = btInterface.getTemplateID(objID)
        if ok:
            return True, (templateID, )
        else:
            return False, 'Could not find templateID <{}>'.format(templateID)

    @typecheck
    def getAllObjectIDs(self, dummy=None):
        """
        Return all ``objIDs`` in the simulation.

        .. note::
           The ``dummy`` argument is a placeholder because the ``runCommand``
           function assumes that every method takes at least one argument.

        :param bytes dummy: irrelevant
        :return: (ok, (list of objIDs, ))
        :rtype: (bool, (list(bytes), ))
        """
        ok, data = btInterface.getAllObjectIDs()
        if not ok:
            return False, data
        else:
            return True, (data, )
