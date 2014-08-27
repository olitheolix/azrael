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
def loads(data: bytes):
    # Convenience function for decoding ``data``.
    return json.loads(data.decode('utf8'))
