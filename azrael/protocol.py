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

import azrael.util
import azrael.igor
import azrael.types as types
import azrael.leo_api as leo_api

from azrael.types import typecheck, RetVal, Template
from azrael.types import RetVal, ConstraintMeta, ConstraintP2P
from azrael.types import FragState, FragDae, FragRaw, FragMeta, FragNone

from IPython import embed as ipshell


# ---------------------------------------------------------------------------
# Ping
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_Ping_Encode(dummyarg=None):
    return RetVal(True, None, {})


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
    return RetVal(True, None, {'objID': objID})


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
# AddTemplates
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_AddTemplates_Encode(templates: list):
    out = [tt._asdict() for tt in templates]
    return RetVal(True, None, {'data': out})


@typecheck
def ToClerk_AddTemplates_Decode(payload: dict):
    templates = []

    with azrael.util.Timeit('clerk.decode') as timeit:
        templates = [Template(**_) for _ in payload['data']]

    # Return decoded quantities.
    return True, (templates, )


@typecheck
def FromClerk_AddTemplates_Encode(dummyarg):
    return True, {}


@typecheck
def FromClerk_AddTemplates_Decode(dummyarg):
    return RetVal(True, None, None)


# ---------------------------------------------------------------------------
# GetTemplates
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_GetTemplates_Encode(templateIDs: list):
    return RetVal(True, None, {'templateIDs': templateIDs})


@typecheck
def ToClerk_GetTemplates_Decode(payload: dict):
    return True, (payload['templateIDs'], )


@typecheck
def FromClerk_GetTemplates_Encode(templates):
    out = {}
    for objID, data in templates.items():
        out[objID] = {'url': data['url'],
                      'template': data['template']._asdict()}
    return True, out


@typecheck
def FromClerk_GetTemplates_Decode(payload: dict):
    out = {}
    for objID, data in payload.items():
        out[objID] = {'url': data['url'],
                      'template': Template(**data['template'])}
    return RetVal(True, None, out)


# ---------------------------------------------------------------------------
# GetAllObjectIDs
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetAllObjectIDs_Encode(dummyarg=None):
    return RetVal(True, None, {})


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
# SetBodyStates
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_SetBodyState_Encode(objID: int, sv: tuple):
    return RetVal(True, None, {'objID': objID, 'sv': sv})


@typecheck
def ToClerk_SetBodyState_Decode(payload: dict):
    # Convenience.
    objID = payload['objID']

    # Convert the state variable into a RigidBodyStateOverride instance.
    sv = payload['sv']
    tmp = dict(zip(types.RigidBodyStateOverride._fields, sv))
    sv = types.RigidBodyStateOverride(**tmp)

    return True, (objID, sv)


@typecheck
def FromClerk_SetBodyState_Encode(dummyarg):
    return True, {}


@typecheck
def FromClerk_SetBodyState_Decode(dummyarg):
    return RetVal(True, None, None)


# ---------------------------------------------------------------------------
# SetForce
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_SetForce_Encode(objID: int, force: tuple, rpos: tuple):
    d = {'objID': objID, 'rel_pos': rpos, 'force': force}
    return RetVal(True, None, d)


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
# GetFragmentGeometries
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetFragmentGeometries_Encode(objIDs: list):
    return RetVal(True, None, {'objIDs': objIDs})


@typecheck
def ToClerk_GetFragmentGeometries_Decode(payload: dict):
    # Convert all objIDs to integers (JSON always converts integers in hash
    # maps to strings, which is why this conversion is necessary).
    objIDs = [int(_) for _ in payload['objIDs']]
    return True, (objIDs, )


@typecheck
def FromClerk_GetFragmentGeometries_Encode(geo):
    return True, geo


@typecheck
def FromClerk_GetFragmentGeometries_Decode(payload: dict):
    # Convert all objIDs to integers (JSON always converts integers in hash
    # maps to strings, which is why this conversion is necessary).
    payload = {int(k): v for (k, v) in payload.items()}
    return RetVal(True, None, payload)


