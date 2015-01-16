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
Manoeuvre the swarm of cubes in an orchestrated fashion.

Due to the lack of any feedback control the cubes may not move too orderly but
it suffices to demonstrate the principle.
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

import azrael.client
import azrael.parts as parts
import azrael.config as config


class ControllerCubeLeft(azrael.client.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.left = 0
        self.right = 1

    def run(self):
        # Boiler plate: setup
        self.setupZMQ()

        # ---------------------------------------------------------------------
        # Edit here to change the force of boosters.
        # ---------------------------------------------------------------------
        # Turn both boosters on after 2s.
        left = parts.CmdBooster(self.left, force=0.1)
        right = parts.CmdBooster(self.right, force=0.1)
        self.controlParts(self.objID, [right, left], [])
        print('{0:02d}: Manoeuvre 1'.format(self.objID))
        time.sleep(2)

        # Fire the booster assymetrically to make the cube turn.
        left = parts.CmdBooster(self.left, force=0)
        right = parts.CmdBooster(self.right, force=1)
        self.controlParts(self.objID, [right, left], [])
        print('{0:02d}: Manoeuvre 2'.format(self.objID))
        time.sleep(2)

        # Reverse the force settings to stop the spinning.
        left = parts.CmdBooster(self.left, force=1)
        right = parts.CmdBooster(self.right, force=0)
        self.controlParts(self.objID, [right, left], [])
        print('{0:02d}: Manoeuvre 3'.format(self.objID))
        time.sleep(2)

        # Use the same force on both boosters to just move forward without
        # inducing any more spinning.
        left = parts.CmdBooster(self.left, force=0.1)
        right = parts.CmdBooster(self.right, force=0.1)
        self.controlParts(self.objID, [right, left], [])
        time.sleep(4)

        # Done.
        print('{0:02d}: Manoeuvre 4'.format(self.objID))
        self.close()


class ControllerCubeRight(ControllerCubeLeft):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.left = 1
        self.right = 0


def main():
    addr = config.addr_clerk

    # Controllers for columns 1, 2, 3, 4.
    CCL, CCR = ControllerCubeLeft, ControllerCubeRight
    group_1 = [CCL(4 * _ + 0, addr) for _ in range(1, 5)]
    group_2 = [CCL(4 * _ + 1, addr) for _ in range(1, 5)]
    group_3 = [CCR(4 * _ + 2, addr) for _ in range(1, 5)]
    group_4 = [CCR(4 * _ + 3, addr) for _ in range(1, 5)]

    # Start the cubes in the two outer columns.
    time.sleep(0.5)
    for p0, p1 in zip(group_1, group_4):
        p0.start()
        p1.start()
        time.sleep(0.5)

    # Start the cubes in the two inner columns.
    time.sleep(1)
    for p0, p1 in zip(group_2, group_3):
        p0.start()
        p1.start()
        time.sleep(0.5)
    print('done')


if __name__ == '__main__':
    main()
