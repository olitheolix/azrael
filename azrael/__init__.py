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

import time
import multiprocessing
import azrael.datastore
import azrael.eventstore

# Use 'fork' system call to create new processes.
multiprocessing.set_start_method('fork')


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
            raise ImportError('Could not connect to databases')
        print('.', end='', flush=True)


# Do not proceed with Azrael until the databases are ready.
waitForDatabases(timeout=60)
waitForEventStore(timeout=60)
