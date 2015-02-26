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
import azrael.util
import azrael.parts as parts
import azrael.bullet.bullet_data as bullet_data
import azrael.physics_interface as physics_interface

from collections import namedtuple
from azrael.typecheck import typecheck

ipshell = IPython.embed
RetVal = azrael.util.RetVal
Template = azrael.util.Template


# ---------------------------------------------------------------------------
# Ping
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_Ping_Encode(dummyarg=None):
    return True, {}


@typecheck
def ToClerk_Ping_Decode(dummyarg):
    return True, dummyarg


@typecheck
def FromClerk_Ping_Encode(payload: str):
    return True, {'response': payload}


@typecheck
def FromClerk_Ping_Decode(payload: dict):
    return RetVal(True, None, payload['response'])


# ---------------------------------------------------------------------------
# GetTemplateID
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetTemplateID_Encode(objID: int):
    return True, {'objID': objID}


@typecheck
def ToClerk_GetTemplateID_Decode(payload: dict):
    return True, (payload['objID'], )


@typecheck
def FromClerk_GetTemplateID_Encode(templateID: str):
    return True, {'templateID': templateID}


@typecheck
def FromClerk_GetTemplateID_Decode(payload: dict):
    return RetVal(True, None, payload['templateID'])


# ---------------------------------------------------------------------------
# GetTemplates
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_GetTemplates_Encode(templateIDs: list):
    return True, {'templateIDs': templateIDs}


@typecheck
def ToClerk_GetTemplates_Decode(payload: dict):
    if 'templateIDs' not in payload:
        return False, 'Corrupt payload'
    return True, (payload['templateIDs'], )


@typecheck
def FromClerk_GetTemplates_Encode(templates):
    out = {}
    for name, data in templates.items():
        # The cshape is still a NumPy array --> convert it to a list.
        data['cshape'] = data['cshape'].tolist()
        out[name] = data
    return True, out


@typecheck
def FromClerk_GetTemplates_Decode(payload: dict):
    out = {}
    for name, data in payload.items():
        # Return the complete information in a named tuple.
        nt = namedtuple('Template', 'cs vert uv rgb boosters factories aabb')
        ret = nt(np.array(data['cshape'], np.float64),
                 np.array(data['vert'], np.float64),
                 np.array(data['uv'], np.float64),
                 np.array(data['rgb'], np.uint8),
                 data['boosters'], data['factories'], data['aabb'])
        out[name] = ret
    return RetVal(True, None, out)


# ---------------------------------------------------------------------------
# AddTemplates
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_AddTemplates_Encode(templates: list):
    out = []
    with azrael.util.Timeit('clerk.encode') as timeit:
        for tt in templates:
            name, cs, vert, UV, RGB, boosters, factories = tt
            d = {'name': name, 'cs': cs.tolist(), 'vert': vert.tolist(),
                 'UV': UV.tolist(), 'RGB': RGB.tolist(),
                 'boosters': boosters,
                 'factories': factories}
            out.append(d)
    return True, {'data': out}


@typecheck
def ToClerk_AddTemplates_Decode(payload: dict):
    templates = []
    with azrael.util.Timeit('clerk.decode') as timeit:
        for data in payload['data']:
            # Wrap the Booster- and Factory data into their dedicated named
            # tuples.
            boosters = [parts.Booster(*_) for _ in data['boosters']]
            factories = [parts.Factory(*_) for _ in data['factories']]

            # Convert template ID to a byte string.
            name = data['name']

            # Convert collision shape and geometry to NumPy array (via byte
            # string).
            cs = np.array(data['cs'], np.float64)
            vert = data['vert']
            UV = data['UV']
            RGB = data['RGB']

            args = name, cs, vert, UV, RGB, boosters, factories
            try:
                templates.append(Template(*args))
            except TypeError:
                return False, 'Template payload is corrupt'

    # Return decoded quantities.
    return True, (templates, )


@typecheck
def FromClerk_AddTemplates_Encode(dummyarg):
    return True, {}


@typecheck
def FromClerk_AddTemplates_Decode(dummyarg):
    return RetVal(True, None, None)


# ---------------------------------------------------------------------------
# GetAllObjectIDs
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetAllObjectIDs_Encode(dummyarg=None):
    return True, {}


@typecheck
def ToClerk_GetAllObjectIDs_Decode(dummyarg):
    return True, (None,)


@typecheck
def FromClerk_GetAllObjectIDs_Encode(data: (list, tuple)):
    return True, {'objIDs': data}


@typecheck
def FromClerk_GetAllObjectIDs_Decode(payload: dict):
    return RetVal(True, None, payload['objIDs'])


# ---------------------------------------------------------------------------
# SetStateVector
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_SetStateVector_Encode(objID: int, sv: tuple):
    return True, {'objID': objID, 'sv': sv}


@typecheck
def ToClerk_SetStateVector_Decode(payload: dict):
    # Convenience.
    objID = payload['objID']

    # Convert the state variable into a BulletDataOverride instance.
    sv = payload['sv']
    sv = [np.array(_) if isinstance(_, list) else _ for _ in sv]
    tmp = dict(zip(bullet_data.BulletDataOverride._fields, sv))
    sv = bullet_data.BulletDataOverride(**tmp)

    return True, (objID, sv)


@typecheck
def FromClerk_SetStateVector_Encode(dummyarg):
    return True, {}


@typecheck
def FromClerk_SetStateVector_Decode(dummyarg):
    return RetVal(True, None, None)


# ---------------------------------------------------------------------------
# SetForce
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_SetForce_Encode(objID: int, force: np.ndarray, rpos: np.ndarray):
    d = {'objID': objID, 'rel_pos': rpos, 'force': force}
    return True, d


