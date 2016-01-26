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
A simple Asteroids game with Azrael.
"""
import time
import json
import argparse
import demolib
import numpy as np

# Import the necessary Azrael modules.
import azrael.clerk
import azrael.startup
import azrael.eventstore
import azrael.config as config
import azrael.aztypes as aztypes

from IPython import embed as ipshell
from azrael.aztypes import Template


def parseCommandLine():
    """
    Parse program arguments.
    """
    # Create the parser.
    parser = argparse.ArgumentParser(
        description=('Azrael Asteroid Demo'),
        formatter_class=argparse.RawTextHelpFormatter)

    # Shorthand.
    padd = parser.add_argument

    # Add the command line options.
    padd('--noviewer', action='store_true', default=False,
         help='Do not spawn a viewer')
    padd('-N', metavar='', type=int, default=3,
         help='Number of Asteroids to spawn (default=3)')
    padd('--loglevel', type=int, metavar='level', default=1,
         help='Specify error log level (0: Debug, 1:Info)')
    padd('--reset-interval', type=int, metavar='T', default=None,
         help='Reset simulation every T seconds (default: never/None)')

    # Run the parser.
    param = parser.parse_args()
    return param


def getLargeAsteroidTemplate(hlen):
    """
    Return the template for a large asteroid.

    A large asteroids consists of multiple 6 patched together cubes. Each cube
    has a half length of ``hlen``.
    """
    def _randomise(scale, pos):
        pos = scale * np.random.uniform(-1, 1, 3) + pos
        return pos.tolist()

    # Geometry and collision shape for a single cube.
    vert, csmetabox = demolib.cubeGeometry(hlen, hlen, hlen)

    # Define the positions of the individual cubes/fragments in that will
    # constitute the Asteroid. The positions are slightly randomised to make the
    # Asteroids somewhat irregular.
    ofs = 1.5 * hlen
    noise = 0.6
    frag_src = {
        'up': _randomise(noise, [0, ofs, 0]),
        'down': _randomise(noise, [0, -ofs, 0]),
        'left': _randomise(noise, [ofs, 0, 0]),
        'right': _randomise(noise, [-ofs, 0, 0]),
        'front': _randomise(noise, [0, 0, ofs]),
        'back': _randomise(noise, [0, 0, -ofs]),
    }
    del ofs

    # Patch together the fragments that will constitute the geometry of a
    # single large Asteroid. While at it, also create the individual collision
    # shapes for each fragment (not part of the geometry but needed
    # afterwards).
    frags, cshapes = {}, {}
    for name, pos in frag_src.items():
        frags[name] = demolib.getFragMetaRaw(
            vert=vert,
            uv=[],
            rgb=[],
            scale=1,
            pos=pos,
            rot=[0, 0, 0, 1],
        )

        # Collision shape for this fragment.
        cshapes[name] = csmetabox._replace(position=pos)
        del name, pos
    del frag_src

    # Specify the physics of the overall bodies.
    body = demolib.getRigidBody(
        imass=0.01,
        inertia=[3, 3, 3],
        cshapes=cshapes,
    )

    # Return the completed Template.
    return Template('Asteroid_large', body, frags, {}, {})


def getSmallAsteroidTemplate(hlen):
    """
    Return the template for a small asteroid.

    A small asteroid is merely a cube with half length ``hlen``.
    """
    vert, cshapes = demolib.cubeGeometry(hlen, hlen, hlen)

    # Define the geometry of the Asteroids.
    fm = demolib.getFragMetaRaw(
        vert=vert,
        uv=[],
        rgb=[],
        scale=1,
        pos=(0, 0, 0),
        rot=(0, 0, 0, 1)
    )
    frags = {'frag_1': fm}

    # Define the physics parameters for the Asteroids.
    body = demolib.getRigidBody(
        imass=80,
        inertia=[1, 1, 1],
        cshapes={'cs': cshapes},
    )

    return Template('Asteroid_small', body, frags, {}, {})


def addAsteroids(num_asteroids):
    """
    Spawn ``num_asteroids`` and return their IDs.

    The initial position of the asteroids is always the same. Their initial
    velocity vector is random.
    """
    # Connect to Azrael.
    client = azrael.clerk.Clerk()

    # Upload a template for large and small Asteroids.
    assert client.addTemplates([
        getLargeAsteroidTemplate(hlen=1.5),
        getSmallAsteroidTemplate(hlen=0.5),
    ]).ok

    # Spawn the asteroids in fixed positions but random initial velocities.
    asteroids = []
    for ii in range(num_asteroids):
        asteroids.append({
            'templateID': 'Asteroid_large',
            'rbs': {
                'position': (-10 + ii * 10, -ii * 5, -20),
                'velocityLin': list(np.random.uniform(-1, 1, 3)),
                'velocityRot': list(np.random.uniform(-1, 1, 3)),
            },
            'custom': 'asteroid_large_{}'.format(ii),
        })
    ret = client.spawn(asteroids)
    assert ret.ok
    return tuple(ret.data)


class Simulation(azrael.eventstore.EventStore):
    """
    Govern the simulation, keep score, split large Asteroids into smaller one
    upon impact.
    """
    def __init__(self, viewer, num_asteroids, reset_interval, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Store arguments.
        self.viewer = viewer
        self.num_asteroids = num_asteroids
        self.reset_interval = reset_interval
        self.next_reset = reset_interval

        # Connect to Azrael.
        self.client = azrael.clerk.Clerk()

        # IDs of all (small and large) asteroids.
        self.asteroidsSmall = set()
        self.asteroidsLarge = set()

        # The scoreboard.
        self.scoreboard = {}

        # Reset the simulation.
        self.reset()

    def onMessage(self):
        """
        If a projectile collided with an Asteroid that take action.

        This method triggers whenever a collision event arrives via the
        EventStore.
        """
        # Query the messages and decode them.
        msg = self.getMessages().data
        msg = [json.loads(_body.decode('utf8')) for (_topic, _body) in msg]

        # Iterate over all messages, each of which contains the pair of objects
        # that collides, as well as the associated list of collision positions
        # (which we don't care about here).
        pairs = set()
        for m in msg:
            for (aidA, aidB, _) in m:
                pairs.add((aidA, aidB))
        bodies = [body for pair in pairs for body in pair]

        # Query their tags to determine what collided with what.
        ret = self.client.getObjectTags(bodies)
        assert ret.ok
        tags = ret.data
        del ret

        all = self.asteroidsLarge.union(self.asteroidsSmall)
        for (aidA, aidB) in pairs:
            # Continue if the collision is not between an Asteroid and a
            # projectile.
            if len(all.intersection([aidA, aidB])) != 1:
                continue

            # Determine which object was the Asteroid.
            if aidA in all:
                aidAsteroid = aidA
                aidOther = aidB
            else:
                aidAsteroid = aidB
                aidOther = aidA

            # Determine if the other other object was a projectile. If not then
            # do nothing and skip to the next pair (we only care about
            # collisions between Asteroids and projectiles).
            try:
                tmp = json.loads(tags[aidOther])
                assert tmp['name'] == 'projectile'
                assert tmp['type'] in ['A', 'B']
                player_id = tmp['parent']
                score = 2 if tmp['type'] == 'B' else 1
                del tmp
            except (AssertionError, json.JSONDecodeError, KeyError, TypeError):
                continue

            # Update score board based on player and projectile type. That
            # information is JSON encoded in the tag.
            if player_id not in self.scoreboard:
                self.scoreboard[player_id] = 0
            self.scoreboard[player_id] += score
            del player_id, score

            # Query the state variables of the Asteroid.
            state = self.client.getObjectStates([aidAsteroid])
            state = state.data[aidAsteroid]['rbs']
            del aidA, aidB, aidOther

            # Delete the Asteroid and projectile.
            self.client.removeObjects(bodies)

            # Split large Asteroids into smaller pieces.
            if aidAsteroid in self.asteroidsLarge:
                self.splitAsteroids(state, 4)

            # Remove the asteroid ID from the sets of large and small asteroids
            # (should only be in a single set but to be safe we discard it from
            # both).
            self.asteroidsLarge.discard(aidAsteroid)
            self.asteroidsSmall.discard(aidAsteroid)

            print('{} large Asteroids left'.format(len(self.asteroidsLarge)))
            print('{} small Asteroids left'.format(len(self.asteroidsSmall)))
            print('Score: ', self.scoreboard)

    def splitAsteroids(self, state, N):
        """
        Spawn `N` small asteroids based on the position/velocity in `state`.
        """
        ru = np.random.uniform

        bodies = []
        for ii in range(N):
            pos = state['position'] + 2 * ru(-1, 1, 3)
            vLin = state['velocityLin'] + 1 * ru(-1, 1, 3)
            vRot = state['velocityRot'] + 1 * ru(-1, 1, 3)
            bodies.append({
                'templateID': 'Asteroid_small',
                'rbs': {
                    'position': list(pos),
                    'velocityLin': list(vLin),
                    'velocityRot': list(vRot),
                },
                'custom': 'asteroid_small',
            })

        ret = self.client.spawn(bodies)
        assert ret.ok
        for aid in ret.data:
            self.asteroidsSmall.add(aid)

    def onTimeout(self):
        """
        Shut down the simulation when the user closes the viewer (if any was
        started with this simulation).
        """
        # End the simulation if all asteroids have been destroyed.
        if self.asteroidsLarge == self.asteroidsSmall == set():
            print('Game finished')
            if self.viewer is not None:
                self.viewer.terminate()
            self.rmq['chan'].stop_consuming()

        # End the simulation if the viewer was closed (assuming there was one
        # to begin with).
        if (self.viewer is not None) and (self.viewer.poll() is not None):
            self.rmq['chan'].stop_consuming()

        # Periodically reset the simulation.
        if (self.next_reset is not None) and (time.time() >= self.next_reset):
            self.reset()

    def reset(self):
        """
        Put the simulation in the default state.
        """
        # Delete all asteroids.
        assert self.client.removeObjects(list(self.asteroidsLarge)).ok
        assert self.client.removeObjects(list(self.asteroidsSmall)).ok

        # Reset the scoreboard and reset timeout.
        self.scoreboard = {}
        if self.next_reset is not None:
            self.next_reset = time.time() + self.reset_interval

        # Repopulate the simulation with large asteroids.
        self.asteroidsSmall = set()
        self.asteroidsLarge = set(addAsteroids(self.num_asteroids))

    def run(self):
        """
        Print some status messages before entering the event loop.
        """
        print('Asteroids now live')
        try:
            super().run()
        except KeyboardInterrupt:
            pass
        print('Game aborted by user')


def main():
    # Parse the command line.
    param = parseCommandLine()

    # Helper class to start/stop Azrael stack and other processes.
    az = azrael.startup.AzraelStack(param.loglevel)
    az.start()
    print('Azrael now live')

    # Spawn the viewer.
    if param.noviewer:
        viewer = None
    else:
        viewer = demolib.launchQtViewer()

    # Start the games...
    Simulation(viewer, param.N, param.reset_interval, topics=['#']).run()

    # Stop Azrael stack.
    az.stop()
    print('Clean shutdown')


if __name__ == '__main__':
    main()
