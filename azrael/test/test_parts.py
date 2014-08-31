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

import numpy as np
import azrael.parts as parts


def test_booster_factory_serialisation():
    """
    Serialise and de-serialise a Booster- and Factory part.
    """
    p = parts.Booster(1, [1, 2, 3])
    assert p == parts.fromstring(p.tostring())

    p = parts.Factory(1, [1, 2, 3], [4, 5, 6], b'x', [0, 1])
    assert p == parts.fromstring(p.tostring())

    print('Test passed')


def test_command_serialisation():
    """
    Serialise and de-serialise a Booster- and Factory command.
    """
    c = parts.CmdBooster(1, 5)
    assert c == parts.fromstring(c.tostring())

    print('Test passed')


if __name__ == '__main__':
    test_command_serialisation()
    test_booster_factory_serialisation()
