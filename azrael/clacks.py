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
Bridge between Websocket Controller and Clerk.

It does little more than wrapping a ``ControllerBase`` instance. As such it has
the same capabilities.
"""

import sys
import time
import logging
import multiprocessing
import tornado.websocket
import tornado.httpserver
import zmq.eventloop.zmqstream

import numpy as np

import azrael.util as util
import azrael.config as config
import azrael.protocol_json as json
import azrael.controller as controller

from azrael.typecheck import typecheck


class WebsocketHandler(tornado.websocket.WebSocketHandler):
    """
    Clacks server.

    Clacks is nothing more than a Websocket wrapper around a Controller. Its
    main purpose is to facilitate browser access to Azrael since most browsers
    support it natively, unlike ZeroMQ.

    Every Websocket connection has its own Controller instance. It is created
    once when the Websocket is opened and processes (almost) every request sent
    through the Websocket.

    Among the few exceptions that are not passed to the Controller are Pings
    directed specifically to this Clacks server and the `get_id` command which
    directly returns the ID of the associated Controller.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

    def open(self):
        """
        Create a controller instance as an instance variable.

        This method is a Tornado callback and triggers when a client initiates
        a new Websocket connection.
        """
        self.controller = None

    @typecheck
    def returnOk(self, data: dict, msg: str):
        """
        Send affirmative reply.

        This is a convenience method to enhance readability.

        :param dict data: arbitrary data to pass back to client.
        :param str msg: text message to pass along.
        :return: None
        """
        try:
            ret = json.dumps({'ok': True, 'payload': data, 'msg': msg})
        except (ValueError, TypeError) as err:
            self.returnErr({}, 'JSON encoding error')

        self.write_message(ret, binary=False)

    @typecheck
    def returnErr(self, data: dict, msg: str):
        """
        Send negative reply and log a warning message.

        This is a convenience method to enhance readability.

        :param dict data: arbitrary data to pass back to client.
        :param str msg: text message to pass along.
        :return: None
        """
        msg = {'ok': False, 'payload': {}, 'msg': msg}
        msg = json.dumps(msg)
        self.write_message(msg, binary=False)

    @typecheck
    def on_message(self, msg: str):
        """
        Parse client request and return reply.

        This method is a Tornado callback and triggers whenever a message
        arrives from the client. By definition, every message starts with a
        command byte (always exactly one byte) plus an optional payload.

        Based on the command Byte this handler will either respond directly to
        that command or pass it on to the Controller instances associated with
        this Websocket/client.

        :param bytes msg: message from client.
        """
        try:
            msg = json.loads(msg)
        except (TypeError, ValueError) as err:
            self.returnErr({}, 'JSON decoding error in Clacks')
            return

        if not (('cmd' in msg) and ('payload' in msg)):
            self.returnErr({}, 'Invalid command format')
            return

        # Extract command word (always first byte) and the payload.
        cmd, payload = msg['cmd'], msg['payload']

        if cmd == 'ping_clacks':
            # Handle ourselves: return the pong.
            self.returnOk({'response': 'pong clacks'}, '')
        elif cmd == 'get_id':
            # Handle ourselves: return the ID of the associated Controller.
            if self.controller is None:
                self.returnErr({}, 'No Controller has been instantiate yet')
            else:
                self.returnOk({'objID': self.controller.objID}, '')
        elif cmd == 'set_id':
            if (isinstance(payload, dict)) and ('objID' in payload):
                # Handle ourselves: create a controller with a specific ID.
                if payload['objID'] is None:
                    # Client did not request a specific objID
                    objID = None
                else:
                    # Convert the objID specified by the client to a byte
                    # string.
                    objID = bytes(payload['objID'])
                # Create the Controller instance.
                ok, ret = self.createController(objID)
                self.returnOk({'objID': ret}, '')
            else:
                self.returnErr({}, 'Payload misses the objID field')
        else:
            if self.controller is None:
                # Skip the command if no controller has been instantiated yet
                # to actually process the command.
                self.returnErr({}, 'No controller has been instantiated yet')
                return

            # Pass all other commands directly to the Controller which will
            # (probably) send it to Clerk for processing.
            ok, ret, msg = self.controller.sendToClerk(cmd, payload)

            if ok:
                self.returnOk(ret, msg)
            else:
                self.returnErr({}, msg)

    def createController(self, objID: bytes):
        """
        Create a Controller for ``objID``.

        The created controller object is an instance variable for this
        Websocket connection.

        If ``objID`` is invalid then Clerk will assign the Controller a new and
        unique ID.

        :param bytes objID: desired object ID.
        :return: (ok, objID)
        """
        # This command is only allowed for as long as no controller has
        # been created yet.
        if self.controller is not None:
            msg = 'Controller already has an ID'.encode('utf8')
            self.write_message(msg, binary=True)
            return False, msg

        if objID is None:
            # Constructor of WSControllerBase requests a new objID.
            objID = None

        # Instantiate the controller for the desired objID.
        self.controller = controller.ControllerBase(objID)
        self.controller.setupZMQ()
        self.controller.connectToClerk()
        return True, self.controller.objID

    def on_close(self):
        """
        Shutdown Controller.

        This method is a Tornado callback and triggers whenever the Websocket
        is closed.

        Cleanly shutdown the Controller, most notably the REQ ZeroMQ sockets
        which may cause problems when disconnected without the knowledge of the
        server. This is still a  potential bug that needs a test to reproduce
        it reliably. For now however it is a safe assumption that the handler
        is not forcefully terminated by the OS.
        """
        if self.controller is not None:
            self.controller.close()
        self.logit.debug('Connection closed')


class ClacksServer(multiprocessing.Process):
    """
    Tornado server that constitutes Clacks.

    The server itself only responds to Websocket requests. The entire logic for
    these is defined in ``WebsocketHandler``.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __del__(self):
        self.terminate()

    def run(self):
        # Not sure if this really does anything but it certainly does not
        # hurt.
        self.daemon = True
        time.sleep(0.02)

        # Use the ZeroMQ version of the Tornado event loop to facilitate a
        # seamless integration of the two.
        ioloop = zmq.eventloop.ioloop
        ioloop.install()

        # Install the Websocket handler.
        app = tornado.web.Application([(r"/websocket", WebsocketHandler)])
        http = tornado.httpserver.HTTPServer(app)

        # Specify the server port and create Tornado instance.
        http.listen(config.webserver_port)
        tornado_app = ioloop.IOLoop.instance()

        # Start Tornado event loop.
        try:
            tornado_app.start()
        except KeyboardInterrupt:
            print(' Webserver interrupted by user')
