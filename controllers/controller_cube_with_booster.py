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
Default controller that does nothing other than returning messages.

Clerk knows about the ``ControllerCube`` by default. Its spawn command can
hence start a new Python process for it, pass it the object ID, and leave it to
its own devices.

This particular controller ensures the object periodically moves upwards and
downwards in addition to its natural motion.
"""

import os
import sys
p = os.path.dirname(os.path.abspath(__file__))
p = os.path.join(p, '..')
sys.path.insert(0, p)
del p

import time
import setproctitle
import numpy as np

import azrael.util as util
import azrael.config as config
import azrael.controller


class ControllerCube(azrael.controller.ControllerBase):
    """
    Alternately apply an up/down force to itself.

    This is a simplistic demo of how a controller script can influence an
    object in the simulation.
    """
    def run(self):
        # Setup.
        self.setupZMQ()
        self.connectToClerk()

        # Specify the toggle interval in seconds.
        toggle_interval = 1

        # The force point in all three directions.
        force = 1 * np.ones(3)

        # Apply the force.
        self.setForce(self.objID, force)
        time.sleep(toggle_interval)

        # Reverse the force and apply it again.
        force = -force
        self.setForce(self.objID, force)
        time.sleep(2 * toggle_interval)

        # Periodically reverse and apply the force.
        self.setForce(self.objID, np.zeros(3))
        time.sleep(toggle_interval)
        while True:
            force = -force
            self.setForce(self.objID, force)
            time.sleep(2 * toggle_interval)


if __name__ == '__main__':
    # Read the object from the command line.
    obj_id = util.int2id(int(sys.argv[1]))

    # Rename this process to ensure it is easy to find and kill.
    name = 'killme Controller {}'.format(util.id2int(obj_id))
    setproctitle.setproctitle(name)

    # Instantiate the controller and start it in this thread.
    ctrl = ControllerCube(obj_id)
    ctrl.run()