# ---------------------------------------------------------------------------
# SetFragmentGeometry
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_SetFragmentGeometry_Encode(objID: int, frags: list):
    out = {
        'objID': objID,
        'frags': [_._asdict() for _ in frags],
    }
    return RetVal(True, None, out)


@typecheck
def ToClerk_SetFragmentGeometry_Decode(payload: dict):
    # Wrap the fragments into their dedicated tuple.
    frags = []
    for frag in payload['frags']:
        mf = FragMeta(**frag)
        frags.append(mf)
    return True, (payload['objID'], frags)


@typecheck
def FromClerk_SetFragmentGeometry_Encode(dummyarg):
    return True, {}


@typecheck
def FromClerk_SetFragmentGeometry_Decode(dummyarg):
    return RetVal(True, None, None)


# ---------------------------------------------------------------------------
# GetBodyStates
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetBodyState_Encode(objIDs: (list, tuple)):
    return RetVal(True, None, {'objIDs': objIDs})


@typecheck
def ToClerk_GetBodyState_Decode(payload: dict):
    return True, (payload['objIDs'], )


@typecheck
def FromClerk_GetBodyState_Encode(payload: dict):
    out = {}
    for objID, data in payload.items():
        if data is None:
            # fixme: this case should not be possible once Clerk.getBodyState
            # was fixed up.
            out[objID] = None
            continue

        # Convert the constituent elements to dictionaries.
        if data['sv'] is None:
            sv = None
        else:
            sv = data['sv']._asdict()
        frag = [_._asdict() for _ in data['frag']]

        # Replace the original 'sv' and 'frag' entries with the new ones.
        out[objID] = {'sv': sv, 'frag': frag}
    return True, {'data': out}


@typecheck
def FromClerk_GetBodyState_Decode(payload: dict):
    out = {}
    for objID, data in payload['data'].items():
        if data is None:
            # fixme: this case should not be possible once Clerk.getBodyState
            # was fixed up.
            out[int(objID)] = None
            continue

        # Compile the proper data types from the dictionaries.
        if data['sv'] is None:
            sv = None
        else:
            sv = types.RigidBodyState(**data['sv'])
        frag = [types.FragState(**_) for _ in data['frag']]

        # Replace the original 'sv' and 'frag' entries with the new ones.
        out[int(objID)] = {'sv': sv, 'frag': frag}
    return RetVal(True, None, out)


# ---------------------------------------------------------------------------
# GetAllBodyStates
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetAllBodyStates_Encode():
    return RetVal(True, None, None)


@typecheck
def ToClerk_GetAllBodyStates_Decode(payload: dict):
    return True, (None, )

# Reuse the protocol for 'getBodyStates' for the data that comes
# back from Clerk.
FromClerk_GetAllBodyStates_Encode = FromClerk_GetBodyState_Encode
FromClerk_GetAllBodyStates_Decode = FromClerk_GetBodyState_Decode


# ---------------------------------------------------------------------------
# Spawn
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_Spawn_Encode(objectInfos: (tuple, list)):
    return RetVal(True, None, {'objInfos': objectInfos})


@typecheck
def ToClerk_Spawn_Decode(payload: dict):
    # Convenience.
    RigidBodyState = types.RigidBodyState
    RigidBodyStateOverride = types.RigidBodyStateOverride
    _updateRigidBodyStateTuple = leo_api._updateRigidBodyStateTuple

    out = []
    for data in payload['objInfos']:
        templateID = data['template']
        del data['template']

        sv = RigidBodyStateOverride(**data)
        if sv is None:
            return False, 'Invalid State Variable data'
        sv = _updateRigidBodyStateTuple(RigidBodyState(), sv)

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
    return RetVal(True, None, {'objID': objID})


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
         'cmd_boosters': [_._asdict() for _ in cmds_b],
         'cmd_factories': [_._asdict() for _ in cmds_f]}

    return RetVal(True, None, d)


