# Copyright 2015, Oliver Nagy <olitheolix@gmail.com>
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
Test the Igor module.
"""
import pytest
import azrael.igor

import unittest.mock as mock
from IPython import embed as ipshell
from azrael.types import ConstraintMeta, ConstraintP2P
from azrael.test.test_leonard import killAzrael


def isEqualConstraint(ca, cb):
    try:
        assert len(ca) == len(cb)
        ca = ConstraintMeta(**ca)
        cb = ConstraintMeta(**cb)
        assert ca.rb_a == cb.rb_a
        assert ca.rb_b == cb.rb_b
        assert ca.type == cb.type
        assert list(ca.data) == list(cb.data)
    except (KeyError, TypeError, AssertionError):
        return False
    return True


class TestClerk:
    @classmethod
    def setup_class(cls):
        killAzrael()
        cls.igor = azrael.igor.Igor()

    @classmethod
    def teardown_class(cls):
        killAzrael()

    def setup_method(self, method):
        self.igor.reset()

    def teardown_method(self, method):
        self.igor.reset()

    def test_add_get(self):
        """
        Add/get several constraints.
        """
        # Define a few dummy constraint for this test.
        id_a, id_b, id_c, id_d = 1, 2, 3, 4
        p2p = ConstraintP2P([0, 0, -1], [0, 0, 1])
        c1 = ConstraintMeta('p2p', id_a, id_b, p2p)
        c2 = ConstraintMeta('p2p', id_b, id_c, p2p)
        c3 = ConstraintMeta('p2p', id_c, id_d, p2p)

        # Query the constraint for a non-existing object.
        ret = self.igor.get(10)
        assert ret == (True, None, tuple())

        # Query the constraint for a non-existing pair.
        ret = self.igor.get(10, 20)
        assert ret == (True, None, tuple())
        
        # Add the first constraint. Exactly one constraint must have been
        # added.
        assert self.igor.add(c1) == (True, None, 1)

        # Add the same constraint again. This time none must have been added.
        assert self.igor.add(c1) == (True, None, 0)

        # Query the constraint for rb_a and rb_b individually.
        ret_a = self.igor.get(c1.rb_a)
        ret_b = self.igor.get(c1.rb_b)
        assert ret_a.ok and ret_b.ok
        assert ret_a == ret_b
        
        # Query the joint constraint.
        ret = self.igor.get(c1.rb_a, c1.rb_b)
        assert ret.ok
        assert isEqualConstraint(ret.data[0], c1._asdict())

        # Query the joint constraint between two objects, only one of which
        # actually exists. This must return nothing.
        ret = self.igor.get(c1.rb_a, c2.rb_b)
        assert ret == (True, None, tuple())
        
        # Add the other two constraints.
        assert self.igor.add(c2) == (True, None, 1)
        assert self.igor.add(c3) == (True, None, 1)

        # Query the constraints individually.
        for _c in (c1, c2, c3):
            ret = self.igor.get(_c.rb_a, _c.rb_b)
            assert ret.ok and isEqualConstraint(ret.data[0], _c._asdict())
            ret = self.igor.get(_c.rb_b, _c.rb_a)
            assert ret.ok and isEqualConstraint(ret.data[0], _c._asdict())

        # Query the constraints for the second object. This must return 2
        # constraints.
        ret = self.igor.get(id_b)
        assert ret.ok
        assert len(ret.data) == 2
        if isEqualConstraint(ret.data[0], c1._asdict()):
           assert isEqualConstraint(ret.data[1], c2._asdict())
        else:
           assert isEqualConstraint(ret.data[1], c1._asdict())
           assert isEqualConstraint(ret.data[0], c2._asdict())
