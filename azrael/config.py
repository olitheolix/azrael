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
import azutils
import pymongo
import logging
import setproctitle
import multiprocessing

# ---------------------------------------------------------------------------
# Configure logging.
# ---------------------------------------------------------------------------

# Specify the log level for Azrael.
log_file = os.path.dirname(os.path.abspath(__file__))
log_file = os.path.join(log_file, '..', 'azrael.log')
logger = logging.getLogger('azrael')

# Prevent it from logging to console no matter what.
logger.propagate = False

# Create a handler instance to log the messages to stdout.
console = logging.StreamHandler(sys.stdout)
console.setLevel(logging.DEBUG)
# console.setLevel(logging.ERROR)

logFormat = '%(levelname)s %(module)s.%(funcName)s: %(message)s'
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
# Determine the host/ip addresses of all the services.
azService = azutils.getAzraelServiceHosts('/etc/hosts')


# WebServer URLs for the model- templates and instances. These *must not* include
# the trailing slash.
url_templates = '/templates'
url_instances = '/instances'
assert not url_templates.endswith('/') and not url_templates.endswith('/')


def getMongoClient(timeout: float=10):
    """
    Return a connected `MongoClient` instance.

    This is a convenience method that automatically connects to the correct
    host on the correct address.

    This function does *not* intercept any errors. It is the responsibility of
    the caller to use the correct try/except statement.

    :param float timeout: timeout in Seconds.
    :return: connection to MongoDB
    :rtype: `pymongo.MongoClient`.
    :raises: pymongo.errors.*
    """
    timeout_milliseconds = int(1000 * timeout)
    return pymongo.MongoClient(
        host=azService['database'].ip,
        port=azService['database'].port,
        serverSelectionTimeoutMS=timeout_milliseconds,
        socketTimeoutMS=timeout_milliseconds,
        connectTimeoutMS=timeout_milliseconds,
    )


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

        # Kill this (parent) process as well. However, it may not be running
        # anymore (this terminate method is usually called from another
        # thread), hence the try/except clause.
        try:
            super().terminate()
        except psutil.NoSuchProcess:
            pass
