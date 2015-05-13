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
Bridge between Websocket Client and Clerk.

It does little more than wrapping a ``Client`` instance. As such it has
the same capabilities.
"""

import os
import sys
import time
import json
import logging
import multiprocessing
import tornado.websocket
import tornado.httpserver
import zmq.eventloop.zmqstream

import numpy as np

import azrael.client
import azrael.dibbler
import azrael.util as util
import azrael.config as config

from azrael.types import typecheck


class WebsocketHandler(tornado.websocket.WebSocketHandler):
    """
    Clacks server.

    Clacks is nothing more than Websocket relay to Clerk. Its main purpose is
    to facilitate browser access to Azrael/Clerk since most browsers support
    Websockets but not necessarily ZeroMQ.

    Internally, every Websocket instance creates a standard ``Client``
    instance, and uses to relay the request to a Clerk.

    Among the few exceptions that are not passed to the Client instance are
    Pings directed specifically to this Clacks server.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

    def open(self):
        """
        Create a Client instance.

        This method is a Tornado callback and triggers when a client initiates
        a new Websocket connection.
        """
        self.client = azrael.client.Client()

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
        that command or pass it on to the Client instances associated with
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
        else:
            # Pass all other commands directly to the Client instnace which
            # will (probably) send it to Clerk for processing.
            ret = self.client.sendToClerk(cmd, payload)

            if ret.ok:
                self.returnOk(ret.data, ret.msg)
            else:
                self.returnErr({}, ret.msg)

    def on_close(self):
        """
        Disconnect Client from Azrael.

        This method is a Tornado callback and triggers whenever the Websocket
        is closed.
        """
        if self.client is not None:
            # Not strictly necessary but forcefully triggering the desctructor
            # to close the ZeroMQ connection cannot be a bad idea.
            del self.client
        self.logit.debug('Connection closed')


class ServeViewer(tornado.web.RequestHandler):
    """
    Serve start page.
    """
    def get(self):
        self.redirect("/static/webviewer.html", permanent=True)


class MyGridFSHandler(tornado.web.RequestHandler):
    """
    fixme: docu
    fixme: rename
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.dibbler = azrael.dibbler.DibblerAPI()

        # fixme: add logger instance
        # fixme: use logger instead of print

    def get(self, username):
        tmp = self.dibbler.getFile(self.request.path)
        self.write(tmp.data)

class MyStaticFileHandler(tornado.web.StaticFileHandler):
    """
    fixme: remove this class

    A static file handler that tells the client to never cache anything.

    For more information see
    http://stackoverflow.com/questions/12031007/\
    disable-static-file-caching-in-tornado
    """
    def set_extra_headers(self, path):
        self.set_header('Cache-Control',
                        'no-store, no-cache, must-revalidate, max-age=0')


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
        # Not sure if this really does anything but it certainly does not hurt.
        self.daemon = True
        time.sleep(0.02)

        # Use the ZeroMQ version of the Tornado event loop to facilitate a
        # seamless integration of the two.
        ioloop = zmq.eventloop.ioloop
        ioloop.install()

        # Initialise the list of Tornado handlers.
        handlers = []

        # Redirect to the viewer file.
        handlers.append(('/', ServeViewer))

        # Static HTML files.
        FH = MyStaticFileHandler
        base = os.path.dirname(__file__)
        dirname = os.path.join(base, 'static')
        handlers.append(('/static/(.*)', FH, {'path': dirname}))

        # Fixme: these directories are also hard coded in Dibbler.
        self.dirNameBase = '/tmp/dibbler'
        self.dirNames = {
            'templates': os.path.join(self.dirNameBase, 'templates'),
            'instances': os.path.join(self.dirNameBase, 'instances')}

        # fixme: rename mygridfshandler
        FH = MyGridFSHandler

        # # Template models.
        # fixme: remove these comments
        # handlers.append(
        #     ('/templates/(.*)', FH, {'path': self.dirNames['templates']}))

        # # Instance models.
        # handlers.append(
        #     ('/instances/(.*)', FH, {'path': self.dirNames['instances']}))

        handlers.append(('/templates/(.*)', FH))
        handlers.append(('/instances/(.*)', FH))

        # Websocket to Clacks.
        handlers.append(('/websocket', WebsocketHandler))

        # Install the Websocket handler.
        app = tornado.web.Application(handlers)
        http = tornado.httpserver.HTTPServer(app)

        # Specify the server port and create Tornado instance.
        http.listen(config.port_clacks)
        tornado_app = ioloop.IOLoop.instance()

        # Start Tornado event loop.
        try:
            tornado_app.start()
        except KeyboardInterrupt:
            print(' Webserver interrupted by user')
