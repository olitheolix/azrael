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
from azrael.types import FragDae, FragRaw, FragMeta, FragNone

from IPython import embed as ipshell


# ---------------------------------------------------------------------------
# Ping
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_Ping_Encode(payload: dict):
    return RetVal(True, None, payload)


@typecheck
def ToClerk_Ping_Decode(payload):
    return payload


@typecheck
def FromClerk_Ping_Encode(payload: str):
    return {'response': payload}


@typecheck
def FromClerk_Ping_Decode(payload: dict):
    return payload


# ---------------------------------------------------------------------------
# GetTemplateID
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetTemplateID_Encode(payload: dict):
    return RetVal(True, None, payload)


@typecheck
def ToClerk_GetTemplateID_Decode(payload: dict):
    return (payload['objID'], )


@typecheck
def FromClerk_GetTemplateID_Encode(templateID: str):
    return {'templateID': templateID}


@typecheck
def FromClerk_GetTemplateID_Decode(payload: dict):
    return payload


# ---------------------------------------------------------------------------
# AddTemplates
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_AddTemplates_Encode(payload: dict):
    return RetVal(True, None, payload)


@typecheck
def ToClerk_AddTemplates_Decode(payload: dict):
    templates = []

    with azrael.util.Timeit('clerk.decode') as timeit:
        templates = [Template(**_) for _ in payload['templates']]

    # Return decoded quantities.
    return (templates, )


@typecheck
def FromClerk_AddTemplates_Encode(dummyarg):
    return {}


@typecheck
def FromClerk_AddTemplates_Decode(payload):
    return payload


# ---------------------------------------------------------------------------
# GetTemplates
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_GetTemplates_Encode(payload: dict):
    return RetVal(True, None, payload)


@typecheck
def ToClerk_GetTemplates_Decode(payload: dict):
    return (payload['templateIDs'], )


@typecheck
def FromClerk_GetTemplates_Encode(templates):
    out = {}
    for objID, data in templates.items():
        out[objID] = {'url_frag': data['url_frag'],
                      'template': data['template']._asdict()}
    return out


@typecheck
def FromClerk_GetTemplates_Decode(payload: dict):
    return payload


# ---------------------------------------------------------------------------
# GetAllObjectIDs
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetAllObjectIDs_Encode(payload: dict):
    return RetVal(True, None, payload)


@typecheck
def ToClerk_GetAllObjectIDs_Decode(dummyarg):
    return (None,)


@typecheck
def FromClerk_GetAllObjectIDs_Encode(data: (list, tuple)):
    return {'objIDs': data}


@typecheck
def FromClerk_GetAllObjectIDs_Decode(payload: dict):
    return payload


# ---------------------------------------------------------------------------
# SetRigidBodies
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_SetRigidBodies_Encode(payload: dict):
    return RetVal(True, None, payload)


@typecheck
def ToClerk_SetRigidBodies_Decode(payload: dict):
    out = {int(k): v for (k, v) in payload['bodies'].items()}
    return (out, )


@typecheck
def FromClerk_SetRigidBodies_Encode(dummyarg):
    return {}


@typecheck
def FromClerk_SetRigidBodies_Decode(payload):
    return payload


# ---------------------------------------------------------------------------
# SetForce
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_SetForce_Encode(payload: dict):
    return RetVal(True, None, payload)


@typecheck
def ToClerk_SetForce_Decode(payload: dict):
    # Convert to native Python types and return to caller.
    objID = payload['objID']
    force = payload['force']
    rel_pos = payload['rel_pos']
    return (objID, force, rel_pos)


@typecheck
def FromClerk_SetForce_Encode(dummyarg):
    return {}


@typecheck
def FromClerk_SetForce_Decode(payload):
    return payload


# ---------------------------------------------------------------------------
# GetFragments
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetFragments_Encode(payload: dict):
    return RetVal(True, None, payload)


@typecheck
def ToClerk_GetFragments_Decode(payload: dict):
    # Convert all objIDs to integers (JSON always converts integers in hash
    # maps to strings, which is why this conversion is necessary).
    objIDs = [int(_) for _ in payload['objIDs']]
    return (objIDs, )


@typecheck
def FromClerk_GetFragments_Encode(geo):
    return geo


@typecheck
def FromClerk_GetFragments_Decode(payload: dict):
    return payload


# ---------------------------------------------------------------------------
# SetFragments
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_SetFragments_Encode(payload: dict):
    return RetVal(True, None, payload)


