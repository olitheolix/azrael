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
Simulate an extremely simplified version of the Rosetta mission.

This demo creates a small probe (Rosetta) and a sphere (the asteroid 67P).  The
probe will first approach the asteroid. Then it will fly around the asteroid on
a triangular path and finally come to rest.

In terms of the manoeuvres this replicates the gist of the mission parameters.
However, the simplifying assumptions are enormous. For instance, the probe has
unlimited fuel, its thrusters can apply arbitrarily large forces, cannot roll
(which makes manoeuvres that much simpler), knows its positions and velocity
exactly, knows the position and velocity of 67P exactly... As for the asteroid
67P, in this simulation it is simplified to a perfect sphere with known radius
that does not move...

These simplifications are not due to limitations in Azrael itself but because
they constitute the simplest non-trivial example in terms of simulating the
Rosetta mission.

Usage
-----

Start the auxiliary services:
  >> docker-compose -f ../devtools/docker-compose-dev.yml up

Then activate the Anaconda/Azrael environment and type:
  >> python demo_rosetta.py --noviewer

and view the scene at http://localhost:8080. If you have a recent GPU then you
may omit the --noviewer argument to get a custom viewer.

"""
# Always import this first because it sets the path to the Azrael module.
import demolib

# Standard imports.
import argparse
import numpy as np
import pyazrael
import time
from IPython import embed as ipshell

# This module contains the template for a simple space ship. We will re-purpose
# it as the Rosetta probe :)
import ship_boostercube

# Azrael related imports.
import azrael.startup


class Rosetta(ship_boostercube.CtrlBoosterCube):
    """
    Our Rosetta probe.
    """
    pass


def parseCommandLine():
    """
    Parse program arguments.
    """
    # Create the parser.
    parser = argparse.ArgumentParser(
        description=('Rosetta Mission'),
        formatter_class=argparse.RawTextHelpFormatter)

    # Shorthand.
    padd = parser.add_argument

    # Add the command line options.
    padd('--noviewer', action='store_true', default=False,
         help='Do not spawn a viewer')
    padd('--loglevel', type=int, metavar='level', default=1,
         help='Specify error log level (0: Debug, 1:Info)')

    # Run the parser.
    param = parser.parse_args()
    return param


def conductMission(client, viewer, asteroidID, rosetta):
    """Replicate the basic Rosetta manoeuvres.

    Args:
        client (object): handle to Python client for Azrael.
        viewer (object): handle to Qt viewer.
        asteroidID (str): the AID for the asteroid.
        rosetta (object): instance of a space ship with auto-pilot.

    Returns:
        None
    """
    # Convenience: extract the AID of the Rosetta probe.
    rosettaID = rosetta.shipID

    # -------------------------------------------------------------------------
    #                      Approach the Asteroid 67P
    # -------------------------------------------------------------------------
    # To determine the direction and distance between Rosetta and the asteroid
    # we first need their current positions.
    ret = client.getRigidBodyData([asteroidID, rosettaID])
    assert ret.ok
    pos_asteroid = ret.data[asteroidID]['rbs'].position
    pos_rosetta = ret.data[rosettaID]['rbs'].position

    # Compute the vector that points from our position to the asteroid.
    # Afterwards, this will tell us in which direction to move the probe.
    tmp = np.array(pos_asteroid) - np.array(pos_rosetta)
    distance = np.linalg.norm(tmp)
    direction = tmp / np.linalg.norm(tmp)
    del tmp

    # Compute Rosetta's target position in the asteroid's orbit. In this
    # example, we want to stay 20 Meters away from the asteroid's surface
    # (which has a radius of 10m).
    pos_orbit = pos_rosetta + direction * (distance - 30)

    # Run the autopilot for short intervals at a time until we have reach out
    # destination in the orbit.
    while True:
        # Activate the auto pilot
        rosetta.controller(pos_orbit, dt=0.1, num_steps=10, verbose=False)

        # Query current position and velocity of Rosetta.
        ret = client.getRigidBodyData([rosetta.shipID])
        assert ret.ok
        pos_rosetta = ret.data[rosettaID]['rbs'].position
        vel_rosetta = ret.data[rosettaID]['rbs'].velocityLin

        # If we are within 0.2m of the desired orbit, and Rosetta has almost
        # come to a standstill, then our approach has been successful.
        if np.linalg.norm(pos_rosetta - pos_orbit) < 0.2:
            if np.linalg.norm(vel_rosetta) < 0.05:
                break

        # Abort this demo if the user has closed the Qt viewer (unless he used
        # the '--noviewer' option).
        if viewer.poll() is not None:
            print('Viewer was closed')
            return
    print('Approach finished')

    # -------------------------------------------------------------------------
    #               Compute Triangular Path Around Asteroid
    # -------------------------------------------------------------------------

    # Side length of equilateral triangle.
    sidelen = 50

    # Total height of triangle, as well as the length of the two partitions
    # that make up the line perpendicular to a side and passing through the
    # triangle's centre.
    height = sidelen * np.cos(np.pi / 6)
    hl = (sidelen / 2) * np.tan(np.pi / 6)
    hu = height - hl

    # The three points of the triangle. Note: this assumes the triangle aligns
    # with the x/y axes and z=0 for all its corners -- yet another unrealistic
    # assumption.
    orbit_positions = [
        (-sidelen / 2, -hl, 0),
        (sidelen / 2, -hl, 0),
        (0, hu, 0),
    ]
    orbit_positions = pos_asteroid + np.array(orbit_positions)
    del sidelen, height, hl, hu

    # -------------------------------------------------------------------------
    #                    Traverse The Triangular Path
    # -------------------------------------------------------------------------
    # Manoeuvre the probe to each point in the triangle.
    for ii, pos_target in enumerate(orbit_positions):
        msg = 'Navigating to way point x={:.1f}  y={:.1f}  z={:.1f}'
        msg = msg.format(*pos_target)
        print(msg)

        # Like before, engage the auto pilot for short periods at a time until
        # we have reached the desired position.
        while True:
            # Auto pilot.
            rosetta.controller(pos_target, dt=0.1, num_steps=10, verbose=False)

            # Query position and velocity of Rosetta.
            ret = client.getRigidBodyData([rosetta.shipID])
            assert ret.ok
            pos_rosetta = ret.data[rosettaID]['rbs'].position
            vel_rosetta = ret.data[rosettaID]['rbs'].velocityLin

            # If we are within 0.2m of the desired orbit, and Rosetta has
            # almost come to a standstill, then we have reached our target
            # position.
            if np.linalg.norm(pos_rosetta - pos_target) < 0.2:
                if np.linalg.norm(vel_rosetta) < 0.05:
                    break

            # Abort this demo if the user has closed the Qt viewer (unless he
            # used the '--noviewer' option).
            if viewer.poll() is not None:
                print('Viewer was closed')
                return
    print('Finished path around 67P - Rosetta mission was a success!')


def spawnAsteroid(client):
    """Spawn the asteroid 67P and return its Azrael ID (AID).
    """
    # This is a convenience function that returns geometry and collision shape
    # for a sphere.
    vert, cshapes = demolib.loadSphere(10)

    # This is a convenience function that compiles the rigid body parameters to
    # compute the Newtonian physics.
    body = demolib.getRigidBody(cshapes={'cs': cshapes})

    # Define the visual geometry of the Asteroid.
    frags = {'foo': demolib.getFragMetaRaw(vert=vert, uv=[], rgb=[])}

    # Define the template for the asteroid and upload it to Azrael.
    template = pyazrael.aztypes.Template('asteroid', body, frags, {}, {})
    ret = client.addTemplates([template])

    # Specify the parameters for the asteroid and spawn it.
    spawn_param = {
        'templateID': 'asteroid',
        'rbs': {
            'position': (0, 0, -100),
            'velocityLin': (0, 0, 0),
            'imass': 0.0001,
        }
    }
    ret = client.spawn([spawn_param])
    assert ret.ok

    # The return value contains the Azrael IDs (AIDs) of all spawned objects.
    # In this case we have only spawned one, namely the asteroid.
    asteroidID = ret.data[0]

    # Tag the asteroid with a custom string (optional).
    assert client.setObjectTags({asteroidID: '67P'}).ok
    return asteroidID


def main():
    # Parse the command line.
    param = parseCommandLine()

    # Guess Azrael's IP address on the local computer.
    host = demolib.azService['clerk'].ip
    print('Assuming Azrael services on <{}>'.format(host))

    # Helper class to start/stop Azrael stack and other processes.
    az = azrael.startup.AzraelStack(param.loglevel)
    az.start()
    print('Azrael now live')

    # Connect to Azrael.
    client = pyazrael.AzraelClient(host)

    # Create the template for the asteroid and spawn one instance.
    asteroidID = spawnAsteroid(client)

    # Create the template for our ship and spawn one instance thereof.
    rosetta = Rosetta(host)
    rosetta.spawn((0, 50, -100))

    # Start the Qt viewer unless the user specified '--noviewer'.
    if param.noviewer:
        viewer = None
    else:
        viewer = demolib.launchQtViewer()

    # Conduct the Rosetta mission.
    conductMission(client, viewer, asteroidID, rosetta)

    # Stop Azrael stack and exit.
    rosetta.removeShip()
    az.stop()
    print('Clean shutdown')


if __name__ == '__main__':
    main()
