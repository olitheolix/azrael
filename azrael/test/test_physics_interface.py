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
import IPython
import numpy as np

import azrael.leonard as leonard
import azrael.physics_interface as physAPI
import azrael.bullet.bullet_data as bullet_data

from azrael.test.test_clacks import killAzrael
from azrael.test.test_leonard import getLeonard
from azrael.bullet.test_boost_bullet import isEqualBD

ipshell = IPython.embed
BulletData = bullet_data.BulletData
BulletDataOverride = bullet_data.BulletDataOverride


def test_add_get_remove_single():
    """
    Add an object to the SV database.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Create an object ID for the test.
    id_0 = 0
    id_1 = 1

    # The number of SV entries must now be zero.
    assert physAPI.getNumObjects() == 0

    # Query an object. Since none exists yet this must return with an error.
    assert physAPI.getStateVariables([id_0]) == (True, None, {id_0: None})

    # Create an object and serialise it.
    data = BulletData()

    # Add the object to the DB with ID=0.
    assert physAPI.addCmdSpawn(id_0, data, aabb=0)
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

    # Attempt to remove non-existing ID --> must fail.
    assert physAPI.addCmdRemoveObject(id_1).ok
    leo.processCommandsAndSync()

    ret = physAPI.getStateVariables([id_0])
    assert ret.ok
    assert isEqualBD(ret.data[id_0], data)

    ret = physAPI.getAllStateVariables()
    assert (ret.ok, len(ret.data)) == (True, 1)

    # Remove existing ID --> must succeed.
    assert physAPI.addCmdRemoveObject(id_0).ok
    leo.processCommandsAndSync()

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
    id_0 = 0
    id_1 = 1

    # The number of SV entries must now be zero.
    assert physAPI.getNumObjects() == 0
    assert physAPI.getStateVariables([id_0]) == (True, None, {id_0: None})

    # Create an object and serialise it.
    data_0 = BulletData(position=[0, 0, 0])
    data_1 = BulletData(position=[10, 10, 10])

    # Add the objects to the DB.
    assert physAPI.addCmdSpawn(id_0, data_0, aabb=0)
    assert physAPI.addCmdSpawn(id_1, data_1, aabb=0)
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
    id_0 = 0

    # The number of SV entries must now be zero.
    assert physAPI.getNumObjects() == 0
    assert physAPI.getStateVariables([id_0]) == (True, None, {id_0: None})

    # Create two State Vectors.
    data_0 = BulletData(imass=1)
    data_1 = BulletData(imass=2)
    data_2 = BulletData(imass=3)

    # The command queue for spawning objects must be empty.
    ret = physAPI.getCmdSpawn()
    assert ret.ok and (ret.data == [])

    # Request to spawn the first object.
    assert physAPI.addCmdSpawn(id_0, data_0, aabb=0).ok
    ret = physAPI.getCmdSpawn()
    assert ret.ok and (ret.data[0]['objID'] == id_0)

    # Attempt to add another object with the same objID *before* Leonard gets
    # around to add the first one --> this must fail and not add anything.
    assert not physAPI.addCmdSpawn(id_0, data_1, aabb=0).ok
    ret = physAPI.getCmdSpawn()
    assert ret.ok and (len(ret.data) == 1) and (ret.data[0]['objID'] == id_0)

    # Let Leonard pick up the commands. This must flush the command queue.
    leo.step(0, 1)
    ret = physAPI.getCmdSpawn()
    assert ret.ok and (ret.data == [])

    # Similar test to before, but this time Leonard has already pulled id_0
    # into the simulation, and only *afterwards* are we requesting to spawn yet
    # another object with the same ID. the 'addSpawnCmd' must succeed because
    # it cannot reliably verify if Leonard has an object id_0 (it can only
    # verify if another such request is in the queue already -- see
    # above). However, Leonard itself must ignore that request. To verify this,
    # request to spawn a new object with the same id_0 but a different State
    # Vectors, let Leonard evaluate the queue, and finally verify that Leonard
    # did not add/modify id_0.
    ret = physAPI.getStateVariables([id_0])
    assert ret.ok
    assert isEqualBD(ret.data[id_0], data_0)
    assert physAPI.addCmdSpawn(id_0, data_2, aabb=0).ok
    ret = physAPI.getCmdSpawn()
    assert ret.ok and (len(ret.data) == 1) and (ret.data[0]['objID'] == id_0)
    leo.step(0, 1)

    # Must still be original 'data_0' state vector, not 'data_2'.
    ret = physAPI.getStateVariables([id_0])
    assert ret.ok
    assert isEqualBD(ret.data[id_0], data_0)

    print('Test passed')


def test_dequeueCommands():
    """
    Add-, query, and remove commands from the command queue.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Convenience.
    dcSpawn = physAPI.dequeueCmdSpawn
    dcModify = physAPI.dequeueCmdModify
    dcRemove = physAPI.dequeueCmdRemove
    data_0 = BulletData()
    data_1 = BulletDataOverride(imass=2, scale=3)

    id_0, id_1 = 0, 1

    # The command queue must be empty for every category.
    ret = physAPI.getCmdSpawn()
    assert ret.ok and (ret.data == [])
    ret = physAPI.getCmdRemove()
    assert ret.ok and (ret.data == [])

    # Queue one request for id_0.
    assert physAPI.addCmdSpawn(id_0, data_0, aabb=1).ok
    ret = physAPI.getCmdSpawn()
    assert ret.ok and (ret.data[0]['objID'] == id_0)

    assert physAPI.addCmdModifyStateVariable(id_0, data_1).ok
    ret = physAPI.getCmdModifyStateVariables()
    assert ret.ok and (ret.data[0]['objID'] == id_0)

    assert physAPI.addCmdRemoveObject(id_0).ok
    ret = physAPI.getCmdRemove()
    assert ret.ok and (ret.data[0]['objID'] == id_0)

    # De-queue one object --> one objects must have been de-queued.
    assert dcSpawn([id_0]) == (True, None, 1)
    assert dcModify([id_0]) == (True, None, 1)
    assert dcRemove([id_0]) == (True, None, 1)

    # Repeat --> none must have been de-queued.
    assert dcSpawn([id_0]) == (True, None, 0)
    assert dcModify([id_0]) == (True, None, 0)
    assert dcRemove([id_0]) == (True, None, 0)

    # Add two commands.
    for objID in (id_0, id_1):
        assert physAPI.addCmdSpawn(objID, data_0, aabb=1).ok
        assert physAPI.addCmdModifyStateVariable(objID, data_1).ok
        assert physAPI.addCmdRemoveObject(objID).ok

    # De-queue two objects --> two must have been de-queued.
    assert dcSpawn([id_1, id_0]) == (True, None, 2)
    assert dcModify([id_1, id_0]) == (True, None, 2)
    assert dcRemove([id_1, id_0]) == (True, None, 2)

    # Repeat --> none must have been de-queued.
    assert dcSpawn([id_1, id_0]) == (True, None, 0)
    assert dcModify([id_1, id_0]) == (True, None, 0)
    assert dcRemove([id_1, id_0]) == (True, None, 0)

    print('Test passed')


