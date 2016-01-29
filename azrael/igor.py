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
        self.db = datastore.getDSHandle('Constraints')
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
        Add all ``constraints`` to the database and return success.

        All entries in ``constraints`` must be ``ConstraintMeta`` instances,
        and their `data` attribute must be a valid ``Constraint*`` instance.

        Abort immediately if any of the constraints are invalid, or if the same
        constraint occurs multiple times in ``constraints``.

        The return value is an list of Booleans to indicate which constraint
        was newly added. If a constraint already exists then it will not be
        overwritten and the return value for it would be False.

        :param list constraints: a list of ``ConstraintMeta`` instances.
        :return: list[Bool]
        """
        # Validate the constraints and convert them into a sane format (most
        # notably, making sure that rb_a and rb_b are sorted.
        constraints_sane = []
        for con in constraints:
            # Compile- and sanity check all constraints.
            try:
                con = ConstraintMeta(*con)
            except TypeError:
                return RetVal(False, 'Invalid constraint data', None)

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
        idx2key = {}
        for idx, con in enumerate(constraints_sane):
            # The key is a colon seprated string that encodes the AID of
            # constraint, constraint type, and AIDs of first and second rigid
            # body. This is not very elegant but the data store only supports
            # string keys (for now). The colon itself will not lead to
            # ambiguities because the the various AIDs are not allowed to
            # contain them.
            key = ':'.join([con.aid, con.contype, con.rb_a, con.rb_b])
            ops[key] = {'data': con._asdict()}

            # Record which datastore key belonged to which constraint. We will
            # need this to compile the return value where we indicate which
            # constraints could be added, and which could not.
            idx2key[idx] = key

        # Verify that we have as many data store operations as we have
        # constraints. If not then one or more constraints mapped to the same
        # key and were thus duplicates.
        if len(constraints_sane) > len(ops):
            return RetVal(False, 'Not all constraints are unique', None)
        else:
            ret = self.db.put(ops)

        # Return the number of newly created constraints.
        success = [ret.data[idx2key[_]] for _ in range(len(constraints_sane))]
        return RetVal(True, None, success)

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

    def removeConstraints(self, constraints: (tuple, list)):
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

        # Return the number of deleted constraints.
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
