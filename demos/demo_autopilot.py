"""
This module contains a convenience wrapper around Azrael's Client module to
streamline the presentation at PyCon Australia 2015.

Use this class in conjunction with the 'demos/demo_boostercube.py' and the
IPython notebook 'pydata_dallas.py'.
"""
import os
import sys
import time
import numpy as np

# Import the necessary Azrael modules.
p = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(p, '../'))
import azrael.client
import azrael.types as types
del p


class PyConBrisbaneClient():
    """
    Wraps Client *specifically* for 'demos/demo_boostercube.py'.
    """
    def __init__(self, ip='127.0.0.1', port=5555):
        # Connect to Azrael.
        self.client = azrael.client.Client(ip=ip, port=port)

        # Ping Azrael. This call will block if it cannot connect.
        ret = self.client.ping()
        if not ret.ok:
            print('Could not connect to Azrael')
            assert False
            
        # The ID of the ship with the booster. This assumption is only valid if
        # Azrael runs the 'demo_boostercube.py' simulation.
        self.shipID = 1
        print('Connected')

        # Take a snapshot of the current simulation, in particular the position
        # of all objects.
        ret = self.client.getObjectStates(None)
        assert ret.ok
        self.allowed_objIDs = ret.data

    def reset(self, mass=None):
        """
        Reset the position of all the cubes and update their mass.
        """
        # Turn off all boosters.
        self.boosterForce([0,0,0])

        # Convert the mass to an inverse mass.
        if mass is None:
            imass = 1
        else:
            imass = 1 / mass

        # Periodically reset the SV values. Set them several times because it
        # is well possible that not all State Variables reach Leonard in the
        # same frame, which means some objects will be reset while other are
        # not. This in turn may cause strange artefacts in the next physics
        # update step, especially when the objects now partially overlap.

        # Remove all newly added objects.
        ret = self.client.getAllObjectIDs()
        for objID in ret.data:
            if objID not in self.allowed_objIDs:
                self.client.removeObject(objID)

        # Forcefully reset the position and velocity of every object. Do
        # this several times since network latency may result in some
        # objects being reset sooner than others.
        reset_val = {}
        for objID, body in self.allowed_objIDs.items():
            # Do not reset the state of the ship itself.
            if objID == self.shipID:
                continue

            # Compile the new motion state.
            reset_val[objID] = {
                'imass': imass,
                'position': body['rbs']['position'],
                'velocityLin': body['rbs']['velocityLin'],
                'velocityRot': body['rbs']['velocityRot'],
                'rotation': body['rbs']['rotation']
            }

        for ii in range(3):
            self.client.setRigidBodies(reset_val)
            time.sleep(0.1)

    def asteroids(self, mass=None):
        """
        Assign random positions and velocities to the cubes. This will create
        an "asteroid" field effect.
        """
        # Convert the mass to an inverse mass.
        if mass is None:
            imass = 1
        else:
            imass = 1 / mass

        # Iterate over all objects and assign a random position and velocity.
        new_states = {}
        for objID, body in self.allowed_objIDs.items():
            # Do not alter the position of the ship.
            if objID == self.shipID:
                continue

            # Create a random position and velocity.
            spread = 5
            pos = spread * (2 * np.random.rand(3) - 1)
            pos += [0, 0, 5 + spread]
            vel_lin = 0 * 0.2 * (2 * np.random.rand(3) - 1)
            vel_rot = 2 * np.random.rand(3) - 1

            # Compile the new motion state and apply it.
            new_states[objID] = {
                'imass': imass,
                'position': list(pos),
                'velocityLin': list(vel_lin),
                'velocityRot': list(vel_rot),
            }

        for ii in range(1):
            assert self.client.setRigidBodies(new_states).ok
            time.sleep(0.1)

    def getPosition(self):
        """
        Return the current position of our space ship.

        :return: the current position, eg [1, 2.5, -3.1]
        :rtype: NumPy array
        """
        # Query the state variables of the ship.
        ret = self.client.getObjectStates([self.shipID])
        if not ret.ok:
            print('Error getPosAndVel: ', ret.msg)
            return None, None

        # Extract the position value from the returned data structure.
        pos = ret.data[self.shipID]['rbs']['position']
        return np.array(pos, np.float64)

    def setPositionAndVelocity(self, pos, vel):
        """
        Set the ship's position and velocity to ``pos`` and ``vel``.

        :param vec3 pos: position (eg. [1, 2, 3])
        :param vec3 vel: velocity (eg. [1, -2.5, -0.8])
        """
        # Send the update request to Azrael and check for errors.
        new = {self.shipID: {'position': pos, 'velocityLin': vel}}
        ret = self.client.setRigidBodies(new)
        if not ret.ok:
            print('Error setPosAndVel: ', ret.msg)
        return ret

    def activateBooster(self, force):
        """
        Apply the constituent ``force`` components to the respective thruster.

        The net effect is that the ship will start to accelerate in the
        specified direction.

        :param vec-3 force: force (in Newton) of each booster.
        """
        # The ship has three boosters named 'b_x', 'b_y', and 'b_z'. These are
        # all located at the centre of the cube, even though visually the cube
        # has 6 boosters, one on each surface. The  net effect is the same for
        # this simple demo, but it is a tad bit simpler to deal with.
        cmd_b = {
            'b_x': types.CmdBooster(force_mag=force[0]),
            'b_y': types.CmdBooster(force_mag=force[1]),
            'b_z': types.CmdBooster(force_mag=force[2]),
        }

        # Send the command to Azrael and wait for the reply.
        ret = self.client.controlParts(self.shipID, cmd_b, {})
        if not ret.ok:
            print('Error activating the boosters: ', ret.msg)
        return ret

    def boosterForce(self, force: (tuple, list, np.ndarray)):
        """
        Wrapper around :func:setBooster and :func:setFlame to give visual feedback.

        See :func:setBooster for the meaning of ``force`` and ``axis``.
        """
        # Sanity check: force must be a three element vector.
        assert isinstance(force, (tuple, list, np.ndarray))
        assert len(force) == 3

        # Activate the boosters.
        ret = self.activateBooster(force)
        if not ret.ok:
            return ret

        # Place a "flame" next to each thruster and scale it according to the
        # applied force.
        self.setBoosterFlame(force)
        
    def setBoosterFlame(self, force):
        # Compute the size of the flame that comes out of the thruster, as well
        # as the distance of the flame from the cube's centre.
        flame_size = 0.1 * np.sqrt(np.abs(force))
        flame_pos = -np.sign(force) * (0.8 + flame_size)

        # The final position of the flame depends on which thruster was
        # activated.
        pos_x = np.array([flame_pos[0], 0, 0]).tolist()
        pos_y = np.array([0, flame_pos[1], 0]).tolist()
        pos_z = np.array([0, 0, flame_pos[2]]).tolist()
        flame_size = flame_size.tolist()

        # Compile the data for the updated state of the flame fragment.
        new_frags = {
            'b_x': {'scale': flame_size[0], 'position': [flame_pos[0], 0, 0]},
            'b_y': {'scale': flame_size[1], 'position': [flame_pos[1], 0, 0]},
            'b_z': {'scale': flame_size[2], 'position': [flame_pos[2], 0, 0]},
        }

        # Send the update request to Azrael and check for errors.
        ret = self.client.setFragments({self.shipID: new_frags})
        if not ret.ok:
            print('Error setFragments: ', ret.msg)

    def controller(self, pos_ref, dt, num_steps: int):
        """
        Manoeuvre cube to ``dst`` position.
        """
        # Periodically query the position, compute the error relative to the
        # desired reference position, and engage the thrusters accordingly.
        time.sleep(dt)
        pos_log = [self.getPosition()]
        for ii in range(num_steps):
            # Wait.
            time.sleep(dt)

            # Query current position and add it to the log.
            p = self.getPosition()
            pos_log.append(p)

            # Compute the position error and its slope.
            err_val = pos_ref - pos_log[ii + 1]
            err_slope = (pos_log[ii + 1] - pos_log[ii]) / dt

            # Determine the booster output with a Proportional-Differential
            # Controller.
            force = 10 * err_val - 8 * err_slope

            # Update the booster values
            self.boosterForce(force=force)
        return pos_log