@typecheck
def ToClerk_ControlParts_Decode(payload: dict):
    objID = payload['objID']
    cmds_b = [types.CmdBooster(**_) for _ in payload['cmd_boosters']]
    cmds_f = [types.CmdFactory(**_) for _ in payload['cmd_factories']]

    return True, (objID, cmds_b, cmds_f)


@typecheck
def FromClerk_ControlParts_Encode(objIDs: (list, tuple)):
    return True, {'objIDs': objIDs}


@typecheck
def FromClerk_ControlParts_Decode(payload: dict):
    return RetVal(True, None, payload['objIDs'])


# ---------------------------------------------------------------------------
# SetFragmentStates
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_SetFragmentStates_Encode(fragData: dict):
    # fragData = {objID_1: [FragState, FragState, ...],
    #             objID_2: [FragState, FragState, ...],}
    return RetVal(True, None, fragData)


@typecheck
def ToClerk_SetFragmentStates_Decode(payload: dict):
    out = {}
    for objID, frag_states in payload.items():
        out[int(objID)] = [FragState(*_) for _ in frag_states]
    return True, (out, )


@typecheck
def FromClerk_SetFragmentStates_Encode(dummyarg):
    return True, {}


@typecheck
def FromClerk_SetFragmentStates_Decode(dummyarg):
    return RetVal(True, None, None)


# ---------------------------------------------------------------------------
# AddConstraints
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_AddConstraints_Encode(constraints: (tuple, list)):
    constraints = [_._asdict() for _ in constraints]
    return RetVal(True, None, {'constraints': constraints})


@typecheck
def ToClerk_AddConstraints_Decode(payload: dict):
    out = [ConstraintMeta(**_) for _ in payload['constraints']]
    return True, (out, )


@typecheck
def FromClerk_AddConstraints_Encode(num_added):
    return True, {'added': num_added}


@typecheck
def FromClerk_AddConstraints_Decode(payload):
    return RetVal(True, None, payload['added'])


# ---------------------------------------------------------------------------
# DeleteConstraints
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_DeleteConstraints_Encode(constraints: (tuple, list)):
    return ToClerk_AddConstraints_Encode(constraints)


@typecheck
def ToClerk_DeleteConstraints_Decode(payload: dict):
    return ToClerk_AddConstraints_Decode(payload)


@typecheck
def FromClerk_DeleteConstraints_Encode(num_added):
    return FromClerk_AddConstraints_Encode(num_added)


@typecheck
def FromClerk_DeleteConstraints_Decode(payload):
    return FromClerk_AddConstraints_Decode(payload)


# ---------------------------------------------------------------------------
# getConstraints
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetConstraints_Encode(bodyIDs: (tuple, list)):
    return RetVal(True, None, {'bodyIDs': bodyIDs})


@typecheck
def ToClerk_GetConstraints_Decode(payload: dict):
    return True, (payload['bodyIDs'], )


@typecheck
def FromClerk_GetConstraints_Encode(constraints):
    constraints = [_._asdict() for _ in constraints]
    return True, {'constraints': constraints}


@typecheck
def FromClerk_GetConstraints_Decode(payload):
    out = [ConstraintMeta(**_) for _ in payload['constraints']]
    return RetVal(True, None, out)


# ---------------------------------------------------------------------------
# getAllConstraints
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetAllConstraints_Encode(dummyarg):
    return RetVal(True, None, {})


@typecheck
def ToClerk_GetAllConstraints_Decode(payload):
    return True, tuple()


@typecheck
def FromClerk_GetAllConstraints_Encode(constraints: (tuple, list)):
    return FromClerk_GetConstraints_Encode(constraints)


@typecheck
def FromClerk_GetAllConstraints_Decode(payload: dict):
    return FromClerk_GetConstraints_Decode(payload)
