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
import numpy as np
import azrael.parts as parts
import azrael.config as config
import azrael.bullet.bullet_data as bullet_data

from collections import namedtuple
from azrael.typecheck import typecheck

ipshell = IPython.embed


# ---------------------------------------------------------------------------
# Ping
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_Ping_Encode(dummyarg=None):
    return True, {}


@typecheck
def ToClerk_Ping_Decode(data: dict):
    return True, data


@typecheck
def FromClerk_Ping_Encode(response: str):
    return True, {'response': response}


@typecheck
def FromClerk_Ping_Decode(data: dict):
    return True, data['response']


# ---------------------------------------------------------------------------
# GetID
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_GetID_Encode(dummyarg=None):
    return True, {}


@typecheck
def ToClerk_GetID_Decode(data: dict):
    return True, data


@typecheck
def FromClerk_GetID_Encode(objID: bytes):
    return True, {'objID': objID}


@typecheck
def FromClerk_GetID_Decode(data: dict):
    return True, bytes(data['objID'])


# ---------------------------------------------------------------------------
# GetTemplateID
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetTemplateID_Encode(objID: bytes):
    return True, {'objID': objID}


@typecheck
def ToClerk_GetTemplateID_Decode(data: dict):
    return True, (bytes(data['objID']), )


@typecheck
def FromClerk_GetTemplateID_Encode(templateID: bytes):
    return True, {'templateID': templateID}


@typecheck
def FromClerk_GetTemplateID_Decode(data: dict):
    return True, bytes(data['templateID'])


# ---------------------------------------------------------------------------
# GetTemplate
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_GetTemplate_Encode(templateID: bytes):
    return True, {'templateID': list(templateID)}


@typecheck
def ToClerk_GetTemplate_Decode(data: dict):
    if 'templateID' in data:
        return True, (bytes(data['templateID']), )
    else:
        return False, 'Corrupt payload'


@typecheck
def FromClerk_GetTemplate_Encode(
        cs: np.ndarray, vert: np.ndarray, UV: np.ndarray, RGB: np.ndarray,
        boosters: (list, tuple), factories: (list, tuple), aabb: float):
    for b in boosters:
        assert isinstance(b, parts.Booster)
    for f in factories:
        assert isinstance(f, parts.Factory)

    d = {'cs': cs, 'vert': vert, 'UV': UV, 'RGB': RGB, 'AABB': aabb,
         'boosters': [_.tostring() for _ in boosters],
         'factories': [_.tostring() for _ in factories]}
    return True, d


@typecheck
def FromClerk_GetTemplate_Decode(data: dict):
    # Wrap the Booster- and Factory data into their dedicated named tuples.
    boosters = [parts.fromstring(_) for _ in data['boosters']]
    factories = [parts.fromstring(_) for _ in data['factories']]

    # Return the complete information in a named tuple.
    nt = namedtuple('Template', 'cs vert uv rgb boosters factories aabb')
    ret = nt(np.array(data['cs'], np.float64),
             np.array(data['vert'], np.float64),
             np.array(data['UV'], np.float64),
             np.array(data['RGB'], np.uint8),
             boosters, factories, data['AABB'])
    return True, ret


# ---------------------------------------------------------------------------
# AddTemplate
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_AddTemplate_Encode(templateID: bytes, cs: np.ndarray,
                               vert: np.ndarray, UV: np.ndarray,
                               RGB: np.ndarray, boosters, factories):
    for b in boosters:
        assert isinstance(b, parts.Booster)
    for f in factories:
        assert isinstance(f, parts.Factory)

    d = {'name': templateID, 'cs': cs.tolist(), 'vert': vert.tolist(),
         'UV': UV.tolist(), 'RGB': RGB.tolist(),
         'boosters': [_.tostring() for _ in boosters],
         'factories': [_.tostring() for _ in factories]}

    return True, d


@typecheck
def ToClerk_AddTemplate_Decode(data: dict):
    # Wrap the Booster- and Factory data into their dedicated named tuples.
    boosters = [parts.fromstring(_) for _ in data['boosters']]
    factories = [parts.fromstring(_) for _ in data['factories']]

    # Convert template ID to a byte string.
    templateID = bytes(data['name'])

    # Convert collision shape and geometry to NumPy array (via byte string).
    cs = np.array(data['cs'], np.float64)
    vert = np.array(data['vert'], np.float64)
    UV = np.array(data['UV'], np.float64)
    RGB = np.array(data['RGB'], np.uint8)

    # Return decoded quantities.
    return True, (templateID, cs, vert, UV, RGB, boosters, factories)


@typecheck
def FromClerk_AddTemplate_Encode(templateID: bytes):
    return True, {'templateID': templateID}


@typecheck
def FromClerk_AddTemplate_Decode(data: dict):
    return True, bytes(data['templateID'])


# ---------------------------------------------------------------------------
# GetAllObjectIDs
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetAllObjectIDs_Encode(dummyarg=None):
    return True, {}


@typecheck
def ToClerk_GetAllObjectIDs_Decode(data: dict):
    return True, data


@typecheck
def FromClerk_GetAllObjectIDs_Encode(data: (list, tuple)):
    return True, {'objIDs': [list(_) for _ in data]}


@typecheck
def FromClerk_GetAllObjectIDs_Decode(data: dict):
    # Partition the byte stream into individual object IDs.
    data = [bytes(_) for _ in data['objIDs']]
    return True, data


# ---------------------------------------------------------------------------
# SuggestPosition
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_SuggestPosition_Encode(objID: bytes, pos: np.ndarray):
    return True, {'objID': objID, 'pos': pos}


