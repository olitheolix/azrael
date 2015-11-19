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

import numpy as np

import azrael.database
import azrael.leo_api as leoAPI

from IPython import embed as ipshell
from azrael.test.test import getLeonard
from azrael.test.test import getCSEmpty, getCSBox
from azrael.test.test import getCSSphere, getCSPlane, getRigidBody


class TestLeonardAPI:
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
        id_1 = '1'

        # The number of SV entries must now be zero.
        assert len(leo.allBodies) == 0

        # Query an object. Since none exists yet this must fail.
        assert id_1 not in leo.allBodies

        # Create an object and serialise it.
        body = getRigidBody(cshapes={'cssphere': getCSSphere()})

        # Add the object to Leonard and verify it worked.
        assert leoAPI.addCmdSpawn([(id_1, body)])
        leo.processCommandsAndSync()
        assert leo.allBodies[id_1] == body

        # Remove object id_1.
        assert leoAPI.addCmdRemoveObject(id_1).ok
        leo.processCommandsAndSync()

        # Object must not exist anymore in the simulation.
        assert id_1 not in leo.allBodies
        assert len(leo.allBodies) == 0

    def test_add_get_multiple(self):
        """
        Add multiple objects to the DB.
        """
        # Reset the SV database and instantiate a Leonard.
        leo = getLeonard()

        # Create two object IDs for this test.
        id_1, id_2 = '1', '2'

        # The number of bodies in Leonard must be zero.
        assert len(leo.allBodies) == 0

        # Create an object and serialise it.
        body_1 = getRigidBody(position=[0, 0, 0])
        body_2 = getRigidBody(position=[10, 10, 10])

        # Add the bodies to Leonard.
        tmp = [(id_1, body_1), (id_2, body_2)]
        assert leoAPI.addCmdSpawn(tmp)
        leo.processCommandsAndSync()

        # Verify the bodies.
        assert leo.allBodies[id_1] == body_1
        assert leo.allBodies[id_2] == body_2

    def test_add_same(self):
        """
        Try to add two objects with the same ID.
        """
        # Instantiate a Leonard.
        leo = getLeonard()

        # Convenience.
        id_1 = '1'

        # The number of bodies in Leonard must be zero.
        assert len(leo.allBodies) == 0

        # Create three bodies.
        body_1 = getRigidBody(imass=1)
        body_2 = getRigidBody(imass=2)
        body_3 = getRigidBody(imass=3)

        # The command queue for spawning objects must be empty.
        ret = leoAPI.dequeueCommands()
        assert ret.ok and (ret.data['spawn'] == [])

        # Spawn the first object, then attempt to spawn another with the same
        # objID *before* Leonard gets around to add even the first one --> this
        # must fail and not add anything.
        assert leoAPI.addCmdSpawn([(id_1, body_1)]).ok
        assert not leoAPI.addCmdSpawn([(id_1, body_2)]).ok
        ret = leoAPI.dequeueCommands()
        spawn = ret.data['spawn']
        assert ret.ok and (len(spawn) == 1) and (spawn[0]['objID'] == id_1)

        # Similar test as before, but this time Leonard has already pulled id_1
        # into the simulation *before* we (attempt to) spawn another object
        # with the same ID. The 'addSpawnCmd' must succeed because it cannot
        # reliably verify if Leonard has an object id_1 (it can only verify if
        # another such request is in the queue already -- see above). However,
        # Leonard itself must ignore that request. To verify this claim we will
        # now spawn a new object with the same id_1 but a different state data,
        # let Leonard process the queue, and then verify that it did not
        # add/modify the object with id_1.
        assert leoAPI.addCmdSpawn([(id_1, body_1)]).ok
        leo.processCommandsAndSync()
        assert leo.allBodies[id_1] == body_1

        # Spawn anoter object with id_1 but different state data and verify
        # that Leonard did not modify the original body.
        assert leoAPI.addCmdSpawn([(id_1, body_3)]).ok
        leo.processCommandsAndSync()
        assert leo.allBodies[id_1] == body_1

    def test_commandQueue(self):
        """
        Add-, query, and remove commands from the command queue.
        """
        # Convenience.
        body_1 = getRigidBody()
        body_2 = {'imass': 2, 'scale': 3}
        id_1, id_2 = '0', '1'

        # The command queue must be empty for every category.
        ret = leoAPI.dequeueCommands()
        assert ret.ok
        assert ret.data['spawn'] == []
        assert ret.data['remove'] == []
        assert ret.data['modify'] == []
        assert ret.data['direct_force'] == []
        assert ret.data['booster_force'] == []

        # Spawn two objects with id_1 and id_2.
        tmp = [(id_1, body_1), (id_2, body_1)]
        assert leoAPI.addCmdSpawn(tmp).ok

        # Verify that the spawn commands were added.
        ret = leoAPI.dequeueCommands()
        assert ret.ok
        assert ret.data['spawn'][0]['objID'] == id_1
        assert ret.data['spawn'][1]['objID'] == id_2
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

        # Modify state variable for body with id_1.
        newSV = {'imass': 10, 'position': [3, 4, 5]}
        assert leoAPI.addCmdModifyBodyState(id_1, newSV).ok
        ret = leoAPI.dequeueCommands()
        modify = ret.data['modify']
        assert ret.ok and len(modify) == 1
        assert modify[0]['objID'] == id_1
        assert modify[0]['rbs'] == newSV
        del newSV

        # Set the direct force and torque for id_2.
        force, torque = [1, 2, 3], [4, 5, 6]
        assert leoAPI.addCmdDirectForce(id_2, force, torque).ok
        ret = leoAPI.dequeueCommands()
        fat = ret.data['direct_force']
        assert ret.ok
        assert len(fat) == 1
        assert fat[0]['objID'] == id_2
        assert fat[0]['force'] == force
        assert fat[0]['torque'] == torque

        # Set the booster force and torque for id_1.
        force, torque = [1, 2, 3], [4, 5, 6]
        assert leoAPI.addCmdBoosterForce(id_1, force, torque).ok
        ret = leoAPI.dequeueCommands()
        fat = ret.data['booster_force']
        assert ret.ok
        assert len(fat) == 1
        assert fat[0]['objID'] == id_1
        assert fat[0]['force'] == force
        assert fat[0]['torque'] == torque

        # Remove an object.
        assert leoAPI.addCmdRemoveObject(id_1).ok
        ret = leoAPI.dequeueCommands()
        assert ret.ok and ret.data['remove'][0]['objID'] == id_1

        # Add commands for two objects (it is perfectly ok to add commands for
        # non-existing body IDs since this is just a command queue - Leonard
        # will skip commands for non-existing IDs automatically).
        force, torque = [7, 8, 9], [10, 11.5, 12.5]
        for objID in (id_1, id_2):
            assert leoAPI.addCmdSpawn([(objID, body_1)]).ok
            assert leoAPI.addCmdModifyBodyState(objID, body_2).ok
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

    def test_setRigidBody(self):
        """
        Set and retrieve object attributes like position, velocity,
        acceleration, and rotation.
        """
        # Instantiate a Leonard.
        leo = getLeonard()

        # Test constants.
        body_new = {
            'imass': 2,
            'scale': 3,
            'cshapes': {'csempty': getCSEmpty()},
            'position': (1, 2, 5),
            'velocityLin': (8, 9, 10.5),
            'velocityRot': (9, 10, 11.5),
            'rotation': (11, 12.5, 13, 13.5)
        }

        # Create a test body.
        id_1 = '0'
        body = getRigidBody(cshapes={'csempty': getCSEmpty()})

        # Add the object to the DB with ID=0.
        assert leoAPI.addCmdSpawn([(id_1, body)]).ok
        leo.processCommandsAndSync()

        # Modify the state vector for body with id_1.
        assert leoAPI.addCmdModifyBodyState(id_1, body_new).ok
        leo.processCommandsAndSync()

        # Query the body again and verify the changes are in effect.
        ret = leo.allBodies[id_1]
        assert ret.imass == body_new['imass']
        assert ret.scale == body_new['scale']
        assert np.array_equal(ret.position, body_new['position'])
        assert np.array_equal(ret.velocityLin, body_new['velocityLin'])
        assert np.array_equal(ret.velocityRot, body_new['velocityRot'])
        assert np.array_equal(ret.rotation, body_new['rotation'])

        # Query the AABB, update the collision shapes, and verify that the new
        # AABBs are in effect.
        assert leo.allAABBs[id_1] == {}

        # Modify the body state by adding a collision shape.
        body_new = {'cshapes': {'cssphere': getCSSphere(radius=1)}}
        assert body_new is not None
        assert leoAPI.addCmdModifyBodyState(id_1, body_new).ok
        leo.processCommandsAndSync()
        assert leo.allAABBs[id_1] == {'cssphere': [0, 0, 0, 1, 1, 1]}

        # Modify the body state by adding a collision shape.
        cs_a = getCSSphere(radius=1, pos=(1, 2, 3))
        cs_b = getCSSphere(radius=2, pos=(4, 5, 6))
        cshapes = {'1': cs_a, '2': getCSEmpty(), '3': cs_b}
        body_new = {'cshapes': cshapes}
        assert leoAPI.addCmdModifyBodyState(id_1, body_new).ok
        leo.processCommandsAndSync()
        correct = {'1': [1, 2, 3, 1, 1, 1], '3': [4, 5, 6, 2, 2, 2]}
        assert leo.allAABBs[id_1] == correct

    def test_get_set_forceandtorque(self):
        """
        Query and update the force- and torque vectors for an object.
        """
        # Reset the SV database and instantiate a Leonard.
        leo = getLeonard()

        # Create two object IDs for this test.
        id_1, id_2 = '0', '1'

        # Create two objects and serialise them.
        body_1 = getRigidBody(position=[0, 0, 0])
        body_2 = getRigidBody(position=[10, 10, 10])

        # Add the two objects to the simulation.
        tmp = [(id_1, body_1), (id_2, body_2)]
        assert leoAPI.addCmdSpawn(tmp).ok
        leo.processCommandsAndSync()

        # Update the direct force and torque of the second object only.
        force, torque = [1, 2, 3], [4, 5, 6]
        assert leoAPI.addCmdDirectForce(id_2, force, torque)
        leo.processCommandsAndSync()

        # Only the force an torque of the second object must have changed.
        assert np.array_equal(leo.allForces[id_1].forceDirect, [0, 0, 0])
        assert np.array_equal(leo.allForces[id_1].torqueDirect, [0, 0, 0])
        assert np.array_equal(leo.allForces[id_2].forceDirect, force)
        assert np.array_equal(leo.allForces[id_2].torqueDirect, torque)

        # Update the booster force and torque of the first object only.
        force, torque = [1, 2, 3], [4, 5, 6]
        assert leoAPI.addCmdBoosterForce(id_2, force, torque)
        leo.processCommandsAndSync()

        # Only the booster- force an torque of the second object must have
        # changed.
        assert np.array_equal(leo.allForces[id_1].forceDirect, [0, 0, 0])
        assert np.array_equal(leo.allForces[id_1].torqueDirect, [0, 0, 0])
        assert np.array_equal(leo.allForces[id_2].forceDirect, force)
        assert np.array_equal(leo.allForces[id_2].torqueDirect, torque)

    def test_RigidBodyData_tuple(self):
        """
        Test the ``RigidBodyData`` class, most notably the __eq__ method.
        """
        # Compare two identical objects.
        sv1 = getRigidBody()
        sv2 = getRigidBody()
        assert sv1 == sv2

        # Compare two different objects.
        sv1 = getRigidBody()
        sv2 = getRigidBody(position=[1, 2, 3])
        assert sv1 != sv2

    def test_set_get_AABB(self):
        """
        Create a new object with an AABB and query it back again.
        """
        # Reset the SV database and instantiate a Leonard.
        leo = getLeonard()

        # Create two IDs and body instances for this test.
        id_1, id_2 = '0', '1'
        aabb_2 = {'cssphere': [0, 0, 0, 1, 1, 1]}
        aabb_3 = {'cssphere': [0, 0, 0, 2, 2, 2]}
        body_a = getRigidBody(cshapes={'cssphere': getCSSphere(radius=1)})
        body_b = getRigidBody(cshapes={'cssphere': getCSSphere(radius=2)})

        # Add two new objects to the DB.
        tmp = [(id_1, body_a), (id_2, body_b)]
        assert leoAPI.addCmdSpawn(tmp).ok
        leo.processCommandsAndSync()

        # Verify the two AABBs
        assert leo.allAABBs[id_1] == aabb_2
        assert leo.allAABBs[id_2] == aabb_3

    def test_compute_AABB(self):
        """
        Create some collision shapes and verify that 'computeAABBs' returns the
        correct results.
        """
        # Convenience.
        computeAABBs = azrael.leo_api.computeAABBs

        # Empty set of Collision shapes.
        assert computeAABBs({}) == (True, None, {})

        # Cubes with different side lengths. The algorithm must always pick
        # the largest side length times sqrt(3)
        for size in (0, 0.5, 1, 2):
            # The three side lengths used for the cubes.
            s1, s2, s3 = size, 2 * size, 3 * size

            # The AABB dimensions must always be the largest side lengths time
            # sqrt(3) to accommodate all rotations. However, Azreal adds some
            # slack and uses sqrt(3.1).
            v = s3 * np.sqrt(3.1)
            correct = (1, 2, 3, v, v, v)
            pos = correct[:3]

            cs = getCSBox(dim=(s1, s2, s3), pos=pos)
            assert computeAABBs({'1': cs}) == (True, None, {'1': correct})

            cs = getCSBox(dim=(s2, s3, s1), pos=pos)
            assert computeAABBs({'2': cs}) == (True, None, {'2': correct})

            cs = getCSBox(dim=(s3, s1, s2), pos=pos)
            assert computeAABBs({'3': cs}) == (True, None, {'3': correct})

        # The AABB for a sphere must always exactly bound the sphere.
        for radius in (0, 0.5, 1, 2):
            correct = (0, 0, 0, radius, radius, radius)
            cs = getCSSphere(radius=radius)
            assert computeAABBs({'': cs}) == (True, None, {'': correct})

        # Sphere at origin but with a rotation: must remain at origin.
        pos, rot = (0, 0, 0), (np.sqrt(2), 0, 0, np.sqrt(2))
        correct = {'': (0, 0, 0, 1, 1, 1)}
        cs = getCSSphere(radius=1, pos=pos, rot=rot)
        assert computeAABBs({'': cs}) == (True, None, correct)

        # Sphere at y=1 and rotated 180degrees around x-axis. This must result
        # in a sphere at y=-1.
        pos, rot = (0, 1, 0), (1, 0, 0, 0)
        correct = {'': (0, -1, 0, 1, 1, 1)}
        cs = getCSSphere(radius=1, pos=pos, rot=rot)
        assert computeAABBs({'': cs}) == (True, None, correct)

        # Sphere at y=1 and rotated 90degrees around x-axis. This must move the
        # sphere onto the z-axis, ie to position (x, y, z) = (0, 0, 1). Due to
        # roundoff errors it will be necessary to test with np.allclose instead
        # for exact equality.
        pos = (0, 1, 0)
        rot = (1 / np.sqrt(2), 0, 0, 1 / np.sqrt(2))
        correct = {'': (0, 0, 1, 1, 1, 1)}
        cs = getCSSphere(radius=1, pos=pos, rot=rot)
        ret = computeAABBs({'': cs})
        assert ret.ok
        assert np.allclose(ret.data[''], correct[''])

        # Use an empty shape. This must not return any AABB.
        cs = getCSEmpty()
        assert computeAABBs({'': cs}) == (True, None, {})

        # Pass in multiple collision shapes, namely [box, empty, sphere]. This
        # must return 2 collision shapes because the empty one is skipped.
        cs = {'1': getCSSphere(), '2': getCSEmpty(), '3': getCSBox()}
        correct = {
            '1': (0, 0, 0, 1, 1, 1),
            '3': (0, 0, 0, np.sqrt(3.1), np.sqrt(3.1), np.sqrt(3.1))
        }
        assert computeAABBs(cs) == (True, None, correct)

        # Pass in invalid arguments. This must return with an error.
        assert not computeAABBs({'x': (1, 2)}).ok

    def test_computeAABBS_StaticPlane(self):
        """
        Static planes are permissible collision shapes for a body if
        that is indeed the only collision shape for that body.
        Conversely, it is not allowed for a body to have multiple
        collision shapes if one of them is a StaticPlane.
        """
        computeAABBs = azrael.leo_api.computeAABBs

        # One or more spheres are permissible.
        cs = {'cssphere': getCSSphere()}
        assert computeAABBs(cs).ok

        # A single plane is permissible.
        cs = {'csplane': getCSPlane()}
        assert computeAABBs(cs).ok

        # A plane in conjunction with any other object is not allowed...
        cs = {'csplane': getCSPlane(), 'cssphere': getCSSphere()}
        assert not computeAABBs(cs).ok

        # not even with another plane.
        cs = {'csplane': getCSPlane(), 'cssphere': getCSSphere()}
        assert not computeAABBs(cs).ok

        # The position and rotation of a plane is defined via the normal
        # vector and its offset. The position/rotation fields in the
        # CollShapeMeta structure are thus redundant and *must* be set to
        # defaults to avoid unintended side effects.
        cs = {'csplane': getCSPlane(pos=(0, 1, 2))}
        assert not computeAABBs(cs).ok

        cs = {'csplane': getCSPlane(rot=(1, 0, 0, 0))}
        assert not computeAABBs(cs).ok
