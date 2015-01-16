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
Default controller that does nothing other than returning messages.

Clerk knows about the ``ControllerCube`` by default. Its spawn command can
hence start a new Python process for it, pass it the object ID, and leave it to
its own devices.
"""

import os
import sys
p = os.path.dirname(os.path.abspath(__file__))
p = os.path.join(p, '..')
sys.path.insert(0, p)
del p

import time
import setproctitle
import azrael.client
import azrael.util as util


class ControllerCube(azrael.client.Client):
    pass


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('You forgot to supply the object ID')
        sys.exit(1)

    # Read the object from the command line.
    obj_id = int(sys.argv[1])

    # Rename this process to ensure it is easy to find and kill.
    name = 'killme Controller {}'.format(obj_id)
    setproctitle.setproctitle(name)

    # Instantiate the controller and start it in this thread.
    ctrl = ControllerCube(obj_id)
    ctrl.run()
