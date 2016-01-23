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

import os
import sys
import signal
import multiprocessing

# Use 'fork' system call to create new processes.
multiprocessing.set_start_method('fork')

# Add the 'shared' directory to the path.
tmp = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(tmp, '..', 'shared'))
del tmp

# Wait for the data- and event store to come online.
import azrael.startup
azrael.startup.waitForDatabases(timeout=60)
azrael.startup.waitForEventStore(timeout=6)


# Intercept SIGTERM. Docker sends this signal when it wants to shut down
# containers.
def sighandler(signum, frame):
    print('Azrael intercepted SIGTERM - exiting gracefully now.')
    sys.exit(0)
signal.signal(signal.SIGTERM, sighandler)
