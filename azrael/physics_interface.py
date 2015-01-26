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
Specify and implement the necessary functions to create, access and manipulate
state variables.
"""

import sys
import logging
import IPython
import numpy as np
import azrael.util as util
import azrael.config as config
import azrael.database as database
import azrael.bullet.bullet_data as bullet_data

from azrael.typecheck import typecheck

ipshell = IPython.embed

# Convenience.
_BulletData = bullet_data._BulletData
BulletDataOverride = bullet_data.BulletDataOverride

# Return value signature.
RetVal = util.RetVal

# Create module logger.
logit = logging.getLogger('azrael.' + __name__)


def getNumObjects():
    """
    Return the number of objects in the simulation.

    :returns int: number of objects in simulation.
    """
    return database.dbHandles['SV'].count()


@typecheck
def dequeueCommands():
    """
    Return and de-queue all commands currently in the command queue.

    :return QueuedCommands: a tuple with lists for each command.
    """
    # Convenience.
    db = database.dbHandles['Commands']

    # Query all pending commands and delete them from the queue.
    docs = list(db.find())
    ret = db.remove({'_id': {'$in': [_['_id'] for _ in docs]}})

    # Split the commands into categories.
    spawn = [_ for _ in docs if _['cmd'] == 'spawn']
    remove = [_ for _ in docs if _['cmd'] == 'remove']
    modify = [_ for _ in docs if _['cmd'] == 'modify']
    force = [_ for _ in docs if _['cmd'] == 'force']

    # Compile the output dictionary.
    out = {'spawn': spawn, 'remove': remove, 'modify': modify, 'force': force}
    return RetVal(True, None, out)


@typecheck
def addCmdSpawn(objData: (tuple, list)):
    """
    Enqueue a new object with ``objID`` for Leonard to spawn.

    Contrary to what the name ``aabb`` suggests, this actually denotes a
    bounding sphere and thus requires only a scalar argument instead of 3 side
    lengths. This will change eventually to become a proper AABB.

    Returns **False** if ``objID`` already exists or is already queued.

    Leonard will apply this request once per physics cycle but it is impossible
    to determine when exactly.

    fixme: argument docu

    :param int objID: object ID to insert.
    :param bytes sv: encoded state variable data.
    :param float aabb: size of AABB.
    :return: success.
    """
    for objID, sv, aabb in objData:
        try:
            assert isinstance(objID, int)
            assert isinstance(sv, _BulletData)
            assert isinstance(aabb, (int, float))
        except AssertionError:
            msg = '<addCmdQueue> received invalid argument type'
            return RetVal(False, msg, None)

        # Sanity checks.
        if objID < 0:
            msg = 'Object ID is negative'
            logit.warning(msg)
            return RetVal(False, msg, None)
        if aabb < 0:
            msg = 'AABB must be non-negative'
            logit.warning(msg)
            return RetVal(False, msg, None)

    # Meta data for spawn command.
    db = database.dbHandles['Commands']
    bulk = db.initialize_unordered_bulk_op()
    for objID, sv, aabb in objData:
        query = {'cmd': 'spawn', 'objID': objID}
        data = {'sv': sv, 'AABB': float(aabb)}

        # Insert this document unless a document with matching query already
        # exists.
        bulk.find(query).upsert().update({'$setOnInsert': data})

    ret = bulk.execute()
    if ret['nMatched'] > 0:
        # A template with name ``templateID`` already existed --> failure.
        # It should be impossible for this to happen if the object IDs come
        # from ``database.getUniqueObjectIDs``.
        msg = 'At least one objID already existed --> serious bug'
        logit.error(msg)
        return RetVal(False, msg, None)
    else:
        # All objIDs were unique --> success.
        return RetVal(True, None, None)

@typecheck
def addCmdRemoveObject(objID: int):
    """
    Remove ``objID`` from the physics simulation.

    Leonard will apply this request once per physics cycle but it is impossible
    to determine when exactly.

    .. note:: This function always succeeds.

    :param int objID: ID of object to delete.
    :return: Success.
    """
    # The 'data' is dummy because Mongo's 'update' requires one.
    db = database.dbHandles['Commands']
    data = query = {'cmd': 'remove', 'objID': objID}
    db.update(query, {'$setOnInsert': data}, upsert=True)
    return RetVal(True, None, None)


@typecheck
def addCmdModifyStateVariable(objID: int, data: BulletDataOverride):
    """
    Queue request to Override State Variables of ``objID`` with ``data``.

    Leonard will apply this request once per physics cycle but it is impossible
    to determine when exactly.

    :param int objID: object to update.
    :param BulletDataOverride pos: new object attributes.
    :return bool: Success
    """
    # Sanity check.
    if objID < 0:
        msg = 'Object ID is negative'
        logit.warning(msg)
        return RetVal(False, msg, None)

    # Do nothing if data is None.
    if data is None:
        return RetVal(True, None, None)

    # Make sure that ``data`` is really valid by constructing a new
    # BulletDataOverride instance from it.
    data = BulletDataOverride(*data)
    if data is None:
        return RetVal(False, 'Invalid override data', None)

    # All fields in ``data`` (a BulletDataOverride instance) are, by
    # definition, one of {None, int, float, np.ndarray}. The following code
    # merely converts the  NumPy arrays to normal lists so that Mongo can store
    # them. For example, BulletDataOverride(None, 2, array([1,2,3]), ...)
    # would become [None, 2, [1,2,3], ...].
    data = list(data)
    for idx, val in enumerate(data):
        if isinstance(val, np.ndarray):
            data[idx] = val.tolist()

    # Save the new SVs to the DB (overwrite existing ones).
    db = database.dbHandles['Commands']
    query = {'cmd': 'modify', 'objID': objID}
    data = {'sv': data}
    db.update(query, {'$setOnInsert': data},  upsert=True)

    # This function was successful if exactly one document was updated.
    return RetVal(True, None, None)


@typecheck
def addCmdSetForceAndTorque(objID: int, force: list, torque: list):
    """
    Apply ``torque`` and central ``force`` to ``objID``.

    :param int objID: the object
    :param list force: apply this central ``force`` to ``objID``.
    :param list torque: apply this ``torque`` to ``objID``.
    :return bool: Success
    """
    # Sanity check.
    if objID < 0:
        msg = 'Object ID is negative'
        logit.warning(msg)
        return RetVal(False, msg, None)
    if not (len(force) == len(torque) == 3):
        return RetVal(False, 'force or torque has invalid length', None)

    # Update the DB.
    db = database.dbHandles['Commands']
    query = {'cmd': 'force', 'objID': objID}
    data = {'force': force, 'torque': torque}
    db.update(query, {'$setOnInsert': data}, upsert=True)

    return RetVal(True, None, None)


@typecheck
def getStateVariables(objIDs: (list, tuple)):
    """
    Retrieve the state variables for all ``objIDs``.

    Return *None* for every entry non-existing objID.

    :param iterable objIDs: list of object IDs for which to return the SV.
    :return dict: dictionary of the form {objID: sv}
    """
    # Sanity check.
    for objID in objIDs:
        if objID < 0:
            msg = 'Object ID is negative'
            logit.warning(msg)
            return RetVal(False, msg, None)

    # Retrieve the state variables.
    out = {_: None for _ in objIDs}
    with util.Timeit('physAPI.1_getSV') as timeit:
        tmp = list(database.dbHandles['SV'].find({'objID': {'$in': objIDs}}))

    with util.Timeit('physAPI.2_getSV') as timeit:
        for doc in tmp:
            out[doc['objID']] = _BulletData(*doc['sv'])
    return RetVal(True, None, out)


@typecheck
def getAABB(objIDs: (list, tuple)):
    """
    Retrieve the AABBs for all ``objIDs``.

    This function returns the AABBs (or *None* if it does not exist) for all
    ``objIDs``.

    :param iterable objIDs: list of object ID for which to return the SV.
    :return: size of AABBs.
    :rtype: list of *floats*.
    """
    # Sanity check.
    for objID in objIDs:
        if objID < 0:
            msg = 'Object ID is negative'
            logit.warning(msg)
            return RetVal(False, msg, None)

    # Retrieve the state variables.
    out = list(database.dbHandles['SV'].find({'objID': {'$in': objIDs}}))

    # Put all AABBs into a dictionary to simplify sorting afterwards.
    out = {_['objID']: np.array(_['AABB'], np.float64) for _ in out}

    # Compile the AABB values into a list ordered by ``objIDs``. Insert a None
    # element if a particular objID has no AABB (probably means the object was
    # recently deleted).
    out = [out[_] if _ in out else None for _ in objIDs]

    # Return the AABB values.
    return RetVal(True, None, out)


@typecheck
def _updateBulletDataTuple(orig: _BulletData,
                           new: bullet_data.BulletDataOverride):
    """
    Overwrite fields in ``orig`` with content of ``new``.

    If one or more fields in ``new`` are *None* then the original value in
    ``orig`` will not be modified.

    This is a convenience function. It avoids code duplication which was
    otherwise unavoidable because not all Leonard implementations inherit the
    same base class.

    :param _BulletData orig: the original tuple.
    :param BulletDataOverride new: the new values (*None* entries are ignored).
    :return: updated version of ``orig``.
    :rtype: _BulletData
    """
    if new is None:
        return orig

    # Convert the named tuple ``orig`` into a dictionary.
    fields = orig._fields
    dict_orig = {_: getattr(orig, _) for _ in fields}

    # Copy all not-None values from ``new`` into ``dict_orig``.
    for k, v in zip(fields, new):
        if v is not None:
            dict_orig[k] = v

    # Build a new _BulletData instance and return it.
    return _BulletData(**dict_orig)


def getAllStateVariables():
    """
    Return a dictionary of {objID: SV} all objects in the simulation.

    The keys and values of the returned dictionary correspond to the object ID
    and their associated State Vectors, respectively.

    :return: dictionary of state variables with object IDs as keys.
    :rtype: dict
    """
    # Compile all object IDs and state variables into a dictionary.
    out = {}
    for doc in database.dbHandles['SV'].find():
        key, value = doc['objID'], _BulletData(*doc['sv'])
        out[key] = value
    return RetVal(True, None, out)


def getAllObjectIDs():
    """
    Return all object IDs in the simulation.

    :return: list of all object IDs in the simulation.
    :rtype: list
    """
    # Compile and return the list of all object IDs.
    out = [_['objID'] for _ in database.dbHandles['SV'].find()]
    return RetVal(True, None, out)