def test_overrideAttributes():
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
    data = BulletDataOverride(imass=2, scale=3, position=p, velocityLin=vl,
                              velocityRot=vr, orientation=o)
    del p, vl, vr, o

    # Create an object ID for the test.
    id_0 = 0

    # Create an object and serialise it.
    btdata = BulletData()

    # Add the object to the DB with ID=0.
    assert physAPI.addCmdSpawn(id_0, btdata, aabb=0).ok
    leo.processCommandsAndSync()

    # Set the overwrite attributes for the just created object.
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


def test_BulletDataOverride():
    """
    ``BulletDataOverride`` must only accept valid input where the
    ``BulletData`` function defines what constitutes as "valid".
    """
    killAzrael()

    # Convenience.
    BulletData = bullet_data.BulletData
    BulletDataOverride = bullet_data.BulletDataOverride

    # Valid BulletData and BulletDataOverride calls.
    assert BulletData() is not None
    assert BulletDataOverride() is not None

    assert BulletData(position=[1, 2, 3]) is not None
    assert BulletDataOverride(position=[1, 2, 3]) is not None

    # Pass positional arguments with None values.
    assert BulletDataOverride(None, None) is not None

    # Pass a dictionary with None values. This must still result in the default
    # structure.
    tmp = {'velocityRot': None, 'cshape': None}
    assert BulletDataOverride(**tmp) is not None
    tmp = {'velocityRot': np.array([1, 2, 3], np.float64), 'cshape': None}
    out = BulletDataOverride(**tmp)
    assert out is not None
    assert np.array_equal(out.velocityRot, tmp['velocityRot'])

    # Combine positional and keyword arguments.
    assert BulletDataOverride(None, None, **tmp) is not None

    # Pass Python- scalars and lists instead of NumPy types. The scalars must
    # remain unaffected but the lists must become NumPy arrays.
    ret = BulletData(imass=3, position=[1, 2, 3])
    assert isinstance(ret.imass, int)
    assert isinstance(ret.position, list)

    ret = BulletDataOverride(imass=3, position=[1, 2, 3])
    assert isinstance(ret.imass, int)
    assert isinstance(ret.position, list)

    # Invalid calls.
    assert BulletData(position=[1, 2]) is None
    assert BulletDataOverride(position=[1, 2]) is None
    assert BulletData(position=np.array([1, 2])) is None
    assert BulletDataOverride(position=np.array([1, 2])) is None

    assert BulletDataOverride(position=1) is None
    assert BulletDataOverride(position='blah') is None

    print('Test passed')


