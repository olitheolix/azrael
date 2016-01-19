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
A (rather simple) auto pilot to fly around the scene.
"""
import os
import sys
import time
import demolib
import ship_boostercube

import numpy as np
from IPython import embed as ipshell

# Import the necessary Azrael modules.
p = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(p, '../'))
import pyazrael
import pyazrael.aztypes as aztypes


class Ship(ship_boostercube.CtrlBoosterCube):
    """
    Leverage the `BoosterCube`.
    """
    pass


def main():
    # Guess Azrael's IP address on the local computer.
    if os.getenv('INSIDEDOCKER') is None:
        print('Determining IP address')
        ip = demolib.getNetworkAddress()
    else:
        print('Running inside Docker container')
        ip = 'azrael'
    print('Connecting to <{}>'.format(ip))

    time.sleep(5)

    # Spawn our ship.
    c = Ship(ip)
    c.spawn((0, 5, 0))

    # Manoeuvre the ship to deterministic way points. This may not be very
    # exiciting but is good enough for a first demo.
    while True:
        for ii in range(5):
            pos_ref = (-10 + ii * 5, -ii * 2 + 2.5, -20)
            c.controller(pos_ref, dt=0.1, num_steps=50, verbose=False)


if __name__ == '__main__':
    main()
