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

import azrael.util as util
import azrael.config as config
import azrael.bullet.btInterface as btInterface


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
    Coordinate controllers and their messages.

    There can only be one running instance of Clerk because it binds 0MQ
    sockets.

    Clerk is only accessible via 0MQ sockets. It exposes the one and only
    public API into Azrael.

    All messages are binary, Byte oriented, and not language agnostic. This
    makes Clerk accessible from any language which has binding for 0MQ (which
    is pretty much every language).
    """
    def __init__(self, reset, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

        # Create all database collections that Azrael will need.
        client = pymongo.MongoClient()
        self.db_msg = client['azrael']['msg']
        self.db_admin = client['azrael']['admin']
        self.db_objdesc = client['azrael']['objdesc']

        # Drop all collections, if requested.
        if reset:
            client.drop_database('azrael')
            self.db_objdesc.insert({'name': 'objcnt', 'cnt': 0})

        # Insert default objects. None has a geometry, but their collision
        # shapes are: none, sphere, cube.
        self.createObjectDescription(
            np.array([0, 1, 1, 1], np.float64).tostring(), b'')
        self.createObjectDescription(
            np.array([3, 1, 1, 1], np.float64).tostring(), b'')
        self.createObjectDescription(
            np.array([4, 1, 1, 1], np.float64).tostring(), b'')

        # Initialise the SV related collections.
        btInterface.initSVDB(reset)

        # Dictionary of all controllers this Clerk is aware of. The key is the
        # object ID and the value the process ID.
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

        # Reset the object counter. In conjunction with atomic DB updates this
        # counter will be the sole source for new and unique object IDs.
        self.db_admin.insert({'name': 'objcnt', 'cnt': 0})

        # Wait for socket activity.
        while True:
            sock = dict(poller.poll())
            if self.sock_cmd in sock:
                self.processCmd()

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

    def getObjectDescription(self, objdesc: bytes):
        """
        Return the collision shape and geometry data, or None.
        """
        assert isinstance(objdesc, bytes)
        doc = self.db_objdesc.find_one({'objdesc': objdesc})
        if doc is None:
            return None
        else:
            return doc['cshape'], doc['geometry']
        
    def createObjectDescription(self, cshape, geometry):
        """
        Add a new object to the 'objdesc' DB and return its ID.

        Only objects created with this method can be spawned later on.
        """
        new_id = self.db_objdesc.find_and_modify(
            {'name': 'objcnt'}, {'$inc': {'cnt': 1}}, new=True)
        new_id = new_id['cnt']
        objdescid = np.int64(new_id).tostring()
        self.db_objdesc.update(
            {'objdesc': objdescid},
            {'$set': {'objdesc': objdescid,
                      'cshape': cshape, 'geometry': geometry}},
            upsert=True)
        return objdescid
    
    def getUniqueID(self):
        """
        Return unique object ID.
        """
        # Increment- and return the object counter with a single atomic Mongo
        # command.
        new_id = self.db_admin.find_and_modify(
            {'name': 'objcnt'}, {'$inc': {'cnt': 1}}, new=True)

        if new_id is None:
            self.logit.error('Could not fetch counter - this is a bug!')
            sys.exit(1)
        return new_id['cnt']

    def returnOk(self, addr, data: bytes=b''):
        self.sock_cmd.send_multipart([addr, b'', b'\x00' + data])

    def returnErr(self, addr, data: (bytes, str)=b''):
        if isinstance(data, str):
            data = data.encode('utf8')
        self.logit.warning(data)
        self.sock_cmd.send_multipart([addr, b'', b'\x01' + data])

    def processCmd(self):
        # Read from ROUTER socket.
        msg = self.sock_cmd.recv_multipart()

        # Unpack address and message; add sanity checks.
        assert len(msg) == 3
        addr, empty, msg = msg[0], msg[1], msg[2]
        assert empty == b''

        if len(msg) == 0:
            # Sanity check: every message must contain at least a command byte.
            self.returnErr(addr, 'Did not receive command word.')
            return

        # Split message into command word and payload.
        cmd, payload = msg[:1], msg[1:]

        if cmd == config.cmd['ping_clerk']:
            # Return a hard coded 'pong' message.
            self.returnOk(addr, 'pong clerk'.encode('utf8'))
        elif cmd == config.cmd['get_id']:
            # Create new ID, encode it as a byte stream, and send to client.
            new_id = util.int2id(self.getUniqueID())
            self.returnOk(addr, new_id)
        elif cmd == config.cmd['send_msg']:
            # Client wants to clerk a message to another client.
            src = payload[:config.LEN_ID]
            dst = payload[config.LEN_ID:2 * config.LEN_ID]
            data = payload[2 * config.LEN_ID:]

            if len(dst) != config.LEN_ID:
                self.returnErr(addr, 'Insufficient arguments')
            else:
                # Add the message to the queue in Mongo.
                doc = {'src': src, 'dst': dst, 'msg': data}
                self.db_msg.insert(doc)

                # Acknowledge that everything went well.
                self.returnOk(addr)
        elif cmd == config.cmd['get_msg']:
            # Check if any messages for a particular controller ID are
            # pending. Return the first such message if there are any and
            # remove them from the queue. The controller ID is the only
            # payload.
            obj_id = payload[:config.LEN_ID]

            if len(obj_id) != config.LEN_ID:
                self.returnErr(addr, 'Insufficient arguments')
                return

            # Retrieve and remove a matching document from Mongo.
            doc = self.db_msg.find_and_modify({'dst': obj_id}, remove=True)

            # Format the return message.
            if doc is None:
                msg = b''
            else:
                # Protocol: sender, message.
                msg = doc['src'] + doc['msg']
            self.returnOk(addr, msg)
        elif cmd == config.cmd['spawn']:
            # Spawn a new object/controller.

            if len(payload) == 0:
                self.returnErr(addr, 'Insufficient arguments')
                return

            # Extract name of Python object to launch. The first byte denotes
            # the length of that name (in bytes).
            name_len = payload[0]
            if len(payload) != (name_len + 1 + 8 + config.LEN_SV_BYTES):
                self.returnErr(addr, 'Invalid Payload Length')
                return

            # Extract and decode the Controller name.
            ctrl_name = payload[1:name_len+1]
            ctrl_name = ctrl_name.decode('utf8')

            # Query the object description ID to spawn.
            objdesc = payload[name_len+1:name_len+1+8]
            sv = payload[name_len+1+8:]

            tmp = self.getObjectDescription(objdesc)
            if tmp is None:
                self.returnErr(addr, 'Invalid Raw Object ID')
                return
            else:
                # Unpack the return values.
                cshape, geo = tmp
                del tmp

            # Unpack the SV, then overwrite the supplied CS information.
            sv = btInterface.unpack(np.fromstring(sv))
            sv.cshape[:] = np.fromstring(cshape)
            sv = btInterface.pack(sv).tostring()

            # Find and launch the Controller.
            prog = self.getControllerClass(ctrl_name)
            if prog is None:
                self.returnErr(addr, 'Unknown Controller Name')
            else:
                new_id = util.int2id(self.getUniqueID())
                self.processes[new_id] = PythonInstance(prog, new_id)
                self.processes[new_id].start()
                btInterface.add(new_id, sv, objdesc)
                self.returnOk(addr, new_id)
        elif cmd == config.cmd['get_statevar']:
            # Return the state variables as a byte string preceeded by the
            # controller ID. If the requested ID is zero return the state
            # variables for all objects as a concatenated byte stream.

            # Payload must be exactly one ID.
            if len(payload) != config.LEN_ID:
                self.returnErr(addr, 'Insufficient arguments')
                return

            if util.id2int(payload) == 0:
                # The ID is zero: retrieve all objects and concatenate the SV
                # byte strings.
                data, ok = btInterface.getAll()
                if not ok:
                    self.returnErr(addr, 'Could not retrieve objects')
                else:
                    ret = [_ + data[_] for _ in data]
                    ret = b''.join(ret)
                    self.returnOk(addr, ret)
            else:
                # If the ID is non-zero then retrieve the SV for that
                # controller, or return an error if no such controller ID
                # exists.
                doc, ok = btInterface.get(payload)
                if not ok:
                    self.returnErr(addr, 'ID does not exist')
                else:
                    self.returnOk(addr, payload + doc)
        elif cmd == config.cmd['new_raw_object']:
            # Payload must consist of at least a collision shape (4 float64).
            if len(payload) < 4 * 8:
                self.returnErr(addr, 'Insufficient arguments')
                return

            # Unpack the data.
            cshape, geometry = payload[:32], payload[32:]

            # Geometry can only be a valid mesh of triangles if its length is a
            # multiple of 9.
            if len(geometry) % 9 != 0:
                self.returnErr(addr, 'Geometry is not a multiple of 9')
                return

            # Create the new raw object and return its ID.
            objdesc = self.createObjectDescription(cshape, geometry)
            self.returnOk(addr, objdesc)
        elif cmd == config.cmd['get_geometry']:
            # Payload must be exactly one objdescid.
            if len(payload) != 8:
                self.returnErr(addr, 'Insufficient arguments')
                return

            # Retrieve the geometry. Return an error if the ID does not
            # exist. Note: an empty geometry field is valid.
            doc = self.db_objdesc.find_one({'objdesc': payload})
            if doc is None:
                self.returnErr(addr, 'ID does not exist')
            else:
                self.returnOk(addr, doc['geometry'])
        elif cmd == config.cmd['set_force']:
            # Payload must comprise one ID plus two 3-element vectors (8 Bytes
            # each) for force and relative position of that force with respect
            # to the center of mass.
            if len(payload) != (config.LEN_ID + 6 * 8):
                self.returnErr(addr, 'Insufficient arguments')
                return

            # Unpack the ID and 'force' value, then issue the update.
            obj_id = payload[:config.LEN_ID]
            _ = config.LEN_ID
            force, rpos = payload[_:_ + 3 * 8], payload[_ + 3 * 8:_ + 6 * 8]
            force, rpos = np.fromstring(force), np.fromstring(rpos)
            ok = btInterface.setForce(obj_id, force, rpos)
            if ok:
                self.returnOk(addr)
            else:
                self.returnErr(addr, 'ID does not exist')
        elif cmd == config.cmd['suggest_pos']:
            # Payload must be exactly one ID plus a 3-element position vector
            # with 8 Bytes (64 Bits) each.
            if len(payload) != (config.LEN_ID + 3 * 8):
                self.returnErr(addr, 'Insufficient arguments')
                return

            # Unpack the suggested position.
            obj_id, pos = payload[:config.LEN_ID], payload[config.LEN_ID:]
            pos = np.fromstring(pos)
            ok = btInterface.setSuggestedPosition(obj_id, pos)
            if ok:
                self.returnOk(addr)
            else:
                self.returnErr(addr, 'ID does not exist')
        elif cmd == config.cmd['get_template_id']:
            objdesc, ok = btInterface.getTemplateID(payload)
            if ok:
                self.returnOk(addr, objdesc)
            else:
                msg = 'Could not find objdesc for <{}>'.format(payload)
                self.returnErr(addr, msg)
        else:
            self.returnErr(addr, 'Invalid Command')