@typecheck
def ToClerk_SuggestPosition_Decode(data: dict):
    # Convert to native Python types and return to caller.
    objID = bytes(data['objID'])
    pos = np.array(data['pos'], np.float64)
    return True, (objID, pos)


@typecheck
def FromClerk_SuggestPosition_Encode(dummyarg):
    return True, {}


@typecheck
def FromClerk_SuggestPosition_Decode(payload):
    return True, payload


# ---------------------------------------------------------------------------
# SetForce
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_SetForce_Encode(objID: bytes, force: np.ndarray, rpos: np.ndarray):
    d = {'objID': objID, 'rel_pos': rpos, 'force': force}
    return True, d


@typecheck
def ToClerk_SetForce_Decode(data: dict):
    # Convert to native Python types and return to caller.
    objID = bytes(data['objID'])
    force = np.array(data['force'], np.float64)
    rel_pos = np.array(data['rel_pos'], np.float64)
    return True, (objID, force, rel_pos)


@typecheck
def FromClerk_SetForce_Encode(dummyarg):
    return True, {}


@typecheck
def FromClerk_SetForce_Decode(data: dict):
    return True, payload


# ---------------------------------------------------------------------------
# GetGeometry
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetGeometry_Encode(templateID: bytes):
    return True, {'templateID': templateID}


@typecheck
def ToClerk_GetGeometry_Decode(data: dict):
    return True, (bytes(data['templateID']), )


@typecheck
def FromClerk_GetGeometry_Encode(
        vert: np.ndarray, uv: np.ndarray, rgb: np.ndarray):
    return True, {'vert': vert.tolist(),
                  'UV': uv.tolist(),
                  'RGB': rgb.tolist()}


@typecheck
def FromClerk_GetGeometry_Decode(data: dict):
    vert = np.array(data['vert'], np.float64)
    uv = np.array(data['UV'], np.uint8)
    rgb = np.array(data['RGB'], np.uint8)
    return True, (vert, uv, rgb)


# ---------------------------------------------------------------------------
# GetStateVariables
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetStateVariable_Encode(objIDs: (list, tuple)):
    for objID in objIDs:
        assert isinstance(objID, bytes)
    return True, {'objIDs': [list(_) for _ in objIDs]}


@typecheck
def ToClerk_GetStateVariable_Decode(data: dict):
    objIDs = [bytes(_) for _ in data['objIDs']]
    return True, (objIDs, )


@typecheck
def FromClerk_GetStateVariable_Encode(
        objIDs: (list, tuple), sv: (list, tuple)):
    for _ in sv:
        assert isinstance(_, bullet_data.BulletData)
    d = {'data': [{'objID': objID, 'sv': sv.toJsonDict()}
                  for (objID, sv) in zip(objIDs, sv)]}
    return True, d


@typecheck
def FromClerk_GetStateVariable_Decode(data: dict):
    out = {}
    for d in data['data']:
        out[bytes(d['objID'])] = bullet_data.fromJsonDict(d['sv'])
    return True, out


# ---------------------------------------------------------------------------
# Spawn
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_Spawn_Encode(
        name: bytes, templateID: bytes, sv: bullet_data.BulletData):
    return True, {'name': name, 'templateID': templateID,
                  'sv': sv.toJsonDict()}


@typecheck
def ToClerk_Spawn_Decode(data: dict):
    if data['name'] is None:
        ctrl_name = None
    else:
        ctrl_name = bytes(data['name'])

    templateID = bytes(data['templateID'])
    sv = bullet_data.fromJsonDict(data['sv'])

    if sv is None:
        return False, 'Invalid State Variable data'
    else:
        return True, (ctrl_name, templateID, sv)


@typecheck
def FromClerk_Spawn_Encode(objID: bytes):
    return True, {'objID': objID}


@typecheck
def FromClerk_Spawn_Decode(data: dict):
    return True, bytes(data['objID'])


# ---------------------------------------------------------------------------
# RecvMsg
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_RecvMsg_Encode(objID: bytes):
    return True, {'objID': objID}


@typecheck
def ToClerk_RecvMsg_Decode(data: dict):
    return True, (bytes(data['objID']), )


@typecheck
def FromClerk_RecvMsg_Encode(objID: bytes, msg: bytes):
    return True, {'objID': objID, 'msg': msg}


@typecheck
def FromClerk_RecvMsg_Decode(data: dict):
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
    return True, {'src': srcID, 'dst': dstID, 'msg': msg}


@typecheck
def ToClerk_SendMsg_Decode(data: dict):
    src = bytes(data['src'])
    dst = bytes(data['dst'])
    msg = bytes(data['msg'])

    if len(dst) != config.LEN_ID:
        return False, 'Insufficient arguments'
    else:
        return True, (src, dst, msg)


@typecheck
def FromClerk_SendMsg_Encode(dummyarg=None):
    return True, {}


@typecheck
def FromClerk_SendMsg_Decode(data: dict):
    return True, data


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

    return True, d


@typecheck
def ToClerk_ControlParts_Decode(data: dict):
    objID = bytes(data['objID'])
    cmds_b = [parts.fromstring(_) for _ in data['cmd_boosters']]
    cmds_f = [parts.fromstring(_) for _ in data['cmd_factories']]

    return True, (objID, cmds_b, cmds_f)


@typecheck
def FromClerk_ControlParts_Encode(objIDs: (list, tuple)):
    return True, {'objIDs': objIDs}


@typecheck
def FromClerk_ControlParts_Decode(data: dict):
    return True, [bytes(_) for _ in data['objIDs']]
