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

import pyazrael
import azrael.util as util
import azrael.config as config


def startController(objID):
    """
    Alternately apply an up/down force to itself.

    This is a simplistic demo of how a controller script can influence an
    object in the simulation.
    """
    # Connect to Clerk.
    client = pyazrael.AzraelClient()

    # Specify the toggle interval in seconds.
    toggle_interval = 4.0

    # Fire the booster asymmetrically to get the object spinning.
    cmd_0 = aztypes.CmdBooster(partID='0', force=1.0)
    cmd_1 = aztypes.CmdBooster(partID='1', force=0.9)
    client.controlParts(objID, [cmd_0, cmd_1], [])
    time.sleep(0.1)

    # Turn off the boosters and prevent further angular acceleration.
    cmd_0 = aztypes.CmdBooster(partID='0', force=0)
    cmd_1 = aztypes.CmdBooster(partID='1', force=0)
    client.controlParts(objID, [cmd_0, cmd_1], [])
    time.sleep(toggle_interval)

    # Define the commands to spawn objects from factory.
    cmd_2 = aztypes.CmdFactory(partID='0', exit_speed=0.1)
    cmd_3 = aztypes.CmdFactory(partID='1', exit_speed=0.9)

    # Periodically apply a boost and spawn objects.
    while True:
        # Turn the boosters on (symmetrically).
        cmd_0 = aztypes.CmdBooster(partID='0', force=5)
        cmd_1 = aztypes.CmdBooster(partID='1', force=5)
        client.controlParts(objID, [cmd_0, cmd_1], [])
        time.sleep(1)

        # Turn the boosters off.
        cmd_0 = aztypes.CmdBooster(partID='0', force=0)
        cmd_1 = aztypes.CmdBooster(partID='1', force=0)
        client.controlParts(objID, [cmd_0, cmd_1], [])
        time.sleep(toggle_interval)

        # Spawn objects.
        client.controlParts(objID, [], [cmd_2, cmd_3])
        time.sleep(toggle_interval)


def main():
    # Read object ID from command line or use a default value.
    if len(sys.argv) < 2:
        objID = 1
    else:
        objID = sys.argv[1]

    # Instantiate the controller and start it in this thread.
    startController(int(objID))
    print('done')


if __name__ == '__main__':
    main()