@typecheck
def ToClerk_SetFragments_Decode(payload: dict):
    # Wrap the fragments into their dedicated tuple.
    ret = {int(k): v for (k, v) in payload.items()}
    return (ret, )


@typecheck
def FromClerk_SetFragments_Encode(dummyarg):
    return {}


@typecheck
def FromClerk_SetFragments_Decode(payload):
    return payload


# ---------------------------------------------------------------------------
# GetRigidBodies
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetRigidBodies_Encode(payload: dict):
    return RetVal(True, None, payload)


@typecheck
def ToClerk_GetRigidBodies_Decode(payload: dict):
    return (payload['objIDs'], )


@typecheck
def FromClerk_GetRigidBodies_Encode(payload: dict):
    out = {}
    for objID, data in payload.items():
        if data is None:
            # Clerk could not find this particular object.
            out[objID] = None
            continue

        # Replace the original 'rbs' and 'frag' entries with the new ones.
        out[objID] = {'rbs': data['rbs']._asdict()}
    return out


@typecheck
def FromClerk_GetRigidBodies_Decode(payload: dict):
    return payload


# ---------------------------------------------------------------------------
# GetObjectStates
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetObjectStates_Encode(payload: dict):
    return RetVal(True, None, payload)


@typecheck
def ToClerk_GetObjectStates_Decode(payload: dict):
    return (payload['objIDs'], )


@typecheck
def FromClerk_GetObjectStates_Encode(payload: dict):
    return payload


@typecheck
def FromClerk_GetObjectStates_Decode(payload: dict):
    return payload


# ---------------------------------------------------------------------------
# Spawn
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_Spawn_Encode(payload: dict):
    return RetVal(True, None, payload)


@typecheck
def ToClerk_Spawn_Decode(payload: dict):
    return (payload['spawn'], )


@typecheck
def FromClerk_Spawn_Encode(objIDs: (list, tuple)):
    return {'objIDs': objIDs}


@typecheck
def FromClerk_Spawn_Decode(payload: dict):
    return payload


# ---------------------------------------------------------------------------
# Remove
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_Remove_Encode(payload: dict):
    return RetVal(True, None, payload)


@typecheck
def ToClerk_Remove_Decode(payload: dict):
    return (payload['objID'], )


@typecheck
def FromClerk_Remove_Encode(dummyarg):
    return {}


@typecheck
def FromClerk_Remove_Decode(payload):
    return payload


# ---------------------------------------------------------------------------
# ControlParts
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_ControlParts_Encode(payload: dict):
    return RetVal(True, None, payload)


@typecheck
def ToClerk_ControlParts_Decode(payload: dict):
    objID = payload['objID']
    cmds_b = {k: types.CmdBooster(**v) for (k, v) in payload['cmd_boosters'].items()}
    cmds_f = {k: types.CmdFactory(**v) for (k, v) in payload['cmd_factories'].items()}

    return (objID, cmds_b, cmds_f)


@typecheck
def FromClerk_ControlParts_Encode(objIDs: (list, tuple)):
    return {'objIDs': objIDs}


@typecheck
def FromClerk_ControlParts_Decode(payload: dict):
    return payload


# ---------------------------------------------------------------------------
# AddConstraints
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_AddConstraints_Encode(payload: dict):
    return RetVal(True, None, payload)


@typecheck
def ToClerk_AddConstraints_Decode(payload: dict):
    out = [ConstraintMeta(**_) for _ in payload['constraints']]
    return (out, )


@typecheck
def FromClerk_AddConstraints_Encode(num_added):
    return {'added': num_added}


@typecheck
def FromClerk_AddConstraints_Decode(payload):
    return payload


# ---------------------------------------------------------------------------
# DeleteConstraints
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_DeleteConstraints_Encode(payload: dict):
    return payload


@typecheck
def ToClerk_DeleteConstraints_Decode(payload: dict):
    return ToClerk_AddConstraints_Decode(payload)


@typecheck
def FromClerk_DeleteConstraints_Encode(num_added):
    return FromClerk_AddConstraints_Encode(num_added)


@typecheck
def FromClerk_DeleteConstraints_Decode(payload):
    return payload


# ---------------------------------------------------------------------------
# getConstraints
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetConstraints_Encode(payload: dict):
    return payload


@typecheck
def ToClerk_GetConstraints_Decode(payload: dict):
    return (payload['bodyIDs'], )


@typecheck
def FromClerk_GetConstraints_Encode(constraints):
    constraints = [_._asdict() for _ in constraints]
    return {'constraints': constraints}


@typecheck
def FromClerk_GetConstraints_Decode(payload):
    return payload
