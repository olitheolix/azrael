#!/usr/bin/python3

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
Start a new viewer.

A new Azrael instance will be created if none is live yet.
"""

# Add the viewer directory to the Python path.
import os
import sys
p = os.path.dirname(os.path.abspath(__file__))
p = os.path.join(p, 'viewer')
sys.path.insert(0, p)
del p

import time
import logging
import argparse
import subprocess
import model_import
import azrael.clerk
import azrael.clacks
import azrael.parts as parts
import azrael.config as config
import azrael.leonard as leonard
import azrael.wscontroller as wscontroller
import azrael.bullet.btInterface as btInterface

import numpy as np

def parseCommandLine():
    """
    Parse program arguments.
    """
    # Create the parser.
    parser = argparse.ArgumentParser(
        description=('Azrael Demo Script'),
        formatter_class=argparse.RawTextHelpFormatter)

    # Shorthand.
    padd = parser.add_argument

    # Add the command line options.
    padd('--noviewer', action='store_true', default=False,
         help='Do not spawn a viewer')
    padd('--noinit', action='store_true', default=False,
         help='Do not load any models')
    padd('--port', metavar='port', type=int, default=8080,
         help='Port number')
    padd('--loglevel', type=int, metavar='level', default=1,
         help='Specify error log level (0: Debug, 1:Info)')

    # run the parser.
    return parser.parse_args()


def setupLogging(loglevel):
    # Create the logger instance.
    logger = logging.getLogger('azrael')
    logger.setLevel(logging.DEBUG)
    
    # Prevent it from logging to console no matter what.
    logger.propagate = False
    
    # Create a handler instance to log the messages to stdout.
    logFormat = '%(levelname)s - %(name)s - %(message)s'
    formatter = logging.Formatter(logFormat)
    console = logging.StreamHandler(sys.stdout)
    if loglevel == 0:
        console.setLevel(logging.DEBUG)
    elif loglevel == 1:
        console.setLevel(logging.INFO)
    elif loglevel == 2:
        console.setLevel(logging.WARNING)
    else:
        print('Unknown log level {}'.format(loglevel))
        sys.exit(1)
    console.setFormatter(formatter)
    
    # Create a handler instance to log the messages to a file.
    logFormat = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    formatter = logging.Formatter(logFormat)
    fileHandler = logging.FileHandler(config.log_file, mode='a')
    fileHandler.setLevel(logging.DEBUG)
    fileHandler.setFormatter(formatter)
    
    # Install the handler.
    logger.addHandler(console)
    logger.addHandler(fileHandler)
    del formatter, console, fileHandler


def loadGroundModel(scale, model_name):
    # Establish connection to Azrael.
    ctrl = wscontroller.WSControllerBase('ws://127.0.0.1:8080/websocket')
    assert ctrl.pingClacks()

    # Load the model mesh.
    print('  Importing <{}>... '.format(model_name), end='', flush=True)
    mesh = model_import.loadModelMesh(model_name)
    mesh = mesh['vertices']
    buf_vert = []
    for l in mesh:
        buf_vert.extend(l)
    buf_vert = scale * np.array(buf_vert)
    print('done')

    # Set the geometry of the object in Azrael.
    print('  Adding geometry to Azrael... ', end='', flush=True)
    cs = np.zeros(4, np.float64)
    templateID = 'ground'.encode('utf8')
    ok, _ = ctrl.addTemplate(templateID, cs, buf_vert, [], [])
    
    # Tell Azrael to spawn the 'ground' object near the center of the scene.
    print('  Spawning object... ', end='', flush=True)
    ok, objID = ctrl.spawn(None, templateID, 2 * np.array([0, -2, 1],
                           np.float64), np.zeros(3))
    print('done (ID=<{}>)'.format(objID))


def defineBoosterCube():
    """
    Define a BoosterCube object.

    The cube has two boosters and two factories.
    """
    # Establish connection to Azrael.
    ctrl = wscontroller.WSControllerBase('ws://127.0.0.1:8080/websocket')
    assert ctrl.pingClacks()

    # Collision shape for a cube.
    cs = np.array([4, 1, 1, 1], np.float64)

    # Geometry of a unit cube.
    geo = 0.5 * np.array([
        -1.0, -1.0, -1.0,   -1.0, -1.0, +1.0,   -1.0, +1.0, +1.0,
        +1.0, +1.0, -1.0,   -1.0, -1.0, -1.0,   -1.0, +1.0, -1.0,
        +1.0, -1.0, +1.0,   -1.0, -1.0, -1.0,   +1.0, -1.0, -1.0,
        +1.0, +1.0, -1.0,   +1.0, -1.0, -1.0,   -1.0, -1.0, -1.0,
        -1.0, -1.0, -1.0,   -1.0, +1.0, +1.0,   -1.0, +1.0, -1.0,
        +1.0, -1.0, +1.0,   -1.0, -1.0, +1.0,   -1.0, -1.0, -1.0,
        -1.0, +1.0, +1.0,   -1.0, -1.0, +1.0,   +1.0, -1.0, +1.0,
        +1.0, +1.0, +1.0,   +1.0, -1.0, -1.0,   +1.0, +1.0, -1.0,
        +1.0, -1.0, -1.0,   +1.0, +1.0, +1.0,   +1.0, -1.0, +1.0,
        +1.0, +1.0, +1.0,   +1.0, +1.0, -1.0,   -1.0, +1.0, -1.0,
        +1.0, +1.0, +1.0,   -1.0, +1.0, -1.0,   -1.0, +1.0, +1.0,
        +1.0, +1.0, +1.0,   -1.0, +1.0, +1.0,   +1.0, -1.0, +1.0])

    # Convenience.
    dir_0, dir_1 = [0, 0, +1], [0, 0, -1]
    pos_0, pos_1 = [+1.5, 0, 0], [-1.5, 0, 0]
    
    # Create templates for what the factory will be able to spawn.
    tID_1 = 'Product1'.encode('utf8')
    tID_2 = 'Product2'.encode('utf8')
    ctrl.addTemplate(tID_1, np.array([4, 1, 1, 1], np.float64), 0.75 * geo, [], [])
    ctrl.addTemplate(tID_2, np.array([4, 1, 1, 1], np.float64), 0.24 * geo, [], [])

    # Two boosters, one left, one right. Both point in the same direction.
    b0 = parts.Booster(
        partID=0, pos=pos_0, direction=dir_0, max_force=10.0)
    b1 = parts.Booster(
        partID=1, pos=pos_1, direction=dir_0, max_force=10.0)

    # Two factories, one left one right. The spawned objects exit forwards and
    # backwards, respectively.
    f0 = parts.Factory(
        partID=0, pos=pos_0, direction=[+1, 0, 0],
        templateID=tID_1, exit_speed=[0.1, 1])
    f1 = parts.Factory(
        partID=1, pos=pos_1, direction=[-1, 0, 0],
        templateID=tID_2, exit_speed=[0.1, 1])

    # Add the template.
    templateID_2 = 'BoosterCube'.encode('utf8')
    ok, _ = ctrl.addTemplate(templateID_2, cs, geo, [b0, b1], [f0, f1])
    assert ok
    

def main():
    # Parse the command line.
    param = parseCommandLine()
    setupLogging(param.loglevel)

    # Determine if Azrael is live.
    try:
        addr = 'ws://127.0.0.1:{}/websocket'.format(param.port)
        wscontroller.WSControllerBase(addr)
        is_azrael_live = True
    except ConnectionRefusedError as err:
        is_azrael_live = False

    if not is_azrael_live:
        print('Starting Azrael...')

        # Kill all left over processes from previous runs.
        subprocess.call(['pkill', 'killme'])

        # Start the Azrael processes.
        #leo = leonard.LeonardBase()
        #leo = leonard.LeonardBaseWPRMQ()
        leo = leonard.LeonardBulletMonolithic()
        leo.start()
        clerk = azrael.clerk.Clerk(reset=True)
        clerk.start()
        clacks = azrael.clacks.ClacksServer()
        clacks.start()
        btInterface.initSVDB(reset=True)

        if not param.noinit:
            # Add a model to the center. The sphere is included. You can get the
            # Vatican model here:
            # http://artist-3d.com/free_3d_models/dnm/model_disp.php?\
            # uid=3290&count=count
            model_name = (1, 'viewer/models/sphere/sphere.obj')
            #model_name = (50, 'viewer/models/vatican/vatican-cathedral.3ds')
            loadGroundModel(*model_name)
    
            # Define additional templates.
            defineBoosterCube()
        print('Azrael now live')
    else:
        print('Azrael already live')

    # Launch the viewer process.
    try:
        if param.noviewer:
            while True:
                time.sleep(360000)
        else:
            subprocess.call(['python3', 'viewer/viewer.py'])
    except KeyboardInterrupt:
        pass

    if not is_azrael_live:
        # Shutdown Azrael.
        clerk.terminate()
        clacks.terminate()
        leo.terminate()
        clerk.join()
        clacks.join()
        leo.join()

    print('Clean shutdown')


if __name__ == '__main__':
    main()