def test_get_set_forceandtorque():
    """
    Query and update the force- and torque vectors for an object.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Create two object IDs for this test.
    id_0 = 0
    id_1 = 1

    # Create two objects and serialise them.
    data_0 = BulletData(position=[0, 0, 0])
    data_1 = BulletData(position=[10, 10, 10])

    # Add the two objects to the simulation.
    assert physAPI.addCmdSpawn(id_0, data_0, aabb=0).ok
    assert physAPI.addCmdSpawn(id_1, data_1, aabb=0).ok
    leo.processCommandsAndSync()

    # Update the force and torque of the second object only.
    force, torque = [1, 2, 3], [4, 5, 6]
    assert physAPI.addCmdSetForceAndTorque(id_1, force, torque)
    leo.processCommandsAndSync()

    # Only the force an torque of the second object must have changed.
    assert np.array_equal(leo.allForces[id_0], [0, 0, 0])
    assert np.array_equal(leo.allTorques[id_0], [0, 0, 0])
    assert np.array_equal(leo.allForces[id_1], force)
    assert np.array_equal(leo.allTorques[id_1], torque)

    print('Test passed')


def test_StateVariable_tuple():
    """
    Test the BulletData class, most notably comparison and (de)serialisation.
    """
    killAzrael()

    # Compare two identical objects.
    sv1 = BulletData()
    sv2 = BulletData()
    assert isEqualBD(sv1, sv2)

    # Compare two different objects.
    sv1 = BulletData()
    sv2 = BulletData(position=[1, 2, 3])
    assert not isEqualBD(sv1, sv2)

    print('Test passed')


def test_set_get_AABB():
    """
    Create a new object with an AABB and query it back again.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Create two object IDs and a BulletData instances for this test.
    id_0, id_1 = 0, 1
    id_2, id_3 = 2, 3
    data = BulletData()

    # Attempt to add an object with a negative AABB value. This must fail.
    assert not physAPI.addCmdSpawn(id_0, data, aabb=-1.5).ok

    # Add two new objects to the DB.
    assert physAPI.addCmdSpawn(id_0, data, aabb=1.5).ok
    assert physAPI.addCmdSpawn(id_1, data, aabb=2.5).ok
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
    test_dequeueCommands()
    test_BulletDataOverride()
    test_set_get_AABB()
    test_StateVariable_tuple()
    test_get_set_forceandtorque()
    test_overrideAttributes()
    test_add_same()
    test_add_get_multiple()
    test_add_get_remove_single()
