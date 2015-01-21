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

from collections import namedtuple
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
def getCmdSpawn():
    """
    Return all queued "Spawn" commands.

    The commands remain in the DB and successive calls to this function will
    thus return the previous results.

    :return: objects as inserted by ``addCmdSpawn``.
    :rtype: list of dicts.
    """
    return RetVal(True, None, list(database.dbHandles['CmdSpawn'].find()))


@typecheck
def getCmdModifyStateVariables():
    """
    Return all queued "Modify" commands.

    The commands remain in the DB and successive calls to this function will
    thus return the previous results.

    :return: objects as inserted by ``addCmdModifyStateVariable``.
    :rtype: list of dicts.
    """
    return RetVal(True, None, list(database.dbHandles['CmdModify'].find()))


@typecheck
def getCmdBlah():
    """
    Return all queued "SetForceAndTorque" commands.

    The commands remain in the DB and successive calls to this function will
    thus return the previous results.

    :return: objects as inserted by ``addCmdSetForceAndTorque``.
    :rtype: list of dicts.
    """
    return RetVal(True, None, list(database.dbHandles['CmdForce'].find()))


@typecheck
def getCmdRemove():
    """
    Return all queued "Remove" commands.

    The commands remain in the DB and successive calls to this function will
    thus return the previous results.

    :return: objects as inserted by ``addCmdRemoveObject``.
    :rtype: list of dicts.
    """
    return RetVal(True, None, list(database.dbHandles['CmdRemove'].find()))


@typecheck
def dequeueCmdSpawn(spawn: list):
    """
    De-queue ``spawn`` commands from "Spawn" queue.

    Non-existing documents do not count and will be silently ignored.

    :param list spawn: Mongo documents to remove from "Spawn"
    :return int: number of de-queued commands
    """
    ret = database.dbHandles['CmdSpawn'].remove({'objID': {'$in': spawn}})
    return RetVal(True, None, ret['n'])


@typecheck
def dequeueCmdModify(modify: list):
    """
    De-queue ``modify`` commands from "Modify" queue.

    Non-existing documents do not count and will be silently ignored.

    :param list modify: list of Mongo documents to de-queue.
    :return: number of de-queued commands
    :rtype: tuple
    """
    ret = database.dbHandles['CmdModify'].remove({'objID': {'$in': modify}})
    return RetVal(True, None, ret['n'])


@typecheck
def dequeueCmdRemove(remove: list):
    """
    De-queue ``remove`` commands from "Remove" queue.

    Non-existing documents do not count and will be silently ignored.

    :param list spawn: list of Mongo documents to de-queue.
    :return: number of de-queued commands
    :rtype: tuple
    """
    ret = database.dbHandles['CmdRemove'].remove({'objID': {'$in': remove}})
    return RetVal(True, None, ret['n'])


@typecheck
def dequeueCmdBlah(remove: list):
    """
    De-queue ``setForceAndTorque`` commands from "Force" queue.

    Non-existing documents do not count and will be silently ignored.

    :param list spawn: list of Mongo documents to de-queue.
    :return: number of de-queued commands
    :rtype: tuple
    """
    ret = database.dbHandles['CmdForce'].remove({'objID': {'$in': remove}})
    return RetVal(True, None, ret['n'])


@typecheck
def addCmdSpawn(objID: int, sv: _BulletData, aabb: (int, float)):
    """
    Enqueue a new object with ``objID`` for Leonard to spawn.

    Contrary to what the name ``aabb`` suggests, this actually denotes a
    bounding sphere and thus requires only a scalar argument instead of 3 side
    lengths. This will change eventually to become a proper AABB.

    Returns **False** if ``objID`` already exists or is already queued.

    Leonard will apply this request once per physics cycle but it is impossible
    to determine when exactly.

    :param int objID: object ID to insert.
    :param bytes sv: encoded state variable data.
    :param float aabb: size of AABB.
    :return: success.
    """
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
    data = {'objID': objID, 'sv': sv, 'AABB': float(aabb)}

    # This implements the fictitious "insert_if_not_yet_exists" command. It
    # will return whatever the latest value from the DB, which is either the
    # one we just inserted (success) or a previously inserted one (fail). The
    # only way to distinguish them is to verify that the SVs are identical.
    db = database.dbHandles['CmdSpawn']
    doc = db.find_and_modify({'objID': objID},
                             {'$setOnInsert': data},
                             upsert=True, new=True)
    success = (_BulletData(*doc['sv']) == data['sv'])

    # Return success status to caller.
    if success:
        return RetVal(True, None, None)
    else:
        return RetVal(False, None, None)


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
    data = {'del': objID}
    doc = database.dbHandles['CmdRemove'].find_and_modify(
        {'objID': objID}, {'$setOnInsert': data}, upsert=True, new=True)
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
    doc = database.dbHandles['CmdModify'].find_and_modify(
        {'objID': objID}, {'$setOnInsert': {'sv': data}},
        upsert=True, new=True)

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
    ret = database.dbHandles['CmdForce'].update(
        {'objID': objID},
        {'$set': {'force': force, 'torque': torque}},
        upsert=True)

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


@typecheck
def addTemplate(templateID: bytes, data: dict):
    """
    Store the template ``data`` under the name ``templateID``.

    This function does not care what ``data`` contains, as long as it can be
    serialised.

    :param bytes templateID: template name
    :param dict data: arbitrary template data.
    :return: Success
    """
    # Insert the document only if it does not exist already. The return
    # value contains the old document, ie. **None** if the document
    # did not yet exist.
    ret = database.dbHandles['Templates'].find_and_modify(
        {'templateID': templateID}, {'$setOnInsert': data}, upsert=True)

    if ret is None:
        # No template with name ``templateID`` exists yet --> success.
        return RetVal(True, None, None)
    else:
        # A template with name ``templateID`` already existed --> failure.
        msg = 'Template ID <{}> already exists'.format(templateID)
        return RetVal(False, msg, None)


@typecheck
def getRawTemplate(templateID: bytes):
    """
    Return the raw data in the database for ``templateID``.

    :param bytes templateID:
    :return dict: template data.
    """
    # Retrieve the template. Return immediately if it does not exist.
    doc = database.dbHandles['Templates'].find_one({'templateID': templateID})
    if doc is None:
        msg = 'Invalid template ID <{}>'.format(templateID)
        logit.info(msg)
        return RetVal(False, msg, None)
    else:
        return RetVal(True, None, doc)
