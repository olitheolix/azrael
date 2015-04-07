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

import sys
import pytest
import cytoolz
import numpy as np

import azrael.leonard as leonard
import azrael.physics_interface as physAPI
import azrael.bullet.bullet_data as bullet_data

from IPython import embed as ipshell
from azrael.test.test_leonard import getLeonard, killAzrael
from azrael.bullet.test_boost_bullet import isEqualBD

MotionState = bullet_data.MotionState
MotionStateOverride = bullet_data.MotionStateOverride


def test_add_get_remove_single():
    """
    Add an object to the SV database.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Create an object ID for the test.
    id_0, id_1, aabb = 0, 1, 0

    # The number of SV entries must now be zero.
    assert physAPI.getNumObjects() == 0

    # Query an object. Since none exists yet this must return with an error.
    assert physAPI.getStateVariables([id_0]) == (True, None, {id_0: None})

    # Create an object and serialise it.
    data = MotionState()

    # Add the object to the DB with ID=0.
    assert physAPI.addCmdSpawn([(id_0, data, aabb)])
    leo.processCommandsAndSync()

    # Query the object. This must return the SV data directly.
    ret = physAPI.getStateVariables([id_0])
    assert ret.ok
    assert isEqualBD(ret.data[id_0], data)

    # Query the same object but supply it as a list. This must return a list
    # with one element which is the exact same object as before.
    ret = physAPI.getStateVariables([id_0])
    assert ret.ok
    assert isEqualBD(ret.data[id_0], data)

    # Verify that the system contains exactly one object.
    ret = physAPI.getAllStateVariables()
    assert (ret.ok, len(ret.data)) == (True, 1)

    # Remove object id_0.
    assert physAPI.addCmdRemoveObject(id_0).ok
    leo.processCommandsAndSync()

    # Object must not exist anymore in the simulation.
    assert physAPI.getStateVariables([id_0]) == (True, None, {id_0: None})
    ret = physAPI.getAllStateVariables()
    assert (ret.ok, len(ret.data)) == (True, 0)

    print('Test passed')


def test_add_get_multiple():
    """
    Add multiple objects to the DB.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Create two object IDs for this test.
    id_0, id_1, aabb = 0, 1, 0

    # The number of SV entries must now be zero.
    assert physAPI.getNumObjects() == 0
    assert physAPI.getStateVariables([id_0]) == (True, None, {id_0: None})

    # Create an object and serialise it.
    data_0 = MotionState(position=[0, 0, 0])
    data_1 = MotionState(position=[10, 10, 10])

    # Add the objects to the DB.
    tmp = [(id_0, data_0, aabb), (id_1, data_1, aabb)]
    assert physAPI.addCmdSpawn(tmp)
    leo.processCommandsAndSync()

    # Query the objects individually.
    ret = physAPI.getStateVariables([id_0])
    assert ret.ok
    assert isEqualBD(ret.data[id_0], data_0)
    ret = physAPI.getStateVariables([id_1])
    assert ret.ok
    assert isEqualBD(ret.data[id_1], data_1)

    # Manually query multiple objects.
    ret = physAPI.getStateVariables([id_0, id_1])
    assert (ret.ok, len(ret.data)) == (True, 2)
    assert isEqualBD(ret.data[id_0], data_0)
    assert isEqualBD(ret.data[id_1], data_1)

    # Repeat, but change the order of the objects.
    ret = physAPI.getStateVariables([id_1, id_0])
    assert (ret.ok, len(ret.data)) == (True, 2)
    assert isEqualBD(ret.data[id_0], data_0)
    assert isEqualBD(ret.data[id_1], data_1)

    # Query all objects at once.
    ret = physAPI.getAllStateVariables()
    assert (ret.ok, len(ret.data)) == (True, 2)
    assert isEqualBD(ret.data[id_0], data_0)
    assert isEqualBD(ret.data[id_1], data_1)

    print('Test passed')


