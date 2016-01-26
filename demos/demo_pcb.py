# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""
Convenience wrapper around Azrael's Client module to streamline the
presentation at PyCon Australia 2015.

Setup
-----

To reproduce the demos from the presentation make sure you have the Azrael
Anaconda environment active and a running MongoDB instance (version should not
matter).

Then run

  >> python demo_boostercube.py --noviewer

and point your browser (Firefox or Chrome only) to http://localhost:8080


First Demo
----------

Will do little more than spawn an IPython shell to demonstrate the basic
commands of the PyConBrisbaneClient client.

  >> python demo_pcb.py basic


Second Demo
-----------

This one requires at least two terminals. First make sure to quit the program
from the previous demo. Then issue

  >> python demo_pcb.py reset

to clear the simulation and spawn two (or more) target objects with

  >> python demo_pcb.py target 2

Finally, open another terminal to spawn a ship that will try to match the
target's position (you can start several of these programs simultaneously to
create more ships):

  >> python demo_pcb.py ship

"""
import os
import sys
import time
import random
import demolib
import numpy as np

from IPython import embed as ipshell

import pyazrael
import azrael.aztypes as aztypes


def resetSimulation(host, port=5555):
    """
    Delete all objects in the scene.

    Azrael does not have a command to do that (yet), which is why this function
    queries all objects and the deletes them one-by-one.

    The `host` and `port` parameters specify the location of the Azrael API.
    """
    # Connect to Azrael.
    client = pyazrael.AzraelClient(host, port=port)

    # Query IDs of all objects in the simulation.
    ret = client.getAllObjectIDs()
    assert ret.ok
    allIDs = ret.data

    # Delete all objects.
    for objID in allIDs:
        assert client.removeObjects([objID]).ok


class PyConBrisbaneClient():
    """
    Demo class for the PyCon Brisbane 2015 presentation.

    This class wraps Azrael's client library specifically for the presentation.

    The `host` and `port` parameters specify the location of the Azrael API.
    """
    def __init__(self, host, port=5555):
        # Connect to Azrael.
        self.client = pyazrael.AzraelClient(host, port)

        # Ping Azrael. This call will block if it cannot connect.
        ret = self.client.ping()
        if not ret.ok:
            print('Could not connect to Azrael')
            assert False
        print('Connected to Azrael')

        # Initialise the ID of the target object (for now we have none). The
        # controller will attempt to match the position of that target when
        # this script was started with the 'ship' option (see main function).
        self.targetID = None

    def spawn(self, pos=(0, 0, 0)):
        """
        Spawn the ship at position `pos`.
        """
        # Compile the parameters for spawning the ship and send it to Azrael.
        ship_init = {
            'templateID': 'spaceship',
            'rbs': {
                'imass': 0.1,
                'position': pos,
                'rotFactor': [0, 0, 0],
            }
        }
        ret = self.client.spawn([ship_init])

        # Verify the call succeeded and record the ID of our space ship.
        assert ret.ok
        self.shipID = ret.data[0]
        print('Spawned spaceship', self.shipID)

    def getPosition(self):
        """
        Return the current position of the space ship.

        :return: the current position, eg [1, 2.5, -3.1]
        :rtype: NumPy array
        """
        # Query the state variables of the ship.
        ret = self.client.getObjectStates([self.shipID])
        if not ret.ok:
            print('Error getPosAndVel: ', ret.msg)
            sys.exit(1)

        # Extract the position value from the returned data structure.
        try:
            pos = ret.data[self.shipID]['rbs']['position']
            return np.array(pos, np.float64)
        except TypeError:
            sys.exit(1)

    def setScale(self, scale):
        """
        Change the size of the ship's geometry to `scale`.
        """
        assert scale >= 0

        cmd = {'frag_1': {'scale': scale}}
        return self.client.setFragments({self.shipID: cmd})

    def setPosition(self, pos):
        """
        Place the ship at position `pos`.
        """
        return self.setPositionAndVelocity(pos, (0, 0, 0))

    def setPositionAndVelocity(self, pos, vel):
        """
        Set the ship's position and velocity to ``pos`` and ``vel``.

        :param vec3 pos: position (eg. [1, 2, 3])
        :param vec3 vel: velocity (eg. [1, -2.5, -0.8])
        """
        # Send the update request to Azrael and check for errors.
        new = {self.shipID: {'position': pos, 'velocityLin': vel}}
        ret = self.client.setRigidBodyData(new)
        if not ret.ok:
            print('Error setPosAndVel: ', ret.msg)
        return ret

    def setBoosterForce(self, force):
        """
        Apply the constituent ``force`` components to the respective thruster.

        The net effect is that the ship will start to accelerate in the
        specified direction.

        :param vec-3 force: force (in Newton) of each booster.
        """
        # The ship has three boosters named 'b_x', 'b_y', and 'b_z'. The names
        # are hard coded in the template which the `demo_boostercube` script
        # generated (see doc string of this module). The thrusters are located
        # at the centre of the cube, even though visually the cube has 6
        # boosters, one on each surface. The  net effect is the same for this
        # simple demo, but it is a tad bit simpler to deal with.
        #
        # The following command specifies the amount of force to apply at each
        # booster.
        cmd_b = {
            'b_x': aztypes.CmdBooster(force=force[0]),
            'b_y': aztypes.CmdBooster(force=force[1]),
            'b_z': aztypes.CmdBooster(force=force[2]),
        }

        # Send the command to Azrael and wait for the reply.
        ret = self.client.controlParts(self.shipID, cmd_b, {})
        if not ret.ok:
            print('Error activating the boosters: ', ret.msg)
        return ret

    def setBoosterFlame(self, force):
        """
        Modify the geometry of the ship to provide visual feedback about the
        thrusters.

        The "flames" are blue spheres placed next to the thruster and scaled
        according to `force`. The flames are already part of the model. All we
        have to do is place- and scale them.

        This method will not activate any forces; it will only modify the
        visual appearance of the object to give visual feedback. The
        `activateBooster` method will use this method in conjunction
        with `setBoosterForce` to combine visual and physical effects of
        booster activation.
        """
        # Compute the size of the flame that comes out of the thruster, as well
        # as the distance of the flame from the cube's centre.
        flame_size = 0.1 * np.sqrt(np.abs(force))
        flame_pos = -np.sign(force) * (1.3 + flame_size)

        # The final position of the flame depends on which thruster was
        # activated.
        pos_x = np.array([flame_pos[0], 0, 0]).tolist()
        pos_y = np.array([0, flame_pos[1], 0]).tolist()
        pos_z = np.array([0, 0, flame_pos[2]]).tolist()
        flame_size = flame_size.tolist()

        # Compile the data for the updated state of the flame fragment.
        new_frags = {
            'b_x': {'scale': flame_size[0], 'position': pos_x},
            'b_y': {'scale': flame_size[1], 'position': pos_y},
            'b_z': {'scale': flame_size[2], 'position': pos_z},
        }

        # Send the update request to Azrael and check for errors.
        ret = self.client.setFragments({self.shipID: new_frags})
        if not ret.ok:
            print('Error setFragments: ', ret.msg)

    def activateBooster(self, force: (tuple, list, np.ndarray)):
        """
        Wrapper around :func:setBooster and :func:setFlame to give visual feedback.

        See :func:setBooster for the meaning of ``force`` and ``axis``.
        """
        # Sanity check: force must be a three element vector.
        assert isinstance(force, (tuple, list, np.ndarray))
        assert len(force) == 3

        # Activate the physics for the boosters.
        ret = self.setBoosterForce(force)
        if not ret.ok:
            return ret

        # Update the geometry to give visual feedback about which booster is
        # active and how strong.
        self.setBoosterFlame(force)

    def controller(self, pos_ref, dt, num_steps: int, verbose=False):
        """
        Use a simple control algorithm to manoeuvre the ship to `pos_ref`.

        The controller will execute ``num_steps`` force updates, one every `dt`
        seconds.
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

            # Engage the boosters with the newly computed force.
            self.activateBooster(force=force)
        return pos_log

    def selectNewTarget(self):
        """
        Find the ID of an object tagged with 'TARGET'.

        Another convenience function for the demo. It queries the tags of all
        objects in the scene, extracts those that start with 'TARGET', picks
        one of those randomly, and assigns it to an instance variable.
        """
        # Query the tags of all objects in the scene.
        ret = self.client.getObjectTags(None)
        assert ret.ok

        # Compile a list of all objIDs whose associated object has a 'TARGET'
        # tag.
        targetIDs = [k for (k, v) in ret.data.items()
                     if v.upper().startswith('TARGET')]

        if len(targetIDs) == 0:
            # None of the objects has the desired tag.
            self.targetID = None
        else:
            # Pick one of the targets at random.
            self.targetID = random.choice(targetIDs)
            print('Selected new target {}'.format(self.targetID))

    def findTargetPosition(self):
        """
        Return the position of the target for this instance.

        Call `selectNewTarget` beforehand to identify a target object first.
        """
        try:
            # Target ID must be valid (ie. `selectNewTarget` must have been
            # called already).
            assert self.targetID is not None

            # Query the state of the target object.
            ret = self.client.getObjectStates([self.targetID])
            assert ret.ok

            # Unpack the position from the rigid body state (rbs) data of the
            # object.
            position = ret.data[self.targetID]['rbs']['position']
        except (AssertionError, KeyError, TypeError):
            # Return None if an error has occurred.
            position = None
        return position


