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
from azrael.types import ConstraintMeta, ConstraintP2P, Constraint6DofSpring2
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


def getP2P(rb_a, rb_b, constraint_id):
    """
    Return a Point2Point constraint for bodies ``rb_a`` and ``rb_b`.

    This is a convenience method only.
    """
    pivot_a, pivot_b = [0, 0, -1], [0, 0, 1]
    p2p = ConstraintP2P(pivot_a, pivot_b)
    return ConstraintMeta('p2p', constraint_id, rb_a, rb_b, p2p)


def get6DofSpring2(rb_a, rb_b, constraint_id):
    """
    Return a 6DofSpring2 constraint for bodies ``rb_a`` and ``rb_b`.

    This is a convenience method only.
    """
    dof = Constraint6DofSpring2(
        frameInA=[0, 0, 0, 0, 0, 0, 1],
        frameInB=[0, 0, 0, 0, 0, 0, 1],
        stiffness=[1, 2, 3, 4, 5.5, 6],
        damping=[2, 3.5, 4, 5, 6.5, 7],
        equilibrium=[-1, -1, -1, 0, 0, 0],
        linLimitLo=[-10.5, -10.5, -10.5],
        linLimitHi=[10.5, 10.5, 10.5],
        rotLimitLo=[-0.1, -0.2, -0.3],
        rotLimitHi=[0.1, 0.2, 0.3],
        bounce=[1, 1.5, 2],
        enableSpring=[True, False, False, False, False, False])
    con = ConstraintMeta('6DOFSPRING2', constraint_id, rb_a, rb_b, dof)
    return con


