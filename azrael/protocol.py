import cytoolz
import numpy as np
import azrael.json as json
import azrael.types as types
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
    boosters = [types.booster(*_) for _ in data['boosters']]
    factories = [types.factory(*_) for _ in data['factories']]
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
def ToClerk_AddTemplate_Encode(cs: np.ndarray, geo: np.ndarray,
                               boosters, factories):
    cs = cs.tostring()
    geo = geo.tostring()

    d = {'cs': cs, 'geo': geo, 'boosters': boosters,
         'factories': factories}
    d = json.dumps(d).encode('utf8')

    return True, d


@typecheck
def ToClerk_AddTemplate_Decode(payload: bytes):
    data = json.loads(payload)
    boosters = [types.booster(*_) for _ in data['boosters']]
    factories = [types.factory(*_) for _ in data['factories']]
    cs = np.fromstring(bytes(data['cs']), np.float64)
    geo = np.fromstring(bytes(data['geo']), np.float64)
    return True, (cs, geo, boosters, factories)


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
def FromClerk_SuggestPosition_Encode():
    return True, b''


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
def FromClerk_SetForce_Encode(dummyarg=None):
    return True, b''


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
    # Payload must be exactly one templateID.
    if len(payload) != 8:
        return False, 'Insufficient arguments'

    return True, (payload, )


@typecheck
def FromClerk_GetGeometry_Encode(geo):
    return True, geo


@typecheck
def FromClerk_GetGeometry_Decode(payload: bytes):
    return True, payload

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
def FromClerk_GetStateVariable_Encode(geo: bytes):
    return True, geo


@typecheck
def FromClerk_GetStateVariable_Decode(payload: bytes):
    return True, payload

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_Spawn_Encode(name: str, templateID: bytes, sv):
    data = bytes([len(name.encode('utf8'))]) + name.encode('utf8')
    data += templateID + btInterface.pack(sv).tostring()
    return True, data


@typecheck
def ToClerk_Spawn_Decode(payload: bytes):
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
