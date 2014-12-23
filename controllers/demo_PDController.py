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
A Proportional-Differential (PD) controller to maintain the sphere's position
at a constant value.
"""

import os
import sys
import time
import setproctitle

import numpy as np

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
    def PDController(self, ref_pos_z):
        """
        A PD controller to maintain the object's z-position at ``ref_pos``.

        This controller makes several assumption with respect to the booster
        orientations, most notably that booster with partID=1 and partID=2
        point forwards and backwards, respectively. Furthermore, it assumes the
        sphere cannot rotate. To guarantee this the sphere's rotation axes
        should all be locked.

        :param float ref_pos_z: keep the object at this z-position.
        """
        # Time step for polling/updating the booster values.
        dt = 0.3

        # Parameters of PD controller (work in tandem with time step dt).
        K_p, K_d = 5, 10

        # Query the sphere's initial position.
        pos = self.getStateVariables([self.objID])
        pos = pos[1][self.objID].position[2]

        # Keep a history of past errors because the differential component will
        # need it to compute the rate of change. This array has several
        # elements to allow for some smoothing.
        filter_len = 3
        err_log = [ref_pos_z - pos] * (filter_len + 1)

        # Run the controller.
        while True:
            # Compute the error between current and expected position.
            err = ref_pos_z - pos
            err_log.pop(0)
            err_log.append(err)

            # PD Controller.
            force = K_p * err_log[-1]
            force += K_d * (err_log[-1] - err_log[0]) / (filter_len * dt)

            # The sign of the desired force determines which booster (front or
            # back) to activate. This is necessary because boosters can only
            # apply positive forces along their axis of orientation. Maybe one
            # day I will add boosters that allow both directions, but this code
            # utilises two boosters facing each other (one at the front of the
            # sphere, the other at the back).
            if force > 0:
                force_1 = abs(force)
                force_3 = 0
            else:
                force_1 = 0
                force_3 = abs(force)

            # Send new force values to boosters.
            b0 = parts.CmdBooster(partID=1, force=force_1)
            b1 = parts.CmdBooster(partID=3, force=force_3)
            self.controlParts(self.objID, [b0, b1], [])

            # Wait one time step.
            time.sleep(dt)

            # Query the sphere's position.
            pos = self.getStateVariables([self.objID])
            pos = pos[1][self.objID].position[2]

            # Dump some info.
            print('Pos={0:+.3f}  Err={1:+.3f}  Force={2:+.3f}'
                  .format(pos, err_log[-1], force))

    def run(self):
        # Boiler plate: setup
        print('Connecting to Azrael...', flush=True, end='')
        self.setupZMQ()
        self.connectToClerk()
        print('done')

        # Wait a bit before starting the controller.
        print('Starting controller...', flush=True, end='')
        time.sleep(2)
        print('done')

        # Keep the sphere at z=-5.0
        self.PDController(ref_pos_z=-5.0)


def main():
    if len(sys.argv) < 2:
        objID = 2
    else:
        objID = sys.argv[1]

    # Read the object from the command line.
    objID = util.int2id(int(objID))

    # Rename this process to ensure it is easy to find and kill.
    name = 'killme Controller {}'.format(util.id2int(objID))
    setproctitle.setproctitle(name)

    # Instantiate the controller and start it in this thread.
    ctrl = ControllerSphere(objID, config.addr_clerk)
    ctrl.run()
    print('done')


if __name__ == '__main__':
    main()
