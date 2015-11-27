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

import logging
import numpy as np
import azrael.util as util
import azrael.aztypes as aztypes
import azrael.datastore as datastore

from IPython import embed as ipshell
from azrael.aztypes import typecheck, RetVal, _RigidBodyData
from azrael.aztypes import CollShapeMeta, CollShapeSphere, CollShapeBox

# Create module logger.
logit = logging.getLogger('azrael.' + __name__)


def computeAABBs(cshapes: dict):
    """
    Return a dictionary of AABBs that correspond to the ``cshapes``.

    This function returns an error as soon as it encounters an unknown
    collision shape.

    If ``cshapes`` contains a Plane shape then it must be the only collision
    shape (ie len(cshapes) == 1). Furthermore, planes must have default values
    for position and rotation.

    ..note:: The bounding boxes are large enough to accommodate all possible
             rotations of the collision shape. This makes them larger than
             necessary yet avoids recomputing them whenever the rotation of
             the body changes.

    :param dict[name: CollShapeMeta] cshapes: collision shapes
    :return: AABBs for the ``cshapes``.
    """
    # Convenience.
    s3 = np.sqrt(3.1)

    # Compute the AABBs for each shape.
    aabbs = {}
    try:
        # Wrap the inputs into CollShapeMeta structures.
        cshapes = {k: CollShapeMeta(*v) for (k, v) in cshapes.items()}
        if 'PLANE' in [_.cstype.upper() for _ in cshapes.values()]:
            if len(cshapes) > 1:
                msg = 'Plane must be the only collision shape'
                return RetVal(False, msg, None)

            name, cshape = cshapes.popitem()

            # Planes must have defaule values for position and rotation, or
            # Azrael considers them invalid.
            pos, rot = tuple(cshape.position), tuple(cshape.rotation)
            if (pos == (0, 0, 0)) and (rot == (0, 0, 0, 1)):
                aabbs[name] = (0, 0, 0, 0, 0, 0)
                return RetVal(True, None, aabbs)
            else:
                msg = 'Planes must have default position and rotation'
                return RetVal(False, msg, None)

        for name, cs in cshapes.items():
            # Move the origin of the collision shape according to its rotation.
            quat = util.Quaternion(cs.rotation[3], cs.rotation[:3])
            pos = tuple(quat * cs.position)

            # Determine the AABBs based on the collision shape type.
            ctype = cs.cstype.upper()
            if ctype == 'SPHERE':
                # All half lengths have the same length (equal to radius).
                r = CollShapeSphere(*cs.csdata).radius
                aabbs[name] = pos + (r, r, r)
            elif ctype == 'BOX':
                # All AABBs half lengths are equal. The value equals the
                # largest extent times sqrt(3) to accommodate all possible
                # rotations.
                tmp = s3 * max(CollShapeBox(*cs.csdata))
                aabbs[name] = pos + (tmp, tmp, tmp)
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
    db = datastore.dbHandles['Commands']

    # Fetch all pending commands.
    ret = db.getAll()
    if not ret.ok:
        return ret
    docs = ret.data

    # Delete all the commands we have just fetched.
    db.remove(list(docs.keys()))

    # Decompose the command:objID key into its constituents and add them to the
    # document. This will allow us to compile all spawn/remove/etc commands
    # easily below.
    for key, doc in docs.items():
        cmd, objID = key.split(':')
        docs[key]['cmd'] = cmd
        docs[key]['objID'] = objID
        del cmd, objID
    docs = docs.values()

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
    Announce that the elements in ``objData`` were created.

    The ``objData`` variables comprises a list of (objID, body) tuples.

    Returns **False** if ``objID`` already exists, is already scheduled to
    spawn, or if any of the parameters are invalid.

    Other services, most notably Leonard, will periodically check for new
    announcements and incorporate them into the simulation as necessary.

    :param tuple[(int, _RigidBodyData)]: the new objects created in Azrael.
    :return: success.
    """
    # Sanity check all bodies.
    for objID, body in objData:
        try:
            assert isinstance(objID, str)
            assert isinstance(body, _RigidBodyData)
        except AssertionError:
            msg = '<addCmdQueue> received invalid argument type'
            return RetVal(False, msg, None)

        if objID == '':
            msg = 'Invalid Object ID'
            logit.warning(msg)
            return RetVal(False, msg, None)

    # Compile the datastore ops.
    ops = {}
    for objID, body in objData:
        # Compile the AABBs. Return immediately if an error occurs.
        aabbs = computeAABBs(body.cshapes)
        if not aabbs.ok:
            return RetVal(False, 'Could not compile all AABBs', None)

        # Insert this document.
        data = {'rbs': body._asdict(), 'AABBs': aabbs.data}
        key = 'spawn:{}'.format(objID)
        ops[key] = {'data': data}

    # Store the spawn commands.
    db = datastore.dbHandles['Commands']
    ret = db.put(ops)
    if not ret.ok:
        return ret

    # Notify the user if not all spawn commands could be written. This should
    # not happen because all object IDs must be unique. If this error occurs
    # then something is wrong with the atomic object count.
    if False in ret.data.values():
        msg = ('At least one spawn command for the same objID already '
               'exists --> serious bug')
        logit.error(msg)
        return RetVal(False, msg, None)
    else:
        # All objIDs were unique --> success.
        return RetVal(True, None, None)


@typecheck
def addCmdRemoveObject(objID: str):
    """
    Remove ``objID`` from the physics simulation.

    Other services, most notably Leonard, will periodically check for new
    announcements and incorporate them into the simulation as necessary.

    .. note:: This function always succeeds.

    :param str objID: ID of object to delete.
    :return: Success.
    """
    db = datastore.dbHandles['Commands']
    key = 'remove:{}'.format(objID)
    ops = {key: {'data': {}}}
    db.put(ops)

    return RetVal(True, None, None)


@typecheck
def addCmdModifyBodyState(objID: str, body: dict):
    """
    Queue request to override the Body State of ``objID`` with ``body``.

    Other services, most notably Leonard, will periodically check for new
    announcements and incorporate them into the simulation as necessary.

    :param int objID: object to update.
    :param dict body: new object attributes.
    :return bool: Success
    """
    # Sanity check.
    if objID == '':
        msg = 'Invalid Object ID'
        logit.warning(msg)
        return RetVal(False, msg, None)

    # Make sure that ``body`` is really valid by constructing a new
    # DefaultRigidBody from it.
    body_sane = aztypes.DefaultRigidBody(**body)
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
    db = datastore.dbHandles['Commands']

    data = {'rbs': body, 'AABBs': aabbs}
    key = 'modify:{}'.format(objID)
    ops = {key: {'data': data}}
    db.put(ops)

    # This function was successful if exactly one document was updated.
    return RetVal(True, None, None)


@typecheck
def addCmdDirectForce(objID: str, force: list, torque: list):
    """
    Apply ``torque`` and central ``force`` to ``objID``.

    Other services, most notably Leonard, will periodically check for new
    announcements and incorporate them into the simulation as necessary.

    :param str objID: the object
    :param list force: apply this central ``force`` to ``objID``.
    :param list torque: apply this ``torque`` to ``objID``.
    :return bool: Success
    """
    # Sanity check.
    if objID == '':
        msg = 'Invalid Object ID'
        logit.warning(msg)
        return RetVal(False, msg, None)
    if not (len(force) == len(torque) == 3):
        return RetVal(False, 'force or torque has invalid length', None)

    # Compile datastore ops.
    db = datastore.dbHandles['Commands']
    data = {'force': force, 'torque': torque}
    key = 'direct_force:{}'.format(objID)
    ops = {key: {'data': data}}
    db.put(ops)

    return RetVal(True, None, None)


@typecheck
def addCmdBoosterForce(objID: str, force: list, torque: list):
    """
    Orient ``torque`` and ``force`` according to the ``objID`` and then apply
    them to the object.

    The only difference between this command and ``addCmdDirectForce`` is that
    the ``force`` and ``torque`` vector are specified in the object coordinate
    system and Leonard will rotate them to world coordinates before actually
    applying the force.

    Other services, most notably Leonard, will periodically check for new
    announcements and incorporate them into the simulation as necessary.

    :param str objID: the object
    :param list force: apply this central ``force`` to ``objID``.
    :param list torque: apply this ``torque`` to ``objID``.
    :return bool: Success
    """
    # Sanity check.
    if objID == '':
        msg = 'Invalid Object ID'
        logit.warning(msg)
        return RetVal(False, msg, None)
    if not (len(force) == len(torque) == 3):
        return RetVal(False, 'force or torque has invalid length', None)

    # Compile datastore ops.
    db = datastore.dbHandles['Commands']
    data = {'force': force, 'torque': torque}
    key = 'booster_force:{}'.format(objID)
    ops = {key: {'data': data}}
    db.put(ops)

    return RetVal(True, None, None)
