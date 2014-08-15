import numpy as np
import azrael.config as config
from collections import namedtuple as NT

CmdBooster = NT('CmdBooster', 'unitID force_mag')
CmdFactory = NT('CmdFactory', 'unitID')


def controlBooster(unitID, force: float):
    unitID = np.int64(unitID)
    force = np.float64(force)
    return CmdBooster(unitID, force)


def serialiseCommands(objID: bytes, cmds_b: list, cmds_f: list):
    assert isinstance(objID, bytes)
    for cmd in cmds_b:
        assert isinstance(cmd, CmdBooster)
    for cmd in cmds_f:
        assert isinstance(cmd, CmdFactory)

    assert len(cmds_b) < 256
    assert len(cmds_f) < 256

    out = objID

    out += np.int64(len(cmds_b))
    for cmd in cmds_b:
        out += b''.join([_.tostring() for _ in cmd])

    out += np.int64(len(cmds_f))
    for cmd in cmds_f:
        out += b''.join([_.tostring() for _ in cmd])

    return out


def deserialiseCommands(cmds: bytes):
    assert isinstance(cmds, bytes)

    objID = cmds[0:config.LEN_ID]
    cmds_b, cmds_f = [], []

    ofs = config.LEN_ID
    num_boosters = np.fromstring(cmds[ofs:ofs+8], np.int64)[0]
    ofs += 8
    for ii in range(num_boosters):
        cmds_b.append(
            CmdBooster(np.fromstring(cmds[ofs+0:ofs+8], np.int64),
                       np.fromstring(cmds[ofs+8:ofs+16], np.float64)))
        ofs += 16
        
    num_factories = np.fromstring(cmds[ofs:ofs+8], np.int64)[0]
    ofs += 8
    for ii in range(num_factories):
        cmds_f.append(
            CmdFactory(np.fromstring(cmds[ofs+0:ofs+8], np.int64),
                       np.fromstring(cmds[ofs+8:ofs+16], np.float64)))
        ofs += 16
    return objID, cmds_b, cmds_f
