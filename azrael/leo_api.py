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
import numpy as np
import azrael.util as util
import azrael.config as config
import azrael.database as database
import azrael.rb_state as rb_state

from IPython import embed as ipshell
from azrael.types import typecheck, RetVal, _RigidBodyState
from azrael.types import CollShapeMeta, CollShapeEmpty, CollShapeSphere, CollShapeBox

# Convenience.
RigidBodyStateOverride = rb_state.RigidBodyStateOverride

# Create module logger.
logit = logging.getLogger('azrael.' + __name__)


def computeAABBs(cshapes: (tuple, list)):
    """
    Return a list of AABBs for each element in ``cshapes``.

    This function returns an error as soon as it encounters an unknown
    collision shape.

    ..note:: The bounding boxes are large enough to accomodate all possible
             orientations of the collision shape. This makes them larger than
             necessary yet avoids recomputing them whenever the orientation of
             the body changes.

    :param list[CollShapeMeta] cshapes: collision shapes
    :return: list of AABBs for the ``cshapes``.
    """
    # Convenience.
    s3 = np.sqrt(3.1)

    # Compute the AABBs for each shape.
    aabbs = []
    try:
        for cs in cshapes:
            # Verify that the collision shape is sane.
            cs = CollShapeMeta(*cs)

            # Move the origin of the collision shape according to its rotation.
            quat = util.Quaternion(cs.rot[3], cs.rot[:3])
            pos = tuple(quat * cs.pos)

            # Determine the AABBs based on the collision shape type.
            ctype = cs.type.upper()
            if ctype == 'SPHERE':
                # All AABBs half lengths have the same length (equal to radius).
                r = CollShapeSphere(*cs.cshape).radius
                aabbs.append(pos + (r, r, r))
            elif ctype == 'BOX':
                # All AABBs half lengths are equal. The value equals the largest
                # extent times sqrt(3) to accommodate all possible orientations.
                tmp = s3 * max(CollShapeBox(*cs.cshape))
                aabbs.append(pos + (tmp, tmp, tmp))
            elif ctype == 'EMPTY':
                # Empty shapes do not have an AABB.
                continue
            else:
                # Error.
                msg = 'Unknown collision shape <{}>'.format(ctype)
                return RetVal(False, msg, None)
    except TypeError:
        # Error: probably because 'CollShapeMeta' or one of its sub-shapes,
        # could not be constructed.
        msg = 'Encountered invalid collision shape data'
        return RetVal(False, msg, None)

    return RetVal(True, None, aabbs)


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
    direct_force = [_ for _ in docs if _['cmd'] == 'direct_force']
    booster_force = [_ for _ in docs if _['cmd'] == 'booster_force']

    # Compile the output dictionary.
    out = {'spawn': spawn, 'remove': remove, 'modify': modify,
           'direct_force': direct_force, 'booster_force': booster_force}
    return RetVal(True, None, out)


@typecheck
def addCmdSpawn(objData: (tuple, list)):
    """
    Enqueue a new object described by ``objData`` for Leonard to spawn.

    The ``objData`` tuple comprises (objID, sv).

    Returns **False** if ``objID`` already exists, is scheduled to spawn, or if
    any of the parameters are invalid.

    Leonard will process the queue (and thus this command) once per physics
    cycle. However, it is impossible to determine when exactly.

    :param int objID: object ID to insert.
    :param _RigidBodyState sv: encoded state variable data.
    :return: success.
    """
    # Sanity checks all the provided bodies.
    for objID, sv in objData:
        try:
            assert isinstance(objID, int)
            assert isinstance(sv, _RigidBodyState)
        except AssertionError:
            msg = '<addCmdQueue> received invalid argument type'
            return RetVal(False, msg, None)

        if objID < 0:
            msg = 'Object ID is negative'
            logit.warning(msg)
            return RetVal(False, msg, None)

    # Meta data for spawn command.
    db = database.dbHandles['Commands']
    bulk = db.initialize_unordered_bulk_op()
    for objID, sv in objData:
        # Compile the AABBs. Return immediately if an error occurs.
        aabbs = computeAABBs(sv.cshapes)
        if not aabbs.ok:
            return RetVal(False, 'Could not compile all AABBs', None)

        # Insert this document unless one already matches the query.
        query = {'cmd': 'spawn', 'objID': objID}
        data = {'sv': sv, 'AABBs': aabbs.data}
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

    Leonard will process the queue (and thus this command) once per physics
    cycle. However, it is impossible to determine when exactly.

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
def addCmdModifyBodyState(objID: int, body: RigidBodyStateOverride):
    """
    Queue request to override the Body State of ``objID`` with ``body``.

    Leonard will process the queue (and thus this command) once per physics
    cycle. However, it is impossible to determine when exactly.

    :param int objID: object to update.
    :param RigidBodyStateOverride body: new object attributes.
    :return bool: Success
    """
    # Sanity check.
    if objID < 0:
        msg = 'Object ID is negative'
        logit.warning(msg)
        return RetVal(False, msg, None)

    # Do nothing if body is None.
    if body is None:
        return RetVal(True, None, None)

    # Make sure that ``body`` is really valid by constructing a new
    # RigidBodyStateOverride instance from it.
    body = RigidBodyStateOverride(*body)
    if body is None:
        return RetVal(False, 'Invalid override data', None)

    # Recompute the AABBs if new collision shapes were provided.
    aabbs = None
    if body.cshapes is not None:
        ret = computeAABBs(body.cshapes)
        if ret.ok:
            aabbs = ret.data

    # Save the new body state and AABBs to the DB. This will overwrite already
    # pending update commands for the same object - tough luck.
    db = database.dbHandles['Commands']
    query = {'cmd': 'modify', 'objID': objID}
    db_data = {'sv': body, 'AABBs': aabbs}
    db.update(query, {'$setOnInsert': db_data},  upsert=True)

    # This function was successful if exactly one document was updated.
    return RetVal(True, None, None)