# List of all constraint getter functions. This variables is only useful for
# the pytest.parametrize decorator.
_AllConstraintGetters = [getP2P, get6DofSpring2]


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

    def test_basic(self):
        """
        Verify that it is safe to call any Igor methods right from the start
        without updating the cache or resetting the database.
        """
        igor = azrael.igor.Igor()
        assert igor.getAllConstraints().ok
        assert igor.getConstraints([1, 2]).ok
        assert igor.uniquePairs().ok

    @pytest.mark.parametrize('getCon', _AllConstraintGetters)
    def test_update_and_add(self, getCon):
        """
        Verify that 'updateLocalCache' downloads the correct number of
        constraints.
        """
        # Convenience.
        igor = self.igor
        igor.reset()

        # Create the constraints for this test.
        c1 = getCon(1, 2, 'foo')
        c2 = getCon(2, 3, 'foo')
        c3 = getCon(3, 4, 'foo')
        c4 = getCon(4, 5, 'foo')
        c5 = getCon(5, 6, 'foo')
        c6 = getCon(6, 7, 'foo')

        # There must not be any objects to download.
        assert igor.updateLocalCache() == (True, None, 0)

        # Pass an empty list.
        assert igor.addConstraints([]) == (True, None, 0)

        # Add one constraint and update the cache.
        assert igor.addConstraints([c1]) == (True, None, 1)
        assert igor.updateLocalCache() == (True, None, 1)

        # Add the same constraint. This must add no constraint, but the update
        # function must still fetch exactly one constraint.
        assert igor.addConstraints([c1]) == (True, None, 0)
        assert igor.updateLocalCache() == (True, None, 1)

        # Add two new constraints.
        assert igor.addConstraints([c2, c3]) == (True, None, 2)
        assert igor.updateLocalCache() == (True, None, 3)

        # Add two more constraints, one of which is not new. This must add one
        # new constraint and increase the total number of unique constraints to
        # four.
        assert igor.addConstraints([c3, c4]) == (True, None, 1)
        assert igor.updateLocalCache() == (True, None, 4)

        # Add five more constaints, but only two of them are actually unique.
        assert igor.addConstraints([c5, c5, c6, c6, c6]) == (True, None, 2)
        assert igor.updateLocalCache() == (True, None, 6)
        ref = sorted((c1, c2, c3, c4, c5, c6))
        assert sorted(igor.getAllConstraints().data) == ref

        # Reset igor and add two constraints, of which only one has a valid
        # 'type'. The 'addConstraints' must only add the valid one.
        c6 = c6._replace(type='foo')
        assert igor.reset().ok
        assert igor.addConstraints([c1, c6]) == (True, None, 1)
        assert igor.updateLocalCache() == (True, None, 1)

    @pytest.mark.parametrize('getCon', _AllConstraintGetters)
    def test_add_unique_bug1(self, getCon):
        """
        Add two constraints that are identical except for their 'id'.

        In the original implementation this was handled incorrectly
        because the 'id' was not considered when adding constraints.
        This made it impossible to add more than once constraint of each
        type (eg more than one Point2Point constraint between objects).
        """
        # Convenience.
        igor = self.igor

        # Two constraints that only differ in their 'id' attribute.
        c1 = getCon(1, 2, 'foo')
        c2 = getCon(1, 2, 'bar')

        # Attempt to add the first constraint twice. Igor must detect this and
        # only add it once.
        assert igor.reset().ok
        assert igor.addConstraints([c1, c1]) == (True, None, 1)

        # Attempt to both constraints. Without the bug fix Igor would only add
        # the first one, whereas with the bug fix it adds both.
        assert igor.reset().ok
        assert igor.addConstraints([c1, c2]) == (True, None, 2)

        # Update the local cache and verify that really both constraints are
        # available.
        assert igor.updateLocalCache() == (True, None, 2)
        assert sorted(igor.getAllConstraints().data) == sorted((c1, c2))

    @pytest.mark.parametrize('getCon', _AllConstraintGetters)
    def test_getAllConstraints(self, getCon):
        """
        Add constraints and very that Igor can return them after cache updates.
        """
        # Convenience.
        igor = self.igor

        # Create the constraints for this test.
        c1 = getCon(1, 2, 'foo')
        c2 = getCon(2, 3, 'foo')
        c3 = getCon(3, 4, 'foo')
        c4 = getCon(4, 5, 'foo')

        # The list of constraints must be empty after a reset.
        assert igor.reset() == (True, None, None)
        assert igor.getAllConstraints().data == tuple()
        assert igor.updateLocalCache() == (True, None, 0)
        assert igor.getAllConstraints().data == tuple()

        # Add two constraints and verify that Igor returns them *after* a cache
        # update.
        assert igor.addConstraints([c2, c3]) == (True, None, 2)
        assert igor.getAllConstraints().data == tuple()
        assert igor.updateLocalCache() == (True, None, 2)
        assert sorted(igor.getAllConstraints().data) == sorted((c2, c3))

        # Add another two constraints, only one of which is new. Verify that
        # Igor returns the correct three constraints.
        assert igor.addConstraints([c3, c4]) == (True, None, 1)
        assert igor.updateLocalCache() == (True, None, 3)
        assert sorted(igor.getAllConstraints().data) == sorted((c2, c3, c4))

    @pytest.mark.parametrize('getCon', _AllConstraintGetters)
    def test_delete(self, getCon):
        """
        Add- and delete several constraints.
        """
        # Convenience.
        igor = self.igor

        # Create the constraints for this test.
        c1 = getCon(1, 2, 'foo')
        c2 = getCon(2, 3, 'foo')
        c3 = getCon(3, 4, 'foo')
        c4 = getCon(4, 5, 'foo')

        # Attempt to delete a non-existing constraint. This must neither return
        # an error not delete anything.
        assert igor.reset().ok
        assert igor.deleteConstraints([c1]) == (True, None, 0)
        assert igor.deleteConstraints([c1, c2]) == (True, None, 0)
        assert igor.updateLocalCache() == (True, None, 0)

        # Add some constraints, delete them, and update the cache.
        assert igor.addConstraints([c1, c2, c3]) == (True, None, 3)
        assert igor.updateLocalCache() == (True, None, 3)
        assert igor.deleteConstraints([c1, c2]) == (True, None, 2)
        assert igor.updateLocalCache() == (True, None, 1)

        # Add/delete more constraints without every updating the cache. These
        # operations must not affect the local cache of constraints in Igor.
        assert igor.reset().ok
        assert igor.addConstraints([c1, c2, c3]) == (True, None, 3)
        assert igor.deleteConstraints([c1, c2]) == (True, None, 2)
        assert igor.deleteConstraints([c1, c2]) == (True, None, 0)
        assert igor.addConstraints([c1, c2]) == (True, None, 2)
        assert igor.deleteConstraints([c1]) == (True, None, 1)
        assert igor.deleteConstraints([c1, c2]) == (True, None, 1)
        assert igor.deleteConstraints([c1, c2]) == (True, None, 0)
        assert igor.updateLocalCache() == (True, None, 1)
        assert igor.getAllConstraints().data == (c3, )

    @pytest.mark.parametrize('getCon', _AllConstraintGetters)
    def test_uniquePairs(self, getCon):
        """
        Add- and delete constraints and verify that Igor maintins a consistent
        list of unique body pairs.
        """
        # Convenience.
        igor = self.igor

        # Create the constraints for this test.
        c1 = getCon(1, 2, 'foo')
        c2 = getCon(2, 3, 'foo')
        c3 = getCon(3, 4, 'foo')

        # There must not be any pairs after a reset.
        assert igor.reset() == (True, None, None)
        assert igor.uniquePairs() == (True, None, tuple())

        # Adding a constraint must result in one unique pair of IDs *after*
        # updating the Igor cache.
        assert igor.addConstraints([c1]) == (True, None, 1)
        assert igor.uniquePairs() == (True, None, tuple())
        assert igor.updateLocalCache() == (True, None, 1)
        assert igor.uniquePairs().data == ((c1.rb_a, c1.rb_b), )

        # Add three more constraints, only two of which are actually new.
        assert igor.addConstraints([c1, c2, c3]) == (True, None, 2)
        assert igor.updateLocalCache() == (True, None, 3)

        # Verify that the set of unique pairs now covers those involved in the
        # constraints.
        ref = [(_.rb_a, _.rb_b) for _ in (c1, c2, c3)]
        assert set(igor.uniquePairs().data) == set(tuple(ref))

        # Delete two constraints.
        assert igor.deleteConstraints([c1, c3]) == (True, None, 2)
        assert set(igor.uniquePairs().data) == set(tuple(ref))
        assert igor.updateLocalCache() == (True, None, 1)
        assert igor.uniquePairs().data == ((c2.rb_a, c2.rb_b), )

    @pytest.mark.parametrize('getCon', _AllConstraintGetters)
    def test_getConstraint(self, getCon):
        """
        Verify that Igor returns the correct constraints.
        """
        # Convenience.
        igor = self.igor

        # Create the constraints for this test.
        c1 = getCon(1, 2, 'foo')
        c2 = getCon(2, 3, 'foo')
        c3 = getCon(3, 4, 'foo')

        # Query the constraints for bodies that do not feature in any
        # constraints.
        assert igor.reset() == (True, None, None)
        assert igor.getConstraints([]) == (True, None, tuple())
        assert igor.getConstraints([1]) == (True, None, tuple())
        assert igor.getConstraints([1, 2]) == (True, None, tuple())

        # Add four constraints for the following tests.
        assert igor.addConstraints([c1, c2, c3]) == (True, None, 3)

        # Query the constraints that involve object one. This must return only
        # the first object, and only *after* the local Igor cache was updated.
        assert igor.getConstraints([1]) == (True, None, ())
        assert igor.updateLocalCache() == (True, None, 3)
        ret = igor.getConstraints([1])
        assert ret.data == (c1, )

        # Query the constraints that involve body 1 & 5. This must again return
        # only a single hit because body 5 is not part of any constraint.
        ret = igor.getConstraints([1, 5])
        assert ret.data == (c1, )

        # Objects 1 & 4 feature in to individual constraints.
        ret = igor.getConstraints([1, 4])
        assert sorted(ret.data) == sorted((c1, c3))

        # Objects 1 & 2 & 4 feature in all three constraints.
        ret = igor.getConstraints([1, 2, 4])
        assert len(ret.data) == 3
        assert sorted(ret.data) == sorted((c1, c2, c3))

        # Body 2 features in two constraints whereas body 10 features in none.
        ret = igor.getConstraints([2, 10])
        assert sorted(ret.data) == sorted((c1, c2))
