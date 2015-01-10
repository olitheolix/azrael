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
import pymongo
import IPython
import numpy as np
import azrael.util as util
import azrael.config as config
import azrael.bullet.bullet_data as bullet_data

from collections import namedtuple
from azrael.typecheck import typecheck

ipshell = IPython.embed

# Global database handles.
_DB_SV = None
_DB_CMDSpawn = None
_DB_CMDRemove = None
_DB_CMDModify = None
_DB_CMDForceAndTorque = None


# Convenience.
BulletDataOverride = bullet_data.BulletDataOverride

# Return value signature.
RetVal = util.RetVal

# Create module logger.
logit = logging.getLogger('azrael.' + __name__)


@typecheck
def initSVDB(reset=True):
    """
    Connect to the State Variable database. Flush it if ``reset`` is **True**.

    :param bool reset: flush the database.
    """
    global _DB_SV, _DB_CMDSpawn, _DB_CMDRemove, _DB_CMDModify
    global _DB_CMDForceAndTorque
    client = pymongo.MongoClient()
    _DB_SV = client['azrael']['sv']
    _DB_CMDSpawn = client['azrael']['CmdSpawn']
    _DB_CMDRemove = client['azrael']['CmdRemove']
    _DB_CMDModify = client['azrael']['CmdModify']
    _DB_CMDForceAndTorque = client['azrael']['CmdForceAndTorque']
    if reset:
        _DB_SV.drop()
        _DB_CMDSpawn.drop()
        _DB_CMDRemove.drop()
        _DB_CMDModify.drop()
        _DB_CMDForceAndTorque.drop()


def getNumObjects():
    """
    Return the number of objects in the simulation.

    :returns int: number of objects in simulation.
    """
    return _DB_SV.count()


@typecheck
def spawn(objID: bytes, sv: bullet_data.BulletData, templateID: bytes,
          aabb: (int, float)):
    """
    Add the new ``objID`` to the physics DB and return success.

    Contrary to the name ``aabb``, it actually denotes a bounding sphere and
    thus requires only a scalar argument instead of 3 side lengths. This will
    change eventually.

    Returns **False** if ``objID`` already exists in the simulation.

    :param bytes objID: object ID to insert.
    :param bytes sv: encoded state variable data.
    :param bytes templateID: the template from which the object is spawned.
    :param float aabb: size of AABB.
    :return: success.
    """
    # Serialise SV.
    sv = sv.toJsonDict()

    # Sanity checks.
    if len(objID) != config.LEN_ID:
        return RetVal(False, 'objID has wrong length', None)
    if aabb < 0:
        msg = 'AABB must be non-negative'
        logit.warning(msg)
        return RetVal(False, msg, None)

    # Dummy variable to specify the initial force and its relative position.
    z = np.zeros(3).tostring()

    # fixme: improve this and the next docu.
    # Add the objects. The find_and_modify command below implements the
    # fictional 'insert_if_not_exists' command. This ensures that we will not
    # overwrite an existing object.
    data = {'objid': objID, 'sv': sv, 'AABB': float(aabb)}
    doc = _DB_CMDSpawn.find_and_modify(
        {'objid': objID},
        {'$setOnInsert': data},
        upsert=True, new=True)

    # The SV in the returned document will only match ``sv`` if either no
    # object with objID existed before the call, or the objID existed but with
    # identical SV. In any other case there will be no match because the
    # objID already existed.
    isNew = (doc['sv'] == sv)

    return RetVal(isNew, None, None)


@typecheck
def deleteObject(objID: bytes):
    """
    Delete ``objID`` from the physics simulation.

    This function always suceeds.

    fixme: must be able to delete multiple objects at once.

    :param bytes objID: ID of object to delete.
    :return: Success.
    """
    data = {'del': objID}
    doc = _DB_CMDRemove.find_and_modify(
        {'objid': objID}, {'$setOnInsert': data}, upsert=True, new=True)
    return RetVal(True, None, None)


@typecheck
def getStateVariables(objIDs: (list, tuple)):
    """
    Retrieve the state variables for all ``objIDs``.

    If one or more objIDs int ``objIDs`` do not not exist then the respective
    entry will return *None*.

    :param iterable objIDs: list of object IDs for which to return the SV.
    :return dict: dictionary of the form {objID_k: sv_k}
    """
    # Sanity check.
    for _ in objIDs:
        if not isinstance(_, bytes) or (len(_) != config.LEN_ID):
            msg = 'Object ID has invalid type'
            logit.warning(msg)
            return RetVal(False, msg, None)

    # Retrieve the state variables.
    out = {_: None for _ in objIDs}
    for doc in _DB_SV.find({'objid': {'$in': objIDs}}):
        out[doc['objid']] = bullet_data.fromJsonDict(doc['sv'])
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
    for _ in objIDs:
        if not isinstance(_, bytes) or (len(_) != config.LEN_ID):
            msg = 'Object ID has invalid type'
            logit.warning(msg)
            return RetVal(False, msg, None)

    # Retrieve the state variables.
    out = list(_DB_SV.find({'objid': {'$in': objIDs}}))

    # Put all AABBs into a dictionary to simplify sorting afterwards.
    out = {_['objid']: np.array(_['AABB'], np.float64) for _ in out}

    # Compile the AABB values into a list ordered by ``objIDs``. Insert a None
    # element if a particular objID has no AABB (probably means the object was
    # recently deleted).
    out = [out[_] if _ in out else None for _ in objIDs]

    # Return the AABB values.
    return RetVal(True, None, out)


