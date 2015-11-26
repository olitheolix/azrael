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

from IPython import embed as ipshell
from azrael.test.test import killAzrael, getP2P, get6DofSpring2


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
        assert igor.getConstraints(None).ok
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
        c1 = getCon('foo', '1', '2')
        c2 = getCon('foo', '2', '3')
        c3 = getCon('foo', '3', '4')
        c4 = getCon('foo', '4', '5')
        c5 = getCon('foo', '5', '6')
        c6 = getCon('foo', '6', '7')

        # There must not be any objects to download.
        assert igor.updateLocalCache() == (True, None, 0)

        # Pass an empty list.
        assert igor.addConstraints([]) == (True, None, 0)

        # Add one constraint and update the cache.
        assert igor.addConstraints([c1]) == (True, None, [True])
        assert igor.updateLocalCache() == (True, None, 1)

        # Add the same constraint. This must add no constraint, but the update
        # function must still fetch exactly one constraint.
        assert igor.addConstraints([c1]) == (True, None, [False])
        assert igor.updateLocalCache() == (True, None, 1)

        # Add two new constraints.
        assert igor.addConstraints([c2, c3]) == (True, None, [True] * 2)
        assert igor.updateLocalCache() == (True, None, 3)

        # Add two more constraints, one of which is not new. This must add one
        # new constraint and increase the total number of unique constraints to
        # four.
        assert igor.addConstraints([c3, c4]) == (True, None, [False, True])
        assert igor.updateLocalCache() == (True, None, 4)

        # Add five more constraints, only two of which are actually unique.
        # This must return with an error and do nothing.
        assert igor.addConstraints([c5, c5, c6, c6, c6]).ok is False
        assert igor.updateLocalCache() == (True, None, 4)
        ref = sorted((c1, c2, c3, c4))
        assert sorted(igor.getConstraints(None).data) == ref

        # Reset igor and add two constraints. Only one has a valid
        # 'contype'. The 'addConstraints' must only add the valid one.
        c6 = c6._replace(contype='foo')
        assert igor.reset().ok
        assert igor.addConstraints([c1, c6]).ok is False
        assert igor.updateLocalCache() == (True, None, 0)

    @pytest.mark.parametrize('getCon', _AllConstraintGetters)
    def test_add_unique_bug1(self, getCon):
        """
        Add two constraints that are identical except for their 'aid'.

        In the original implementation this was handled incorrectly
        because the 'aid' was not considered when adding constraints.
        This made it impossible to add more than once constraint of each
        type (eg more than one Point2Point constraint between objects).
        """
        # Convenience.
        igor = self.igor

        # Two constraints that only differ in their 'aid' attribute.
        c1 = getCon('foo', '1', '2')
        c2 = getCon('bar', '1', '2')

        # Attempt to add the first constraint twice. Igor must detect this and
        # only add it once.
        assert igor.reset().ok
        assert igor.addConstraints([c1, c1]).ok is False

        # Attempt to both constraints. Without the bug fix Igor would only add
        # the first one, whereas with the bug fix it adds both.
        assert igor.reset().ok
        assert igor.addConstraints([c1, c2]) == (True, None, [True] * 2)

        # Update the local cache and verify that really both constraints are
        # available.
        assert igor.updateLocalCache() == (True, None, 2)
        assert sorted(igor.getConstraints(None).data) == sorted((c1, c2))

    @pytest.mark.parametrize('getCon', _AllConstraintGetters)
    def test_getConstraints_all(self, getCon):
        """
        Add constraints and very that Igor can return them after cache updates.
        """
        # Convenience.
        igor = self.igor

        # Create the constraints for this test.
        c1 = getCon('foo', '2', '3')
        c2 = getCon('foo', '3', '4')
        c3 = getCon('foo', '4', '5')

        # The list of constraints must be empty after a reset.
        assert igor.reset() == (True, None, None)
        assert igor.getConstraints(None).data == tuple()
        assert igor.updateLocalCache() == (True, None, 0)
        assert igor.getConstraints(None).data == tuple()

        # Add two constraints and verify that Igor returns them *after* a cache
        # update.
        assert igor.addConstraints([c1, c2]) == (True, None, [True] * 2)
        assert igor.getConstraints(None).data == tuple()
        assert igor.updateLocalCache() == (True, None, 2)
        assert sorted(igor.getConstraints(None).data) == sorted((c1, c2))

        # Add another two constraints, only one of which is new. Verify that
        # Igor returns the correct three constraints.
        assert igor.addConstraints([c2, c3]) == (True, None, [False, True])
        assert igor.updateLocalCache() == (True, None, 3)
        assert sorted(igor.getConstraints(None).data) == sorted((c1, c2, c3))

    @pytest.mark.parametrize('getCon', _AllConstraintGetters)
    def test_delete(self, getCon):
        """
        Add- and delete several constraints.
        """
        # Convenience.
        igor = self.igor

        # Create the constraints for this test.
        c1 = getCon('foo', '1', '2')
        c2 = getCon('foo', '2', '3')
        c3 = getCon('foo', '3', '4')

        # Attempt to delete a non-existing constraint. This must neither return
        # an error nor delete anything.
        assert igor.reset().ok
        assert igor.deleteConstraints([c1]) == (True, None, 0)
        assert igor.deleteConstraints([c1, c2]) == (True, None, 0)
        assert igor.updateLocalCache() == (True, None, 0)

        # Add some constraints, delete them, and update the cache.
        assert igor.addConstraints([c1, c2, c3]) == (True, None, [True] * 3)
        assert igor.updateLocalCache() == (True, None, 3)
        assert igor.deleteConstraints([c1, c2]) == (True, None, 2)
        assert igor.updateLocalCache() == (True, None, 1)

        # Add/delete more constraints without every updating the cache. These
        # operations must not affect the local cache of constraints in Igor.
        assert igor.reset().ok
        assert igor.addConstraints([c1, c2, c3]) == (True, None, [True] * 3)
        assert igor.deleteConstraints([c1, c2]) == (True, None, 2)
        assert igor.deleteConstraints([c1, c2]) == (True, None, 0)
        assert igor.addConstraints([c1, c2]) == (True, None, [True] * 2)
        assert igor.deleteConstraints([c1]) == (True, None, 1)
        assert igor.deleteConstraints([c1, c2]) == (True, None, 1)
        assert igor.deleteConstraints([c1, c2]) == (True, None, 0)
        assert igor.updateLocalCache() == (True, None, 1)
        assert igor.getConstraints(None).data == (c3, )

    @pytest.mark.parametrize('getCon', _AllConstraintGetters)
    def test_uniquePairs(self, getCon):
        """
        Add- and delete constraints and verify that Igor maintins a consistent
        list of unique body pairs.
        """
        # Convenience.
        igor = self.igor

        # Create the constraints for this test.
        c1 = getCon('foo', '1', '2')
        c2 = getCon('foo', '2', '3')
        c3 = getCon('foo', '3', '4')

        # There must not be any pairs after a reset.
        assert igor.reset() == (True, None, None)
        assert igor.uniquePairs() == (True, None, tuple())

        # Adding a constraint must result in one unique pair of IDs *after*
        # updating the Igor cache.
        assert igor.addConstraints([c1]) == (True, None, [True])
        assert igor.uniquePairs() == (True, None, tuple())
        assert igor.updateLocalCache() == (True, None, 1)
        assert igor.uniquePairs().data == ((c1.rb_a, c1.rb_b), )

        # Add three more constraints, only two of which are actually new.
        assert igor.addConstraints([c1, c2, c3]) == (True, None, [False, True, True])
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
        c1 = getCon('foo', '1', '2')
        c2 = getCon('foo', '2', '3')
        c3 = getCon('foo', '3', '4')

        # Query the constraints for bodies that do not feature in any
        # constraints.
        assert igor.reset() == (True, None, None)
        assert igor.getConstraints([]) == (True, None, tuple())
        assert igor.getConstraints([1]) == (True, None, tuple())
        assert igor.getConstraints([1, 2]) == (True, None, tuple())

        # Add four constraints for the following tests.
        assert igor.addConstraints([c1, c2, c3]) == (True, None, [True] * 3)

        # Query the constraints that involve object one. This must return only
        # the first object, and only *after* the local Igor cache was updated.
        assert igor.getConstraints(['1']) == (True, None, ())
        assert igor.updateLocalCache() == (True, None, 3)
        ret = igor.getConstraints(['1'])
        assert ret.data == (c1, )

        # Query the constraints that involve body 1 & 5. This must again return
        # only a single hit because body 5 is not part of any constraint.
        ret = igor.getConstraints(['1', '5'])
        assert ret.data == (c1, )

        # Objects 1 & 4 feature in to individual constraints.
        ret = igor.getConstraints(['1', '4'])
        assert sorted(ret.data) == sorted((c1, c3))

        # Objects 1 & 2 & 4 feature in all three constraints.
        ret = igor.getConstraints(['1', '2', '4'])
        assert len(ret.data) == 3
        assert sorted(ret.data) == sorted((c1, c2, c3))

        # Body 2 features in two constraints whereas body 10 features in none.
        ret = igor.getConstraints(['2', '10'])
        assert sorted(ret.data) == sorted((c1, c2))
