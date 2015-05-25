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

from azrael.types import RetVal, ConstraintMeta


class Igor:
    """
    fixme:
     - return error if objects do not exist?
     - add: accept list argument
     - get: accept list argument; must only return unique constraints; must
            return ConstraintMeta tuples (not necessary to wrap the data in its
            respective eg ConstraintsP2P tuple)
     - docu
    """
    def __init__(self):
        self.db = database.dbHandles['Constraints']

    def reset(self):
        self.db.drop()
    
    def add(self, con: ConstraintMeta):
        rb_a, rb_b = con.rb_a, con.rb_b
        assert rb_a is not None
        if rb_b is not None:
            rb_a, rb_b = sorted((rb_a, rb_b))
        
        query = {'rb_a': rb_a, 'rb_b': rb_b, 'type': con.type}
        r = self.db.update(query, {'$setOnInsert': con._asdict()}, upsert=True)
        if r['updatedExisting']:
            cnt = r['nModified']
        else:
            cnt = r['n']
        return RetVal(True, None, cnt)

    def get(self, id_a: int, id_b: int=None):
        assert id_a is not None
        if id_b is not None:
            id_a, id_b = sorted((id_a, id_b))

        if id_b is None:
            res1 = list(self.db.find({'rb_a': id_a}))
            res2 = list(self.db.find({'rb_b': id_a}))
            res = res1 + res2
        else:
            query = {'rb_a': id_a, 'rb_b': id_b}
            res = list(self.db.find(query))

        for el in res:
            del el['_id']
        return RetVal(True, None, tuple(res))

    def getMulti(self, IDs: (tuple, list)):
        query = {'$or': [{'rb_a': {'$in': IDs}}, {'rb_b': {'$in': IDs}}]}
        prj = {_: True for _ in ConstraintMeta._fields}
        prj['_id'] = False
        res = [ConstraintMeta(**_) for _ in self.db.find(query, prj)]
        return RetVal(True, None, tuple(res))