@typecheck
def addCmdDirectForce(objID: int, force: list, torque: list):
    """
    Apply ``torque`` and central ``force`` to ``objID``.

    Leonard will process the queue (and thus this command) once per physics
    cycle. However, it is impossible to determine when exactly.

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
    query = {'cmd': 'direct_force', 'objID': objID}
    data = {'force': force, 'torque': torque}
    db.update(query, {'$setOnInsert': data}, upsert=True)

    return RetVal(True, None, None)


@typecheck
def addCmdBoosterForce(objID: int, force: list, torque: list):
    """
    Orient ``torque`` and ``force`` according to the ``objID`` and then apply
    them to the object.

    The only difference between this command and ``addCmdDirectForce`` is that
    the ``force`` and ``torque`` vector are specified in the object coordinate
    system and Leonard will rotate them to world coordinates before actually
    applying the force.

    Leonard will process the queue (and thus this command) once per physics
    cycle. However, it is impossible to determine when exactly.

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
    query = {'cmd': 'booster_force', 'objID': objID}
    data = {'force': force, 'torque': torque}
    db.update(query, {'$setOnInsert': data}, upsert=True)

    return RetVal(True, None, None)


@typecheck
def getBodyStates(objIDs: (list, tuple)):
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
    with util.Timeit('leoAPI.1_getSV') as timeit:
        tmp = list(database.dbHandles['SV'].find({'objID': {'$in': objIDs}}))

    with util.Timeit('leoAPI.2_getSV') as timeit:
        for doc in tmp:
            out[doc['objID']] = _RigidBodyState(*doc['sv'])
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

    # Retrieve the objects states.
    out = list(database.dbHandles['SV'].find({'objID': {'$in': objIDs}}))

    # Put all AABBs into a dictionary to simplify sorting afterwards.
    out = {_['objID']: _['AABBs'] for _ in out}

    # Compile the AABB values into a list ordered by ``objIDs``. Insert a None
    # element if a particular objID has no AABB (probably means the object was
    # recently deleted).
    out = [out[_] if _ in out else None for _ in objIDs]

    # Return the AABB values.
    return RetVal(True, None, out)


@typecheck
def _updateRigidBodyStateTuple(orig: _RigidBodyState,
                               new: rb_state.RigidBodyStateOverride):
    """
    Overwrite fields in ``orig`` with content of ``new``.

    If one or more fields in ``new`` are *None* then the original value in
    ``orig`` will not be modified.

    This is a convenience function. It avoids code duplication which was
    otherwise unavoidable because not all Leonard implementations inherit the
    same base class.

    :param _RigidBodyState orig: the original tuple.
    :param RigidBodyStateOverride new: new values (*None* entries are ignored).
    :return: updated version of ``orig``.
    :rtype: _RigidBodyState
    """
    if new is None:
        return orig

    # Copy all not-None values from ``new`` into the dictionary version of
    # ``orig``.
    dict_orig = orig._asdict()
    for k, v in zip(dict_orig, new):
        if v is not None:
            dict_orig[k] = v

    # Convert the dictionary back to a _RigidBodyState instance and return it.
    return _RigidBodyState(**dict_orig)


def getAllBodyStates():
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
        key, value = doc['objID'], _RigidBodyState(*doc['sv'])
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