def test_add_same():
    """
    Try to add two objects with the same ID.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Convenience.
    id_0, aabb = 0, 0

    # The number of SV entries must now be zero.
    assert physAPI.getNumObjects() == 0
    assert physAPI.getStateVariables([id_0]) == (True, None, {id_0: None})

    # Create two State Vectors.
    data_0 = MotionState(imass=1)
    data_1 = MotionState(imass=2)
    data_2 = MotionState(imass=3)

    # The command queue for spawning objects must be empty.
    ret = physAPI.dequeueCommands()
    assert ret.ok and (ret.data['spawn'] == [])

    # Spawn the first object, then attempt to spawn another with the same objID
    # *before* Leonard gets around to add even the first one --> this must fail
    # and not add anything.
    assert physAPI.addCmdSpawn([(id_0, data_0, aabb)]).ok
    assert not physAPI.addCmdSpawn([(id_0, data_1, aabb)]).ok
    ret = physAPI.dequeueCommands()
    spawn = ret.data['spawn']
    assert ret.ok and (len(spawn) == 1) and (spawn[0]['objID'] == id_0)

    # Similar test as before, but this time Leonard has already pulled id_0
    # into the simulation *before* are we want to spawn yet another object with
    # the same ID. the 'addSpawnCmd' must succeed because it cannot reliably
    # verify if Leonard has an object id_0 (it can only verify if another such
    # request is in the queue already -- see above). However, Leonard itself
    # must ignore that request. To verify this claim we will now spawn a new
    # object with the same id_0 but a different State Vectors, let  Leonard
    # process the queue, and then verify that it did not add/modify the object
    # with id_0.
    assert physAPI.addCmdSpawn([(id_0, data_0, aabb)]).ok
    leo.processCommandsAndSync()
    ret = physAPI.getStateVariables([id_0])
    assert ret.ok and isEqualBD(ret.data[id_0], data_0)

    # Spawn a new object with same id_0 but different State Vector data_2.
    assert physAPI.addCmdSpawn([(id_0, data_2, aabb)]).ok
    leo.processCommandsAndSync()

    # The State Vector for id_0 must still be data_0.
    ret = physAPI.getStateVariables([id_0])
    assert ret.ok and isEqualBD(ret.data[id_0], data_0)

    print('Test passed')


def test_commandQueue():
    """
    Add-, query, and remove commands from the command queue.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Convenience.
    data_0 = MotionState()
    data_1 = MotionStateOverride(imass=2, scale=3)
    id_0, id_1 = 0, 1
    aabb = 1

    # The command queue must be empty for every category.
    ret = physAPI.dequeueCommands()
    assert ret.ok
    assert ret.data['spawn'] == []
    assert ret.data['remove'] == []
    assert ret.data['modify'] == []
    assert ret.data['direct_force'] == []
    assert ret.data['booster_force'] == []

    # Spawn two objects with id_0 and id_1.
    tmp = [(id_0, data_0, aabb), (id_1, data_1, aabb)]
    assert physAPI.addCmdSpawn(tmp).ok

    # Verify that the spawn commands were added.
    ret = physAPI.dequeueCommands()
    assert ret.ok
    assert ret.data['spawn'][0]['objID'] == id_0
    assert ret.data['spawn'][1]['objID'] == id_1
    assert ret.data['remove'] == []
    assert ret.data['modify'] == []
    assert ret.data['direct_force'] == []
    assert ret.data['booster_force'] == []

    # De-queuing the commands once more must not return any results because
    # they have already been removed.
    ret = physAPI.dequeueCommands()
    assert ret.ok
    assert ret.data['spawn'] == []
    assert ret.data['remove'] == []
    assert ret.data['modify'] == []
    assert ret.data['direct_force'] == []
    assert ret.data['booster_force'] == []

    # Modify State Variable for id_0.
    newSV = MotionStateOverride(imass=10, position=[3, 4, 5])
    assert physAPI.addCmdModifyStateVariable(id_0, newSV).ok
    ret = physAPI.dequeueCommands()
    modify = ret.data['modify']
    assert ret.ok and len(modify) == 1
    assert modify[0]['objID'] == id_0
    assert tuple(modify[0]['sv']) == tuple(newSV)
    del newSV

    # Set the direct force and torque for id_1.
    force, torque = [1, 2, 3], [4, 5, 6]
    assert physAPI.addCmdDirectForce(id_1, force, torque).ok
    ret = physAPI.dequeueCommands()
    fat = ret.data['direct_force']
    assert ret.ok
    assert len(fat) == 1
    assert fat[0]['objID'] == id_1
    assert fat[0]['force'] == force
    assert fat[0]['torque'] == torque

    # Set the booster force and torque for id_0.
    force, torque = [1, 2, 3], [4, 5, 6]
    assert physAPI.addCmdBoosterForce(id_0, force, torque).ok
    ret = physAPI.dequeueCommands()
    fat = ret.data['booster_force']
    assert ret.ok
    assert len(fat) == 1
    assert fat[0]['objID'] == id_0
    assert fat[0]['force'] == force
    assert fat[0]['torque'] == torque

    # Remove an object.
    assert physAPI.addCmdRemoveObject(id_0).ok
    ret = physAPI.dequeueCommands()
    assert ret.ok and ret.data['remove'][0]['objID'] == id_0

    # Add commands for two objects (it is perfectly ok to add commands for
    # non-existing object IDs since this is just a command queue - Leonard will
    # skip commands for non-existing IDs automatically).
    force, torque = [7, 8, 9], [10, 11.5, 12.5]
    for objID in (id_0, id_1):
        assert physAPI.addCmdSpawn([(objID, data_0, aabb)]).ok
        assert physAPI.addCmdModifyStateVariable(objID, data_1).ok
        assert physAPI.addCmdRemoveObject(objID).ok
        assert physAPI.addCmdDirectForce(objID, force, torque).ok
        assert physAPI.addCmdBoosterForce(objID, force, torque).ok

    # De-queue all commands.
    ret = physAPI.dequeueCommands()
    assert ret.ok
    assert len(ret.data['spawn']) == 2
    assert len(ret.data['remove']) == 2
    assert len(ret.data['modify']) == 2
    assert len(ret.data['direct_force']) == 2
    assert len(ret.data['booster_force']) == 2

    print('Test passed')


