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
Move the sphere in the default simulation.
"""

import os
import sys
import time
import setproctitle

# Augment the Python path so that we can include the main project.
p = os.path.dirname(os.path.abspath(__file__))
p = os.path.join(p, '..')
sys.path.insert(0, p)
del p

import azrael.controller
import azrael.util as util
import azrael.parts as parts
import azrael.config as config


class ControllerSphere(azrael.controller.ControllerBase):
    def run(self):
        # Boiler plate: setup
        self.setupZMQ()

        # ---------------------------------------------------------------------
        # Central booster (partID=1)
        # ---------------------------------------------------------------------
        time.sleep(2)
        # Engage. This will accelerate the sphere forwards.
        print('Fire central booster...', end='', flush=True)
        central = parts.CmdBooster(partID=1, force=20)
        self.controlParts(self.objID, [central], [])

        # Turn off after 4s.
        time.sleep(2)
        central = parts.CmdBooster(partID=1, force=0)
        self.controlParts(self.objID, [central], [])
        print('done')

        # ---------------------------------------------------------------------
        # Peripheral booster to the left and right (partID=0 and partID=2)
        # ---------------------------------------------------------------------
        # Engage. This will induce spinning due to the booster positions.
        print('Fire peripheral boosters...', end='', flush=True)
        left = parts.CmdBooster(partID=0, force=0.01)
        right = parts.CmdBooster(partID=2, force=0.01)
        self.controlParts(self.objID, [left, right], [])

        # Turn off after 2s.
        time.sleep(2)
        left = parts.CmdBooster(partID=0, force=0)
        right = parts.CmdBooster(partID=2, force=0)
        self.controlParts(self.objID, [left, right], [])
        print('done')


def main():
    if len(sys.argv) < 2:
        objID = 2
    else:
        objID = sys.argv[1]

    # Read the object from the command line.
    objID = int(objID)

    # Rename this process to ensure it is easy to find and kill.
    name = 'killme Controller {}'.format(objID)
    setproctitle.setproctitle(name)

    # Instantiate the controller and start it in this thread.
    ctrl = ControllerSphere(objID, config.addr_clerk)
    ctrl.run()
    print('done')


if __name__ == '__main__':
    main()