@typecheck
def _updateBulletDataTuple(orig: bullet_data.BulletData,
                           new: bullet_data.BulletDataOverride):
    """
    Overwrite fields in ``orig`` with content of ``new``.

    If one or more fields in ``new`` are *None* then the original value in
    ``orig`` will not be modified.

    This is a convenience function. It avoids code duplication which was
    otherwise unavoidable because not all Leonard implementations inherit the
    same base class.

    :param BulletData orig: the original tuple.
    :param BulletDataOverride new: all None values will be copied to ``orig``.
    :return: updated version of ``orig``.
    :rtype: BulletData
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

    # Build a new BulletData instance and return it.
    return bullet_data.BulletData(**dict_orig)


@typecheck
def update(objID: bytes, sv: bullet_data.BulletData, token=None):
    """
    Update the ``sv`` data for object ``objID`` and return the success flag.

    Return **False** if the update failed, most likely because the ``objID``
    was invalid.

    .. warning::
       Do not manually call this function unless you know what you are doing,
       because it may well break the physics synchronisation cycle.

    :param bytes objID: the object for which to update the state variables.
    :param bytes sv: encoded state variables.
    :return bool: success.
    """
    # Sanity check.
    if len(objID) != config.LEN_ID:
        return RetVal(False, 'objID has invalid length', None)

    # Retrieve the State Variables for ``objID``.
    query = {'objid': objID}
    if token is not None:
        query['token'] = token
    doc = _DB_SV.find_and_modify(
        query, {'$set': {'attrOverride': BulletDataOverride()}}, new=False)
    if doc is None:
        return RetVal(False, 'Could not find update <{}>'.format(objID), None)

    # Import the overriden State Variables into a ``BulletDataOverride`` tuple.
    fields = BulletDataOverride._fields
    sv_new = BulletDataOverride(**dict(zip(fields, doc['attrOverride'])))

    # Copy all active variables from 'sv_new' to 'sv'.
    sv = _updateBulletDataTuple(sv, sv_new)

    # Update the State Variables and void the user specified ones.
    doc = _DB_SV.update(
        query,
        {'$set': {'sv': sv.toJsonDict()},
         '$unset': {'token': 1}})

    # This function was successful if exactly one document was updated.
    return RetVal(doc['n'] == 1, None, None)


def getAllStateVariables():
    """
    Return the state variables for all objects in a dictionary.

    The keys and values of the returned dictionary correspond to the object ID
    and its associated state variables, respectively.

    :return: dictionary of state variables with object IDs as keys.
    :rtype: dict
    """
    # Compile all object IDs and state variables into a dictionary.
    out = {}
    for doc in _DB_SV.find():
        key, value = doc['objid'], bullet_data.fromJsonDict(doc['sv'])
        out[key] = value
    return RetVal(True, None, out)


def getAllObjectIDs():
    """
    Return all object IDs.

    Unlike ``getAllStateVariables`` this function merely returns object IDs but
    no associated data (eg. state variables).

    :return: list of all object IDs present in the simulation.
    :rtype: list
    """
    # Compile and return the list of all object IDs.
    out = [_['objid'] for _ in _DB_SV.find()]
    return RetVal(True, None, out)


@typecheck
def setForce(objID: bytes, force: np.ndarray, relpos: np.ndarray):
    """
    Update the ``force`` acting on ``objID``.

    This function is a wrapper around ``setForceAndTorque``.

    :param bytes objID: the object to which the force applies.
    :param np.ndarray force: force
    :param np.ndarray relpos: position of force relative to COM.
    :return bool: success.
    """
    # Sanity check.
    if (len(objID) != config.LEN_ID):
        return RetVal(False, 'objID has invalid length', None)
    if not (len(force) == len(relpos) == 3):
        return RetVal(False, 'force or relpos have invalid length', None)

    # Compute the torque and then call setForceAndTorque.
    torque = np.cross(relpos, force)
    ret = setForceAndTorque(objID, force, torque)
    if ret.ok:
        return RetVal(True, None, None)
    else:
        return RetVal(False, ret.msg, None)


@typecheck
def getForceAndTorque(objID: bytes):
    """
    Return the force and torque for ``objID``.

    :param bytes objID: object for which to query the force and torque.
    :returns: force and torque as {'force': force, 'torque': torque}.
    :rtype: dict
    """
    # Sanity check.
    if (len(objID) != config.LEN_ID):
        return RetVal(False, 'objID has invalid length', None)

    # Query the object.
    doc = _DB_CMDForceAndTorque.find_one({'objid': objID})
    if doc is None:
        return RetVal(False, 'Could not find <{}>'.format(objID), None)

    # Unpack the force.
    try:
        force = np.fromstring(doc['central_force'])
    except KeyError:
        force = np.zeros(3)

    # Unpack the torque.
    try:
        torque = np.fromstring(doc['torque'])
    except KeyError:
        torque = np.zeros(3)

    # Return the result.
    return RetVal(True, None, {'force': force, 'torque': torque})


@typecheck
def setForceAndTorque(objID: bytes, force: np.ndarray, torque: np.ndarray):
    """
    Set the central ``force`` and ``torque`` acting on ``objID``.

    This function always suceeds.

    .. note::
       The force always applies to the centre of the mass only, unlike the
       ``setForce`` function which allows for position relative to the centre
       of mass.

    :param bytes objID: the object
    :param ndarray force: central force to apply
    :param ndarray torque: torque to apply
    :return bool: Success
    """
    # Sanity check.
    if (len(objID) != config.LEN_ID):
        return RetVal(False, 'objID has invalid length', None)
    if not (len(force) == len(torque) == 3):
        return RetVal(False, 'force or torque has invalid length', None)

    # Serialise the force and torque.
    force = force.astype(np.float64).tostring()
    torque = torque.astype(np.float64).tostring()

    # Update the DB.
    ret = _DB_CMDForceAndTorque.update(
        {'objid': objID},
        {'$set': {'central_force': force, 'torque': torque}},
        upsert=True)

    return RetVal(True, None, None)


@typecheck
def setStateVariables(objID: bytes, data: BulletDataOverride):
    """
    Override State Variables of ``objID`` with those in ``data``.

    All *None* fields in ``data`` are ignored.

    Calling this function does not immediately update the State Variables for
    ``objID``. Instead, it queues them whereupon the ``btInterface.update``
    function will apply them.

    If this function is invoked multiple times before ``btInterface.update``
    runs then only the ``data`` of the last call will be applied.

    .. note::
       Do not manually call ``btInterface.update`` because it breaks the
       synchronisation cycle for the physics update.

    :param bytes objID: object to update.
    :param BulletDataOverride pos: new object attributes.
    :return bool: Success
    """
    # Sanity check.
    if (len(objID) != config.LEN_ID):
        return RetVal(False, 'objID has invalid length', None)

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
    doc = _DB_CMDModify.find_and_modify(
        {'objid': objID}, {'$setOnInsert': {'sv': data}},
        upsert=True, new=True)

    # This function was successful if exactly one document was updated.
    return RetVal(True, None, None)


@typecheck
def getOverrideAttributes(objID: bytes):
    """
    Retrieve the explicitly specified State Variable for ``objID``.

    Returns **None** if no attributes are available for ``objID``.

    :param bytes objID: object for which to return the attribute request.
    :return: return the queued State Variable (if any exists).
    :rtype: ``BulletDataOverride``
    """
    # Sanity check.
    if len(objID) != config.LEN_ID:
        return RetVal(False, 'objID has invalid length', None)

    # Query the object.
    doc = _DB_SV.find_one({'objid': objID})
    if doc is None:
        return RetVal(False, 'Could not find <{}>'.format(objID), None)

    # If no 'attrOverride' field exists then return the default
    # ``BulletDataOverride`` instance (it will have all values set to *None*).
    if doc['attrOverride'] is None:
        return RetVal(True, None, BulletDataOverride())

    # Convert the data into a ``BulletDataOverride`` instance which means all
    # values that are not *None* must be converted to a NumPy array.
    tmp = dict(zip(BulletDataOverride._fields, doc['attrOverride']))
    try:
        for k, v in tmp.items():
            if isinstance(v, (list, tuple)):
                tmp[k] = np.array(v, np.float64)
    except TypeError:
        return RetVal(False, 'Type conversion error', None)

    # Construct the BulletDataOverride instance and verify it was really
    # created.
    val = BulletDataOverride(**tmp)
    if val is None:
        # 'attrOverride' is valid.
        return RetVal(False, 'Invalid override attributes', None)
    else:
        # 'attrOverride' is invalid.
        return RetVal(True, None, val)


@typecheck
def getTemplateID(objID: bytes):
    """
    Return the template ID for object ``objID``.

    :param bytes objID: object ID
    :return: Template ID
    :rtype: bytes
    """
    # Sanity check.
    if len(objID) != config.LEN_ID:
        return RetVal(False, 'objID has invalid length', None)

    # Query the document.
    doc = _DB_SV.find_one({'objid': objID})
    if doc is None:
        msg = 'Could not retrieve templateID for objID={}'.format(objID)
        return RetVal(False, msg, None)
    else:
        return RetVal(True, None, doc['templateID'])
