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

# List of known constraints and the associated named tuple.
_Known_Constraints = {
    'P2P': ConstraintP2P,
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

        This method will skip over all constraints with an invalid/unknown type.

        It will return the number of constraints

        fixme: add sanity checks.
        fixme: must be a buld query
        fixme: the key must include the tag

        :param list constraints: a list of ``ConstraintMeta`` instances.
        :return: number of newly added constraints.
        """
        cnt = 0
        for con in constraints:
            # Skip all constraints with an unknown type.
            if con.type.upper() not in _Known_Constraints:
                continue

            # Convenience.
            rb_a, rb_b = con.rb_a, con.rb_b

            # The first body must not be None.
            if rb_a is None:
                continue

            # If both bodies are not None then sort them to simplify the logic
            # that fetches constraints.
            if rb_b is not None:
                rb_a, rb_b = sorted((rb_a, rb_b))
            con = con._replace(rb_a=rb_a, rb_b=rb_b)

            # Convert content of the 'data' field into a dictionary to store it
            # in MongoDB without loosing the attribute names.
            con = con._replace(data=con.data._asdict())

            # Insert the constraints into MongoDB. They key specifies the IDs
            # of the two involved bodies, the type, and the tag.
            query = {'rb_a': rb_a, 'rb_b': rb_b, 'type': con.type}
            r = self.db.update(query, {'$setOnInsert': con._asdict()}, upsert=True)

            # Determine how many new constraints were actually added
            if r['updatedExisting']:
                cnt += r['nModified']
            else:
                cnt += r['n']

        return RetVal(True, None, cnt)

    def getConstraints(self, bodyIDs: (tuple, list)):
        """
        """
        bodyIDs = set(bodyIDs)
        out = []
        for tmp in self._cache:
            if not (tmp.rb_a in bodyIDs or tmp.rb_b in bodyIDs):
                continue
            out.append(self._cache[tmp])
        return RetVal(True, None, tuple(out))

    def getAllConstraints(self):
        return RetVal(True, None, tuple(self._cache.values()))

    def delete(self, constraints: (tuple, list)):
        cnt = 0
        for constr in constraints:
            query = {'rb_a': constr.rb_a,
                     'rb_b': constr.rb_b,
                     'tag': constr.tag}
            ret = self.db.remove(query)
            cnt += ret['n']
        return RetVal(True, None, cnt)

    def uniquePairs(self):
        """
        fixme: add test where one body is None
        """

        out = {(_.rb_a, _.rb_b) for _ in self._cache}
        return RetVal(True, None, tuple(out))
