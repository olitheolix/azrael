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

import sys
import logging

# ---------------------------------------------------------------------------
# Configure logging.
# ---------------------------------------------------------------------------

# Specify the log level for Azrael.
log_file = 'azrael.log'
logger = logging.getLogger('azrael')

# Prevent it from logging to console no matter what.
logger.propagate = False

# Create a handler instance to log the messages to stdout.
console = logging.StreamHandler(sys.stdout)
console.setLevel(logging.DEBUG)
console.setLevel(logging.ERROR)

logFormat = '%(levelname)s - %(name)s - %(message)s'
console.setFormatter(logging.Formatter(logFormat))

# Install the handler.
logger.addHandler(console)
del logger, console, logFormat

# ---------------------------------------------------------------------------
# Global variables.
# ---------------------------------------------------------------------------

# Length of object ID in bytes.
LEN_ID = 3

# Length of a single state variable record in terms of NumPy float64.
LEN_SV_FLOATS = 21

# Length of a single state variable record in terms of Bytes.
LEN_SV_BYTES = 21 * 8

# Specify all commands. Every command will be assigned a unique ID encoded as a
# byte. For instance: 'cmd' could be {'get_msg': bytes([0]), 'clerk':
# bytes([1])}. Note: the 'invalid_cmd' is purely for testing the Clerk.
commands = ('invalid_cmd', 'ping_clerk', 'ping_clacks', 'get_id', 'spawn',
            'get_statevar', 'new_raw_object', 'get_geometry', 'set_force',
            'suggest_pos', 'send_msg', 'get_msg', 'get_template_id')
cmd = dict(zip(commands, [bytes([_]) for _ in range(len(commands))]))
del commands

# Port of Tornado server.
webserver_port = 8080

# Address of Clerk.
addr_clerk = 'tcp://127.0.0.1:5555'

# ---------------------------------------------------------------------------
# RabbitMQ parameters.
# ---------------------------------------------------------------------------

# Address of the message Clerk.
clerk_msg = 'tcp://127.0.0.1:5555'

# Name of RabbitMQ exchange for messages.
rmq_wp = 'wp'
rmq_ack = 'ack'

# Routing key 1
route_key1 = 'key1'

# Routing key 2
route_key2 = 'key2'

# RabbitMQ address.
rabbitMQ_host = 'localhost'