def placeTarget(host, numTargets=1):
    """
    Spawn ``numTargets`` in the scene.

    The targets visually oscillate in size. They also have no collision
    shapes and are thus unaffected by physics (ie they cannot collide
    with anything).
    """
    # Connect to Azrael.
    client = pyazrael.AzraelClient(ip=host)

    # Spawn the target object from the 'BoosterCube_1' template (defined in
    # 'demo_boostercube' that must already be running at this point).
    init = []
    for ii in range(numTargets):
        tmp = {
            'templateID': 'BoosterCube_1',
            'rbs': {'imass': 0, 'position': (0, 0, 3 * ii)}
        }
        init.append(tmp)
    ret = client.spawn(init)

    # Check for errors and abort if there are any.
    if not ret.ok:
        print(ret)
        sys.exit(1)

    # Extract the IDs of the spawned target objects.
    targetIDs = ret.data
    print('Spawned {} targets'.format(len(targetIDs)))
    del init, ret

    # Replace the collision shape with an empty one to disable the physics for
    # those targets.
    cs = aztypes.CollShapeEmpty()
    cs = aztypes.CollShapeMeta('empty', (0, 0, 0), (0, 0, 0, 1), cs)
    cmd = {targetID: {'cshapes': {'cssphere': cs}} for targetID in targetIDs}
    assert client.setRigidBodyData(cmd).ok
    del cs

    # Tag the object with target. This is necessary because the
    # `PyConBrisbaneClient.selectNewTarget` method will use to distinguish
    # targets from other objects.
    cmd = {targetID: 'Target' for targetID in targetIDs}
    assert client.setObjectTags(cmd)

    # Create a random phase offset in the oscillation pattern (pure eye candy
    # to avoid all targets scale synchronously).
    phi = 2 * np.pi * np.random.rand(len(targetIDs))

    # Modify the scale of the target every 100ms.
    cnt = 0
    while True:
        time.sleep(0.1)

        # Compile the payload for the update command, then send it to Azrael.
        # The fragment names (eg 'frag_1') are hard coded in the Template
        # (don't worry about them, just accept that they exist).
        cmd = {}
        for idx, targetID in enumerate(targetIDs):
            # Compute the new scale value.
            scale = 1 + np.sin(2 * np.pi * 0.1 * cnt + phi[idx])
            scale *= 0.1

            tmp = {
                'frag_1': {'scale': scale},
                'frag_2': {'scale': scale},
            }
            cmd[targetID] = tmp
        assert client.setFragments(cmd).ok

        # Randomly update the target's position every 10s.
        if (cnt % 100) == 0:
            cmd = {}
            for targetID in targetIDs:
                pos = 15 * np.random.rand(3) - 10
                cmd[targetID] = {'position': pos.tolist()}
            assert client.setRigidBodyData(cmd).ok
        cnt += 1


