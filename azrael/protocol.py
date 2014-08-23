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
This module contains Python <--> binary convertes. These will be used to encode
``Controller`` request to bytes (and back) so that they can be sent via ZeroMQ
sockets.

The ``ToClerk_*_Decode`` (decodes received byte stream) and
``FromClerk_*_Encode`` (serialises the returned data in Clerk) describe the
protocol expected by Azrael whereas their counterparts, namely
``ToClerk_*_Encode`` and ``FromClerk_*_Decode``, are language specific
{en,de}decoders. The Python versions were added to this module for
convenience. Bindings from other languages must implement their own versions of
``ToClerk_*_Encode`` and ``FromClerk_*_Decode``.

The binary protocols are not pickled Python objects but straightforwards
encodings of strings, JSON objects, or C-arrays (via NumPy). This should make
it possible to write clients in other languages.
"""

import cytoolz
import numpy as np
import azrael.json as json
import azrael.parts as parts
import azrael.config as config
import azrael.bullet.btInterface as btInterface
from azrael.typecheck import typecheck


@typecheck
def ToClerk_GetTemplate_Encode(templateID: bytes):
    return True, templateID


@typecheck
def ToClerk_GetTemplate_Decode(payload: bytes):
    return True, (payload, )


@typecheck
def FromClerk_GetTemplate_Encode(cs: np.ndarray, geo: np.ndarray,
                                 boosters: (list, tuple),
                                 factories: (list, tuple)):
    d = {'cs': cs, 'geo': geo, 'boosters': boosters,
         'factories': factories}
    return True, json.dumps(d).encode('utf8')


@typecheck
def FromClerk_GetTemplate_Decode(payload: bytes):
    import collections
    data = json.loads(payload)
    boosters = [parts.booster(*_) for _ in data['boosters']]
    factories = [parts.factory(*_) for _ in data['factories']]
    nt = collections.namedtuple('Generic', 'cs geo boosters factories')
    ret = nt(np.array(data['cs'], np.float64),
             np.array(data['geo'], np.float64),
             boosters, factories)
    return True, ret

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_GetTemplateID_Encode(objID: bytes):
    return True, objID


@typecheck
def ToClerk_GetTemplateID_Decode(payload: bytes):
    return True, (payload, )


@typecheck
def FromClerk_GetTemplateID_Encode(templateID: bytes):
    return True, templateID


@typecheck
def FromClerk_GetTemplateID_Decode(payload: bytes):
    return True, payload

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_AddTemplate_Encode(templateID: bytes, cs: np.ndarray, geo:
                               np.ndarray, boosters, factories):
    cs = cs.tostring()
    geo = geo.tostring()

    d = {'name': templateID, 'cs': cs, 'geo': geo, 'boosters': boosters,
         'factories': factories}
    d = json.dumps(d).encode('utf8')

    return True, d


@typecheck
def ToClerk_AddTemplate_Decode(payload: bytes):
    data = json.loads(payload)
    boosters = [parts.booster(*_) for _ in data['boosters']]
    factories = [parts.factory(*_) for _ in data['factories']]
    templateID = bytes(data['name'])
    cs = np.fromstring(bytes(data['cs']), np.float64)
    geo = np.fromstring(bytes(data['geo']), np.float64)
    return True, (templateID, cs, geo, boosters, factories)


@typecheck
def FromClerk_AddTemplate_Encode(templateID: bytes):
    return True, templateID


@typecheck
def FromClerk_AddTemplate_Decode(payload: bytes):
    return True, payload

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_GetAllObjectIDs_Encode(dummyarg=None):
    return True, b''


@typecheck
def ToClerk_GetAllObjectIDs_Decode(payload: bytes):
    return True, b''


@typecheck
def FromClerk_GetAllObjectIDs_Encode(data: (list, tuple)):
    data = b''.join(data)
    return True, data


@typecheck
def FromClerk_GetAllObjectIDs_Decode(payload: bytes):
    data = [bytes(_) for _ in cytoolz.partition(config.LEN_ID, payload)]
    return True, data

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_SuggestPosition_Encode(target: bytes, pos: np.ndarray):
    pos = pos.astype(np.float64)
    pos = pos.tostring()
    return True, target + pos


@typecheck
def ToClerk_SuggestPosition_Decode(payload: bytes):
    # Payload must be exactly one ID plus a 3-element position vector
    # with 8 Bytes (64 Bits) each.
    if len(payload) != (config.LEN_ID + 3 * 8):
        return False, 'Insufficient arguments'

    # Unpack the suggested position.
    obj_id, pos = payload[:config.LEN_ID], payload[config.LEN_ID:]
    pos = np.fromstring(pos)
    return True, (obj_id, pos)


@typecheck
def FromClerk_SuggestPosition_Encode(ret):
    return True, ret.encode('utf8')


@typecheck
def FromClerk_SuggestPosition_Decode(payload: bytes):
    return True, payload

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_SetForce_Encode(target: bytes, force: np.ndarray, relpos: np.ndarray):
    force = force.astype(np.float64).tostring()
    relpos = relpos.astype(np.float64).tostring()
    return True, target + force + relpos


@typecheck
def ToClerk_SetForce_Decode(payload: bytes):
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
def FromClerk_SetForce_Encode(ret):
    return True, ret.encode('utf8')


@typecheck
def FromClerk_SetForce_Decode(payload: bytes):
    return True, payload

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_GetGeometry_Encode(target: bytes):
    return True, target


@typecheck
def ToClerk_GetGeometry_Decode(payload: bytes):
    return True, (payload, )


@typecheck
def FromClerk_GetGeometry_Encode(geo: np.ndarray):
    return True, geo.tostring()


@typecheck
def FromClerk_GetGeometry_Decode(payload: bytes):
    return True, np.fromstring(payload)

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_GetStateVariable_Encode(objIDs: (tuple, list)):
    return True, b''.join(objIDs)


@typecheck
def ToClerk_GetStateVariable_Decode(payload: bytes):
    # We need at least one ID.
    if len(payload) < config.LEN_ID:
        return False, 'Insufficient arguments'

    # The byte string must be an integer multiple of the object ID.
    if (len(payload) % config.LEN_ID) != 0:
        return False, 'Not divisible by objID length'

    # Turn the byte string into a list of object IDs.
    objIDs = [bytes(_) for _ in cytoolz.partition(config.LEN_ID, payload)]

    # Return the result.
    return True, (objIDs, )


@typecheck
def FromClerk_GetStateVariable_Encode(objIDs: (list, tuple),
                                      sv: (list, tuple)):
    data = [_[0] + _[1] for _ in zip(objIDs, sv)]
    return True, b''.join(data)


@typecheck
def FromClerk_GetStateVariable_Decode(payload: bytes):
    # The available data must be an integer multiple of an ID plus SV.
    l = config.LEN_ID + config.LEN_SV_BYTES
    assert (len(payload) % l) == 0

    # Return a dictionary of SV variables. The dictionary key is the
    # object ID (the state variables - incidentally - are another
    # dictionary).
    out = {}
    for data in cytoolz.partition(l, payload):
        data = bytes(data)
        sv = np.fromstring(data[config.LEN_ID:])
        out[data[:config.LEN_ID]] = btInterface.unpack(sv)
    return True, out

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_Spawn_Encode(name: bytes, templateID: bytes, sv:
                         btInterface.BulletData):
    sv = btInterface.pack(sv).tostring()
    d = {'name': name, 'templateID': templateID, 'sv': sv}
    return True, json.dumps(d).encode('utf8')


@typecheck
def ToClerk_Spawn_Decode(payload: bytes):
    data = json.loads(payload)
    if data['name'] is None:
        ctrl_name = None
    else:
        ctrl_name = bytes(data['name'])
    templateID = bytes(data['templateID'])
    sv = np.fromstring(bytes(data['sv']), np.float64)
    sv = btInterface.unpack(sv)

    if sv is None:
        return False, 'Invalid State Variable data'
    else:
        return True, (ctrl_name, templateID, sv)


@typecheck
def FromClerk_Spawn_Encode(objID: bytes):
    return True, objID


@typecheck
def FromClerk_Spawn_Decode(payload: bytes):
    return True, payload

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_RecvMsg_Encode(objID: bytes):
    return True, objID


@typecheck
def ToClerk_RecvMsg_Decode(payload: bytes):
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
def FromClerk_RecvMsg_Encode(objID: bytes, msg: bytes):
    return True, bytes(objID) + bytes(msg)


@typecheck
def FromClerk_RecvMsg_Decode(payload: bytes):
    if len(payload) < config.LEN_ID:
        src, data = None, b''
    else:
        # Protocol: sender ID, data
        src, data = payload[:config.LEN_ID], payload[config.LEN_ID:]
    return True, (src, data)

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_SendMsg_Encode(objID: bytes, target: bytes, msg: bytes):
    return True, objID + target + msg


@typecheck
def ToClerk_SendMsg_Decode(payload: bytes):
    src = payload[:config.LEN_ID]
    dst = payload[config.LEN_ID:2 * config.LEN_ID]
    data = payload[2 * config.LEN_ID:]

    if len(dst) != config.LEN_ID:
        return False, 'Insufficient arguments'
    else:
        return True, (src, dst, data)


@typecheck
def FromClerk_SendMsg_Encode(dummyarg=None):
    return True, b''


@typecheck
def FromClerk_SendMsg_Decode(payload: bytes):
    return True, tuple()
