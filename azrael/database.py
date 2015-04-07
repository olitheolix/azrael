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
import os
import shutil
import pymongo
import logging

import azrael.util
import azrael.config as config
from IPython import embed as ipshell
from azrael.types import typecheck

RetVal = azrael.util.RetVal

# Global database handles.
logit = logging.getLogger('azrael.' + __name__)

client = pymongo.MongoClient()
dbName = 'azrael'
dbHandles = {
    'SV': client[dbName]['sv'],
    'Commands': client[dbName]['Cmd'],
    'Templates': client[dbName]['template'],
    'ObjInstances': client[dbName]['objinstances'],
    'Counters': client[dbName]['Counters']
}

@typecheck
def init(reset=False):
    """
    Connect to the State Variable database. Flush it if ``reset`` is **True**.

    fixme: docu update
    fixme: reset parameter is now redundant

    :param bool reset: flush the database.
    """
    if reset:
        client.drop_database(dbName)
        logit.info('Deleting data directory <{}>'.format(config.dir_data))

        # fixme: delete the rest of this if-block once Dibbler works.
        try:
            shutil.rmtree(config.dir_data)
        except FileNotFoundError:
            pass
        os.makedirs(config.dir_template, exist_ok=True)
        os.makedirs(config.dir_instance, exist_ok=True)



@typecheck
def getUniqueObjectIDs(numIDs: int):
    """
    Return ``numIDs`` unique object IDs as a tuple.

    If ``numIDs`` is Zero then return a scalar with the current value.

    The ``numIDs`` is positive then return a tuple with ``numIDs`` entries,
    each of which constitutes a unique ID.

    This function returns an error unless ``numIDs`` is non-negative.

    :param int numIDs: non-negative integer.
    :return tuple or scalar: object IDs (numIDs > 0) or last issued object ID
                            (numIDs = 0)
    """
    # Sanity check.
    if numIDs < 0:
        return RetVal(False, 'numIDs must be non-negative', None)

    # Increment the counter by ``numIDs``.
    fam = dbHandles['Counters'].find_and_modify
    doc = fam({'name': 'objcnt'},
              {'$inc': {'cnt': numIDs}},
              new=True, upsert=True)

    # Error check.
    if doc is None:
        return RetVal(False, 'Cannot determine new object IDs', None)

    # Extract the new counter value (after it was incremented).
    cnt = doc['cnt']

    # Return the either the current value or the range of new IDs.
    if numIDs == 0:
        return RetVal(True, None, cnt)
    else:
        newIDs = tuple(range(cnt - numIDs + 1, cnt + 1))
        return RetVal(True, None, newIDs)
