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
Control the sphere's position with the help of a Proportional-Differential (PD)
controller.

Use the ``demo_lockedsphere`` to start Azrael because this controller assumes
there exists a sphere with objID=1 in the scene, and that it has certain
boosters and geometry fragment.
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
from azrael.types import FragState
del p


class PDController():
    """
    A (P)roportional (D)ifferential Controller.

    The constructor defines the proportional- and differential gain factors.

    Once instantiated call the ``update`` method to retrieve the corrective
    forces for the next time step.
    """
    def __init__(self, K_p: float, K_d: float, dt: float):
        """
        Create a PD controller with the specified parameters.

        :param float K_p: gain for tracking error
        :param float K_d: gain for tracking error slope
        :param float dt: controller time step.
        """
        # Save the control parameters.
        self.K_p = K_p
        self.K_d = K_d
        self.dt = dt

        # Keep a history of past tracking errors because the differential
        # component will need it to compute the rate of change. This array has
        # several elements to allow for some smoothing.
        filter_len = 3
        self.err_past = np.zeros((filter_len, 3))

    def update(self, pos, ref_pos):
        """
        Return the corrective forces to move from ``pos`` towards ``ref_pos``.

        The force computation itself uses the PD control law, ie

          f = K_p * err + K_d * \frac{d}{dt} err

        :param 3-vec pos: current position
        :param 3-vec ref_pos: desired position
        :return: (force, error)
        :rtype: (3-vec, 3-vec)
        """
        # Convenience.
        err_past = self.err_past

        # Determine the value and slope of the tracking error.
        err_value = ref_pos - pos
        err_slope = (err_value - err_past[0, :]) / (len(err_past) * self.dt)

        # Compute the corrective force via the PD control law.
        force = self.K_p * err_value + self.K_d * err_slope

        # Throw away the oldest tracking error and add the most recent one.
        err_past[:-1] = err_past[1:]
        err_past[-1, :] = err_value

        # Limit the force values.
        force = force.clip(-10, 10)

        # Return the new force and latest tracking error.
        return force, err_past[-1]


def compileCommands(force):
    """
    Return the booster commands that correspond to the corrective ``force``.

    :param vec-3 force: force in all three dimensions.
    :return: list of Booster commands and fragment states.
    :rtype: tuple
    """
    # Convenience: neutral Quaternion.
    q = [0, 0, 0, 1]

    # Compile the commands for Azrael.
    cmds, frags = [], []
    for dim, frag_name in enumerate(('b_x', 'b_y', 'b_z')):
        # Force value for booster with ID `dim` (these were defined in
        # ``demo_lockedsphere``.
        cmds.append(parts.CmdBooster(partID=frag_name, force=force[dim]))

        # Scale the flame according to the booster force.
        scale = 3 * abs(force[dim])

        # Only one "flame" is visible in each direction. Which one depends on
        # whether we accelerate the object in the positive or negative "dim"
        # direction.
        pos = [0, 0, 0]
        if force[dim] < 0:
            # Pushing in negative direction.
            pos[dim] = 1.5
            frags.append(FragState(frag_name, scale, pos, q))
        else:
            # Pushing in positive direction.
            pos[dim] = -1.5
            frags.append(FragState(frag_name, scale, pos, q))

    return cmds, frags


def main(objID, ref_pos):
    """
    :param int objID: ID of sphere.
    :param float ref_pos: desired position in space.
    """
    # Connect to Azrael.
    client = azrael.client.Client()

    # Time step for polling/updating the booster values.
    dt = 0.3

    # Instantiate a PD controller.
    PD = PDController(K_p=0.1, K_d=0.1, dt=dt)

    # Periodically query the sphere's position, pass it to the controller to
    # obtain the force values to moved it towards the desired position, and
    # send those forces to sphere's boosters.
    while True:
        # Query the sphere's position.
        ret = client.getBodyStates([objID])
        assert ret.ok
        pos = ret.data[objID]['sv'].position

        # Call the controller with the current- and desired position.
        force, err = PD.update(pos, ref_pos)

        # Create the commands to apply the forces and visually update the
        # "flames" coming out of the boosters.
        forceCmds, fragStates = compileCommands(force)

        # Send the force commands to Azrael.
        assert client.controlParts(objID, forceCmds, []).ok

        # Send the updated fragment- sizes and position to Azrael.
        assert client.setFragmentStates({objID: fragStates}).ok

        # Dump some info.
        print('Pos={0:+.2f}, {1:+.2f}, {2:+.2f}  '
              'Err={3:+.2f}, {4:+.2f}, {5:+.2f}  '
              'Force={6:+.2f}, {7:+.2f}, {8:+.2f}'
              .format(pos[0], pos[1], pos[2],
                      err[0], err[1], err[2],
                      force[0], force[1], force[2]))

        # Wait one time step.
        time.sleep(dt)


if __name__ == '__main__':
    # Desired position of sphere.
    _ref_pos = -7 * np.ones(3)

    # Read object ID from command line or use a default value.
    if len(sys.argv) < 2:
        _objID = 1
    else:
        _objID = int(sys.argv[1])

    # Instantiate the controller and start it in this thread.
    main(_objID, _ref_pos)