def controlShip(host, numShips=1):
    # Instantiate our space ship controller and spawn the ship.
    pcb = PyConBrisbaneClient(host)
    pcb.spawn(pos=(0, 0, -10))

    # Query the scene for possible targets and select one at random (this
    # assumes that some other program has run the 'placeTarget' function
    # already, possible from another external program).
    pcb.selectNewTarget()

    # Place the ship at a specific position.
    pcb.setPositionAndVelocity(pos=[0, 1, 2], vel=[1, 0, 0])

    # Activate the controller and print the ship's position over time.
    s = 'Ship position: x={:.1f}  y={:.1f}  z={:.1f}'
    target_pos_old = None
    while True:
        target_pos = pcb.findTargetPosition()
        if target_pos is None:
            time.sleep(1)
            continue

        # Print a message if the target's position has changed.
        if target_pos_old != target_pos:
            target_pos_old = target_pos
            print('\nNew target: ({:.1f}, {:.1f}, {:.1f})'.format(*target_pos))

        # Run the controller 5 times, once ever 0.2s.
        pcb.controller(target_pos, 0.2, 5)

        # Query the ship's new position and print it to screen.
        pos = pcb.getPosition()
        print('\r' + ' ' * 80 + '\r', end='', flush=True)
        print(s.format(*pos), end='', flush=True)
    print()

    # Remove the ship from the simulation.
    assert self.client.removeObject([self.shipID]).ok


def interactive(host):
    """
    For the interactive demo. The commented commands are the one I used on
    stage.
    """
    # pcb = PyConBrisbaneClient(host)

    # pcb.spawn()
    # pcb.scale(2)
    # pcb.scale(1)

    # pcb.setPosition((0, 0, 1))
    # pcb.getPosition()

    # pcb.setBoosterFlame((1, 2, 3))
    # pcb.setBoosterForce((0.1, 0.2, 1))
    ipshell()


def main():
    # Guess Azrael's IP address on the local computer.
    host = demolib.azService['clerk'].ip

    # We expect at least on script option to determine which function to run
    # (see below).
    if len(sys.argv) < 2:
        print('Must specify one of {basic, target, ship}')
        sys.exit(1)

    opt = sys.argv[1]
    if opt == 'basic':
        # Interactive demo.
        interactive(host)
    elif opt == 'target':
        # Spawn one or more targets.
        try:
            numTargets = int(sys.argv[2])
        except (IndexError, ValueError):
            numTargets = 1
        placeTarget(host, numTargets)
    elif opt == 'ship':
        # Make the ship match the position of a target.
        controlShip(host)
    elif opt == 'reset':
        # Delete all objects and spawn some Asteroids.
        resetSimulation(host)
    else:
        print('Unrecognised option {}'.format(opt))
        sys.exit(1)


if __name__ == '__main__':
    main()
