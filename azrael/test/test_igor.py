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

    def test_all(self):
        """
        Integration test of Igor.
        """
        def _getC(_a, _b, _tag):
            p2p = ConstraintP2P([0, 0, -1], [0, 0, 1])
            _cm = ConstraintMeta
            assert len(_a) == len(_b) == len(_tag)
            t = [_cm('p2p', _[0], _[1], _[2], p2p) for _ in zip(_a, _b, _tag)]
            return t

        # Create two constraints.
        c1, c2, c3, c4 = _getC([1, 2, 3, 4], [2, 3, 4, 5], ['a'] * 4)

        tmp_igor = azrael.igor.Igor()
        assert tmp_igor.getAllConstraints().ok
        assert tmp_igor.getConstraints([1, 2]).ok
        assert tmp_igor.getUniquePairs().ok
        del tmp_igor

        igor = self.igor
        assert igor.updateLocalCache() == (True, None, 0)
        assert igor.addConstraints([c1]) == (True, None, 1)
        assert igor.addConstraints([c1]) == (True, None, 0)
        assert igor.addConstraints([c2, c3]) == (True, None, 2)
        assert igor.addConstraints([c3, c4]) == (True, None, 1)

        assert igor.reset() == (True, None, None)
        assert igor.getAllConstraints().data == tuple()
        assert igor.updateLocalCache() == (True, None, 0)
        assert igor.addConstraints([c2, c3]) == (True, None, 2)
        assert igor.getAllConstraints().data == tuple()
        assert igor.updateLocalCache() == (True, None, 2)
        assert sorted(igor.getAllConstraints().data) == sorted((c2, c3))
        assert igor.addConstraints([c3, c4]) == (True, None, 1)
        assert igor.updateLocalCache() == (True, None, 3)
        assert sorted(igor.getAllConstraints().data) == sorted((c2, c3, c4))

        assert igor.delete([c1]) == (True, None, 0)
        assert igor.updateLocalCache() == (True, None, 3)

        assert igor.delete([c1, c2]) == (True, None, 1)
        assert igor.updateLocalCache() == (True, None, 2)

        assert igor.reset() == (True, None, None)
        assert igor.uniquePairs() == (True, None, tuple())
        assert igor.addConstraints([c1]) == (True, None, 1)
        assert igor.uniquePairs() == (True, None, tuple())
        assert igor.updateLocalCache() == (True, None, 1)
        assert igor.uniquePairs().data == ((c1.rb_a, c1.rb_b), )

        assert sorted(igor.getAllConstraints().data) == sorted((c1,))
        assert igor.addConstraints([c1, c2, c3, c4]) == (True, None, 3)
        assert igor.updateLocalCache() == (True, None, 4)
        ref = [(_.rb_a, _.rb_b) for _ in (c1, c2, c3, c4)]
        ret = igor.uniquePairs()
        assert set(ret.data) == set(tuple(ref))

        ret = igor.getConstraints([1, 2, 3, 4, 5])
        assert sorted(ret.data) == sorted((c1, c2, c3, c4))

        ret = igor.getConstraints([1])
        assert ret.data == (c1, )

        ret = igor.getConstraints([1, 5])
        assert sorted(ret.data) == sorted((c1, c4))

        ret = igor.getConstraints([1, 2, 5])
        assert len(ret.data) == 3
        assert sorted(ret.data) == sorted((c1, c2, c4))

        ret = igor.getConstraints([10])
        assert ret.data == tuple()

        ret = igor.getConstraints([1, 10])
        assert ret.data == (c1, )


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

    def test_get_multi(self):
        """
        Query multiple constraints at once. This must always return a list of
        ConstraintMeta instances.
        """
        # Define a few dummy constraint for this test.
        id_a, id_b, id_c, id_d = 1, 2, 3, 4
        p2p = ConstraintP2P([0, 0, -1], [0, 0, 1])
        c1 = ConstraintMeta('p2p', id_a, id_b, p2p)
        c2 = ConstraintMeta('p2p', id_b, id_c, p2p)
        c3 = ConstraintMeta('p2p', id_c, id_d, p2p)

        # Query the constraint for a non-existing object.
        ret = self.igor.getMulti([10])
        assert ret == (True, None, tuple())

        # Query the constraint several non-existing objects.
        ret = self.igor.getMulti([10, 20])
        assert ret == (True, None, tuple())

        # Add the first constraint.
        assert self.igor.add(c1) == (True, None, 1)

        # Query the constraint for rb_a and rb_b individually.
        ret_a = self.igor.getMulti([c1.rb_a])
        ret_b = self.igor.getMulti([c1.rb_b])
        assert ret_a.ok and ret_b.ok
        assert ret_a == ret_b

        # Query two objects that are linked by a single constraint. This must
        # return exactly one match.
        ret = self.igor.getMulti([c1.rb_a, c1.rb_b])
        assert ret.ok
        assert len(ret.data) == 1
        assert isEqualConstraint(ret.data[0]._asdict(), c1._asdict())

        # Query two objects, only one of which exists. This must produce only
        # one constraint (the same as before).
        ret = self.igor.getMulti([c1.rb_a, c2.rb_b])
        assert len(ret.data) == 1
        assert isEqualConstraint(ret.data[0]._asdict(), c1._asdict())

        # Add the other two constraints.
        assert self.igor.add(c2) == (True, None, 1)
        assert self.igor.add(c3) == (True, None, 1)

        # Query the constraints for only the second object, once in conjunction
        # with the first object and once without. In both cases we must receive
        # the same two constraints, nameley a-b, and b-c.
        for query in ([id_b], [id_a, id_b]):
            ret = self.igor.getMulti(query)
            assert ret.ok
            assert len(ret.data) == 2
            if isEqualConstraint(ret.data[0]._asdict(), c1._asdict()):
                assert isEqualConstraint(ret.data[1]._asdict(), c2._asdict())
            else:
                assert isEqualConstraint(ret.data[1]._asdict(), c1._asdict())
                assert isEqualConstraint(ret.data[0]._asdict(), c2._asdict())

    def test_getUniquePairs(self):
        """
        Create a few constraints and verify that getUniquePairs returns the
        correct pairs.
        """
        # Define a few dummy constraint for this test.
        id_a, id_b, id_c, id_d = 1, 2, 3, 4
        p2p = ConstraintP2P([0, 0, -1], [0, 0, 1])
        c1 = ConstraintMeta('p2p', id_b, id_a, p2p)
        c2 = ConstraintMeta('p2p', id_b, id_c, p2p)
        c3 = ConstraintMeta('p2p', id_d, id_c, p2p)

        # Query the constraint for a non-existing object.
        assert self.igor.getUniquePairs() == (True, None, tuple())

        # Add the first constraint and verify. The IDs in the returned tuple
        # must always be sorted.
        for c in [c1, c2, c3]:
            self.igor.reset()
            assert self.igor.add(c) == (True, None, 1)
            ret = self.igor.getUniquePairs()
            assert ret.ok
            assert len(ret.data) == 1
            assert ret.data[0] == tuple(sorted([c.rb_a, c.rb_b]))

        # Reset and verify that no pairs are returned.
        self.igor.reset()
        assert self.igor.getUniquePairs() == (True, None, tuple())

        # Add all three constraints.
        assert self.igor.add(c1) == (True, None, 1)
        assert self.igor.add(c2) == (True, None, 1)
        assert self.igor.add(c3) == (True, None, 1)

        ret = self.igor.getUniquePairs()
        assert ret.ok
        expected = [sorted([_.rb_a, _.rb_b]) for _ in [c1, c2, c3]]
        expected = [tuple(_) for _ in expected]
        expected = set(expected)
        assert set(ret.data) == expected
