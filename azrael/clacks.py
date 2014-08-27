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
        self.controller = controller.ControllerBase()
        self.controller.setupZMQ()
        self.controller.connectToClerk()

    @typecheck
    def on_message(self, msg: bytes):
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

        # Extract command word (always first byte) and the payload.
        cmd, payload = msg[:1], msg[1:]

        if cmd == config.cmd['ping_clacks']:
            # Handle ourselves: return the pong.
            msg = b'\x00' + 'pong clacks'.encode('utf8')
            self.write_message(msg, binary=True)
        elif cmd == config.cmd['get_id']:
            # Handle ourselves: return the ID of the associated Controller.
            msg = b'\x00' + self.controller.objID
            self.write_message(msg, binary=True)
        else:
            # Pass all other commands directly to the Controller which will
            # (probably) send it to Clerk for processing.
            ok, ret = self.controller.sendToClerk(cmd + payload)
    
            # Return the Controller's response to the Websocket client. Convert
            # the Boolean `ok` to a byte for the wire transfer.
            if ok:
                ret = b'\x00' + ret
            else:
                ret = b'\x01' + ret
            self.write_message(ret, binary=True)

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
