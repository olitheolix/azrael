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

import os
import sys
import time
import random
import cytoolz
import logging
import pymongo
import setproctitle
import multiprocessing
import zmq.eventloop.zmqstream
import numpy as np

import azrael.json as json
import azrael.util as util
import azrael.types as types
import azrael.unpack as unpack
import azrael.protocol as protocol
import azrael.config as config
import azrael.commands as commands
import azrael.bullet.btInterface as btInterface

from azrael.typecheck import typecheck


class PythonInstance(multiprocessing.Process):
    """
    Replace existing process with pristine Python interpreter.

    This is a convenience wrapper to starts a new Python script that runs
    independently of the Azrael. The procedure is as follows: Azrael will fork
    itself when it triggers the 'start' method of this class instance. This
    will duplicate all of Azrael including sockets etc which I would rather
    avoid. Therefore, do not merely import the Python script but replace this
    forked instance with a new Python interpreter that calls the script.

    The called script will receive the object id as a command line argument.
    """
    def __init__(self, name, obj_id):
        super().__init__()

        # Keep the variables around for after the fork.
        self.script_name = name
        self.obj_id = obj_id

    def run(self):
        # Convert objectID -> integer -> string so that it can be passed as a
        # command line argument.
        obj_id = '{}'.format(util.id2int(self.obj_id))

        # Replace the current process with a new Python process. The first
        # argument is the program to call, the following arguments are the
        # command line arguments. The first of these is 'python3' once more
        # because the program name (ie. python3 in this case) is also the first
        # argument Bash would pass to any new program and we need to emulate
        # the Bash here if we want 'os.argv' to behave as usual).
        import os
        os.execlp('python3', 'python3', self.script_name, obj_id)


