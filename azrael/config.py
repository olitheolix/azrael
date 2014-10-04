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
Global configuration parameters.
"""
import sys
import logging
import netifaces

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
#console.setLevel(logging.ERROR)

logFormat = '%(levelname)s - %(name)s - %(message)s'
console.setFormatter(logging.Formatter(logFormat))

# Install the handler.
logger.addHandler(console)

# Specify a file logger.
logFormat = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
formatter = logging.Formatter(logFormat)
fileHandler = logging.FileHandler(log_file, mode='a')
fileHandler.setLevel(logging.DEBUG)
fileHandler.setFormatter(formatter)
fileHandler.setLevel(logging.DEBUG)

# Install the handler.
logger.addHandler(fileHandler)

del console, logFormat, formatter, fileHandler

# ---------------------------------------------------------------------------
# Global variables.
# ---------------------------------------------------------------------------

# Length of object ID in bytes.
LEN_ID = 8

# Length of a single state variable record in terms of NumPy float64.
LEN_SV_FLOATS = 21

# Length of a single state variable record in terms of Bytes.
LEN_SV_BYTES = 21 * 8

# Port of Tornado server.
webserver_port = 8080

# Determine the IP address where Clerk will listen for ZeroMQ requests.
# eth0 is first choice, localhost is the fallback.
try:
    addr_clerk = netifaces.ifaddresses('eth0')[2][0]['addr']
except (ValueError, KeyError):
    try:
        addr_clerk = netifaces.ifaddresses('lo')[2][0]['addr']
    except (ValueError, KeyError):
        logger.critical('Could not find a valid network interface')
        sys.exit(1)
addr_clerk = 'tcp://' + addr_clerk + ':5555'

# ---------------------------------------------------------------------------
# RabbitMQ parameters.
# ---------------------------------------------------------------------------

# Name of RabbitMQ exchange for messages.
rmq_wp = 'wp'
rmq_ack = 'ack'

# Routing key 1
route_key1 = 'key1'

# Routing key 2
route_key2 = 'key2'

# RabbitMQ address.
rabbitMQ_host = 'localhost'
