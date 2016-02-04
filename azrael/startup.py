# Copyright 2015, Oliver Nagy <olitheolix@gmail.com>
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
Convenience functions for testing and running Azrael.
"""

import sys
import time
import logging
import subprocess
import azrael.web
import azutils
import azrael.clerk
import azrael.config
import azrael.dibbler
import azrael.leonard
import azrael.datastore
import azrael.vectorgrid


def waitForDatabases(timeout=60):
    """
    Raise `ImportError` if data stores are unavailable for ``timeout`` seconds.

    Azrael crucially relies on the databases (via the Datastore API). The main
    purpose of this function is to wait until they are ready. This is not a
    problem locally but if the databases are started separately (eg in Docker
    containers) then it may take a while until they accept connections.
    """
    if azrael.datastore.init(flush=False).ok is True:
        return

    # Attempt to initialise the data stores.
    time.sleep(0.5)
    t0 = time.time()
    print('Waiting for data store .', flush=True, end='')
    while azrael.datastore.init(flush=False).ok is False:
        if time.time() - t0 > timeout:
            # A minute has passed - abort with an error.
            print('failed!')
            print('Could not connect to datastore backends -- Abort')
            raise ImportError('Could not connect to databases')
        time.sleep(0.5)
        print('.', end='', flush=True)
    print('ok')


def waitForEventStore(timeout=60):
    """
    Raise `ImportError` if EventStore cannot connect for ``timeout`` seconds.

    The most likely cause is that the RabbitMQ server is still starting up.
    """
    try:
        azrael.eventstore.EventStore(['#'])
        return
    except RuntimeError:
        pass

    t0 = time.time()
    print('Waiting for event store .', flush=True, end='')
    while True:
        time.sleep(0.5)
        try:
            azrael.eventstore.EventStore(['#'])
            print('ok')
            break
        except RuntimeError:
            pass

        if time.time() - t0 > timeout:
            # A minute has passed - abort with an error.
            print('failed!')
            print('Could not connect to event store -- Abort')
            raise ImportError('Could not connect to event store')
        print('.', end='', flush=True)


class AzraelStack:
    """
    Convenience class to start and stop the necessary Azrael processes.
    """
    def __init__(self, loglevel=1):
        """
        Wait for support services and setup logging.
        """
        waitForDatabases(timeout=60)
        waitForEventStore(timeout=60)

        # List of processes started via this class.
        self.procs = []

        # Kill any pending processes.
        subprocess.run(['pkill', 'Azrael:'], check=False)
        time.sleep(0.2)
        azrael.datastore.init(flush=True)

        # Reset the profiling database and enable logging.
        host, port = azrael.config.azService['database']
        azutils.resetTiming(host=host, port=port)
        self.setupLogging(loglevel)

        # Delete all grids but define a force grid (will not be used but
        # Leonard throws a lot of harmless warnings otherwise).
        vg = azrael.vectorgrid
        assert vg.deleteAllGrids().ok
        assert vg.defineGrid(name='force', vecDim=3, granularity=1).ok

    def __del__(self):
        self.stop()

    def start(self):
        """
        Start the Azrael processes.
        """
        # Spawn Azrael's APIs.
        clerk = azrael.clerk.Clerk()
        web = azrael.web.WebServer()

        if not azutils.isInsideDocker():
            # Flush the model database.
            dibbler = azrael.dibbler.Dibbler()
            dibbler.reset()

            # Start the physics engine.
            # leo = azrael.leonard.LeonardBase()
            # leo = azrael.leonard.LeonardBullet()
            # leo = azrael.leonard.LeonardSweeping()

            leo = azrael.leonard.LeonardDistributedZeroMQ()
            wm = azrael.leonard.WorkerManager(
                numWorkers=3,
                minSteps=500,
                maxSteps=700,
                workerCls=azrael.leonard.LeonardWorkerZeroMQ
            )

            # Start Clerk, WebServer, and Leonard.
            self.startProcess(clerk)
            self.startProcess(web)
            self.startProcess(leo)
            self.startProcess(wm)

    def stop(self):
        """
        Terminate and join all processes registered with this instance.
        """
        [_.terminate() for _ in self.procs]
        [_.join() for _ in self.procs]

        # Empty the process list since the destructor will otherwise try to
        # destroy already destroyed processes.
        self.procs = []

    def startProcess(self, proc):
        """
        Start ``proc`` and keep a handle to it alive.
        """
        proc.start()
        self.procs.append(proc)

    def setupLogging(self, loglevel):
        """
        Change the log level of the 'Azrael' loggers (defined in
        azrael.config).
        """
        logger = logging.getLogger('azrael')
        if loglevel == 0:
            logger.setLevel(logging.DEBUG)
        elif loglevel == 1:
            logger.setLevel(logging.INFO)
        elif loglevel == 2:
            logger.setLevel(logging.WARNING)
        else:
            print('Unknown log level {}'.format(loglevel))
            sys.exit(1)