class Clerk(multiprocessing.Process):
    """
    Administrate all requests coming from the various clients.

    There can only be one instance of Clerk because it binds 0MQ sockets, which
    is also the only way to contact Clerk.

    Philosophy of Clerk:
     * Unpack and inspect all data to ensure it is sane.
     * Speed is irrelevant for now; Clerk will become asynchronous later.
     * Ensure that all physics related data is in compact and read-to-use
       format to avoid overhead.

    All messages are binary Byte strings and language agnostic to ensure
    clients can be written in any language with ZeroMQ bindings (which is
    pretty much every language).
    """
    def __init__(self, reset):
        super().__init__()

        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

        # Create all database collections that Azrael will need.
        client = pymongo.MongoClient()
        self.db_msg = client['azrael']['msg']
        self.db_admin = client['azrael']['admin']
        self.db_templateID = client['azrael']['templateID']

        # Drop all collections if requested.
        if reset:
            client.drop_database('azrael')
            self.db_templateID.insert({'name': 'objcnt', 'cnt': 0})

            # Reset the object counter. We will use atomic increments to
            # guarantee unique object IDs.
            self.db_admin.insert({'name': 'objcnt', 'cnt': 0})

        # Insert default objects. None of them has an actual geometry but
        # their collision shapes are: none, sphere, cube.
        self.addTemplate(
            np.array([0, 1, 1, 1], np.float64), np.array([]), [], [])
        self.addTemplate(
            np.array([3, 1, 1, 1], np.float64), np.array([]), [], [])
        self.addTemplate(
            np.array([4, 1, 1, 1], np.float64), np.array([]), [], [])

        # Initialise the SV related collections.
        btInterface.initSVDB(reset)

        # Dictionary of all controllers this Clerk is aware of. The object ID
        # serves as the dictionary key whereas the the process ID is the value.
        self.processes = {}

    def run(self):
        """
        Digest loop.
        """
        # Rename the process to ensure they are easy to find and kill by
        # external scripts.
        setproctitle.setproctitle('killme Clerk')

        # Setup 0MQ sockets.
        ctx = zmq.Context()
        self.sock_cmd = ctx.socket(zmq.ROUTER)
        self.sock_cmd.bind(config.addr_clerk)
        poller = zmq.Poller()
        poller.register(self.sock_cmd, zmq.POLLIN)

        # Wait for socket activity.
        while True:
            sock = dict(poller.poll())
            if self.sock_cmd in sock:
                self.processCmd()

    def processControlCommand(self, cmds):
        objID, cmd_boosters, cmd_factories = commands.deserialiseCommands(cmds)
        if objID is None:
            return False, 'Problem'

        # Query the templateID for objID.
        ok, templateID = btInterface.getTemplateID(objID)
        if not ok:
            return False, msg

        # Query the object capabilities.
        ok, data = self.getTemplate(templateID)
        if not ok:
            return False, 'Problem'
        else:
            cshape, geo, boosters, factories = data

        # Extract all booster- and factory IDs.
        bid = dict(zip([int(_.bid) for _ in boosters], boosters))
        fid = dict(zip([int(_.fid) for _ in factories], factories))
        
        # Verify that all boosters- and factories addressed in the commands
        # actually exist.
        tot_torque = np.zeros(3, np.float64)
        tot_central_force = np.zeros(3, np.float64)
        for cmd in cmd_boosters:
            if int(cmd.unitID) not in bid:
                return False, 'Invalid booster ID'
            
            # Rotate the unit force vector into the orientation given by the
            # Quaternion.
            f = bid[int(cmd.unitID)].orient * cmd.force_mag
    
            # Accumulate torque and central force.
            pos = bid[int(cmd.unitID)].pos
            tot_torque += np.cross(pos, f)
            tot_central_force += f

        # Set the resulting force.
        btInterface.setForceAndTorque(objID, tot_central_force, tot_torque)

        for cmd in cmd_factories:
            if int(cmd.unitID) not in fid:
                return False, 'Invalid factory ID'

        return True, ''
        
    @typecheck
    def getControllerClass(self, ctrl_name: str):
        """
        Stub.

        Return the location of the Python script associated with
        ``ctrl_name``.
        """
        this_dir = os.path.dirname(os.path.abspath(__file__))
        p = os.path.join(this_dir, '..', 'controllers')
        if ctrl_name == 'Echo':
            return os.path.join(p, 'controller_cube.py')
        elif ctrl_name == 'EchoBoost':
            return os.path.join(p, 'controller_cube_with_booster.py')
        else:
            return None

    @typecheck
    def getTemplate(self, templateID: bytes):
        """
        Return the constituents of the template object.

        The return values are (cs, geo, boosters, factories).

        A template object has the following document structure:
        {'_id': ObjectId('53eeb55062d05244dfec278f'),
        'boosters': {'000': b'', '001': b'', ..},
        'factories': {'000':b'', ...},
        'cshape': b'',
        'templateID': b'',
        'geometry': b''}

        :param bytes templateID: templateID
        :return: (cs, geo, boosters, factories)
        :rtype: tuple
        :raises: None
        """
        # Retrieve the object template and return immediately if it does not
        # exist.
        doc = self.db_templateID.find_one({'templateID': templateID})
        if doc is None:
            self.logit.info('Invalid template ID')
            return False, 'Invalid template ID'

        # Extract the collision shape and object geometry.
        cs, geo = np.fromstring(doc['cshape']), np.fromstring(doc['geometry'])

        # Extract all boosters if the object has any.
        if 'boosters' in doc:
            b = doc['boosters'].values()
            boosters = [types.booster_fromstring(_) for _ in b]
        else:
            boosters = []

        # Extract all factories if the object has any.
        if 'factories' in doc:
            f = doc['factories'].values()
            factories = [types.factory_fromstring(_) for _ in f]
        else:
            factories = []

        return True, (cs, geo, boosters, factories)
        
    @typecheck
    def addTemplate(self, cshape: np.ndarray, geometry: np.ndarray,
                    boosters: (list, tuple), factories: (list, tuple)):
        """
        Add a new object to the 'templateID' DB and return its template ID.

        Azrael can only spawn objects from templates that have been registered
        with this function.

        fixme: this method must go into the database module.
        fixme: some parameters are missing

        :param bytes cshape: collision shape
        :param bytes geometry: object geometry (fixme: what data type? float64?)
        :return: template ID
        :rtype: bytes
        :raises: None
        """
        # Create a new and unique ID for the next template object.
        new_id = self.db_templateID.find_and_modify(
            {'name': 'objcnt'}, {'$inc': {'cnt': 1}}, new=True)
        new_id = new_id['cnt']

        # Convert the integer to NumPy int64.
        templateID = np.int64(new_id).tostring()

        # Compile the Mongo document. It includes the collision shape,
        # geometry, boosters- and factory units.
        data = {'templateID': templateID,
                'cshape': cshape.tostring(), 'geometry': geometry.tostring()}
        for b in boosters:
            data['boosters.{0:03d}'.format(b.bid)] = types.booster_tostring(b)
        for f in factories:
            data['factories.{0:03d}'.format(f.fid)] = types.factory_tostring(f)

        # Insert the document.
        self.db_templateID.update({'templateID': templateID},
                               {'$set': data}, upsert=True)

        # Return the ID of the new template.
        return True, (templateID, )
    
    def getUniqueID(self):
        """
        Return unique object ID.

        fixme: return an encoded object ID

        :returns: another unique object ID
        :rtype: int
        :raises: None

        """
        # Increment- and return the object counter with a single atomic Mongo
        # command.
        new_id = self.db_admin.find_and_modify(
            {'name': 'objcnt'}, {'$inc': {'cnt': 1}}, new=True)

        if new_id is None:
            # This must not happen because it means the DB is corrupt.
            self.logit.error('Could not fetch counter - this is a bug!')
            sys.exit(1)

        # Return the ID.
        return new_id['cnt']

    @typecheck
    def returnOk(self, addr, data: (bytes, str)=b''):
        """
        Send positive reply.

        This is a convenience function only to enhance readability.

        :param addr: ZeroMQ address as returned by the router socket.
        :param bytes data: arbitrary data that should be passed back as well.
        :return: None
        """
        # Convert the data to a byte string if necessary.
        if isinstance(data, str):
            data = data.encode('utf8')

        # The first \x00 bytes tells the receiver that everything is ok.
        self.sock_cmd.send_multipart([addr, b'', b'\x00' + data])

    def returnErr(self, addr, data: (bytes, str)=b''):
        """
        Send negative reply.

        This is a convenience function only to enhance readability. It also
        automatically logs a warning message.

        :param addr: ZeroMQ address as returned by the router socket.
        :param bytes data: arbitrary data that should be passed back as well.
        :return: None
        """
        # Convert the data to a byte string if necessary.
        if isinstance(data, str):
            data = data.encode('utf8')

        # For record keeping.
        self.logit.warning(data)

        # The first \x01 bytes tells the receiver that something went wrong.
        self.sock_cmd.send_multipart([addr, b'', b'\x01' + data])

    @typecheck
    def sendMessage(self, src: bytes, dst: bytes, data: bytes):
        """
        Queue a new message with content ``data`` for ``dst`` from ``src``.

        This currently uses a DB but will eventually use a proper message
        queue. For this reason the method has not been moved to the database
        interface.
        """
        doc = {'src': src, 'dst': dst, 'msg': data}
        self.db_msg.insert(doc)
        return True, tuple()

    @typecheck
    def recvMessage(self, obj_id: bytes):
        # Retrieve and remove a matching document from Mongo.
        doc = self.db_msg.find_and_modify({'dst': obj_id}, remove=True)

        # Format the return message.
        if doc is None:
            return True, (b'', b'')
        else:
            # Protocol: sender, message.
            return True, (doc['src'], doc['msg'])

    @typecheck
    def spawn(self, ctrl_name:str, templateID:bytes, sv: btInterface.BulletData):
        ok, data = self.getTemplate(templateID)
        if not ok:
            return False, 'Invalid Template ID'
        else:
            cshape, geo, boosters, factories = data

        # Unpack the SV, then overwrite the supplied CS information.
        sv.cshape[:] = np.fromstring(cshape)
        sv = btInterface.pack(sv).tostring()

        # Find and launch the Controller.
        prog = self.getControllerClass(ctrl_name)
        if prog is None:
            return False, 'Unknown Controller Name'

        new_id = util.int2id(self.getUniqueID())
        self.processes[new_id] = PythonInstance(prog, new_id)
        self.processes[new_id].start()
        btInterface.spawn(new_id, sv, templateID)
        return True, (new_id, )

    @typecheck
    def getStateVariables(self, objIDs: (list, tuple)):
        """
        Return the latest state variables for all ``objIDs``.
        """
        # Get the State Variables.
        ok, sv = btInterface.getStateVariables(objIDs)
        if not ok:
            return False, 'One or more IDs do not exist'
        else:
            out = b''
            for _id, _sv in zip(objIDs, sv):
                out += _id + _sv
            return True, (out, )

    @typecheck
    def getGeometry(self, templateID: bytes):
        # Retrieve the geometry. Return an error if the ID does not
        # exist. Note: an empty geometry field is valid.
        doc = self.db_templateID.find_one({'templateID': templateID})
        if doc is None:
            return False, 'ID does not exist'
        else:
            return True, doc['geometry']

    @typecheck
    def setForce(self, objID: bytes, force: np.ndarray, rpos: np.ndarray):
        ok = btInterface.setForce(objID, force, rpos)
        if ok:
            return True, ''
        else:
            return False, 'ID does not exist'

    def suggestPosition(self, objID: bytes, pos: np.ndarray):
        ok = btInterface.setSuggestedPosition(objID, pos)
        if ok:
            return True, ''
        else:
            return False, 'ID does not exist'

    @typecheck
    def getTemplateID(self, objID: bytes):
        ok, templateID = btInterface.getTemplateID(objID)
        if ok:
            return True, templateID
        else:
            return False, 'Could not find templateID for <{}>'.format(templateID)

    @typecheck
    def getAllObjectIDs(self, args=None):
        # The ID is zero: retrieve all objects and concatenate the SV
        # byte strings.
        #
        # The ``args`` command is empty but needs to be there to ensure
        # a consistent calling signature for runCommand.
        ok, data = btInterface.getAllObjectIDs()
        if not ok:
            return False, data
        else:
            return True, (data, )

    @typecheck
    def runCommand(self, fun_unpack, fun_cmd, fun_pack=None):
        ok, out = fun_unpack(self.payload)
        if not ok:
            self.returnErr(self.last_addr, out)
        else:
            out = fun_cmd(*out)
            ok, out = out[0], out[1]
            if ok:
                if fun_pack is not None:
                    ok, out = fun_pack(*out)
                self.returnOk(self.last_addr, out)
            else:
                self.returnErr(self.last_addr, out)

    def processCmd(self):
        """
        Unpickle the received command and all the respective handler method.
        """

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

        if cmd == config.cmd['ping_clerk']:
            # Return a hard coded 'pong' message.
            self.returnOk(self.last_addr, 'pong clerk'.encode('utf8'))
        elif cmd == config.cmd['get_id']:
            # Create new ID, encode it as a byte stream, and send to client.
            new_id = util.int2id(self.getUniqueID())
            self.returnOk(self.last_addr, new_id)
        elif cmd == config.cmd['send_msg']:
            self.runCommand(protocol.ToClerk_SendMsg_Decode,
                            self.sendMessage,
                            protocol.FromClerk_SendMsg_Encode)
        elif cmd == config.cmd['get_msg']:
            self.runCommand(protocol.ToClerk_RecvMsg_Decode,
                            self.recvMessage,
                            protocol.FromClerk_RecvMsg_Encode)
        elif cmd == config.cmd['spawn']:
            self.runCommand(protocol.ToClerk_Spawn_Decode,
                            self.spawn,
                            protocol.FromClerk_Spawn_Encode)
        elif cmd == config.cmd['get_statevar']:
            self.runCommand(protocol.ToClerk_GetStateVariable_Decode,
                            self.getStateVariables,
                            protocol.FromClerk_GetStateVariable_Encode)
        elif cmd == config.cmd['get_geometry']:
            self.runCommand(protocol.ToClerk_GetGeometry_Decode,
                            self.getGeometry,
                            protocol.FromClerk_GetGeometry_Encode)
        elif cmd == config.cmd['set_force']:
            self.runCommand(protocol.ToClerk_SetForce_Decode,
                            self.setForce,
                            protocol.FromClerk_SetForce_Encode)
        elif cmd == config.cmd['suggest_pos']:
            self.runCommand(protocol.ToClerk_SuggestPosition_Decode,
                            self.suggestPosition,
                            protocol.FromClerk_SuggestPosition_Encode)
        elif cmd == config.cmd['get_template']:
            self.runCommand(protocol.ToClerk_GetTemplate_Decode,
                            self.getTemplate,
                            protocol.FromClerk_GetTemplate_Encode)
        elif cmd == config.cmd['get_template_id']:
            self.runCommand(unpack.getTemplateID, self.getTemplateID)
        elif cmd == config.cmd['add_template']:
            self.runCommand(protocol.ToClerk_AddTemplate_Decode,
                            self.addTemplate,
                            protocol.FromClerk_AddTemplate_Encode)
        elif cmd == config.cmd['get_all_objids']:
            self.runCommand(protocol.ToClerk_GetAllObjectIDs_Decode,
                            self.getAllObjectIDs,
                            protocol.FromClerk_GetAllObjectIDs_Encode)
        else:
            self.returnErr(self.last_addr, 'Invalid Command')
