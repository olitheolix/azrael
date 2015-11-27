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
WebServer serves up the geometry files (from Dibbler). It also relays Websocket
connections to Clerk.

WebServer facilitates browser access to Azrael/Clerk via Websockets. This would
otherwise be impossible because the rest is built with ZeroMQ, which browsers
do not support.

The second purpose of WebServer is to serve up model geometry files. This is
little more than a wrapper around Dibbler which administrates all model files.
"""

import os
import time
import json
import logging
import tornado.websocket
import tornado.httpserver
import zmq.eventloop.zmqstream

import azrael.dibbler
import azrael.config as config

from azrael.aztypes import typecheck, RetVal


class WebsocketHandler(tornado.websocket.WebSocketHandler):
    """
    Internally, every Websocket instance connects to ``Clerk`` and relays the
    data on behalf of the client.

    Among the few exceptions of commands that are not passed to Clerk are Pings
    directed specifically to this Web server.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Define a dummy in case the destructor is called before the Websocket
        # gets initialised.
        self.sock_cmd = None

        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

    def open(self):
        """
        Connect to Clerk.

        This method is a Tornado callback and triggers when a client initiates
        a new Websocket connection.
        """
        # Create ZeroMQ sockets and connect them to Clerk.
        ip = config.addr_clerk
        port = config.port_clerk
        self.ctx = zmq.Context()
        self.sock_cmd = self.ctx.socket(zmq.REQ)
        self.sock_cmd.linger = 0
        self.sock_cmd.connect('tcp://{}:{}'.format(ip, port))

    @typecheck
    def returnToClient(self, ret: RetVal):
        """
        Send ``ret`` to the Client via the Websocket.

        This is a convenience method to enhance readability.

        :param dict data: arbitrary data to pass back to client.
        :param str msg: text message to pass along.
        :return: None
        """
        # Convert the message to JSON.
        try:
            ret = json.dumps(ret._asdict())
        except (ValueError, TypeError):
            msg = 'Could not convert Clerk return value to JSON'
            ret = json.dumps(RetVal(False, msg, None)._asdict())

        # Send the message via HTTP.
        self.write_message(ret, binary=False)

    @typecheck
    def on_message(self, msg_json: str):
        """
        Parse client request and return reply.

        Tornado triggers this callback whenever a message arrives from
        the client. Every message must contain a command, and may contain a
        payload.

        Based on the command this handler will either respond directly
        or relay everything to a Clerk and return its reponse upon completion.

        :param bytes msg_json: message from client.
        """
        try:
            msg = json.loads(msg_json)
        except (TypeError, ValueError):
            self.returnToClient(RetVal(False, 'JSON decoding error in WebServer', None))
            return

        if not (('cmd' in msg) and ('data' in msg)):
            self.returnToClient(RetVal(False, 'Invalid command format', None))
            return

        # Extract command and payload.
        cmd, payload = msg['cmd'], msg['data']

        if cmd == 'ping_webserver':
            # This one we handle ourselves: return the pong.
            self.returnToClient(RetVal(True, '', {'response': 'pong webserver'}))
        else:
            # Pass the command directly to Clerk, wait for its response, and
            # send that back to the client.
            self.sock_cmd.send(msg_json.encode('utf8'))
            payload = self.sock_cmd.recv().decode('utf8')
            try:
                ret = json.loads(payload)
                ret = RetVal(**ret)
            except (ValueError, TypeError):
                ret = RetVal(False, 'JSON decoding error in Client', None)

            # Return payload (or error message) to client.
            if ret.ok:
                self.returnToClient(ret)
            else:
                self.returnToClient(RetVal(False, ret.msg, None))

    def on_close(self):
        """
        Disconnect Client from Azrael.

        This method is a Tornado callback and triggers whenever the Websocket
        is closed.
        """
        if self.sock_cmd is not None:
            # Not strictly necessary but forcefully triggering the destructor
            # to close the ZeroMQ connection cannot be a bad idea.
            self.sock_cmd.close(linger=0)
        self.logit.debug('Connection closed')


class ServeViewer(tornado.web.RequestHandler):
    """
    Serve start page.
    """
    def get(self):
        self.redirect("/static/webviewer.html", permanent=True)


class MyGridFSHandler(tornado.web.RequestHandler):
    """
    Serve up files from Dibbler.

    This handle is merely a wrapper around Dibbler's 'getFile' function.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.dibbler = azrael.dibbler.Dibbler()

        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

    def set_extra_headers(self, path):
        """
        Disable all caches (maybe). For more information see
        http://stackoverflow.com/questions/12031007/\
        disable-static-file-caching-in-tornado
        """
        self.set_header('Cache-Control',
                        'no-store, no-cache, must-revalidate, max-age=0')

    def get(self, username):
        """
        Fetch the file from Dibbler and serve it up, if possible.

        If the file does not exist then return an empty string to the client.
        """
        # Fetch the file from Dibbler.
        fname = self.request.path
        ret = self.dibbler.get([fname])

        # Return the file to the client if Dibbler found it. Otherwise return
        # nothing.
        if ret.ok and fname in ret.data:
            self.write(ret.data[fname])
        else:
            self.write(b'')


class MyStaticFileHandler(tornado.web.StaticFileHandler):
    """
    A static file handler that tells the client to never cache anything.

    For more information see
    http://stackoverflow.com/questions/12031007/\
    disable-static-file-caching-in-tornado
    """
    def set_extra_headers(self, path):
        self.set_header('Cache-Control',
                        'no-store, no-cache, must-revalidate, max-age=0')


class WebServer(config.AzraelProcess):
    """
    Tornado server that constitutes WebServer.

    The server itself only responds to Websocket requests. The entire logic for
    these is defined in ``WebsocketHandler``.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __del__(self):
        self.terminate()

    def run(self):
        # Call `run` method of `AzraelProcess` base class.
        super().run()

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
        base = os.path.dirname(__file__)
        dirname = os.path.join(base, 'static')
        handlers.append(
            ('/static/(.*)', MyStaticFileHandler, {'path': dirname})
        )

        # Serve up template- and instance models.
        handlers.append(
            (config.url_templates + '/(.*)', MyGridFSHandler))
        handlers.append(
            (config.url_instances + '/(.*)', MyGridFSHandler))

        # Proxy handler to arbitrate between Websockets and WebServer.
        handlers.append(('/websocket', WebsocketHandler))

        # Install the handlers and create the Tornado instance.
        app = tornado.web.Application(handlers)
        http = tornado.httpserver.HTTPServer(app)

        # Specify the server port and start the ioloop.
        http.listen(config.port_webapi)
        tornado_app = ioloop.IOLoop.instance()

        # Start Tornado event loop.
        try:
            tornado_app.start()
        except KeyboardInterrupt:
            self.logit.warning('Webserver interrupted by user')
