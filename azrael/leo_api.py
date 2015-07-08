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
import azrael.types as types
import azrael.config as config
import azrael.database as database

from IPython import embed as ipshell
from azrael.types import typecheck, RetVal, _RigidBodyState
from azrael.types import CollShapeMeta, CollShapeEmpty
from azrael.types import CollShapeSphere, CollShapeBox

# Create module logger.
logit = logging.getLogger('azrael.' + __name__)


def computeAABBs(cshapes: (tuple, list)):
    """
    Return a list of AABBs for each element in ``cshapes``.

    This function returns an error as soon as it encounters an unknown
    collision shape.

    if``cshapes`` contains a plane then it must be the only collision shape
    (ie len(cshapes) == 1). Furthermore, planes must have default values for
    position and orientation.

    ..note:: The bounding boxes are large enough to accommodate all possible
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
        # Wrap the inputs into CollShapeMeta structures.
        cshapes = [CollShapeMeta(*_) for _ in cshapes]
        if 'PLANE' in [_.cstype.upper() for _ in cshapes]:
            if len(cshapes) > 1:
                msg = 'Plane must be the only collision shape'
                return RetVal(False, msg, None)

            # Planes must have defaule values for position and orientation, or
            # Azrael considers them invalid.
            pos, rot = tuple(cshapes[0].position), tuple(cshapes[0].rotation)
            if (pos == (0, 0, 0)) and (rot == (0, 0, 0, 1)):
                aabbs.append((0, 0, 0, 0, 0, 0))
                return RetVal(True, None, aabbs)
            else:
                msg = 'Planes must have default position and orientation'
                return RetVal(False, msg, None)

        for cs in cshapes:
            # Move the origin of the collision shape according to its rotation.
            quat = util.Quaternion(cs.rotation[3], cs.rotation[:3])
            pos = tuple(quat * cs.position)

            # Determine the AABBs based on the collision shape type.
            ctype = cs.cstype.upper()
            if ctype == 'SPHERE':
                # All half lengths have the same length (equal to radius).
                r = CollShapeSphere(*cs.csdata).radius
                aabbs.append(pos + (r, r, r))
            elif ctype == 'BOX':
                # All AABBs half lengths are equal. The value equals the
                # largest extent times sqrt(3) to accommodate all possible
                # orientations.
                tmp = s3 * max(CollShapeBox(*cs.csdata))
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
    for doc in docs:
        del doc['_id']

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

    The ``objData`` tuple comprises (objID, body).

    Returns **False** if ``objID`` already exists, is scheduled to spawn, or if
    any of the parameters are invalid.

    Leonard will process the queue (and thus this command) once per physics
    cycle. However, it is impossible to determine when exactly.

    # fixme: parameters
    :param int objID: object ID to insert.
    :param _RigidBodyState sv: encoded state variable data.
    :return: success.
    """
    # Sanity checks all the provided bodies.
    for objID, body in objData:
        try:
            assert isinstance(objID, int)
            assert isinstance(body, _RigidBodyState)
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
    for objID, body in objData:
        # Compile the AABBs. Return immediately if an error occurs.
        aabbs = computeAABBs(body.cshapes)
        if not aabbs.ok:
            return RetVal(False, 'Could not compile all AABBs', None)

        # Insert this document unless one already matches the query.
        query = {'cmd': 'spawn', 'objID': objID}
        data = {'rbs': body._asdict(), 'AABBs': aabbs.data}
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
def addCmdModifyBodyState(objID: int, body: dict):
    """
    Queue request to override the Body State of ``objID`` with ``body``.

    Leonard will process the queue (and thus this command) once per physics
    cycle. However, it is impossible to determine when exactly.

    fixme: parameters
    :param int objID: object to update.
    :param dict body: new object attributes.
    :return bool: Success
    """
    # Sanity check.
    if objID < 0:
        msg = 'Object ID is negative'
        logit.warning(msg)
        return RetVal(False, msg, None)

    # Make sure that ``body`` is really valid by constructing a new
    # DefaultRigidBody from it.
    body_sane = types.DefaultRigidBody(**body)
    if body_sane is None:
        return RetVal(False, 'Invalid override data', None)

    # Recompute the AABBs if new collision shapes were provided.
    aabbs = None
    if 'cshapes' in body:
        if body_sane.cshapes is not None:
            ret = computeAABBs(body_sane.cshapes)
            if ret.ok:
                aabbs = ret.data

    # Build the original 'body' but from the sanitised version - just to be
    # sure.
    body = {k: v for (k, v) in body_sane._asdict().items() if k in body}
    del body_sane

    # Add the new body state and AABBs to the 'command' database from where
    # clients can read it at their leisure. Note that this will overwrite
    # already pending update commands for the same object - tough luck.
    db = database.dbHandles['Commands']
    query = {'cmd': 'modify', 'objID': objID}
    db_data = {'rbs': body, 'AABBs': aabbs}
    db.update(query, {'$setOnInsert': db_data}, upsert=True)

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
    out = list(database.dbHandles['RBS'].find({'objID': {'$in': objIDs}}))

    # Put all AABBs into a dictionary to simplify sorting afterwards.
    out = {_['objID']: _['AABBs'] for _ in out}

    # Compile the AABB values into a list ordered by ``objIDs``. Insert a None
    # element if a particular objID has no AABB (probably means the object was
    # recently deleted).
    out = [out[_] if _ in out else None for _ in objIDs]

    # Return the AABB values.
    return RetVal(True, None, out)
