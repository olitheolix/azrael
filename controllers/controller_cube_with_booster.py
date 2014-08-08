import os
import sys
p = os.path.dirname(os.path.abspath(__file__))
p = os.path.join(p, '..')
sys.path.insert(0, p)
del p

import time
import setproctitle
import numpy as np

import azrael.util as util
import azrael.config as config
import azrael.controller


class ControllerCube(azrael.controller.ControllerBase):
    def run(self):
        # Setup.
        self.setupZMQ()
        self.connectToClerk()

        # Toggle interval in seconds.
        t0 = 1

        # Engage the booster up for one interval.
        force = 1 * np.ones(3)
        self.setStateVariables(self.objID, force)
        time.sleep(t0)

        # Engage the booster down for two intervals.
        force = -force
        self.setStateVariables(self.objID, force)
        time.sleep(2 * t0)

        # Periodically toggle the booster to make the object oscillate.
        self.setStateVariables(self.objID, np.zeros(3))
        time.sleep(t0)
        while True:
            force = -force
            self.setStateVariables(self.objID, force)
            time.sleep(2 * t0)


if __name__ == '__main__':
    obj_id = int(sys.argv[1])
    obj_id = util.int2id(obj_id)
    name = 'killme Controller {}'.format(util.id2int(obj_id))
    setproctitle.setproctitle(name)
    ctrl = ControllerCube(obj_id)
    ctrl.run()