def test_setStateVariable():
    """
    Set and retrieve object attributes like position, velocity, acceleration,
    and orientation.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Test constants.
    p = np.array([1, 2, 5])
    vl = np.array([8, 9, 10.5])
    vr = 1 + vl
    o = np.array([11, 12.5, 13, 13.5])
    data = MotionStateOverride(imass=2, scale=3, position=p, velocityLin=vl,
                              velocityRot=vr, orientation=o)
    del p, vl, vr, o

    # Create an object ID for the test.
    id_0, aabb = 0, 0

    # Create an object and serialise it.
    btdata = MotionState()

    # Add the object to the DB with ID=0.
    assert physAPI.addCmdSpawn([(id_0, btdata, aabb)]).ok
    leo.processCommandsAndSync()

    # Modify the State Vector for id_0.
    assert physAPI.addCmdModifyStateVariable(id_0, data).ok
    leo.processCommandsAndSync()

    ret = physAPI.getStateVariables([id_0])
    assert ret.ok
    ret = ret.data[id_0]
    assert ret.imass == data.imass
    assert ret.scale == data.scale
    assert np.array_equal(ret.position, data.position)
    assert np.array_equal(ret.velocityLin, data.velocityLin)
    assert np.array_equal(ret.velocityRot, data.velocityRot)
    assert np.array_equal(ret.orientation, data.orientation)

    print('Test passed')


def test_MotionStateOverride():
    """
    ``MotionStateOverride`` must only accept valid input where the
    ``MotionState`` function defines what constitutes as "valid".
    """
    killAzrael()

    # Convenience.
    MotionState = bullet_data.MotionState
    MotionStateOverride = bullet_data.MotionStateOverride

    # Valid MotionState and MotionStateOverride calls.
    assert MotionState() is not None
    assert MotionStateOverride() is not None

    assert MotionState(position=[1, 2, 3]) is not None
    assert MotionStateOverride(position=[1, 2, 3]) is not None

    # Pass positional arguments with None values.
    assert MotionStateOverride(None, None) is not None

    # Pass a dictionary with None values. This must still result in the default
    # structure.
    tmp = {'velocityRot': None, 'cshape': None}
    assert MotionStateOverride(**tmp) is not None
    tmp = {'velocityRot': np.array([1, 2, 3], np.float64), 'cshape': None}
    out = MotionStateOverride(**tmp)
    assert out is not None
    assert np.array_equal(out.velocityRot, tmp['velocityRot'])

    # Combine positional and keyword arguments.
    assert MotionStateOverride(None, None, **tmp) is not None

    # Pass Python- scalars and lists instead of NumPy types. The scalars must
    # remain unaffected but the lists must become NumPy arrays.
    ret = MotionState(imass=3, position=[1, 2, 3])
    assert isinstance(ret.imass, int)
    assert isinstance(ret.position, list)

    ret = MotionStateOverride(imass=3, position=[1, 2, 3])
    assert isinstance(ret.imass, int)
    assert isinstance(ret.position, list)

    # Invalid calls.
    assert MotionState(position=[1, 2]) is None
    assert MotionStateOverride(position=[1, 2]) is None
    assert MotionState(position=np.array([1, 2])) is None
    assert MotionStateOverride(position=np.array([1, 2])) is None

    assert MotionStateOverride(position=1) is None
    assert MotionStateOverride(position='blah') is None

    print('Test passed')


def test_get_set_forceandtorque():
    """
    Query and update the force- and torque vectors for an object.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Create two object IDs for this test.
    id_0, id_1, aabb = 0, 1, 0

    # Create two objects and serialise them.
    data_0 = MotionState(position=[0, 0, 0])
    data_1 = MotionState(position=[10, 10, 10])

    # Add the two objects to the simulation.
    tmp = [(id_0, data_0, aabb), (id_1, data_1, aabb)]
    assert physAPI.addCmdSpawn(tmp).ok
    leo.processCommandsAndSync()

    # Update the direct force and torque of the second object only.
    force, torque = [1, 2, 3], [4, 5, 6]
    assert physAPI.addCmdDirectForce(id_1, force, torque)
    leo.processCommandsAndSync()

    # Only the force an torque of the second object must have changed.
    assert np.array_equal(leo.allForces[id_0].forceDirect, [0, 0, 0])
    assert np.array_equal(leo.allForces[id_0].torqueDirect, [0, 0, 0])
    assert np.array_equal(leo.allForces[id_1].forceDirect, force)
    assert np.array_equal(leo.allForces[id_1].torqueDirect, torque)

    # Update the booster force and torque of the first object only.
    force, torque = [1, 2, 3], [4, 5, 6]
    assert physAPI.addCmdBoosterForce(id_1, force, torque)
    leo.processCommandsAndSync()

    # Only the booster- force an torque of the second object must have
    # changed.
    assert np.array_equal(leo.allForces[id_0].forceDirect, [0, 0, 0])
    assert np.array_equal(leo.allForces[id_0].torqueDirect, [0, 0, 0])
    assert np.array_equal(leo.allForces[id_1].forceDirect, force)
    assert np.array_equal(leo.allForces[id_1].torqueDirect, torque)

    print('Test passed')


