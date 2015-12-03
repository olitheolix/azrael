# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""
JSON schemas to validate data structures.
"""
# 2 Element vector (eg position).
vec2 = {
    'type': 'array',
    'minItems': 2,
    'maxItems': 2,
    'items': {'type': 'number'},
}

# 3 Element vector (eg position).
vec3 = {
    'type': 'array',
    'minItems': 3,
    'maxItems': 3,
    'items': {'type': 'number'},
}

# 4 Element vector (eg rotation Quaternion).
vec4 = {
    'type': 'array',
    'minItems': 4,
    'maxItems': 4,
    'items': {'type': 'number'},
}

# Non-negative scalar.
num_nonneg = {
    'type': 'number',
    'minimum': 0,
}

# Scheme to validate the input to 'Clerk.setFragments'.
setFragments = {
    'title': 'setFragments',
    'type': 'object',
    'properties': {
        'scale': num_nonneg,
        'position': vec3,
        'rotation': vec4,
        'fragtype': {'type': 'string'},
        'del': {'type': 'array', 'items': {'type': 'string'}},
        'put': {
            'type': 'object',
            # 'additionalProperties': {'type': 'string'}
        },
        'op': {'type': 'string', 'pattern': "put|mod|del"},
    },
    'required': ['op'],
    'additionalProperties': False,
}


FragMeta = {
    'title': 'FragMeta',
    'type': 'object',
    'properties': {
        'scale': num_nonneg,
        'position': vec3,
        'rotation': vec4,
        'fragtype': {'type': 'string'},
        'files': {'type': 'object'},
    },
    'required': ['scale', 'position', 'rotation', 'fragtype', 'files'],
    'additionalProperties': False,
}


Booster = {
    'title': 'Booster',
    'type': 'object',
    'properties': {
        'force': {'type': 'number'},
        'position': vec3,
        'direction': vec3,
    },
    'required': ['force', 'position', 'direction'],
    'additionalProperties': False,
}


Factory = {
    'title': 'Factory',
    'type': 'object',
    'properties': {
        'templateID': {'type': 'string'},
        'exit_speed': vec2,
        'position': vec3,
        'direction': vec3,
    },
    'required': ['templateID', 'exit_speed', 'position', 'direction'],
    'additionalProperties': False,
}


RigidBodyState = {
    'title': 'RigidBodyState',
    'type': 'object',
    'properties': {
        'scale': num_nonneg,
        'imass': num_nonneg,
        'restitution': num_nonneg,
        'com': vec3,
        'inertia': vec3,
        'paxis': vec4,
        'position': vec3,
        'velocityLin': vec3,
        'velocityRot': vec3,
        'rotation': vec4,
        'cshapes': {'type': 'object'},
        'linFactor': vec3,
        'rotFactor': vec3,
        'version': {'type': 'number'},
    },
    'required': ['scale', 'imass', 'restitution', 'position', 'rotation',
                 'linFactor', 'rotFactor', 'version', 'cshapes'],
    'additionalProperties': False,
}

Template = {
    'title': 'Template',
    'definitions': {
        'FragMeta': FragMeta,
        'RigidBodyState': RigidBodyState,
        'Booster': Booster,
        'Factory': Factory,
    },
    'type': 'object',
    'properties': {
        'aid': {'type': 'string'},
        'custom': {'type': 'string'},
        'rbs': {'$ref': '#/definitions/RigidBodyState'},
        'fragments': {
            'type': 'object',
            'patternProperties': {
                '.*': {'oneOf': [{'$ref': '#/definitions/FragMeta'}]},
            }
        },
        'boosters': {
            'type': 'object',
            'patternProperties': {
                '.*': {'oneOf': [{'$ref': '#/definitions/Booster'}]},
            }
        },
        'factories': {
            'type': 'object',
            'patternProperties': {
                '.*': {'oneOf': [{'$ref': '#/definitions/Factory'}]},
            }
        },
    },
    'required': ['aid', 'custom', 'rbs', 'fragments', 'boosters', 'factories'],
    'additionalProperties': False,
}

autodoc_allschemas = {
    'sf': setFragments,
    'fm': FragMeta,
    'bo': Booster,
    'fa': Factory,
    'rbs': RigidBodyState,
    'template': Template,
}
