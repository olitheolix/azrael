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

.. note::
   This module has no side effects and can be imported from anywhere by anyone.

.. warning::
   To keep this module free of side effects it is paramount to not import other
   Azrael modules here (circular imports), *and* that *no* other module
   modifies any variables here during run time.
"""
import os
import sys
import psutil
import pymongo
import logging
import netifaces
import setproctitle
import multiprocessing

# ---------------------------------------------------------------------------
# Configure logging.
# ---------------------------------------------------------------------------

# Specify the log level for Azrael.
log_file = os.path.dirname(os.path.abspath(__file__))
log_file = os.path.join(log_file, '..', 'volume', 'azrael.log')
logger = logging.getLogger('azrael')

# Prevent it from logging to console no matter what.
logger.propagate = False

# Create a handler instance to log the messages to stdout.
console = logging.StreamHandler(sys.stdout)
console.setLevel(logging.DEBUG)
# console.setLevel(logging.ERROR)

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

def getNetworkAddress():
    """
    Return the IP address of the first configured network interface.

    The search order is 'eth*', 'wlan*', and localhost last.
    """
    # Find all interface names.
    eth = [_ for _ in netifaces.interfaces() if _.lower().startswith('eth')]
    wlan = [_ for _ in netifaces.interfaces() if _.lower().startswith('wlan')]
    lo = [_ for _ in netifaces.interfaces() if _.lower().startswith('lo')]

    # Search through all interfaces until a configured one (ie one with an IP
    # address) was found. Return that one to the user, or abort with an error.
    host_ip = None
    for iface in eth + wlan + lo:
        try:
            host_ip = netifaces.ifaddresses(iface)[2][0]['addr']
            break
        except (ValueError, KeyError):
            pass
    if host_ip is None:
        logger.critical('Could not find a valid network interface')
        sys.exit(1)

    return host_ip

# Default address where all of Azrael's services will run.
addr_azrael = getNetworkAddress()

# Database host.
if 'INSIDEDOCKER' in os.environ:
    addr_database = 'database'
    port_database = 27017
else:
    addr_database = 'localhost'
    port_database = 27017

# Addresses of the various Azrael services.
addr_webapi = addr_azrael
port_webapi = 8080

addr_dibbler = addr_azrael
port_dibbler = 8081

addr_clerk = addr_azrael
port_clerk = 5555

addr_leonard_repreq = 'tcp://' + addr_azrael + ':5556'

# WebServer URLs for the model- templates and instances. These *must not* include
# the trailing slash.
url_templates = '/templates'
url_instances = '/instances'
assert not url_templates.endswith('/') and not url_templates.endswith('/')


def getMongoClient():
    """
    Return a connected `MongoClient` instance.

    This is a convenience method that automatically connects to the correct
    host on the correct address.

    This function does intercept any errors. It is the responsibility of the
    caller to use the correct try/except statement.

    :return: connection to MongoDB
    :rtype: `pymongo.MongoClient`.
    :raises: pymongo.errors.*
    """
    return pymongo.MongoClient(host=addr_database, port=port_database)


class AzraelProcess(multiprocessing.Process):
    """
    Base class for processes spawned by Azrael.

    This is a convenience wrapper around the multiprocessing.Process that
    automatically sets up the logger and renames in the process table once it
    forks.
    """
    def __init__(self):
        super().__init__()

        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

        # Save the PID of the parent. This will allow the 'run' method to
        # determine if it runs in thread or was actually forked into a new
        # process.
        self._parentPID = os.getpid()

    def run(self):
        # If this is a new process (instead of someone just calling this method
        # directly) then change the name of the process in the Unix process
        # table. This makes it easier to identify and kill the Azrael processes
        # from the command shell.
        if os.getpid() != self._parentPID:
            procname = 'Azrael: {}'.format(self.__class__.__name__)
            setproctitle.setproctitle(procname)
            del procname

    def terminate(self):
        """
        Kill this process and *all* its descendants.
        """
        # Define the current process as the parent.
        parent = psutil.Process(os.getpid())

        # Iterate over all its childrent, grand-children, etc and kill them.
        [_.kill() for _ in parent.children(recursive=True)]

        # Kill this (parent) process as well.
        super().terminate()
