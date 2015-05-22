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

import base64
import azrael.util
import azrael.bullet_data as bullet_data
import azrael.physics_interface as physics_interface

import numpy as np
import azrael.parts as parts

from collections import namedtuple
from azrael.types import typecheck, RetVal, Template
from azrael.types import FragState, FragDae, FragRaw, MetaFragment

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
# GetTemplates
# ---------------------------------------------------------------------------

@typecheck
def ToClerk_GetTemplates_Encode(templateIDs: list):
    return RetVal(True, None, {'templateIDs': templateIDs})


@typecheck
def ToClerk_GetTemplates_Decode(payload: dict):
    if 'templateIDs' not in payload:
        return False, 'Corrupt payload'
    return True, (payload['templateIDs'], )


@typecheck
def FromClerk_GetTemplates_Encode(templates):
    return True, templates


@typecheck
def FromClerk_GetTemplates_Decode(payload: dict):
    out = {}
    for name, data in payload.items():
        # Return the complete information in a named tuple.
        nt = namedtuple('Template',
                        'cs boosters factories aabb url fragments')
        ret = nt(data['cshape'],
                 data['boosters'], data['factories'], data['aabb'],
                 data['url'], data['fragments'])
        out[name] = ret
    return RetVal(True, None, out)


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
    b64d = base64.b64decode

    def _decodeDae(mf):
        """
        Decode the Collada fragment data ``mf``.
        """
        fd = FragDae(*mf.data)
        dae = b64d(fd.dae.encode('utf8'))
        rgb = {k: b64d(v.encode('utf8')) for (k, v) in fd.rgb.items()}
        return mf._replace(data=FragDae(dae, rgb))

    with azrael.util.Timeit('clerk.decode') as timeit:
        for data in payload['data']:
            # Wrap the Booster/Factory data into their dedicated tuples type.
            boosters = [parts.Booster(*_) for _ in data['boosters']]
            factories = [parts.Factory(*_) for _ in data['factories']]

            # Wrap the Meta fragments into its dedicated tuple type.
            meta_frags = [MetaFragment(*_) for _ in data['fragments']]

            # Wrap each fragment model into its dedicated tuple type.
            frags = []
            for mf in meta_frags:
                if mf.type == 'dae':
                    # Collada format.
                    frags.append(_decodeDae(mf))
                else:
                    frags.append(mf)

            try:
                tmp = Template(name=data['name'], cs=data['cs'],
                               fragments=frags, boosters=boosters,
                               factories=factories)
                templates.append(tmp)
            except KeyError:
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
# SetStateVector
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_SetStateVector_Encode(objID: int, sv: tuple):
    return RetVal(True, None, {'objID': objID, 'sv': sv})


@typecheck
def ToClerk_SetStateVector_Decode(payload: dict):
    # Convenience.
    objID = payload['objID']

    # Convert the state variable into a MotionStateOverride instance.
    sv = payload['sv']
    sv = [np.array(_) if isinstance(_, list) else _ for _ in sv]
    tmp = dict(zip(bullet_data.MotionStateOverride._fields, sv))
    sv = bullet_data.MotionStateOverride(**tmp)

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
# GetGeometries
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetGeometries_Encode(objIDs: list):
    return RetVal(True, None, {'objIDs': objIDs})


@typecheck
def ToClerk_GetGeometries_Decode(payload: dict):
    objIDs = payload['objIDs']
    if not isinstance(objIDs, list):
        return False, 'Expected <list> but got <{}>'.format(type(objIDs))

    try:
        objIDs = [int(_) for _ in objIDs]
    except TypeError:
        return False, 'Expected integers in ToClerk_GetGeometries_Decode'
    return True, (objIDs, )


@typecheck
def FromClerk_GetGeometries_Encode(geo):
    return True, geo


@typecheck
def FromClerk_GetGeometries_Decode(payload: dict):
    payload = {int(k): v for (k, v) in payload.items()}
    return RetVal(True, None, payload)


# ---------------------------------------------------------------------------
# SetGeometry
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_SetGeometry_Encode(objID: int, frags: list):
    return RetVal(True, None, {'objID': objID, 'frags': frags})


@typecheck
def ToClerk_SetGeometry_Decode(payload: dict):
    # Wrap the fragments into their dedicated tuple.
    frags = []
    b64d = base64.b64decode
    for frag in payload['frags']:
        mf = MetaFragment(*frag)
        if mf.type == 'dae':
            fd = FragDae(*mf.data)
            dae = b64d(fd.dae.encode('utf8'))
            rgb = {k: b64d(v.encode('utf8')) for (k, v) in fd.rgb.items()}
            mf = mf._replace(data=FragDae(dae, rgb))
        frags.append(mf)
    return True, (payload['objID'], frags)


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
    return RetVal(True, None, {'objIDs': objIDs})


@typecheck
def ToClerk_GetStateVariable_Decode(payload: dict):
    return True, (payload['objIDs'], )


@typecheck
def FromClerk_GetStateVariable_Encode(data: dict):
    # For each objID compile a dictionary with the SV and fragment data in a JS
    # friendly hashmap format.
    for k, v in data.items():
        if v is None:
            data[k] = None
            continue

        # Convert the list of ``FragState`` tuples into a list of dictionaries.
        # This will make it easier in JS to extract specific values instead of
        # using magic array index numbers.
        frags = [_._asdict() for _ in v['frag']]

        # Add the converted tuples to the output dictionary.
        data[k] = {'frag': frags, 'sv': v['sv']._asdict()}
    return True, {'data': data}


@typecheck
def FromClerk_GetStateVariable_Decode(payload: dict):
    return RetVal(True, None, payload['data'])


# ---------------------------------------------------------------------------
# GetAllStateVariables
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_GetAllStateVariables_Encode():
    return RetVal(True, None, None)


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
    return RetVal(True, None, {'objInfos': objectInfos})


@typecheck
def ToClerk_Spawn_Decode(payload: dict):
    # Convenience.
    MotionState = bullet_data.MotionState
    MotionStateOverride = bullet_data.MotionStateOverride
    _updateMotionStateTuple = physics_interface._updateMotionStateTuple

    out = []
    for data in payload['objInfos']:
        templateID = data['template']
        del data['template']

        sv = MotionStateOverride(**data)
        if sv is None:
            return False, 'Invalid State Variable data'
        sv = _updateMotionStateTuple(MotionState(), sv)

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
         'cmd_boosters': cmds_b,
         'cmd_factories': cmds_f}

    return RetVal(True, None, d)


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


# ---------------------------------------------------------------------------
# updateFragmentStates
# ---------------------------------------------------------------------------


@typecheck
def ToClerk_UpdateFragmentStates_Encode(fragData: dict):
    # fragData = {objID_1: [FragState, FragState, ...],
    #             objID_2: [FragState, FragState, ...],}
    return RetVal(True, None, fragData)


@typecheck
def ToClerk_UpdateFragmentStates_Decode(payload: dict):
    out = {}
    for objID, frag_states in payload.items():
        out[int(objID)] = [FragState(*_) for _ in frag_states]
    return True, (out, )


@typecheck
def FromClerk_UpdateFragmentStates_Encode(dummyarg):
    return True, {}


@typecheck
def FromClerk_UpdateFragmentStates_Decode(dummyarg):
    return RetVal(True, None, None)
