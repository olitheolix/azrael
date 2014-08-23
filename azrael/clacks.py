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
Webserver to interface with Azrael.

The Webserver provides a Websocket interface into Azrael. Every Websocket holds
its own Controller instance to communicate with Azrael and has thus exactly the
same means to interact with the simulation as any other controller.
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


class WebsocketHandler(tornado.websocket.WebSocketHandler):
    """
    A simple request/reply handler for Websocket clients.

    Tornado creates a new instance of this class for every client that
    connects.

    The handler instantiates a controller to interact with Azrael. This implies
    that Azrael will assign a unique ID to that controller and, in turn, this
    handler.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

    def open(self):
        """
        Create a controller instance and set it up manually instead
        of starting it as a process. This instance will be the gateway into
        Azrael.
        """
        self.controller = controller.ControllerBase()
        self.controller.setupZMQ()
        self.controller.connectToClerk()

    def controllerWrap(self, cmd, payload):
        if len(payload) == 0:
            ok, ret = self.controller.sendToClerk(cmd)
        else:
            ok, ret = self.controller.sendToClerk(cmd + payload)

        if ok:
            ret = b'\x00' + ret
        else:
            ret = b'\x01' + ret
        self.write_message(ret, binary=True)

    def on_message(self, msg):
        """
        Parse client request and act upon it.

        The requests can be admin tasks like a ping to verify the connection is
        live, but are most likely tasks passed on to the self.controller
        instance to interact with Azrael.

        .. Note:

          * all requests are blocking.
          * all Websocket message are binary.

        The command word is always the first byte (and only one byte).
        """
        if len(msg) == 0:
            return

        # Extract command word and (optional) payload.
        cmd, payload = msg[:1], msg[1:]

        if cmd == config.cmd['ping_clacks']:
            # Return the pong.
            msg = b'\x00' + 'pong clacks'.encode('utf8')
            self.write_message(msg, binary=True)
        elif cmd == config.cmd['get_id']:
            msg = b'\x00' + self.controller.objID
            self.write_message(msg, binary=True)
        else:
            self.controllerWrap(cmd, payload)

    def on_close(self):
        """
        Clean up, most notably the REQ 0MQ sockets which cause problems when
        disconnected without the knowledge of the server. This is still a
        potential bug that needs a test to reproduce it reliably. For now
        however it is a safe assumption that the handler is not forcefully
        terminated by the OS.
        """
        self.controller.close()
        self.logit.debug('Connection closed')


class ClacksServer(multiprocessing.Process):
    """
    Webserver wrapped in a Python Process for convenience.
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

        # Install the websocket handler.
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
