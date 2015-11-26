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
import azrael.datastore as datastore

from IPython import embed as ipshell
from azrael.aztypes import RetVal, ConstraintMeta


class Igor:
    """
    """
    def __init__(self):
        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

        # Create the database handle and local constraint cache.
        self.db = datastore.dbHandles['Constraints']
        self._cache = {}

    def reset(self):
        """
        Flush the constraint database.

        :return: success
        """
        self.db.reset()
        self._cache = {}
        return RetVal(True, None, None)

    def updateLocalCache(self):
        """
        Download *all* constraints from the database into the local cache.

        :return: Number of unique constraints in local cache after operation.
        """
        # Flush the cache and create a convenience handle.
        self._cache = {}
        cache = self._cache

        # Fetch all constraints.
        ret = self.db.getAll()
        if not ret.ok:
            return ret
        docs = ret.data

        # Extract the AID from the compound key value. A compound key is a
        # colon (':') separated string in the form of 'aid:contype:rb_a:rb_b'.
        for k, v in docs.items():
            v['aid'] = k.split(':')[0]

        # Convert the documents into ConstraintMeta instances.
        constraints = (ConstraintMeta(**_) for _ in docs.values())

        # Iterate over all constraints and  build a dictionary. The keys are
        # `ConstraintMeta` tuples with a value of *None* for the data field.
        # The values contain the same `ConstraintMeta` data but with a valid
        # 'condata' attribute.
        for con in constraints:
            # Replace the 'condata' field in the constraint. This will become
            # the key for the self._cache dictionary.
            key = con._replace(condata=None)
            cache[key] = con
            del con, key

        # Return the number of valid constraints currently in the cache.
        return RetVal(True, None, len(self._cache))

    def addConstraints(self, constraints: (tuple, list)):
        """
        Add all ``constraints`` to the database.

        All entries in ``constraints`` must be ``ConstraintMeta`` instances,
        and their `data` attribute must be a valid ``Constraint*`` instance.

        This method will skip over all constraints with an invalid/unknown
        type.

        It will return the number of constraints

        :param list constraints: a list of ``ConstraintMeta`` instances.
        :return: number of newly added constraints.
        """
        constraints_sane = []
        for con in constraints:
            # Compile- and sanity check all constraints.
            try:
                con = ConstraintMeta(*con)
            except TypeError:
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

            # Add it to the list of constraints to update in the database.
            constraints_sane.append(con)

        # Return immediately if the list of constraints to add is empty.
        if len(constraints_sane) == 0:
            return RetVal(True, None, 0)

        # Compile the put operation for each constraint.
        ops = {}
        for con in constraints_sane:
            # The key is a colon seprated string that encodes the AID of
            # constraint, constraint type, and AIDs of first and second rigid
            # body. This is not very elegant but the data store only supports
            # string keys (for now). The colon itself will not lead to
            # ambiguities because the the various AIDs are not allowed to
            # contain them.
            key = ':'.join([con.aid, con.contype, con.rb_a, con.rb_b])
            ops[key] = {'data': con._asdict()}
        ret = self.db.put(ops)

        # Return the number of newly created constraints.
        nupserted = len([_ for _ in ret.data.values() if _ is True])
        return RetVal(True, None, nupserted)

    def getConstraints(self, bodyIDs: (set, tuple, list)):
        """
        Return all constraints that involve any of the bodies in ``bodyIDs``.

        Return all constraints if ``bodyIDs`` is *None*.

        ..note:: this method only consults the local cache. Depending on your
            circumstances you may want to call ``updateLocalCache`` first.

        :param list[int] bodyIDs: list of body IDs
        :return: list of ``ConstraintMeta`` instances.
        :rtype: tuple
        """
        if bodyIDs is None:
            return RetVal(True, None, tuple(self._cache.values()))

        # Reduce bodyIDs to a set. This should speed up look ups.
        bodyIDs = {_ for _ in bodyIDs if isinstance(_, str)}

        # Iterate over all constraints and pick the ones that contain at least
        # one of the bodies specified in `bodyIDs`.
        out = []
        for tmp in self._cache:
            if not (tmp.rb_a in bodyIDs or tmp.rb_b in bodyIDs):
                continue
            out.append(self._cache[tmp])
        return RetVal(True, None, tuple(out))

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
        # Compile- and sanity check the input.
        constraints = [ConstraintMeta(*_) for _ in constraints]

        # Return immediately if the list of constraints to add is empty.
        if len(constraints) == 0:
            return RetVal(True, None, 0)

        # Compile datastore operation for each constraints to remove.
        ops = []
        for con in constraints:
            # See 'addConstraints' method for an explanation of the colon
            # separated compound key.
            key = ':'.join([con.aid, con.contype, con.rb_a, con.rb_b])
            ops.append(key)
        ret = self.db.remove(ops)

        # Return the number of newly created constraints.
        return RetVal(True, None, ret.data)

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
