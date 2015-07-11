# Copyright 2015, Oliver Nagy <olitheolix@gmail.com>
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
Converts the JSON data from Clients to the native Python types Clerk expects,
and vice versa.

The codecs in this module specify the JSON format between Clerk and the
clients.

``ToClerk_*_Encode``: Converts the Client's JSON data to native (Python) types.
``FromClerk_*_Encode``: Converts Clerk's response to plain JSON.

The JSON only protocoly should make it possible to write clients in other
languages.
"""

import azrael.util
import azrael.types as types

from azrael.types import typecheck
from IPython import embed as ipshell


# ---------------------------------------------------------------------------
# Ping
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_Ping_Decode(payload):
    return payload


@typecheck
def FromClerk_Ping_Encode(payload: str):
    return payload


# ---------------------------------------------------------------------------
# AddTemplates
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_AddTemplates_Decode(payload: dict):
    # Compile- and sanity check each template.
    T = types.Template
    with azrael.util.Timeit('clerk.decode') as timeit:
        templates = [T(**_) for _ in payload['templates']]
    payload['templates'] = templates
    return payload


@typecheck
def FromClerk_AddTemplates_Encode(dummyarg):
    return None


# ---------------------------------------------------------------------------
# GetTemplates
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_GetTemplates_Decode(payload: dict):
    return payload


@typecheck
def FromClerk_GetTemplates_Encode(templates):
    out = {}
    for aid, data in templates.items():
        out[aid] = {'url_frag': data['url_frag'],
                    'template': data['template']._asdict()}
    return out


# ---------------------------------------------------------------------------
# Spawn
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_Spawn_Decode(payload: dict):
    return payload


@typecheck
def FromClerk_Spawn_Encode(objIDs: (list, tuple)):
    return objIDs


# ---------------------------------------------------------------------------
# GetTemplateID
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_GetTemplateID_Decode(payload: dict):
    return payload


@typecheck
def FromClerk_GetTemplateID_Encode(templateID: str):
    return templateID


# ---------------------------------------------------------------------------
# GetAllObjectIDs
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_GetAllObjectIDs_Decode(payload):
    return payload


@typecheck
def FromClerk_GetAllObjectIDs_Encode(objIDs: (list, tuple)):
    return objIDs


# ---------------------------------------------------------------------------
# RemoveObject
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_RemoveObject_Decode(payload: dict):
    return payload


@typecheck
def FromClerk_RemoveObject_Encode(dummyarg):
    return None


# ---------------------------------------------------------------------------
# ControlParts
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_ControlParts_Decode(payload: dict):
    # Convenience.
    CmdF, CmdB = types.CmdFactory, types.CmdBooster

    # Compile- and sanity check the commands.
    cmds_b = {k: CmdB(**v) for (k, v) in payload['cmd_boosters'].items()}
    cmds_f = {k: CmdF(**v) for (k, v) in payload['cmd_factories'].items()}

    # Overwrite the data in the payload.
    payload['cmd_boosters'] = cmds_b
    payload['cmd_factories'] = cmds_f
    return payload


@typecheck
def FromClerk_ControlParts_Encode(objIDs: (list, tuple)):
    return objIDs


# ---------------------------------------------------------------------------
# GetFragments
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_GetFragments_Decode(payload: dict):
    # Convert the IDs to integers.
    payload['objIDs'] = [int(_) for _ in payload['objIDs']]
    return payload


@typecheck
def FromClerk_GetFragments_Encode(geo):
    return geo


# ---------------------------------------------------------------------------
# SetFragments
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_SetFragments_Decode(payload: dict):
    # Convert the IDs to integers.
    payload['fragments'] = {int(k): v for (k, v) in payload['fragments'].items()}
    return payload


@typecheck
def FromClerk_SetFragments_Encode(dummyarg):
    return None


# ---------------------------------------------------------------------------
# SetRigidBodies
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_SetRigidBodies_Decode(payload: dict):
    # Convert the IDs to integers.
    payload['bodies'] = {int(k): v for (k, v) in payload['bodies'].items()}
    return payload


@typecheck
def FromClerk_SetRigidBodies_Encode(dummyarg):
    return None


# ---------------------------------------------------------------------------
# GetRigidBodies
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_GetRigidBodies_Decode(payload: dict):
    return payload


@typecheck
def FromClerk_GetRigidBodies_Encode(payload: dict):
    out = {}
    for objID, data in payload.items():
        if data is None:
            # Clerk did not find this particular object.
            out[objID] = None
            continue

        # Replace the original 'rbs' and 'frag' entries with the new ones.
        out[objID] = {'rbs': data['rbs']._asdict()}
    return out


# ---------------------------------------------------------------------------
# GetObjectStates
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_GetObjectStates_Decode(payload: dict):
    return payload


@typecheck
def FromClerk_GetObjectStates_Encode(payload: dict):
    return payload


# ---------------------------------------------------------------------------
# SetForce
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_SetForce_Decode(payload: dict):
    return payload


@typecheck
def FromClerk_SetForce_Encode(dummyarg):
    return None


# ---------------------------------------------------------------------------
# AddConstraints
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_AddConstraints_Decode(payload: dict):
    # Compile- and sanity check the constraints.
    C = types.ConstraintMeta
    payload['constraints'] = [C(**_) for _ in payload['constraints']]
    return payload


@typecheck
def FromClerk_AddConstraints_Encode(num_added):
    return num_added


# ---------------------------------------------------------------------------
# DeleteConstraints
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_DeleteConstraints_Decode(payload: dict):
    return ToClerk_AddConstraints_Decode(payload)


@typecheck
def FromClerk_DeleteConstraints_Encode(num_added):
    return FromClerk_AddConstraints_Encode(num_added)


# ---------------------------------------------------------------------------
# getConstraints
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_GetConstraints_Decode(payload: dict):
    return payload


@typecheck
def FromClerk_GetConstraints_Encode(constraints):
    return [_._asdict() for _ in constraints]
