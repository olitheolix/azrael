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
Igor is a stateless class to manage rigid body constraints.
"""
import logging
import azrael.config as config
import azrael.database as database

from IPython import embed as ipshell
from azrael.types import RetVal, ConstraintMeta, ConstraintP2P
from azrael.types import Constraint6DofSpring2

# List of known constraints and the associated named tuple.
_Known_Constraints = {
    'P2P': ConstraintP2P,
    '6DOFSPRING2': Constraint6DofSpring2,
}


class Igor:
    """
    """
    def __init__(self):
        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

        # Create the database handle and local constraint cache.
        self.db = database.dbHandles['Constraints']
        self._cache = {}

    def reset(self):
        """
        Flush the constraint database.

        :return: success
        """
        self.db.drop()
        self._cache = {}
        return RetVal(True, None, None)

    def updateLocalCache(self):
        """
        Download *all* constraints from the database into the local cache.

        :return: Number of unique constraints in local cache after operation.
        """
        # Create a Mongo cursor that retrieves all constraints (minus the _id
        # field).
        prj = {'_id': False}
        cursor = self.db.find({}, prj)

        # Flush the cache.
        self._cache = {}

        # Convenience.
        cache = self._cache
        CM = ConstraintMeta

        # Build an iterator that returns the constraints from the data base and
        # wraps them into ConstraintMeta tuples.
        constraints = (CM(**_) for _ in cursor)

        # Iterate over all constraints and substitute the 'data' attribute with
        # the correct named tuple for the respective constraint. This will
        # build a dictionary where the keys are ConstraintMeta tuple with a
        # value of *None* for the data field, and the value is the same
        # `ConstraintMeta` data but with a valid 'data' attribute.
        for con in constraints:
            try:
                NT = _Known_Constraints[con.type.upper()]
                con = con._replace(data=NT(**con.data))
            except KeyError:
                # Skip over unknown constraints.
                msg = 'Ignoring unknown constraint {}'.format(con.type)
                self.logit.info(msg)
                continue

            # Replace the 'data' field in the constraint. This will become
            # the key for the self._cache dictionary.
            key = con._replace(data=None)
            cache[key] = con
            del con, key

        # Return the number of valid constraints now in the cache.
        return RetVal(True, None, len(self._cache))

    def addConstraints(self, constraints: (tuple, list)):
        """
        Add all ``constraints`` to the database.

        All entries in ``constraints`` must be ``ConstraintMeta`` instances,
        and their `data` attribute must be a valid ``Consraint***`` instance.

        This method will skip over all constraints with an invalid/unknown
        type.

        It will return the number of constraints

        fixme: add sanity checks.

        :param list constraints: a list of ``ConstraintMeta`` instances.
        :return: number of newly added constraints.
        """
        queries = []
        for con in constraints:
            # Skip all constraints with an unknown type.
            if con.type.upper() not in _Known_Constraints:
                continue

            # Convenience.
            rb_a, rb_b = con.rb_a, con.rb_b

            # The first body must not be None.
            if rb_a is None or rb_b is None:
                continue

            # Sort the body IDs. This will simplify the logic to fetch- and
            # process constraints.
            rb_a, rb_b = sorted((rb_a, rb_b))
            con = con._replace(rb_a=rb_a, rb_b=rb_b)

            # Convert content of the 'data' field into a dictionary to store it
            # in MongoDB without loosing the attribute names.
            con = con._replace(data=con.data._asdict())

            # Insert the constraints into MongoDB. The constraint query must
            # match both objects IDs, the type, and the constraint ID.
            tmp = {'rb_a': rb_a, 'rb_b': rb_b,
                   'type': con.type, 'id': con.id}
            queries.append((tmp, con._asdict()))

        # Return immediately if the list of constraints to add is empty.
        if len(queries) == 0:
            return RetVal(True, None, 0)

        # Compile the bulk query and execute it.
        bulk = self.db.initialize_unordered_bulk_op()
        for q, c in queries:
            bulk.find(q).upsert().update({'$setOnInsert': c})
        ret = bulk.execute()

        # Return the number of newly created constraints.
        return RetVal(True, None, ret['nUpserted'])

    def getConstraints(self, bodyIDs: (set, tuple, list)):
        """
        Return all constraints that involve any of the bodies in ``bodyIDs``.

        ..note:: this method only consults the local cache. Depending on your
                 circumstances you may want to call ``updateLocalCache``
                 first.

        :param list[int] bodyIDs: list of body IDs
        :return: list of ``ConstraintMeta`` instances.
        :rtype: tuple
        """
        # Sanity check: remove all non-integers and turn the list into a set
        # for fast look ups.
        bodyIDs = set([_ for _ in bodyIDs if isinstance(_, int)])

        # Iterate over all constraints and pick the ones that contain at least
        # one of the bodies specified in `bodyIDs`.
        out = []
        for tmp in self._cache:
            if not (tmp.rb_a in bodyIDs or tmp.rb_b in bodyIDs):
                continue
            out.append(self._cache[tmp])
        return RetVal(True, None, tuple(out))

    def getAllConstraints(self):
        """
        Return all constraints in the local cache.

        ..note:: this method only consults the local cache. Depending on your
                 circumstances you may want to to call ``updateLocalCache``
                 first.

        :return: list of all ``ConstraintMeta`` instances in local cache.
        :rtype: tuple
        """
        return RetVal(True, None, tuple(self._cache.values()))

    def deleteConstraints(self, constraints: (tuple, list)):
        """
        Delete the ``constraints`` in the data base.

        It is save to call this method on non-existing constraints (it will
        simply skip them).

        ..note:: this will *not* update the local cache. Call
                 ``updateLocalCache`` to do so.

        :param list constraints: list of `ConstraintMeta` tuples.
        :return: number of deleted entries.
        """
        queries = []
        for constr in constraints:
            # Sanity checks.
            try:
                assert isinstance(constr.rb_a, int)
                assert isinstance(constr.rb_b, int)
                assert isinstance(constr.type, str)
                assert isinstance(constr.id, str)
            except AssertionError:
                continue

            # Create the query for the current constraint.
            tmp = {'rb_a': constr.rb_a,
                   'rb_b': constr.rb_b,
                   'type': constr.type,
                   'id': constr.id}
            queries.append(tmp)

        # Return immediately if the list of constraints to add is empty.
        if len(queries) == 0:
            return RetVal(True, None, 0)

        # Compile the bulk query and execute it.
        bulk = self.db.initialize_unordered_bulk_op()
        for q in queries:
            bulk.find(q).remove()
        ret = bulk.execute()

        # Return the number of newly created constraints.
        return RetVal(True, None, ret['nRemoved'])

    def uniquePairs(self):
        """
        Return the list of unique body pairs involved in any collision.

        ..note:: this method only consults the local cache. Depending on your
                 circumstances you may want to to call ``updateLocalCache``
                 first.

        :return: list of unique body ID pairs (eg ((1, 2), (2, 3), (5, 20)))
        """
        out = {(_.rb_a, _.rb_b) for _ in self._cache}
        return RetVal(True, None, tuple(out))
