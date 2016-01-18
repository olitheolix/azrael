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

    # Instantiate the controller for a BoosterCube ship. Then spawn it.
    c = ship_boostercube.CtrlBoosterCube(ip)
    c.spawn((0, 5, 0))

    # Successively manoeuvre the ship above each platform. The hard coded
    # positions match those of the platforms defined in 'demo_platforms'.
    while True:
        for ii in range(5):
            pos_ref = (-10 + ii * 5, -ii * 2 + 2.5, -20)
            c.controller(pos_ref, dt=0.1, num_steps=50, verbose=False)


if __name__ == '__main__':
    main()
