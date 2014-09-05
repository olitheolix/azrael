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
import json
import logging
import multiprocessing
import tornado.websocket
import tornado.httpserver
import zmq.eventloop.zmqstream

import numpy as np

import azrael.util as util
import azrael.config as config
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
        if len(msg) == 0:
            return

        # fixme: error check
        msg = json.loads(msg)

        # Extract command word (always first byte) and the payload.
        cmd, payload = msg['cmd'], msg['payload']

        if cmd == 'ping_clacks':
            # Handle ourselves: return the pong.
            msg = {'ok': True, 'payload': {'response': 'pong clacks'}}
            msg = json.dumps(msg)
            self.write_message(msg, binary=False)
        elif cmd == 'get_id':
            # Handle ourselves: return the ID of the associated Controller.
            msg = {'ok': True,
                   'payload': {'objID': list(self.controller.objID)}}
            self.write_message(json.dumps(msg), binary=False)
        elif cmd == 'set_id':
            if payload['objID'] is None:
                objID = None
            else:
                objID = bytes(payload['objID'])
            # Handle ourselves: create a controller with a specific ID.
            ok, ret = self.createController(objID)
            ret = {'ok': ok, 'payload': list(ret)}
            self.write_message(json.dumps(ret), binary=False)
        else:
            if self.controller is None:
                # Skip the command if no controller has been instantiated yet
                # to actually process the command.
                msg = {'ok': False,
                       'payload': 'No controller has been instantiated yet'}
                msg = json.dumps(msg)
                self.write_message(msg, binary=False)
                return

            # Pass all other commands directly to the Controller which will
            # (probably) send it to Clerk for processing.
            ok, ret = self.controller.sendToClerk(cmd, payload)

            ret = {'ok': ok, 'payload': ret}
            ret = json.dumps(ret)
            self.write_message(ret, binary=False)

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

        if objID == None:
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
