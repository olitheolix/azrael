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
            if con.type.upper() == 'P2P':
                # Build the correct named tuple for the data part.
                con = con._replace(data=ConstraintP2P(**con.data))
            else:
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

    def addConstraints(self, constraints: (tuple, list)):
        """
        Merge this code into the 'add' function.
        """
        cnt = 0
        for con in constraints:
            rb_a, rb_b = con.rb_a, con.rb_b

            assert rb_a is not None
            if rb_b is not None:
                rb_a, rb_b = sorted((rb_a, rb_b))
            con = con._replace(rb_a=rb_a, rb_b=rb_b)
            con = con._replace(data=con.data._asdict())

            query = {'rb_a': rb_a, 'rb_b': rb_b, 'type': con.type}
            r = self.db.update(query, {'$setOnInsert': con._asdict()}, upsert=True)
            if r['updatedExisting']:
                cnt += r['nModified']
            else:
                cnt += r['n']

        return RetVal(True, None, cnt)

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
        out = {(_.rb_a, _.rb_b) for _ in self._cache}
        return RetVal(True, None, tuple(out))
