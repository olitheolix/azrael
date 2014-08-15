import numpy as np
import azrael.util as util
import azrael.commands as commands


def test_serialisation():
    cmd_0 = commands.controlBooster(unitID=0, force=0.2)
    cmd_1 = commands.controlBooster(unitID=1, force=0.4)
    objID = util.int2id(1)

    cmds = commands.serialiseCommands(objID, [cmd_0, cmd_1], [])
    assert isinstance(cmds, bytes)

    out_objID, cmd_booster, cmd_factory = commands.deserialiseCommands(cmds)
    assert out_objID == objID
    assert len(cmd_booster) == 2
    assert len(cmd_factory) == 0

    # Use getattr to automatically test all attributes.
    assert cmd_booster[0].unitID == cmd_0.unitID
    assert cmd_booster[0].force_mag == cmd_0.force_mag
    assert cmd_booster[1].unitID == cmd_1.unitID
    assert cmd_booster[1].force_mag == cmd_1.force_mag

    print('Test passed')
    

if __name__ == '__main__':
    test_serialisation()
