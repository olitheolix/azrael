import numpy as np
from collections import namedtuple as NT


Booster = NT('Booster', 'bid pos orient max_force')
Factory = NT('Factory', 'fid pos orient speed')


def booster(bid, pos=np.zeros(3), orient=[0, 0, 0, 1], max_force=0.5):
    bid = np.int64(bid)

    pos = np.array(pos, np.float64)
    assert len(pos) == 3

    orient = np.array(orient, np.float64)
    assert len(orient) == 4

    assert isinstance(max_force, (int, float))
    max_force = np.float64(max_force)
    
    return Booster(bid, pos, orient, max_force)


def factory(fid, pos=np.zeros(3), orient=[0, 0, 0, 1], speed=[0.1, 0.5]):
    fid = np.int64(fid)

    pos = np.array(pos, np.float64)
    assert len(pos) == 3

    orient = np.array(orient, np.float64)
    assert len(orient) == 4

    speed = np.array(speed, np.float64)
    assert len(speed) == 2

    return Factory(fid, pos, orient, speed)


def booster_tostring(b: Booster):
    out = b''.join([_.tostring() for _ in b])
    return out


def booster_fromstring(b: bytes):
    _ = np.fromstring
    return Booster(_(b[0:8], np.int64)[0],
                   _(b[8:32]),
                   _(b[32:64]),
                   _(b[64:72])[0])


def factory_tostring(f: Factory):
    out = b''.join([_.tostring() for _ in f])
    return out


def factory_fromstring(f: bytes):
    _ = np.fromstring
    return Factory(_(f[0:8], np.int64)[0],
                   _(f[8:32]),
                   _(f[32:64]),
                   _(f[64:80]))