@typecheck
def ToClerk_SetForce_Decode(payload: dict):
    # Convert to native Python types and return to caller.
    objID = payload['objID']
    force = payload['force']
    rel_pos = payload['rel_pos']
    return True, (objID, force, rel_pos)


@typecheck
def FromClerk_SetForce_Encode(dummyarg):
    return True, {}


@typecheck
def FromClerk_SetForce_Decode(dummyarg):
    return RetVal(True, None, None)


# ---------------------------------------------------------------------------
# GetGeometry
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetGeometry_Encode(objID: int):
    return True, {'objID': objID}


@typecheck
def ToClerk_GetGeometry_Decode(payload: dict):
    tmp = payload['objID']
    if not isinstance(tmp, int):
        return False, 'Expected <int> but got <{}>'.format(type(tmp))
    return True, (tmp, )


@typecheck
def FromClerk_GetGeometry_Encode(geo):
    return True, geo


@typecheck
def FromClerk_GetGeometry_Decode(payload: dict):
    vert = np.array(payload['vert'], np.float64)
    uv = np.array(payload['uv'], np.uint8)
    rgb = np.array(payload['rgb'], np.uint8)
    return RetVal(True, None, (vert, uv, rgb))


# ---------------------------------------------------------------------------
# SetGeometry
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_SetGeometry_Encode(
        objID: int, vert: np.ndarray, uv: np.ndarray, rgb: np.ndarray):
    return True, {'objID': objID, 'vert': vert.tolist(), 'UV': uv.tolist(),
                  'RGB': rgb.tolist()}


@typecheck
def ToClerk_SetGeometry_Decode(payload: dict):
    return True, (payload['objID'], payload['vert'],
                  payload['UV'], payload['RGB'])


@typecheck
def FromClerk_SetGeometry_Encode(dummyarg):
    return True, {}


@typecheck
def FromClerk_SetGeometry_Decode(dummyarg):
    return RetVal(True, None, None)


# ---------------------------------------------------------------------------
# GetStateVariables
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetStateVariable_Encode(objIDs: (list, tuple)):
    for objID in objIDs:
        assert isinstance(objID, int)
    return True, {'objIDs': objIDs}


@typecheck
def ToClerk_GetStateVariable_Decode(payload: dict):
    return True, (payload['objIDs'], )


@typecheck
def FromClerk_GetStateVariable_Encode(data: dict):
    fields = bullet_data._BulletData._fields
    for k, v in data.items():
        if v is None:
            data[k] = None
        else:
            data[k] = dict(zip(fields, v))
    return True, {'data': data}


@typecheck
def FromClerk_GetStateVariable_Decode(payload: dict):
    return RetVal(True, None, payload['data'])


# ---------------------------------------------------------------------------
# GetAllStateVariables
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetAllStateVariables_Encode():
    return True, None


@typecheck
def ToClerk_GetAllStateVariables_Decode(payload: dict):
    return True, (None, )

# Reuse the protocol for 'getStateVariables' for the data that comes
# back from Clerk.
FromClerk_GetAllStateVariables_Encode = FromClerk_GetStateVariable_Encode
FromClerk_GetAllStateVariables_Decode = FromClerk_GetStateVariable_Decode


# ---------------------------------------------------------------------------
# Spawn
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_Spawn_Encode(objectInfos: (tuple, list)):
    return True, {'objInfos': objectInfos}


@typecheck
def ToClerk_Spawn_Decode(payload: dict):
    # Convenience.
    BulletData = bullet_data.BulletData
    BulletDataOverride = bullet_data.BulletDataOverride
    _updateBulletDataTuple = physics_interface._updateBulletDataTuple

    out = []
    for data in payload['objInfos']:
        templateID = data['template']
        del data['template']

        sv = BulletDataOverride(**data)
        if sv is None:
            return False, 'Invalid State Variable data'
        sv = _updateBulletDataTuple(BulletData(), sv)

        out.append((templateID, sv))
    return True, (out, )


@typecheck
def FromClerk_Spawn_Encode(objIDs: (list, tuple)):
    return True, {'objIDs': objIDs}


@typecheck
def FromClerk_Spawn_Decode(payload: dict):
    return RetVal(True, None, tuple(payload['objIDs']))


# ---------------------------------------------------------------------------
# Remove
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_Remove_Encode(objID: int):
    return True, {'objID': objID}


@typecheck
def ToClerk_Remove_Decode(payload: dict):
    return True, (payload['objID'], )


@typecheck
def FromClerk_Remove_Encode(dummyarg):
    return True, {}


@typecheck
def FromClerk_Remove_Decode(dummyarg):
    return RetVal(True, None, None)


# ---------------------------------------------------------------------------
# ControlParts
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_ControlParts_Encode(objID: int, cmds_b: list, cmds_f: list):
    # Compile a dictionary with the payload data.
    d = {'objID': objID,
         'cmd_boosters': cmds_b,
         'cmd_factories': cmds_f}

    return True, d


@typecheck
def ToClerk_ControlParts_Decode(payload: dict):
    objID = payload['objID']
    cmds_b = [parts.CmdBooster(*_) for _ in payload['cmd_boosters']]
    cmds_f = [parts.CmdFactory(*_) for _ in payload['cmd_factories']]

    return True, (objID, cmds_b, cmds_f)


@typecheck
def FromClerk_ControlParts_Encode(objIDs: (list, tuple)):
    return True, {'objIDs': objIDs}


@typecheck
def FromClerk_ControlParts_Decode(payload: dict):
    return RetVal(True, None, payload['objIDs'])
