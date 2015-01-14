# Copyright 2014, Oliver Nagy <olitheolix@gmail.com>
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
Database abstractions.
"""
import pymongo
import IPython
import logging

import azrael.util

ipshell = IPython.embed
RetVal = azrael.util.RetVal

client = pymongo.MongoClient()
_DBCounters = client['azrael']['Counters']
del client


def reset():
    """
    Reset all data bases.
    """
    _DBCounters.drop()


def getNewWPID():
    """
    Return a new and unque WP ID.
    """
    db = _DBCounters.find_and_modify
    wpid = db({'name': 'wpcnt'},
              {'$inc': {'cnt': 1}},
              new=True, upsert=True)

    if wpid is None:
        return RetVal(False, 'Cannot fetch new WPID', None)
    else:
        return RetVal(True, None, wpid['cnt'])


def getNewObjectID():
    """
    Return a new and unique object ID.
    """
    db = _DBCounters.find_and_modify
    wpid = db({'name': 'objcnt'},
              {'$inc': {'cnt': 1}},
              new=True, upsert=True)

    if wpid is None:
        return RetVal(False, 'Cannot fetch new object ID', None)
    else:
        return RetVal(True, None, wpid['cnt'])