def main():
    # Connect to Azrael at the specified IP address.
    ip = 'IP of Azrael goes here'
    ip = '127.0.0.1'
    client = PyConBrisbaneClient(ip=ip)

    # Disable all boosters.
    client.boosterForce([0, 0, 0])

    # Wait a bit to ensure Azrael has picked up the command yet.
    time.sleep(0.5)

    client.asteroids()
    time.sleep(3)
    client.reset()

    assert client.setPositionAndVelocity(pos=[0, 1, 2], vel=[1, 0, 0]).ok
    client.controller([5, 5, 5], 0.2, 10000)
    client.reset()
    return

    # Place the ship at a specific position and give it a velocity. The query
    # its position over time.
    assert client.setPositionAndVelocity(pos=[0, 1, 2], vel=[1, 0, 0]).ok
    for ii in range(3):
        time.sleep(1)
        pos = client.getPosition()
        print('Ship position: x={:.1f}  y={:.1f}  z={:.1f}'.format(*pos))

    # Reset all object states except the ship (typically this simply resets the
    # addition cubes in the simulation).
    client.reset()
    for ii in range(3):
        time.sleep(1)
        pos = client.getPosition()
        print('Ship position: x={:.1f}  y={:.1f}  z={:.1f}'.format(*pos))


if __name__ == '__main__':
    main()