def test_StateVariable_tuple():
    """
    Test the MotionState class, most notably comparison and (de)serialisation.
    """
    killAzrael()

    # Compare two identical objects.
    sv1 = MotionState()
    sv2 = MotionState()
    assert isEqualBD(sv1, sv2)

    # Compare two different objects.
    sv1 = MotionState()
    sv2 = MotionState(position=[1, 2, 3])
    assert not isEqualBD(sv1, sv2)

    print('Test passed')


def test_set_get_AABB():
    """
    Create a new object with an AABB and query it back again.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Create two object IDs and a MotionState instances for this test.
    id_0, id_1 = 0, 1
    id_2, id_3 = 2, 3
    aabb_1, aabb_2 = 1.5, 2.5
    data = MotionState()

    # Attempt to add an object with a negative AABB value. This must fail.
    assert not physAPI.addCmdSpawn([(id_0, data, -1.5)]).ok

    # Add two new objects to the DB.
    tmp = [(id_0, data, aabb_1), (id_1, data, aabb_2)]
    assert physAPI.addCmdSpawn(tmp).ok
    leo.processCommandsAndSync()

    # Query the AABB of the first.
    ret = physAPI.getAABB([id_0])
    assert np.array_equal(ret.data, [1.5])

    # Query the AABB of the second.
    ret = physAPI.getAABB([id_1])
    assert np.array_equal(ret.data, [2.5])

    # Query the AABB of both simultaneously.
    ret = physAPI.getAABB([id_0, id_1])
    assert np.array_equal(ret.data, [1.5, 2.5])

    # Query the AABB of a non-existing ID.
    ret = physAPI.getAABB([id_0, id_3])
    assert ret.ok
    assert np.array_equal(ret.data, [1.5, None])


if __name__ == '__main__':
    test_commandQueue()
    test_MotionStateOverride()
    test_set_get_AABB()
    test_StateVariable_tuple()
    test_get_set_forceandtorque()
    test_setStateVariable()
    test_add_same()
    test_add_get_multiple()
    test_add_get_remove_single()
