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
NumPy away JSON parser.
"""

import json
import numpy as np
from azrael.typecheck import typecheck


class AzraelEncoder(json.JSONEncoder):
    """
    Augment default JSON encoder to handle bytes and NumPy arrays.
    """
    @typecheck
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, bytes):
            return list(obj)
        if isinstance(obj, np.int64):
            return int(obj)
        if isinstance(obj, np.float64):
            return float(obj)
        return json.JSONEncoder.default(self, obj)


def dumps(data):
    # Convenience function for encoding ``data`` with custom JSON encoder.
    return json.dumps(data, cls=AzraelEncoder)


@typecheck
def loads(data: str):
    # Convenience function for decoding ``data``.
    return json.loads(data)
