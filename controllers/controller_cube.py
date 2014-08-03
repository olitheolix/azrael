import os
import sys
p = os.path.dirname(os.path.abspath(__file__))
p = os.path.join(p, '..')
sys.path.insert(0, p)
del p

import time
import setproctitle
import azrael.controller
import azrael.util as util


class ControllerCube(azrael.controller.ControllerBase):
    pass


if __name__ == '__main__':
    obj_id = int(sys.argv[1])
    obj_id = util.int2id(obj_id)
    name = 'killme Controller {}'.format(util.id2int(obj_id))
    setproctitle.setproctitle(name)
    ctrl = ControllerCube(obj_id)
    ctrl.run()
