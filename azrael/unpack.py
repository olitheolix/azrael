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
The functions in this module decode the byte strings sent to Clerk.
"""

import cytoolz
import numpy as np
import azrael.json as json
import azrael.util as util
import azrael.types as types
import azrael.config as config
from azrael.typecheck import typecheck
import azrael.bullet.btInterface as btInterface


@typecheck
def sendMsg(payload: bytes):
    src = payload[:config.LEN_ID]
    dst = payload[config.LEN_ID:2 * config.LEN_ID]
    data = payload[2 * config.LEN_ID:]

    if len(dst) != config.LEN_ID:
        return False, 'Insufficient arguments'
    else:
        return True, (src, dst, data)


@typecheck
def recvMsg(payload: bytes):
    # Check if any messages for a particular controller ID are
    # pending. Return the first such message if there are any and
    # remove them from the queue. The controller ID is the only
    # payload.
    obj_id = payload[:config.LEN_ID]

    if len(obj_id) != config.LEN_ID:
        return False, 'Insufficient arguments'
    else:
        return True, (obj_id, )


@typecheck
def spawn(payload: bytes):
    # Spawn a new object/controller.
    if len(payload) == 0:
        return False, 'Insufficient arguments'

    # Extract name of Python object to launch. The first byte denotes
    # the length of that name (in bytes).
    name_len = payload[0]
    if len(payload) != (name_len + 1 + 8 + config.LEN_SV_BYTES):
        return False, 'Invalid Payload Length'

    # Extract and decode the Controller name.
    ctrl_name = payload[1:name_len+1]
    ctrl_name = ctrl_name.decode('utf8')

    # Query the object description ID to spawn.
    templateID = payload[name_len+1:name_len+1+8]
    sv = payload[name_len+1+8:]
    sv = btInterface.unpack(np.fromstring(sv))
    if sv is None:
        return False, 'Invalid State Variable data'
    else:
        return True, (ctrl_name, templateID, sv)


@typecheck
def getSV(payload: bytes):
    # We need at least one ID.
    if len(payload) < config.LEN_ID:
        return False, 'Insufficient arguments'

    # The byte string must be in integer multiple of the object ID.
    if (len(payload) % config.LEN_ID) != 0:
        return False, 'Not divisible by objID length'

    # Turn the byte string into a list of object IDs.
    objIDs = [bytes(_) for _ in cytoolz.partition(config.LEN_ID, payload)]

    # Return the result.
    return True, (objIDs, )


@typecheck
def newTemplate(payload: bytes):
    # Payload must consist of at least a collision shape (4 float64).
    if len(payload) < 4 * 8:
        return False, 'Insufficient arguments'

    # Unpack the data.
    cshape, geometry = np.fromstring(payload[:32]), np.fromstring(payload[32:])
    return True, (cshape, geometry)


@typecheck
def getGeometry(payload: bytes):
    # Payload must be exactly one templateID.
    if len(payload) != 8:
        return False, 'Insufficient arguments'

    return True, (payload, )


@typecheck
def setForce(payload: bytes):
    # Payload must comprise one ID plus two 3-element vectors (8 Bytes
    # each) for force and relative position of that force with respect
    # to the center of mass.
    if len(payload) != (config.LEN_ID + 6 * 8):
        return False, 'Insufficient arguments'

    # Unpack the ID and 'force' value.
    objID = payload[:config.LEN_ID]
    _ = config.LEN_ID
    force, rpos = payload[_:_ + 3 * 8], payload[_ + 3 * 8:_ + 6 * 8]
    force, rpos = np.fromstring(force), np.fromstring(rpos)
    return True, (objID, force, rpos)


@typecheck
def suggestPos(payload: bytes):
    # Payload must be exactly one ID plus a 3-element position vector
    # with 8 Bytes (64 Bits) each.
    if len(payload) != (config.LEN_ID + 3 * 8):
        return False, 'Insufficient arguments'

    # Unpack the suggested position.
    obj_id, pos = payload[:config.LEN_ID], payload[config.LEN_ID:]
    pos = np.fromstring(pos)
    return True, (obj_id, pos)


@typecheck
def getTemplateID(payload: bytes):
    # Payload must be exactly one templateID.
    if len(payload) != config.LEN_ID:
        return False, 'Invalid object ID encoding'

    return True, (payload, )


@typecheck
def getAllObjectIDs(payload: bytes):
    if len(payload) == 0:
        return True, (payload, )
    else:
        return False, 'Invalid payload'

