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
Controller class for the BoosterCube ship.

When you run this file a script it will spawn a BoosterCube and visit 5
different locations. These locations match those of the platforms created
by 'demo_platform', but the demo will run with other Azrael simulations as
well.
"""

import os
import sys
import time
import demolib
import numpy as np
from IPython import embed as ipshell

# Import the necessary Azrael modules.
p = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(p, '../'))
import pyazrael
import pyazrael.aztypes as aztypes

from pyazrael.aztypes import Template


def BoostercubeTemplate(scale=1.0):
    """
    Return template for BoosterCube.
    """
    # Get a Client instance.
    client = pyazrael.AzraelClient()

    # Load the model.
    vert, uv, rgb = demolib.loadBoosterCubeBlender()
    frag_cube = {'vert': vert, 'uv': uv, 'rgb': rgb, 'scale': scale,
                 'pos': (0, 0, 0), 'rot': (0, 0, 0, 1)}
    del vert, uv, rgb

    # Attach six boosters, two for every axis.
    dir_x = np.array([1, 0, 0])
    dir_y = np.array([0, 1, 0])
    dir_z = np.array([0, 0, 1])
    pos = (0, 0, 0)
    B = aztypes.Booster
    boosters = {
        'b_x': B(pos, direction=(1, 0, 0), minval=0, maxval=10.0, force=0),
        'b_y': B(pos, direction=(0, 1, 0), minval=0, maxval=10.0, force=0),
        'b_z': B(pos, direction=(0, 0, 1), minval=0, maxval=10.0, force=0)
    }
    del dir_x, dir_y, dir_z, pos, B

    # Load sphere and color it blue(ish). This is going to be the (super
    # simple) "flame" that comes out of the (still invisible) boosters.
    p = os.path.dirname(os.path.abspath(__file__))
    fname = os.path.join(p, 'models', 'sphere', 'sphere.obj')
    vert, uv, rgb = demolib.loadModel(fname)
    rgb = np.tile([0, 0, 0.8], len(vert) // 3)
    rgb += 0.2 * np.random.rand(len(rgb))
    rgb = np.array(255 * rgb.clip(0, 1), np.uint8)
    frag_flame = {'vert': vert, 'uv': [], 'rgb': rgb,
                  'pos': (0, 0, 0), 'rot': (0, 0, 0, 1)}
    del p, fname, vert, uv, rgb

    # Add the template to Azrael.
    tID = 'spaceship'
    cs = aztypes.CollShapeBox(scale, scale, scale)
    cs = aztypes.CollShapeMeta('box', (0, 0, 0), (0, 0, 0, 1), cs)
    body = demolib.getRigidBody(cshapes={'0': cs})
    frags = {
        'frag_1': demolib.getFragMetaRaw(**frag_cube),
        'b_x': demolib.getFragMetaRaw(**frag_flame),
        'b_y': demolib.getFragMetaRaw(**frag_flame),
        'b_z': demolib.getFragMetaRaw(**frag_flame),
    }
    template = Template(tID, body, frags, boosters, {})
    return template


class CtrlBoosterCube():
    """
    Controller for BoosterCube.

    This class merely wraps the Azrael client to provide a high(er) level
    interface to spawn and control the BoosterCube space ship.

    The `host` and `port` parameters specify the location of the Azrael API.
    """
    def __init__(self, host, port=5555):
        self.shipID = None

        # Connect to Azrael.
        self.client = pyazrael.AzraelClient(addr_clerk=host, port_clerk=port)

        # Ping Azrael. This call will block if it cannot connect.
        ret = self.client.ping()
        if not ret.ok:
            print('Could not connect to Azrael')
            assert False
        print('Connected to Azrael')

        print('Addding template for this ship...', flush=True, end='')
        template = BoostercubeTemplate(scale=1.0)
        self.client.addTemplates([template])
        print('done')

    def __del__(self):
        if self.shipID is None:
            return
        self.client.removeObjects([self.shipID])
        self.shipID = None

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
        ret = self.client.setRigidBodies(new)
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
        cmd = {
            'b_x': {
                'op': 'mod',
                'scale': flame_size[0],
                'position': pos_x,
            },
            'b_y': {
                'op': 'mod',
                'scale': flame_size[1],
                'position': pos_y,
            },
            'b_z': {
                'op': 'mod',
                'scale': flame_size[2],
                'position': pos_z
            }
        }
        cmd = {self.shipID: cmd}
        ret = self.client.setFragments(cmd)
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


def main():
    # Guess Azrael's IP address on the local computer.
    ip = demolib.getNetworkAddress()

    # Instantiate the controller for a BoosterCube ship. Then spawn it.
    c = CtrlBoosterCube(ip)
    c.spawn((0, 5, 0))

    # Successively manoeuvre the ship above each platform.
    time.sleep(5)
    for ii in range(5):
        pos_ref = (ii * 5, -ii * 2 + 0.5 + 2, ii * 5)
        c.controller(pos_ref, dt=0.1, num_steps=50, verbose=False)
    del c


if __name__ == '__main__':
    main()
