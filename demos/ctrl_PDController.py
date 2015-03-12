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
A Proportional-Differential (PD) controller to maintain the sphere's position.

The parameters for the PD controller were empirically chosen because Azrael's
current implementation neither guarantees constant update intervals provides
the internal simulation time. For now, these shortcomings severely limit the
use of control theory methods.
"""

import os
import sys
import time
import numpy as np

# Import the necessary Azrael modules.
p = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(p, '../'))
import azrael.client
import azrael.parts as parts
from azrael.util import FragState
del p


def PDController(client, objID, ref_pos):
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
    K_p, K_d = 0.1, 0.1

    ref_pos = np.array(ref_pos)
    
    # Query the sphere's initial position.
    ret = client.getStateVariables([objID])
    pos = ret.data[objID]['sv'].position

    # Keep a history of past errors because the differential component will
    # need it to compute the rate of change. This array has several
    # elements to allow for some smoothing.
    filter_len = 3
    err_log = np.zeros((filter_len, 3))
    err_log[:] = ref_pos - pos

    # Run the controller.
    while True:
        # Determine the value and slope of the tracking error.
        err_value = ref_pos - pos
        err_slope = (err_value - err_log[0, :]) / (filter_len * dt)

        # Compute the PD control law.
        force = K_p * err_value + K_d * err_slope

        # Record the error value for the next iteration.
        err_log[:-1] = err_log[1:]
        err_log[-1, :] = err_value
        del err_value, err_slope

        # The sign of the desired force determines which booster (front or
        # back) to activate. This distinction is necessary because boosters can
        # only  apply positive forces along their axis of orientation. Maybe
        # one day I will add boosters that allow both directions, but this code
        # utilises two boosters facing each other (one at the front of the
        # sphere, the other at the back).
        # Furthermore, specify the Quaternion for the "flame" coming out of the
        # booster, either neutral or inverted around the x-axis.
        if force[2] > 0:
            force_1 = abs(force[2])
            force_3 = 0
            fs_q = [0, 0, 0, 1]
        else:
            force_1 = 0
            force_3 = abs(force[2])
            fs_q = [1, 0, 0, 0]

        # Send new force values to boosters.
        b0 = parts.CmdBooster(partID=1, force=force_1)
        b1 = parts.CmdBooster(partID=3, force=force_3)
        client.controlParts(objID, [b0, b1], [])

        # Update the booster fragments to provide some visual feedback for the
        # booster output. Currently, all we do is scale the "flame" coming out
        # of the booster and point it forwards or backwards.
        fs_scale = 2 * abs(force[2])
        newStates = {objID: [
            FragState('b_left', fs_scale, [-1.25 - 0.5, 0, 0], fs_q),
            FragState('b_right', fs_scale, [1.25 + 0.5, 0, 0], fs_q),
            ]}
        assert client.updateFragmentStates(newStates).ok
        del fs_scale, fs_q

        # Wait one time step.
        time.sleep(dt)

        # Query the sphere's position.
        ret = client.getStateVariables([objID])
        pos = ret.data[objID]['sv'].position

        # Dump some info.
        print('Pos={0:+.3f}  Err={1:+.3f}  Force={2:+.3f}'
              .format(pos[2], err_log[-1][2], force[2]))


def startController(objID):
    # Boiler plate: setup
    print('Connecting to Azrael...', flush=True, end='')
    client = azrael.client.Client()
    print('done')

    # Wait a bit before starting the controller.
    print('Starting controller...', flush=True, end='')
    time.sleep(2)
    print('done')

    # Keep the sphere at z=-5.0
    ref_pos = -5 * np.ones(3)
    PDController(client, objID, ref_pos=ref_pos)


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
