import json
import numpy as np

class AzraelEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.ndarray) and obj.ndim == 1:
            return obj.tolist()
        if isinstance(obj, bytes):
            return list(obj)
        if isinstance(obj, np.int64):
            return int(obj)
        if isinstance(obj, np.float64):
            return float(obj)
        return json.JSONEncoder.default(self, obj)

def dumps(data):
    return json.dumps(data, cls=AzraelEncoder)

def loads(data: bytes):
    return json.loads(data.decode('utf8'))


# import customserializer
# def to_json(python_object):
#     if isinstance(python_object, time.struct_time):
#         return {'__class__': 'time.asctime',
#                 '__value__': time.asctime(python_object)}
#     if isinstance(python_object, bytes):
#         return {'__class__': 'bytes',
#                 '__value__': list(python_object)}
#     raise TypeError(repr(python_object) + ' is not JSON serializable')

# json.dump(entry, f, default=customserializer.to_json)
