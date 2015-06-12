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

import azrael.database
import azrael.leonard as leonard
import azrael.leo_api as leoAPI
import azrael.rb_state as rb_state

from IPython import embed as ipshell
from azrael.test.test_leonard import getLeonard
from azrael.test.test_bullet_api import isEqualBD
from azrael.test.test_bullet_api import getCSEmpty, getCSBox, getCSSphere
from azrael.types import CollShapeMeta, CollShapeEmpty, CollShapeSphere

RigidBodyState = rb_state.RigidBodyState
RigidBodyStateOverride = rb_state.RigidBodyStateOverride


class TestClerk:
    @classmethod
    def setup_class(cls):
        pass

    @classmethod
    def teardown_class(cls):
        pass

    def setup_method(self, method):
        azrael.database.init()

    def teardown_method(self, method):
        pass

    def test_add_get_remove_single(self):
        """
        Add an object to the SV database.
        """
        # Reset the SV database and instantiate a Leonard.
        leo = getLeonard()

        # Create an object ID for the test.
        id_0, id_1, aabb = 0, 1, 0

        # The number of SV entries must now be zero.
        assert leoAPI.getNumObjects() == 0

        # Query an object. Since none exists yet this must fail.
        assert leoAPI.getBodyStates([id_0]) == (True, None, {id_0: None})

        # Create an object and serialise it.
        data = RigidBodyState(cshapes=[getCSSphere('cssphere')])

        # Add the object to the DB with ID=0.
        assert leoAPI.addCmdSpawn([(id_0, data, aabb)])
        leo.processCommandsAndSync()

        # Query the object. This must return the SV data directly.
        ret = leoAPI.getBodyStates([id_0])
        assert ret.ok
        assert isEqualBD(ret.data[id_0], data)

        # Query the same object but supply it as a list. This must return a
        # list with one element which is the exact same object as before.
        ret = leoAPI.getBodyStates([id_0])
        assert ret.ok
        assert isEqualBD(ret.data[id_0], data)

        # Verify that the system contains exactly one object.
        ret = leoAPI.getAllBodyStates()
        assert (ret.ok, len(ret.data)) == (True, 1)

        # Remove object id_0.
        assert leoAPI.addCmdRemoveObject(id_0).ok
        leo.processCommandsAndSync()

        # Object must not exist anymore in the simulation.
        assert leoAPI.getBodyStates([id_0]) == (True, None, {id_0: None})
        ret = leoAPI.getAllBodyStates()
        assert (ret.ok, len(ret.data)) == (True, 0)

    def test_add_get_multiple(self):
        """
        Add multiple objects to the DB.
        """
        # Reset the SV database and instantiate a Leonard.
        leo = getLeonard()

        # Create two object IDs for this test.
        id_0, id_1, aabb = 0, 1, 0

        # The number of SV entries must now be zero.
        assert leoAPI.getNumObjects() == 0
        assert leoAPI.getBodyStates([id_0]) == (True, None, {id_0: None})

        # Create an object and serialise it.
        data_0 = RigidBodyState(position=[0, 0, 0])
        data_1 = RigidBodyState(position=[10, 10, 10])

        # Add the objects to the DB.
        tmp = [(id_0, data_0, aabb), (id_1, data_1, aabb)]
        assert leoAPI.addCmdSpawn(tmp)
        leo.processCommandsAndSync()

        # Query the objects individually.
        ret = leoAPI.getBodyStates([id_0])
        assert ret.ok
        assert isEqualBD(ret.data[id_0], data_0)
        ret = leoAPI.getBodyStates([id_1])
        assert ret.ok
        assert isEqualBD(ret.data[id_1], data_1)

        # Manually query multiple objects.
        ret = leoAPI.getBodyStates([id_0, id_1])
        assert (ret.ok, len(ret.data)) == (True, 2)
        assert isEqualBD(ret.data[id_0], data_0)
        assert isEqualBD(ret.data[id_1], data_1)

        # Repeat, but change the order of the objects.
        ret = leoAPI.getBodyStates([id_1, id_0])
        assert (ret.ok, len(ret.data)) == (True, 2)
        assert isEqualBD(ret.data[id_0], data_0)
        assert isEqualBD(ret.data[id_1], data_1)

        # Query all objects at once.
        ret = leoAPI.getAllBodyStates()
        assert (ret.ok, len(ret.data)) == (True, 2)
        assert isEqualBD(ret.data[id_0], data_0)
        assert isEqualBD(ret.data[id_1], data_1)

    def test_add_same(self):
        """
        Try to add two objects with the same ID.
        """
        # Reset the SV database and instantiate a Leonard.
        leo = getLeonard()

        # Convenience.
        id_0, aabb = 0, 0

        # The number of SV entries must now be zero.
        assert leoAPI.getNumObjects() == 0
        assert leoAPI.getBodyStates([id_0]) == (True, None, {id_0: None})

        # Create two State Vectors.
        data_0 = RigidBodyState(imass=1)
        data_1 = RigidBodyState(imass=2)
        data_2 = RigidBodyState(imass=3)

        # The command queue for spawning objects must be empty.
        ret = leoAPI.dequeueCommands()
        assert ret.ok and (ret.data['spawn'] == [])

        # Spawn the first object, then attempt to spawn another with the same
        # objID *before* Leonard gets around to add even the first one --> this
        # must fail and not add anything.
        assert leoAPI.addCmdSpawn([(id_0, data_0, aabb)]).ok
        assert not leoAPI.addCmdSpawn([(id_0, data_1, aabb)]).ok
        ret = leoAPI.dequeueCommands()
        spawn = ret.data['spawn']
        assert ret.ok and (len(spawn) == 1) and (spawn[0]['objID'] == id_0)

        # Similar test as before, but this time Leonard has already pulled id_0
        # into the simulation *before* are we want to spawn yet another object
        # with the same ID. the 'addSpawnCmd' must succeed because it cannot
        # reliably verify if Leonard has an object id_0 (it can only verify if
        # another such request is in the queue already -- see above). However,
        # Leonard itself must ignore that request. To verify this claim we will
        # now spawn a new object with the same id_0 but a different State
        # Vectors, let  Leonard process the queue, and then verify that it did
        # not add/modify the object with id_0.
        assert leoAPI.addCmdSpawn([(id_0, data_0, aabb)]).ok
        leo.processCommandsAndSync()
        ret = leoAPI.getBodyStates([id_0])
        assert ret.ok and isEqualBD(ret.data[id_0], data_0)

        # Spawn a new object with same id_0 but different State Vector data_2.
        assert leoAPI.addCmdSpawn([(id_0, data_2, aabb)]).ok
        leo.processCommandsAndSync()

        # The State Vector for id_0 must still be data_0.
        ret = leoAPI.getBodyStates([id_0])
        assert ret.ok and isEqualBD(ret.data[id_0], data_0)

    def test_commandQueue(self):
        """
        Add-, query, and remove commands from the command queue.
        """
        # Reset the SV database and instantiate a Leonard.
        leo = getLeonard()

        # Convenience.
        data_0 = RigidBodyState()
        data_1 = RigidBodyStateOverride(imass=2, scale=3)
        id_0, id_1 = 0, 1
        aabb = 1

        # The command queue must be empty for every category.
        ret = leoAPI.dequeueCommands()
        assert ret.ok
        assert ret.data['spawn'] == []
        assert ret.data['remove'] == []
        assert ret.data['modify'] == []
        assert ret.data['direct_force'] == []
        assert ret.data['booster_force'] == []

        # Spawn two objects with id_0 and id_1.
        tmp = [(id_0, data_0, aabb), (id_1, data_1, aabb)]
        assert leoAPI.addCmdSpawn(tmp).ok

        # Verify that the spawn commands were added.
        ret = leoAPI.dequeueCommands()
        assert ret.ok
        assert ret.data['spawn'][0]['objID'] == id_0
        assert ret.data['spawn'][1]['objID'] == id_1
        assert ret.data['remove'] == []
        assert ret.data['modify'] == []
        assert ret.data['direct_force'] == []
        assert ret.data['booster_force'] == []

        # De-queuing the commands once more must not return any results because
        # they have already been removed.
        ret = leoAPI.dequeueCommands()
        assert ret.ok
        assert ret.data['spawn'] == []
        assert ret.data['remove'] == []
        assert ret.data['modify'] == []
        assert ret.data['direct_force'] == []
        assert ret.data['booster_force'] == []

        # Modify State Variable for id_0.
        newSV = RigidBodyStateOverride(imass=10, position=[3, 4, 5])
        assert leoAPI.addCmdModifyStateVariable(id_0, newSV).ok
        ret = leoAPI.dequeueCommands()
        modify = ret.data['modify']
        assert ret.ok and len(modify) == 1
        assert modify[0]['objID'] == id_0
        assert tuple(modify[0]['sv']) == tuple(newSV)
        del newSV

        # Set the direct force and torque for id_1.
        force, torque = [1, 2, 3], [4, 5, 6]
        assert leoAPI.addCmdDirectForce(id_1, force, torque).ok
        ret = leoAPI.dequeueCommands()
        fat = ret.data['direct_force']
        assert ret.ok
        assert len(fat) == 1
        assert fat[0]['objID'] == id_1
        assert fat[0]['force'] == force
        assert fat[0]['torque'] == torque

        # Set the booster force and torque for id_0.
        force, torque = [1, 2, 3], [4, 5, 6]
        assert leoAPI.addCmdBoosterForce(id_0, force, torque).ok
        ret = leoAPI.dequeueCommands()
        fat = ret.data['booster_force']
        assert ret.ok
        assert len(fat) == 1
        assert fat[0]['objID'] == id_0
        assert fat[0]['force'] == force
        assert fat[0]['torque'] == torque

        # Remove an object.
        assert leoAPI.addCmdRemoveObject(id_0).ok
        ret = leoAPI.dequeueCommands()
        assert ret.ok and ret.data['remove'][0]['objID'] == id_0

        # Add commands for two objects (it is perfectly ok to add commands for
        # non-existing object IDs since this is just a command queue - Leonard
        # will skip commands for non-existing IDs automatically).
        force, torque = [7, 8, 9], [10, 11.5, 12.5]
        for objID in (id_0, id_1):
            assert leoAPI.addCmdSpawn([(objID, data_0, aabb)]).ok
            assert leoAPI.addCmdModifyStateVariable(objID, data_1).ok
            assert leoAPI.addCmdRemoveObject(objID).ok
            assert leoAPI.addCmdDirectForce(objID, force, torque).ok
            assert leoAPI.addCmdBoosterForce(objID, force, torque).ok

        # De-queue all commands.
        ret = leoAPI.dequeueCommands()
        assert ret.ok
        assert len(ret.data['spawn']) == 2
        assert len(ret.data['remove']) == 2
        assert len(ret.data['modify']) == 2
        assert len(ret.data['direct_force']) == 2
        assert len(ret.data['booster_force']) == 2

    def test_setBodyState(self):
        """
        Set and retrieve object attributes like position, velocity,
        acceleration, and orientation.
        """
        # Reset the SV database and instantiate a Leonard.
        leo = getLeonard()

        # Test constants.
        p = np.array([1, 2, 5])
        vl = np.array([8, 9, 10.5])
        vr = 1 + vl
        o = np.array([11, 12.5, 13, 13.5])
        data = RigidBodyStateOverride(
            imass=2, scale=3, position=p, velocityLin=vl,
            velocityRot=vr, orientation=o)
        del p, vl, vr, o

        # Create an object ID for the test.
        id_0, aabb = 0, 0

        # Create an object and serialise it.
        btdata = RigidBodyState()

        # Add the object to the DB with ID=0.
        assert leoAPI.addCmdSpawn([(id_0, btdata, aabb)]).ok
        leo.processCommandsAndSync()

        # Modify the State Vector for id_0.
        assert leoAPI.addCmdModifyStateVariable(id_0, data).ok
        leo.processCommandsAndSync()

        ret = leoAPI.getBodyStates([id_0])
        assert ret.ok
        ret = ret.data[id_0]
        assert ret.imass == data.imass
        assert ret.scale == data.scale
        assert np.array_equal(ret.position, data.position)
        assert np.array_equal(ret.velocityLin, data.velocityLin)
        assert np.array_equal(ret.velocityRot, data.velocityRot)
        assert np.array_equal(ret.orientation, data.orientation)

    def test_RigidBodyStateOverride(self):
        """
        ``RigidBodyStateOverride`` must only accept valid input where the
        ``RigidBodyState`` function defines what constitutes as "valid".
        """
        # Convenience.
        RigidBodyState = rb_state.RigidBodyState
        RigidBodyStateOverride = rb_state.RigidBodyStateOverride

        # Valid RigidBodyState and RigidBodyStateOverride calls.
        assert RigidBodyState() is not None
        assert RigidBodyStateOverride() is not None

        assert RigidBodyState(position=[1, 2, 3]) is not None
        assert RigidBodyStateOverride(position=[1, 2, 3]) is not None

        # Pass positional arguments with None values.
        assert RigidBodyStateOverride(None, None) is not None

        # Pass a dictionary with None values. This must still result in the
        # default structure.
        tmp = {'velocityRot': None, 'cshapes': None}
        assert RigidBodyStateOverride(**tmp) is not None
        tmp = {'velocityRot': np.array([1, 2, 3], np.float64), 'cshapes': None}
        out = RigidBodyStateOverride(**tmp)
        assert out is not None
        assert np.array_equal(out.velocityRot, tmp['velocityRot'])

        # Combine positional and keyword arguments.
        assert RigidBodyStateOverride(None, None, **tmp) is not None

        # Pass Python- scalars and lists instead of NumPy types. The scalars
        # must remain unaffected but the lists must become NumPy arrays.
        ret = RigidBodyState(imass=3, position=[1, 2, 3])
        assert isinstance(ret.imass, int)
        assert isinstance(ret.position, list)

        ret = RigidBodyStateOverride(imass=3, position=[1, 2, 3])
        assert isinstance(ret.imass, int)
        assert isinstance(ret.position, list)

        # Invalid calls.
        assert RigidBodyState(position=[1, 2]) is None
        assert RigidBodyStateOverride(position=[1, 2]) is None
        assert RigidBodyState(position=np.array([1, 2])) is None
        assert RigidBodyStateOverride(position=np.array([1, 2])) is None

        assert RigidBodyStateOverride(position=1) is None
        assert RigidBodyStateOverride(position='blah') is None

    def test_get_set_forceandtorque(self):
        """
        Query and update the force- and torque vectors for an object.
        """
        # Reset the SV database and instantiate a Leonard.
        leo = getLeonard()

        # Create two object IDs for this test.
        id_0, id_1, aabb = 0, 1, 0

        # Create two objects and serialise them.
        data_0 = RigidBodyState(position=[0, 0, 0])
        data_1 = RigidBodyState(position=[10, 10, 10])

        # Add the two objects to the simulation.
        tmp = [(id_0, data_0, aabb), (id_1, data_1, aabb)]
        assert leoAPI.addCmdSpawn(tmp).ok
        leo.processCommandsAndSync()

        # Update the direct force and torque of the second object only.
        force, torque = [1, 2, 3], [4, 5, 6]
        assert leoAPI.addCmdDirectForce(id_1, force, torque)
        leo.processCommandsAndSync()

        # Only the force an torque of the second object must have changed.
        assert np.array_equal(leo.allForces[id_0].forceDirect, [0, 0, 0])
        assert np.array_equal(leo.allForces[id_0].torqueDirect, [0, 0, 0])
        assert np.array_equal(leo.allForces[id_1].forceDirect, force)
        assert np.array_equal(leo.allForces[id_1].torqueDirect, torque)

        # Update the booster force and torque of the first object only.
        force, torque = [1, 2, 3], [4, 5, 6]
        assert leoAPI.addCmdBoosterForce(id_1, force, torque)
        leo.processCommandsAndSync()

        # Only the booster- force an torque of the second object must have
        # changed.
        assert np.array_equal(leo.allForces[id_0].forceDirect, [0, 0, 0])
        assert np.array_equal(leo.allForces[id_0].torqueDirect, [0, 0, 0])
        assert np.array_equal(leo.allForces[id_1].forceDirect, force)
        assert np.array_equal(leo.allForces[id_1].torqueDirect, torque)

    def test_StateVariable_tuple(self):
        """
        Test the ``RigidBodyState`` class, most notably the __eq__ method.
        """
        # Compare two identical objects.
        sv1 = RigidBodyState()
        sv2 = RigidBodyState()
        assert isEqualBD(sv1, sv2)

        # Compare two different objects.
        sv1 = RigidBodyState()
        sv2 = RigidBodyState(position=[1, 2, 3])
        assert not isEqualBD(sv1, sv2)

    def test_set_get_AABB(self):
        """
        Create a new object with an AABB and query it back again.
        """
        # Reset the SV database and instantiate a Leonard.
        leo = getLeonard()

        # Create two object IDs and a RigidBodyState instances for this test.
        id_0, id_1 = 0, 1
        id_2, id_3 = 2, 3
        aabb_1, aabb_2 = 1.5, 2.5
        data = RigidBodyState()

        # Attempt to add an object with a negative AABB value. This must fail.
        assert not leoAPI.addCmdSpawn([(id_0, data, -1.5)]).ok

        # Add two new objects to the DB.
        tmp = [(id_0, data, aabb_1), (id_1, data, aabb_2)]
        assert leoAPI.addCmdSpawn(tmp).ok
        leo.processCommandsAndSync()

        # Query the AABB of the first.
        ret = leoAPI.getAABB([id_0])
        assert np.array_equal(ret.data, [1.5])

        # Query the AABB of the second.
        ret = leoAPI.getAABB([id_1])
        assert np.array_equal(ret.data, [2.5])

        # Query the AABB of both simultaneously.
        ret = leoAPI.getAABB([id_0, id_1])
        assert np.array_equal(ret.data, [1.5, 2.5])

        # Query the AABB of a non-existing ID.
        ret = leoAPI.getAABB([id_0, id_3])
        assert ret.ok
        assert np.array_equal(ret.data, [1.5, None])
