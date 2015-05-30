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
Manage the constraints between objects.
"""
import azrael.config as config
import azrael.database as database

from azrael.types import RetVal, ConstraintMeta, ConstraintP2P
from IPython import embed as ipshell


class Igor:
    """
    """
    def __init__(self):
        self.db = database.dbHandles['Constraints']
        self._cache = {}

    def reset(self):
        self.db.drop()
        self._cache = {}
        return RetVal(True, None, None)

    def updateLocalCache(self):
        prj = {'_id': False}
        cursor = self.db.find({}, prj)

        self._cache = {}
        cache = self._cache
        CM = ConstraintMeta
        constraints = (CM(**_) for _ in cursor)
        for constr in constraints:
            if constr.type.upper() == 'P2P':
                tmp = constr._replace(data=ConstraintP2P(**constr.data))
                cache[CM(tmp.type, tmp.rb_a, tmp.rb_b, tmp.tag, None)] = tmp
            else:
                continue

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
