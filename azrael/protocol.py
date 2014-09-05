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
Python agnostic Codecs for data transmission to and from Clerk.

The codecs in this module specify the JSON format between Clerk and the
clients.

The encoders and decoders in this module specify the binary protocol for
sending/receiving messages to/from Clerk.

``ToClerk_*_Decode``: Clerk will use this function to de-serialise the incoming
byte stream into native Python types.

``FromClerk_*_Encode``: Clerk will use this function to serialise its response.

``ToClerk_*_Encode``: the (Python) client uses this function to serialise its
request for Clerk.

``FromClerk_*_Decode``: the (Python) client uses this function to de-serialise
Clerk's response.

The binary protocols are not pickled Python objects but (hopefully) language
agnostic encodings of strings, JSON objects, or C-arrays (via NumPy). This
should make it possible to write clients in other languages.
"""

import IPython
import cytoolz
import collections
import numpy as np
import azrael.parts as parts
import azrael.config as config
import azrael.bullet.btInterface as btInterface
import azrael.bullet.bullet_data as bullet_data

from azrael.typecheck import typecheck
from azrael.protocol_json import loads, dumps

ipshell = IPython.embed


def decodeJSON(data):
    # Decode JSON.
    try:
        d = loads(data)
    except ValueError:
        return False, 'JSON decoding error'
    return True, d

def encodeJSON(data):
    try:
        d = dumps(data)
    except TypeError:
        return False, 'JSON encoding error'
    return True, d
    
# ---------------------------------------------------------------------------
# GetTemplate
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_GetTemplate_Encode(templateID: bytes):
    d = {'templateID': list(templateID)}
    return encodeJSON(d)


@typecheck
def ToClerk_GetTemplate_Decode(payload: bytes):
    ok, data = decodeJSON(payload)
    if not ok:
        return False, data
    return True, (bytes(data['templateID']), )


@typecheck
def FromClerk_GetTemplate_Encode(cs: np.ndarray, geo: np.ndarray,
                                 boosters: (list, tuple),
                                 factories: (list, tuple)):
    for b in boosters:
        assert isinstance(b, parts.Booster)
    for f in factories:
        assert isinstance(f, parts.Factory)

    d = {'cs': cs, 'geo': geo,
         'boosters': [_.tostring() for _ in boosters],
         'factories': [_.tostring() for _ in factories]}
    return encodeJSON(d)


@typecheck
def FromClerk_GetTemplate_Decode(payload: bytes):
    ok, data = decodeJSON(payload)
    if not ok:
        return False, data

    # Wrap the Booster- and Factory data into their dedicated named tuples.
    boosters = [parts.fromstring(bytes(_)) for _ in data['boosters']]
    factories = [parts.fromstring(bytes(_)) for _ in data['factories']]

    # Return the complete information in a named tuple.
    nt = collections.namedtuple('Template', 'cs geo boosters factories')
    ret = nt(np.array(data['cs'], np.float64),
             np.array(data['geo'], np.float64),
             boosters, factories)
    return True, ret


# ---------------------------------------------------------------------------
# GetTemplateID
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetTemplateID_Encode(objID: bytes):
    return encodeJSON({'objID': list(objID)})


@typecheck
def ToClerk_GetTemplateID_Decode(payload: bytes):
    ok, data = decodeJSON(payload)
    if not ok:
        return ok, data
    return True, (bytes(data['objID']), )


@typecheck
def FromClerk_GetTemplateID_Encode(templateID: bytes):
    return encodeJSON({'templateID': list(templateID)})


@typecheck
def FromClerk_GetTemplateID_Decode(payload: bytes):
    ok, data = decodeJSON(payload)
    if not ok:
        return ok, data
    return True, bytes(data['templateID'])


# ---------------------------------------------------------------------------
# AddTemplate
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_AddTemplate_Encode(templateID: bytes, cs: np.ndarray, geo:
                               np.ndarray, boosters, factories):
    for b in boosters:
        assert isinstance(b, parts.Booster)
    for f in factories:
        assert isinstance(f, parts.Factory)

    d = {'name': templateID, 'cs': cs.tostring(), 'geo': geo.tostring(),
         'boosters': [_.tostring() for _ in boosters],
         'factories': [_.tostring() for _ in factories]}

    return encodeJSON(d)


@typecheck
def ToClerk_AddTemplate_Decode(payload: bytes):
    ok, data = decodeJSON(payload)
    if not ok:
        return False, data

    # Wrap the Booster- and Factory data into their dedicated named tuples.
    boosters = [parts.fromstring(bytes(_)) for _ in data['boosters']]
    factories = [parts.fromstring(bytes(_)) for _ in data['factories']]

    # Convert template ID to a byte string.
    templateID = bytes(data['name'])

    # Convert collision shape and geometry to NumPy array (via byte string).
    cs = np.fromstring(bytes(data['cs']), np.float64)
    geo = np.fromstring(bytes(data['geo']), np.float64)

    # Return decoded quantities.
    return True, (templateID, cs, geo, boosters, factories)


@typecheck
def FromClerk_AddTemplate_Encode(templateID: bytes):
    return encodeJSON({'templateID': list(templateID)})


@typecheck
def FromClerk_AddTemplate_Decode(payload: bytes):
    ok, data = decodeJSON(payload)
    if not ok:
        return False, data
    return True, bytes(data['templateID'])


# ---------------------------------------------------------------------------
# GetAllObjectIDs
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetAllObjectIDs_Encode(dummyarg=None):
    return encodeJSON({})


@typecheck
def ToClerk_GetAllObjectIDs_Decode(payload: bytes):
    ok, data = decodeJSON(payload)
    if not ok:
        return False, data
    return True, data


@typecheck
def FromClerk_GetAllObjectIDs_Encode(data: (list, tuple)):
    return encodeJSON({'objIDs': [list(_) for _ in data]})


@typecheck
def FromClerk_GetAllObjectIDs_Decode(payload: bytes):
    ok, data = decodeJSON(payload)
    if not ok:
        return False, data
    
    # Partition the byte stream into individual object IDs.
    data = [bytes(_) for _ in data['objIDs']]
    return True, data


# ---------------------------------------------------------------------------
# SuggestPosition
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_SuggestPosition_Encode(objID: bytes, pos: np.ndarray):
    d = {'objID': objID, 'pos': pos}
    return encodeJSON(d)


@typecheck
def ToClerk_SuggestPosition_Decode(payload: bytes):
    ok, data = decodeJSON(payload)
    if not ok:
        return False, data

    # Convert to native Python types and return to caller.
    objID = bytes(data['objID'])
    pos = np.array(data['pos'], np.float64)
    return True, (objID, pos)


@typecheck
def FromClerk_SuggestPosition_Encode(dummyarg):
    return encodeJSON({})


@typecheck
def FromClerk_SuggestPosition_Decode(payload: bytes):
    ok, data = decodeJSON(payload)
    if not ok:
        return False, data
    return True, data


# ---------------------------------------------------------------------------
# SetForce
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_SetForce_Encode(objID: bytes, force: np.ndarray, rpos: np.ndarray):
    d = {'objID': objID, 'rel_pos': rpos, 'force': force}
    return encodeJSON(d)


@typecheck
def ToClerk_SetForce_Decode(payload: bytes):
    ok, data = decodeJSON(payload)
    if not ok:
        return False, data

    # Convert to native Python types and return to caller.
    objID = bytes(data['objID'])
    force = np.array(data['force'], np.float64)
    rel_pos = np.array(data['rel_pos'], np.float64)
    return True, (objID, force, rel_pos)


@typecheck
def FromClerk_SetForce_Encode(dummyarg):
    return encodeJSON({})


@typecheck
def FromClerk_SetForce_Decode(payload: bytes):
    return decodeJSON(payload)


# ---------------------------------------------------------------------------
# GetGeometry
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetGeometry_Encode(templateID: bytes):
    return encodeJSON({'templateID': list(templateID)})


@typecheck
def ToClerk_GetGeometry_Decode(payload: bytes):
    ok, data = decodeJSON(payload)
    if not ok:
        return False, data
    return True, (bytes(data['templateID']), )


@typecheck
def FromClerk_GetGeometry_Encode(geo: np.ndarray):
    return encodeJSON({'geo': geo.tolist()})


@typecheck
def FromClerk_GetGeometry_Decode(payload: bytes):
    ok, data = decodeJSON(payload)
    if not ok:
        return False, data
    return True, np.array(data['geo'], np.float64)


# ---------------------------------------------------------------------------
# GetStateVariables
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetStateVariable_Encode(objIDs: (list, tuple)):
    for objID in objIDs:
        assert isinstance(objID, bytes)
    return encodeJSON({'objIDs': [list(_) for _ in objIDs]})


@typecheck
def ToClerk_GetStateVariable_Decode(payload: bytes):
    ok, data = decodeJSON(payload)
    if not ok:
        return False, data

    objIDs = [bytes(_) for _ in data['objIDs']]
    return True, (objIDs, )


@typecheck
def FromClerk_GetStateVariable_Encode(
        objIDs: (list, tuple), sv: (list, tuple)):
    for _ in sv:
        assert isinstance(_, bullet_data.BulletData)
    d = {'data': [{'objID': objID, 'sv': sv.tojson()}
                  for (objID, sv) in zip(objIDs, sv)]}
    return encodeJSON(d)


@typecheck
def FromClerk_GetStateVariable_Decode(payload: bytes):
    ok, data = decodeJSON(payload)
    if not ok:
        return False, data

    data = data['data']
    out = {}
    for d in data:
        out[bytes(d['objID'])] = bullet_data.fromjson(bytes(d['sv']))
    return True, out


# ---------------------------------------------------------------------------
# Spawn
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_Spawn_Encode(
        name: bytes, templateID: bytes, sv: bullet_data.BulletData):
    d = {'name': name, 'templateID': templateID, 'sv': sv.tojson()}
    return encodeJSON(d)


@typecheck
def ToClerk_Spawn_Decode(payload: bytes):
    ok, data = decodeJSON(payload)
    if not ok:
        return False, data

    if data['name'] is None:
        ctrl_name = None
    else:
        ctrl_name = bytes(data['name'])
    templateID = bytes(data['templateID'])
    sv = bullet_data.fromjson(bytes(data['sv']))

    if sv is None:
        return False, 'Invalid State Variable data'
    else:
        return True, (ctrl_name, templateID, sv)


@typecheck
def FromClerk_Spawn_Encode(objID: bytes):
    return encodeJSON({'objID': list(objID)})


@typecheck
def FromClerk_Spawn_Decode(payload: bytes):
    ok, data = decodeJSON(payload)
    if not ok:
        return False, data

    return True, bytes(data['objID'])


# ---------------------------------------------------------------------------
# RecvMsg
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_RecvMsg_Encode(objID: bytes):
    return encodeJSON({'objID': list(objID)})


@typecheck
def ToClerk_RecvMsg_Decode(payload: bytes):
    ok, data = decodeJSON(payload)
    if not ok:
        return False, data

    return True, (bytes(data['objID']), )


@typecheck
def FromClerk_RecvMsg_Encode(objID: bytes, msg: bytes):
    return encodeJSON({'objID': list(objID), 'msg': list(msg)})


@typecheck
def FromClerk_RecvMsg_Decode(payload: bytes):
    ok, data = decodeJSON(payload)
    if not ok:
        return False, data

    # Unpack the message source. If this string is invalid (most likely empty)
    # then it means no message was available for us.
    src = bytes(data['objID'])
    msg = bytes(data['msg'])
    if len(src) < config.LEN_ID:
        return True, (None, b'')
    else:
        msg = bytes(data['msg'])
        return True, (src, msg)


# ---------------------------------------------------------------------------
# SendMsg
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_SendMsg_Encode(srcID: bytes, dstID: bytes, msg: bytes):
    return encodeJSON({'src': list(srcID), 'dst': list(dstID),
                       'msg': list(msg)})


@typecheck
def ToClerk_SendMsg_Decode(payload: bytes):
    ok, data = decodeJSON(payload)
    if not ok:
        return False, data

    src = bytes(data['src'])
    dst = bytes(data['dst'])
    msg = bytes(data['msg'])

    if len(dst) != config.LEN_ID:
        return False, 'Insufficient arguments'
    else:
        return True, (src, dst, msg)


@typecheck
def FromClerk_SendMsg_Encode(dummyarg=None):
    return encodeJSON({})


@typecheck
def FromClerk_SendMsg_Decode(payload: bytes):
    return decodeJSON(payload)


# ---------------------------------------------------------------------------
# ControlParts
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_ControlParts_Encode(objID: bytes, cmds_b: list, cmds_f: list):
    # Sanity checks.
    for cmd in cmds_b:
        assert isinstance(cmd, parts.CmdBooster)
    for cmd in cmds_f:
        assert isinstance(cmd, parts.CmdFactory)

    # Every object can have at most 256 parts.
    assert len(cmds_b) < 256
    assert len(cmds_f) < 256

    # Compile dictionary with data and encode it as JSON.
    d = {'objID': objID,
         'cmd_boosters': [_.tostring() for _ in cmds_b],
         'cmd_factories': [_.tostring() for _ in cmds_f]}

    return encodeJSON(d)


@typecheck
def ToClerk_ControlParts_Decode(payload: bytes):
    ok, data = decodeJSON(payload)
    if not ok:
        return False, data

    objID = bytes(data['objID'])
    cmds_b = [parts.fromstring(bytes(_)) for _ in data['cmd_boosters']]
    cmds_f = [parts.fromstring(bytes(_)) for _ in data['cmd_factories']]

    return True, (objID, cmds_b, cmds_f)


@typecheck
def FromClerk_ControlParts_Encode(objIDs: (list, tuple)):
    return encodeJSON({'objIDs': objIDs})


@typecheck
def FromClerk_ControlParts_Decode(payload: bytes):
    ok, data = decodeJSON(payload)
    if not ok:
        return False, data
    return True, [bytes(_) for _ in data['objIDs']]
