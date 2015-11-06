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
    'type' : 'object',
    'properties' : {
        'state' : {
            'type': 'object',
            'properties': {
                'scale': num_nonneg,
                'position': vec3,
                'rotation': vec4,
                },
            'additionalProperties': False,
            },
        'fragtype': {'type': 'string'},
        'del': {'type': 'array', 'items': {'type': 'string'}},
        'put' : {
            'type' : 'object',
#            'additionalProperties': {'type': 'string'}
            }
        },
    'additionalProperties': False,
    }
