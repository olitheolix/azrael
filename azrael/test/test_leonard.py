import pytest
import subprocess
import azrael.igor
import azrael.leonard
import azrael.database
import azrael.vectorgrid

import numpy as np
import unittest.mock as mock
import azrael.leo_api as leoAPI
import azrael.rb_state as rb_state

from IPython import embed as ipshell
from azrael.test.test_bullet_api import isEqualBD
from azrael.types import CollShapeBox, CollShapeSphere, RetVal
from azrael.types import CollShapeMeta, CollShapeEmpty
from azrael.types import ConstraintMeta, ConstraintP2P
from azrael.test.test_bullet_api import getCSEmpty, getCSBox, getCSSphere


# List all available engines. This simplifies the parameterisation of those
# tests that must pass for all engines.
allEngines = [
    azrael.leonard.LeonardBase,
    azrael.leonard.LeonardBullet,
    azrael.leonard.LeonardSweeping,
    azrael.leonard.LeonardDistributedZeroMQ]


def killAzrael():
    subprocess.call(['pkill', 'Azreal:'])

    # Delete all grids used in this test.
    assert azrael.vectorgrid.deleteAllGrids().ok

    azrael.database.init()


def getLeonard(LeonardCls=azrael.leonard.LeonardBase):
    """
    Return a ``LeonardCls`` instance.

    This is a convenience function to reduce code duplication in tests.

    :param cls LeonardCls: Leonard class to instantiate.
    """
    # Return a Leonard instance.
    leo = LeonardCls()
    leo.setup()
    return leo


class TestLeonardAllEngines:
    @classmethod
    def setup_class(cls):
        assert azrael.vectorgrid.deleteAllGrids().ok
        cls.igor = azrael.igor.Igor()

    @classmethod
    def teardown_class(cls):
        assert azrael.vectorgrid.deleteAllGrids().ok

    def setup_method(self, method):
        assert azrael.vectorgrid.deleteAllGrids().ok
        self.igor.reset()

    def teardown_method(self, method):
        pass

    @pytest.mark.parametrize('clsLeonard', allEngines)
    def test_getGridForces(self, clsLeonard):
        """
        Spawn an object, specify its State Variables explicitly, and verify the
        change propagated through Azrael.
        """
        # Convenience.
        vg = azrael.vectorgrid

        # Create pristince force grid.
        assert vg.defineGrid(name='force', vecDim=3, granularity=1).ok

        # Get a Leonard instance.
        leo = getLeonard(clsLeonard)

        # Grid parameters.
        Nx, Ny, Nz = 2, 3, 4
        ofs = np.array([-1.1, -2.7, 3.5], np.float64)
        force = np.zeros((Nx, Ny, Nz, 3))

        # Compute grid values.
        idPos, idVal = {}, {}
        val, objID = 0, 0
        for x in range(Nx):
            for y in range(Ny):
                for z in range(Nz):
                    # Assign integer values (allows for equality comparisions
                    # later on without having to worry about rounding effects).
                    force[x, y, z] = [val, val + 1, val + 2]

                    # Build the input dictionary for ``getGridForces``.
                    idPos[objID] = np.array(
                        [x + ofs[0], y + ofs[1], z + ofs[2]])

                    # Keep track of the value assigned to this position.
                    idVal[objID] = force[x, y, z]

                    # Update the counters.
                    val += 3
                    objID += 1

        # Set the grid values with a region operator.
        ret = vg.setRegion('force', ofs, force)

        # Query the grid values at the positions specified in idPos.
        ret = leo.getGridForces(idPos)
        assert ret.ok
        gridForces = ret.data

        # Verify the value at every position we used in this test.
        for objID in idPos:
            # Convenience.
            val_direct = idVal[objID]
            val_gridforce = gridForces[objID]

            # Compare: direct <--> getGridForces.
            assert np.array_equal(val_direct, val_gridforce)

    @pytest.mark.parametrize('clsLeonard', allEngines)
    def test_setBodyState_basic(self, clsLeonard):
        """
        Spawn an object, specify its State Variables explicitly, and verify the
        change propagated through Azrael.
        """
        # Get a Leonard instance.
        leo = getLeonard(clsLeonard)

        # Parameters and constants for this test.
        id_0, id_1 = 0, 1
        aabb = [(0, 0, 0, 1, 1, 1)]
        sv = rb_state.RigidBodyState()
        templateID = '_templateSphere'.encode('utf8')

        # State Vector.
        p = np.array([1, 2, 5])
        vl = np.array([8, 9, 10.5])
        vr = vl + 1
        data = rb_state.RigidBodyStateOverride(
            position=p, velocityLin=vl, velocityRot=vr)
        del p, vl, vr

        # Spawn a new object. It must have ID=1.
        assert leoAPI.addCmdSpawn([(id_1, sv, aabb)]).ok

        # Update the object's State Vector.
        assert leoAPI.addCmdModifyBodyState(id_1, data).ok

        # Sync the commands to Leonard.
        leo.processCommandsAndSync()

        # Verify that the attributes were correctly updated.
        ret = leoAPI.getBodyStates([id_1])
        assert (ret.ok, len(ret.data)) == (True, 1)
        sv = ret.data[id_1]
        assert np.array_equal(sv.position, data.position)
        assert np.array_equal(sv.velocityLin, data.velocityLin)
        assert np.array_equal(sv.velocityRot, data.velocityRot)

    @pytest.mark.parametrize('clsLeonard', allEngines)
    def test_setBodyState_advanced(self, clsLeonard):
        """
        Similar to test_setBodyState_basic but modify the collision shape
        information as well, namely mass and the collision shape itself.
        """
        # Get a Leonard instance.
        leo = getLeonard(clsLeonard)

        # Parameters and constants for this test.
        cshape_box = [getCSBox('csbox')]
        cshape_sphere = [getCSSphere('cssphere')]
        sv = rb_state.RigidBodyState(imass=2, scale=3, cshapes=cshape_sphere)
        templateID = '_templateSphere'.encode('utf8')

        # Spawn an object.
        objID = 1
        aabb = [(0, 0, 0, 1, 1, 1)]
        assert leoAPI.addCmdSpawn([(objID, sv, aabb)]).ok

        # Verify the SV data.
        leo.processCommandsAndSync()
        ret = leoAPI.getBodyStates([objID])
        assert ret.ok
        assert ret.data[objID].imass == 2
        assert ret.data[objID].scale == 3
        tmp = CollShapeMeta(*ret.data[objID].cshapes[0]).aid
        assert tmp == cshape_sphere[0].aid
        del tmp

        # Update the object's SV data.
        sv_new = rb_state.RigidBodyStateOverride(
            imass=4, scale=5, cshapes=cshape_box)
        assert leoAPI.addCmdModifyBodyState(objID, sv_new).ok

        # Verify the SV data.
        leo.processCommandsAndSync()
        ret = leoAPI.getBodyStates([objID])
        assert (ret.ok, len(ret.data)) == (True, 1)
        sv = ret.data[objID]
        assert (sv.imass == 4) and (sv.scale == 5)
        tmp = CollShapeMeta(*ret.data[objID].cshapes[0]).aid
        assert tmp == cshape_box[0].aid
        del tmp

    @pytest.mark.parametrize('clsLeonard', allEngines)
    def test_move_single_object(self, clsLeonard):
        """
        Create a single object with non-zero initial speed and ensure
        Leonard moves it accordingly.
        """
        # Get a Leonard instance.
        leonard = getLeonard(clsLeonard)

        # Constants and parameters for this test.
        id_0 = 0
        aabb = [(0, 0, 0, 1, 1, 1)]
        sv = rb_state.RigidBodyState()

        # Spawn an object.
        assert leoAPI.addCmdSpawn([(id_0, sv, aabb)]).ok

        # Advance the simulation by 1s and verify that nothing has moved.
        leonard.step(1.0, 60)
        ret = leoAPI.getBodyStates([id_0])
        assert ret.ok
        assert np.array_equal(ret.data[id_0].position, [0, 0, 0])

        # Give the object a velocity.
        sv = rb_state.RigidBodyStateOverride(velocityLin=np.array([1, 0, 0]))
        assert leoAPI.addCmdModifyBodyState(id_0, sv).ok

        # Advance the simulation by another second and verify the objects have
        # moved accordingly.
        leonard.step(1.0, 60)
        ret = leoAPI.getBodyStates([id_0])
        assert ret.ok
        assert 0.9 <= ret.data[id_0].position[0] < 1.1
        assert ret.data[id_0].position[1] == ret.data[id_0].position[2] == 0

    @pytest.mark.parametrize('clsLeonard', allEngines)
    def test_move_two_objects_no_collision(self, clsLeonard):
        """
        Same as previous test but with two objects.
        """
        # Get a Leonard instance.
        leonard = getLeonard(clsLeonard)

        # Constants and parameters for this test.
        id_0, id_1 = 0, 1
        aabb = [(0, 0, 0, 1, 1, 1)]
        MS = rb_state.RigidBodyState
        sv_0 = MS(position=[0, 0, 0], velocityLin=[1, 0, 0])
        sv_1 = MS(position=[0, 10, 0], velocityLin=[0, -1, 0])

        # Create two objects.
        tmp = [(id_0, sv_0, aabb), (id_1, sv_1, aabb)]
        assert leoAPI.addCmdSpawn(tmp).ok

        # Advance the simulation by 1s and query the states of both objects.
        leonard.step(1.0, 60)
        ret = leoAPI.getBodyStates([id_0])
        assert ret.ok
        pos_0 = ret.data[id_0].position
        ret = leoAPI.getBodyStates([id_1])
        assert ret.ok
        pos_1 = ret.data[id_1].position

        # The objects must have moved according to their initial velocity.
        assert pos_0[1] == pos_0[2] == 0
        assert pos_1[0] == pos_1[2] == 0
        assert 0.9 <= pos_0[0] <= 1.1
        assert 8.9 <= pos_1[1] <= 9.1

    @pytest.mark.parametrize('clsLeonard', allEngines)
    def test_force_grid(self, clsLeonard):
        """
        Create a force grid and ensure Leonard applies its values to the
        center of the mass.
        """
        # Convenience.
        vg = azrael.vectorgrid

        # Get a Leonard instance.
        leonard = getLeonard(clsLeonard)

        # Constants and parameters for this test.
        id_0 = 0
        aabb = [(0, 0, 0, 1, 1, 1)]
        sv = rb_state.RigidBodyState()

        # Spawn one object.
        assert leoAPI.addCmdSpawn([(id_0, sv, aabb)]).ok

        # Advance the simulation by 1s and verify that nothing has moved.
        leonard.step(1.0, 60)
        ret = leoAPI.getBodyStates([id_0])
        assert ret.ok
        assert np.array_equal(ret.data[id_0].position, [0, 0, 0])

        # Define a force grid.
        assert vg.defineGrid(name='force', vecDim=3, granularity=1).ok

        # Specify a non-zero value somewhere away from the object. This means
        # the object must still not move.
        pos = np.array([1, 2, 3], np.float64)
        value = np.ones(3, np.float64)
        assert vg.setValues('force', [(pos, value)]).ok

        # Step the simulation and verify the object remained where it was.
        leonard.step(1.0, 60)
        ret = leoAPI.getBodyStates([id_0])
        assert ret.ok
        assert np.array_equal(ret.data[id_0].position, [0, 0, 0])

        # Specify a grid value of 1 Newton in x-direction.
        pos = np.array([0, 0, 0], np.float64)
        value = np.array([1, 0, 0], np.float64)
        assert vg.setValues('force', [(pos, value)]).ok

        # Step the simulation and verify the object moved accordingly.
        leonard.step(1.0, 60)

        ret = leoAPI.getBodyStates([id_0])
        assert ret.ok
        assert 0.4 <= ret.data[id_0].position[0] < 0.6
        assert ret.data[id_0].position[1] == ret.data[id_0].position[2] == 0


class TestLeonardOther:
    @classmethod
    def setup_class(cls):
        cls.igor = azrael.igor.Igor()

    @classmethod
    def teardown_class(cls):
        cls.igor.reset()

    def setup_method(self, method):
        assert azrael.vectorgrid.deleteAllGrids().ok
        azrael.database.init()
        self.igor.reset()

    def teardown_method(self, method):
        pass

    def test_worker_respawn(self):
        """
        Ensure the objects move correctly even though the Workers will restart
        themselves after every step.

        The test code is similar to ``test_move_two_objects_no_collision``.
        """
        # Instantiate Leonard.
        leonard = azrael.leonard.LeonardDistributedZeroMQ()
        leonard.workerStepsUntilQuit = (1, 10)
        leonard.setup()

        # Define a force grid (not used in this test but prevent a plethora
        # of meaningleass warning messages).
        vg = azrael.vectorgrid
        assert vg.defineGrid(name='force', vecDim=3, granularity=1).ok

        # Constants and parameters for this test.
        aabb = [(0, 0, 0, 1, 1, 1)]
        id_0, id_1 = 0, 1
        cshapes = [getCSSphere(radius=1)]

        # Two State Vectors for this test.
        sv_0 = rb_state.RigidBodyState(
            position=[0, 0, 0], velocityLin=[1, 0, 0], cshapes=cshapes)
        sv_1 = rb_state.RigidBodyState(
            position=[0, 10, 0], velocityLin=[0, -1, 0], cshapes=cshapes)

        # Create two objects.
        tmp = [(id_0, sv_0, aabb), (id_1, sv_1, aabb)]
        assert leoAPI.addCmdSpawn(tmp).ok

        # Advance the simulation by 1s, but use many small time steps. This
        # ensures that the Workers will restart themselves frequently.
        for ii in range(60):
            leonard.step(1.0 / 60, 1)

        # Query the states of both objects.
        ret = leoAPI.getBodyStates([id_0])
        assert ret.ok
        pos_0 = ret.data[id_0].position
        ret = leoAPI.getBodyStates([id_1])
        assert ret.ok
        pos_1 = ret.data[id_1].position

        # The objects must have moved according to their initial velocity.
        assert pos_0[1] == pos_0[2] == 0
        assert pos_1[0] == pos_1[2] == 0
        assert 0.9 <= pos_0[0] <= 1.1
        assert 8.9 <= pos_1[1] <= 9.1

    def test_createWorkPackages(self):
        """
        Create a Work Package and verify its content.
        """
        # Get a Leonard instance.
        leo = getLeonard(azrael.leonard.LeonardDistributedZeroMQ)

        # Constants.
        id_1, id_2 = 1, 2
        dt, maxsteps = 2, 3
        aabb = [(0, 0, 0, 1, 1, 1)]

        # Invalid call: list of IDs must not be empty.
        assert not leo.createWorkPackage([], dt, maxsteps).ok

        # Invalid call: Leonard has no object with ID 10.
        assert not leo.createWorkPackage([10], dt, maxsteps).ok

        # Test data.
        sv_1 = rb_state.RigidBodyState(imass=1)
        sv_2 = rb_state.RigidBodyState(imass=2)

        # Add two new objects to Leonard.
        tmp = [(id_1, sv_1, aabb), (id_2, sv_2, aabb)]
        assert leoAPI.addCmdSpawn(tmp).ok
        leo.processCommandsAndSync()

        # Create a Work Package with two objects. The WPID must be 1.
        ret = leo.createWorkPackage([id_1], dt, maxsteps)
        ret_wpid, ret_wpdata = ret.data['wpid'], ret.data['wpdata']
        assert (ret.ok, ret_wpid, len(ret_wpdata)) == (True, 0, 1)

        # Create a second WP: it must have WPID=2 and contain two objects.
        ret = leo.createWorkPackage([id_1, id_2], dt, maxsteps)
        ret_wpid, ret_wpdata = ret.data['wpid'], ret.data['wpdata']
        assert (ret.ok, ret_wpid, len(ret_wpdata)) == (True, 1, 2)

        # Check the WP content.
        WPData = azrael.leonard.WPData
        WPMeta = azrael.leonard.WPMeta
        data = [WPData(*_) for _ in ret.data['wpdata']]
        meta = WPMeta(*ret.data['wpmeta'])
        assert (meta.dt, meta.maxsteps) == (dt, maxsteps)
        assert (ret.ok, len(data)) == (True, 2)
        assert (data[0].aid, data[1].aid) == (id_1, id_2)
        assert isEqualBD(data[0].sv, sv_1)
        assert isEqualBD(data[1].sv, sv_2)
        assert np.array_equal(data[0].force, [0, 0, 0])
        assert np.array_equal(data[1].force, [0, 0, 0])

    def test_updateLocalCache(self):
        """
        Update the local object cache in Leonard based on a Work Package.
        """
        # Get a Leonard instance.
        leo = getLeonard(azrael.leonard.LeonardDistributedZeroMQ)

        # Convenience.
        WPData = azrael.leonard.WPData
        data_1 = rb_state.RigidBodyState(imass=1)
        data_2 = rb_state.RigidBodyState(imass=2)
        id_1, id_2 = 1, 2
        aabb = [(0, 0, 0, 1, 1, 1)]

        # Spawn new objects.
        tmp = [(id_1, data_1, aabb), (id_2, data_2, aabb)]
        assert leoAPI.addCmdSpawn(tmp).ok
        leo.processCommandsAndSync()

        # Create a Work Package and verify its content.
        ret = leo.createWorkPackage([id_1, id_2], dt=3, maxsteps=4)

        # Create a new State Vector to replace the old one.
        data_3 = rb_state.RigidBodyState(imass=4, position=[1, 2, 3])
        newWP = [(id_1, data_3)]

        # Check the State Vector for objID=id_1 before and after the update.
        assert isEqualBD(leo.allObjects[id_1], data_1)
        leo.updateLocalCache(newWP)
        assert isEqualBD(leo.allObjects[id_1], data_3)

    def test_processCommandQueue(self):
        """
        Create commands to spawn-, delete, and modify objects or their booster
        values. Then verify that ``processCommandQueue`` corrently updates
        Leonard's object cache.
        """
        # Get a Leonard instance.
        leo = getLeonard(azrael.leonard.LeonardDistributedZeroMQ)

        # Convenience.
        sv_1 = rb_state.RigidBodyState(imass=1)
        sv_2 = rb_state.RigidBodyState(imass=2)
        id_1, id_2 = 1, 2
        aabb = [(0, 0, 0, 1, 1, 1)]

        # Cache must be empty.
        assert len(leo.allObjects) == len(leo.allForces) == 0

        # Spawn two objects.
        tmp = [(id_1, sv_1, aabb), (id_2, sv_2, aabb)]
        assert leoAPI.addCmdSpawn(tmp).ok
        leo.processCommandsAndSync()

        # Verify the local cache (forces and torques must default to zero).
        assert isEqualBD(leo.allObjects[id_1], sv_1)
        assert isEqualBD(leo.allObjects[id_2], sv_2)
        tmp = leo.allForces[id_1]
        assert tmp.forceDirect == tmp.torqueDirect == [0, 0, 0]
        assert tmp.forceBoost == tmp.torqueBoost == [0, 0, 0]
        del tmp

        # Remove first object.
        assert leoAPI.addCmdRemoveObject(id_1).ok
        leo.processCommandsAndSync()
        assert id_1 not in leo.allObjects
        assert id_1 not in leo.allForces

        # Change the State Vector of id_2.
        pos = [10, 11.5, 12]
        sv_3 = rb_state.RigidBodyStateOverride(position=pos)
        assert leo.allObjects[id_2].position == [0, 0, 0]
        assert leoAPI.addCmdModifyBodyState(id_2, sv_3).ok
        leo.processCommandsAndSync()
        assert leo.allObjects[id_2].position == pos

        # Apply a direct force and torque to id_2.
        force, torque = [1, 2, 3], [4, 5, 6]
        assert leoAPI.addCmdDirectForce(id_2, force, torque).ok
        leo.processCommandsAndSync()
        assert leo.allForces[id_2].forceDirect == force
        assert leo.allForces[id_2].torqueDirect == torque

        # Specify a new force- and torque value due to booster activity.
        force, torque = [1, 2, 3], [4, 5, 6]
        assert leoAPI.addCmdBoosterForce(id_2, force, torque).ok
        leo.processCommandsAndSync()
        assert leo.allForces[id_2].forceBoost == force
        assert leo.allForces[id_2].torqueBoost == torque

    def test_maintain_forces(self):
        """
        Leonard must not reset any forces from one iteration to the next
        (used to be the case at some point and thus requires a dedicated
        test now).
        """
        # Get a Leonard instance.
        leo = getLeonard(azrael.leonard.LeonardDistributedZeroMQ)

        # Convenience.
        sv = rb_state.RigidBodyState(imass=1)
        objID = 1
        aabb = [(0, 0, 0, 1, 1, 1)]

        # Spawn object.
        assert leoAPI.addCmdSpawn([(objID, sv, aabb)]).ok
        leo.processCommandsAndSync()

        # Initial force and torque must be zero.
        tmp = leo.allForces[objID]
        assert tmp.forceDirect == tmp.torqueDirect == [0, 0, 0]
        assert tmp.forceBoost == tmp.torqueBoost == [0, 0, 0]
        del tmp

        # Change the direct force and verify that Leonard does not reset it.
        assert leoAPI.addCmdDirectForce(objID, [1, 2, 3], [4, 5, 6]).ok
        for ii in range(10):
            leo.processCommandsAndSync()
            tmp = leo.allForces[objID]
            assert tmp.forceDirect == [1, 2, 3]
            assert tmp.torqueDirect == [4, 5, 6]
            assert tmp.forceBoost == [0, 0, 0]
            assert tmp.torqueBoost == [0, 0, 0]

        # Change the booster force and verify that Leonard does not change
        # it (or the direct force specified earlier)
        assert leoAPI.addCmdBoosterForce(objID, [-1, -2, -3], [-4, -5, -6]).ok
        for ii in range(10):
            leo.processCommandsAndSync()
            tmp = leo.allForces[objID]
            assert tmp.forceDirect == [1, 2, 3]
            assert tmp.torqueDirect == [4, 5, 6]
            assert tmp.forceBoost == [-1, -2, -3]
            assert tmp.torqueBoost == [-4, -5, -6]

        # Change the direct forces again.
        assert leoAPI.addCmdDirectForce(objID, [3, 2, 1], [6, 5, 4]).ok
        for ii in range(10):
            leo.processCommandsAndSync()
            tmp = leo.allForces[objID]
            assert tmp.forceDirect == [3, 2, 1]
            assert tmp.torqueDirect == [6, 5, 4]
            assert tmp.forceBoost == [-1, -2, -3]
            assert tmp.torqueBoost == [-4, -5, -6]

        # Change the booster forces again.
        assert leoAPI.addCmdBoosterForce(objID, [-3, -2, -1], [-6, -5, -4]).ok
        for ii in range(10):
            leo.processCommandsAndSync()
            tmp = leo.allForces[objID]
            assert tmp.forceDirect == [3, 2, 1]
            assert tmp.torqueDirect == [6, 5, 4]
            assert tmp.forceBoost == [-3, -2, -1]
            assert tmp.torqueBoost == [-6, -5, -4]

    def test_totalForceAndTorque_no_rotation(self):
        """
        Verify that 'totalForceAndTorque' correctly adds up the direct-
        and booster forces for an object that is in neutral position (ie
        without rotation).
        """
        # Get a Leonard instance.
        leo = getLeonard(azrael.leonard.LeonardDistributedZeroMQ)

        # Spawn one object.
        orient = np.array([0, 0, 0, 1])
        sv = rb_state.RigidBodyState(imass=1, orientation=orient)
        objID = 1
        aabb = [(0, 0, 0, 1, 1, 1)]
        assert leoAPI.addCmdSpawn([(objID, sv, aabb)]).ok
        leo.processCommandsAndSync()
        del sv, aabb

        # Initial force and torque must be zero.
        assert leo.totalForceAndTorque(objID) == ([0, 0, 0], [0, 0, 0])

        # Change the direct force.
        assert leoAPI.addCmdDirectForce(objID, [1, 2, 3], [4, 5, 6]).ok
        leo.processCommandsAndSync()
        assert leo.totalForceAndTorque(objID) == ([1, 2, 3], [4, 5, 6])

        # Change the direct force.
        assert leoAPI.addCmdDirectForce(objID, [1, 2, 30], [4, 5, 60]).ok
        leo.processCommandsAndSync()
        assert leo.totalForceAndTorque(objID) == ([1, 2, 30], [4, 5, 60])

        # Reset the direct force and change the booster force.
        assert leoAPI.addCmdDirectForce(objID, [0, 0, 0], [0, 0, 0]).ok
        assert leoAPI.addCmdBoosterForce(objID, [-1, -2, -3], [-4, -5, -6]).ok
        leo.processCommandsAndSync()
        assert leo.totalForceAndTorque(objID) == ([-1, -2, -3], [-4, -5, -6])

        # Direct- and booste forces must perfectly balance each other.
        assert leoAPI.addCmdDirectForce(objID, [1, 2, 3], [4, 5, 6]).ok
        assert leoAPI.addCmdBoosterForce(objID, [-1, -2, -3], [-4, -5, -6]).ok
        leo.processCommandsAndSync()
        assert leo.totalForceAndTorque(objID) == ([0, 0, 0], [0, 0, 0])

    def test_totalForceAndTorque_with_rotation(self):
        """
        Similar to the previou 'test_totalForceAndTorque_no_rotation'
        but this time the object does not have a neutral rotation in
        world coordinates. This must have no effect on the direct force
        values, but the booster forces must be re-oriented accordingly.
        """
        # Get a Leonard instance.
        leo = getLeonard(azrael.leonard.LeonardDistributedZeroMQ)

        # Spawn one object rotated 180 degress around x-axis.
        orient = np.array([1, 0, 0, 0])
        sv = rb_state.RigidBodyState(imass=1, orientation=orient)
        objID = 1
        aabb = [(0, 0, 0, 1, 1, 1)]
        assert leoAPI.addCmdSpawn([(objID, sv, aabb)]).ok
        leo.processCommandsAndSync()
        del sv, aabb

        # Initial force and torque must be zero.
        assert leo.totalForceAndTorque(objID) == ([0, 0, 0], [0, 0, 0])

        # Add booster force in z-direction.
        assert leoAPI.addCmdBoosterForce(objID, [1, 2, 3], [-1, -2, -3]).ok
        leo.processCommandsAndSync()

        # The net forces in must have their signs flipped in the y/z
        # directions, and remain unchanged for x since the object itself is
        # rotated 180 degrees around the x-axis.
        assert leo.totalForceAndTorque(objID) == ([1, -2, -3], [-1, 2, 3])

        # The object's rotation must not effect the direct force and torque.
        assert leoAPI.addCmdBoosterForce(objID, [0, 0, 0], [0, 0, 0]).ok
        assert leoAPI.addCmdDirectForce(objID, [1, 2, 3], [4, 5, 6]).ok
        leo.processCommandsAndSync()
        assert leo.totalForceAndTorque(objID) == ([1, 2, 3], [4, 5, 6])

    def test_mergeConstraintSets(self):
        """
        Create a few disjoint sets, specify some constraints, and verify that
        they are merged correctly.
        """
        def _verify(_coll_sets, _correct_answer):
            # Fetch all unique object pairs connected by a constraint.
            assert self.igor.updateLocalCache().ok
            ret = self.igor.uniquePairs()
            assert ret.ok

            # Merge all the sets `_coll_sets` that are connected by at least
            # one constraint.
            ret = azrael.leonard.mergeConstraintSets(ret.data, _coll_sets)
            assert ret.ok
            computed = ret.data

            # Compare the computed- with the expected output.
            computed = [sorted(tuple(_)) for _ in computed]
            correct = [sorted(tuple(_)) for _ in _correct_answer]
            assert sorted(computed) == sorted(correct)

        # Convenience.
        igor = self.igor
        mergeConstraintSets = azrael.leonard.mergeConstraintSets

        # Empty set.
        self.igor.reset()
        assert self.igor.updateLocalCache().ok
        ret = self.igor.uniquePairs()
        assert ret.ok
        assert mergeConstraintSets(ret.data, []) == (True, None, [])
        _verify([], [])

        # Set with only one subset.
        self.igor.reset()
        assert self.igor.updateLocalCache().ok
        ret = self.igor.uniquePairs()
        assert ret.ok
        assert mergeConstraintSets(ret.data, [[1]]) == (True, None, [[1]])
        tmp = [[1, 2, 3]]
        assert mergeConstraintSets(ret.data, tmp) == (True, None, tmp)
        del tmp

        # Two disjoint sets.
        p2p = ConstraintP2P((0, 0, 0), (0, 0, 0))
        self.igor.reset()
        s = [[1], [2]]
        _verify(s, s)
        assert igor.addConstraints([ConstraintMeta('p2p', '', 1, 2, p2p)]).ok
        _verify(s, [[1, 2]])
        self.igor.reset()
        _verify(s, s)

        # Two disjoint sets but the constraint does not link them.
        self.igor.reset()
        s = [[1], [2]]
        _verify(s, s)
        assert igor.addConstraints([ConstraintMeta('p2p', '', 1, 3, p2p)]).ok
        _verify(s, s)

        # Three disjoint sets and the constraint links two of them.
        self.igor.reset()
        s = [[1, 2, 3], [4, 5], [6]]
        _verify(s, s)
        assert igor.addConstraints([ConstraintMeta('p2p', '', 1, 6, p2p)]).ok
        _verify(s, [[1, 2, 3, 6], [4, 5]])

        # Three disjoint sets and two constraint link both of them.
        self.igor.reset()
        s = [[1, 2, 3], [4, 5], [6]]
        _verify(s, s)
        assert igor.addConstraints([ConstraintMeta('p2p', '', 1, 6, p2p)]).ok
        assert igor.addConstraints([ConstraintMeta('p2p', '', 3, 4, p2p)]).ok
        _verify(s, [[1, 2, 3, 6, 4, 5]])

    @pytest.mark.parametrize('clsLeonard', [
        azrael.leonard.LeonardBullet,
        azrael.leonard.LeonardSweeping,
        azrael.leonard.LeonardDistributedZeroMQ])
    def test_constraint_p2p(self, clsLeonard):
        """
        Link two bodies together with a Point2Point constraint and verify that
        they move together.
        """
        # Get a Leonard instance.
        leo = getLeonard(clsLeonard)

        # Convenience.
        id_a, id_b = 1, 2
        aabb = [(0, 0, 0, 1, 1, 1)]
        pos_a, pos_b = (-2, 0, 0), (2, 0, 0)
        cs = CollShapeMeta(
            'sphere', '', (0, 0, 0), (0, 0, 0, 1), CollShapeSphere(1)
        )
        distance = abs(pos_a[0] - pos_b[0])
        assert distance >= 4

        sv_a = rb_state.RigidBodyState(position=pos_a, cshapes=[cs])
        sv_b = rb_state.RigidBodyState(position=pos_b, cshapes=[cs])

        # Specify the constraints.
        p2p = ConstraintP2P(pivot_a=pos_b, pivot_b=pos_a)
        con = ConstraintMeta('p2p', '', id_a, id_b, p2p)
        self.igor.addConstraints([con])

        # Spawn both objects.
        assert leoAPI.addCmdSpawn([(id_a, sv_a, aabb), (id_b, sv_b, aabb)]).ok
        leo.processCommandsAndSync()

        # Apply a force to the left sphere only.
        assert leoAPI.addCmdDirectForce(id_a, [-10, 0, 0], [0, 0, 0]).ok
        leo.processCommandsAndSync()

        # Both object must have moved the same distance 'delta' because they
        # are linked. Their distance must not have changed.
        leo.step(1.0, 60)
        allObjs = leo.allObjects
        delta_a = allObjs[id_a].position - np.array(pos_a)
        delta_b = allObjs[id_b].position - np.array(pos_b)
        assert delta_a[0] < pos_a[0]
        assert np.allclose(delta_a, delta_b)
        tmp = abs(allObjs[id_a].position[0] - allObjs[id_b].position[0])
        assert abs(tmp - distance) < 0.01
        del tmp

        # Unlink the objects again, apply a right-pointing force to the
        # right object and verify that the left continues to move left and the
        # right does not.
        assert self.igor.deleteConstraints([con]) == (True, None, 1)
        assert leoAPI.addCmdDirectForce(id_b, [10, 0, 0], [0, 0, 0]).ok
        leo.processCommandsAndSync()
        leo.step(1.0, 60)

        # The distance between the spheres must have increases since they are
        # not linked anymore.
        tmp = abs(allObjs[id_a].position[0] - allObjs[id_b].position[0])
        assert tmp > (distance + 1)


class TestBroadphase:
    @classmethod
    def setup_class(cls):
        assert azrael.vectorgrid.deleteAllGrids().ok
        cls.igor = azrael.igor.Igor()

    @classmethod
    def teardown_class(cls):
        assert azrael.vectorgrid.deleteAllGrids().ok

    def setup_method(self, method):
        assert azrael.vectorgrid.deleteAllGrids().ok
        self.igor.reset()

    def teardown_method(self, method):
        pass

    def verifySweeping(self, aabbsIn, correct_answer):
        # Create the AABB dictionaries. For this test, the data in all
        # three dimensions is identical.
        aabbs = {}
        for k, v in aabbsIn.items():
            aabbs[k] = {'x': v, 'y': v, 'z': v}

        # Turn ``correct_answer`` into a well ordered list of lists to make
        # the comparison with the actual result easier (see loop below).
        correct_answer = sorted([tuple(set(_)) for _ in correct_answer])

        # Run the sweeping algorithm for every dimension and verify the
        # outputs match the expected 'correct_answer'.
        for dim in ('x', 'y', 'z'):
            # Run sweeping algorithm and inspect its return value.
            ret = azrael.leonard.sweeping(aabbs, dim)
            assert ret.ok
            computed = ret.data

            # Turn the output into a well ordered list of lists and compare
            # it to the expected answer.
            computed = sorted([tuple(set(_)) for _ in computed])
            assert computed == correct_answer

    def test_sweeping_2objects_multi_aabb(self):
        """
        Use objects that use more than one AABB to describe its collision set.
        """
        # Define a force grid (not used in this test but prevent a plethora
        # of meaningleass warning messages).
        vg = azrael.vectorgrid
        assert vg.defineGrid(name='force', vecDim=3, granularity=1).ok

        # Convenience variables.
        _verify = self.verifySweeping

        # Two orthogonal objects; the first has two AABBs, the second only one.
        _verify({0: [[4, 5], [6, 7]], 1: [[0, 1]]},
                correct_answer=[[0], [1]])

        # Self intersecting object: the two objects do not touch, but the AABBs
        # of the first do. This must result in to independent objects.
        _verify({0: [[4, 5], [4, 5]], 1: [[0, 1]]},
                correct_answer=[[0], [1]])

        # Two objects; the first has two AABS the second only one. The second
        # object touches the first AABB of the first object.
        _verify({0: [[4, 5], [6, 7]], 1: [[3, 5]]},
                correct_answer=[[0, 1]])

        # Two identical objects with two AABBs (each). This must produce one
        # set.
        _verify({0: [[4, 5], [6, 7]], 1: [[4, 5], [6, 7]]},
                correct_answer=[[0, 1]])

        # Three objects with one-, two-, and one AABB. The first touches the
        # left AABB of the middle object in 'x', whereas the third touches the
        # right AABB of the middle object in the 'y' dimensions.
        _verify({0: [[3, 5]], 1: [[4, 5], [7, 8]], 2: [[7, 9]]},
                correct_answer=[[0, 1, 2]])

        # Same as above, but the third object does not touch.
        _verify({0: [[3, 5]], 1: [[4, 5], [7, 8]], 2: [[70, 90]]},
                correct_answer=[[0, 1], [2]])

    def test_sweeping_2objects(self):
        """
        Ensure the Sweeping algorithm finds the correct sets.

        The algorithm takes a list of dictionarys and returns a list of
        lists.

        The input dictionary each contains the AABB coordinates. The output
        list contains the set of overlapping AABBs.
        """
        # Define a force grid (not used in this test but prevents a plethora
        # of meaningless warning messages).
        vg = azrael.vectorgrid
        assert vg.defineGrid(name='force', vecDim=3, granularity=1).ok

        # Convenience variables.
        _verify = self.verifySweeping

        # Two orthogonal objects.
        _verify({0: [[4, 5]], 1: [[1, 2]]},
                correct_answer=[[0], [1]])

        # Repeat the test but use a different set of ID labels.
        _verify({3: [[4, 5]], 10: [[1, 2]]},
                correct_answer=[[3], [10]])

        # One object inside the other.
        _verify({0: [[2, 4]], 1: [[0, 1]]},
                correct_answer=[[0], [1]])

        # Partially overlapping to the right of the first object.
        _verify({0: [[1, 5]], 1: [[2, 4]]},
                correct_answer=[[0, 1]])

        # Partially overlapping to the left of the first object.
        _verify({0: [[1, 5]], 1: [[0, 2]]},
                correct_answer=[[0, 1]])

        # Pass no object to the Sweeping algorithm.
        assert azrael.leonard.sweeping({}, 'x').data == []

        # Pass only a single object to the Sweeping algorithm.
        _verify({0: [[1, 5]]},
                correct_answer=[[0]])

    def test_sweeping_3objects(self):
        """
        Same as test_sweeping_2objects but with three objects.
        """
        # Define a force grid (not used in this test but prevent a plethora
        # of meaningleass warning messages).
        vg = azrael.vectorgrid
        assert vg.defineGrid(name='force', vecDim=3, granularity=1).ok

        # Convenience variable.
        sweeping = azrael.leonard.sweeping
        _verify = self.verifySweeping

        # Three non-overlapping objects.
        _verify({0: [[1, 2]], 1: [[3, 4]], 2: [[5, 6]]},
                correct_answer=[[0], [1], [2]])

        # First and second overlap.
        _verify({0: [[1, 2]], 1: [[1.5, 4]], 2: [[5, 6]]},
                correct_answer=[[0, 1], [2]])

        # Repeat test with different set of ID labels.
        _verify({2: [[1, 2]], 4: [[1.5, 4]], 10: [[5, 6]]},
                correct_answer=[[2, 4], [10]])

        # First overlaps with second, second overlaps with third, but third
        # does not overlap with first. The algorithm must nevertheless return
        # all three in a single set.
        _verify({0: [[1, 2]], 1: [[1.5, 4]], 2: [[3, 6]]},
                correct_answer=[[0, 1, 2]])

        # First and third overlap.
        _verify({0: [[1, 2]], 1: [[10, 11]], 2: [[0, 1.5]]},
                correct_answer=[[0, 2], [1]])

    @mock.patch('azrael.leonard.sweeping')
    def test_computeCollisionSetsAABB_mocksweeping(self, mock_sweeping):
        """
        Create three bodies. Then alter their AABBs to create various
        combinations of overlap.
        """
        # Convenience.
        RBS = rb_state.RigidBodyState

        # Get a Leonard instance.
        leo = getLeonard(azrael.leonard.LeonardBase)
        azrael.leonard.sweeping = mock_sweeping
        mock_sweeping.return_value = RetVal(True, None, [])

        def testCCS(pos, AABBs, expected_objIDs):
            """
            Compute broadphase results for bodies  at ``pos`` with ``AABBs``
            verify that the ``expected_objIDs`` sets were produced.
            """
            # Compile the set of bodies- and their AABBs for this test run.
            assert len(pos) == len(aabbs)
            bodies = [RBS(position=_) for _ in pos]

            # Convert to dictionaries: the key is the bodyID in Azrael; here it
            # is a simple enumeration.
            bodies = {idx: val for (idx, val) in enumerate(bodies)}
            AABBs = {idx: val for (idx, val) in enumerate(AABBs)}

            # Determine the list of broadphase collision sets.
            ret = azrael.leonard.computeCollisionSetsAABB(bodies, AABBs)
            assert ret.ok
            mock_sweeping.assert_called_with([])

        # Single body with no AABBs.
        bodies = {5: RBS(position=(0, 0, 0))}
        aabbs = {5: []}
        correct = {5: {'x': [], 'y': [], 'z': []}}
        azrael.leonard.computeCollisionSetsAABB(bodies, aabbs)
        mock_sweeping.assert_called_with(correct, 'x')

        # Single body with one AABB.
        bodies = {5: RBS(position=(0, 0, 0))}
        aabbs = {5: [(0, 0, 0, 1, 2, 3)]}
        correct = {5: {'x': [[-1, 1]],
                       'y': [[-2, 2]],
                       'z': [[-3, 3]]}}
        azrael.leonard.computeCollisionSetsAABB(bodies, aabbs)
        mock_sweeping.assert_called_with(correct, 'x')

        # Single body with two AABBs.
        bodies = {5: RBS(position=(0, 0, 0))}
        aabbs = {5: [(0, 0, 0, 1, 1, 1),
                     (2, 3, 4, 2, 4, 8)]}
        correct = {5: {'x': [[-1, 1], [0, 4]],
                       'y': [[-1, 1], [-1, 7]],
                       'z': [[-1, 1], [-4, 12]]}}
        azrael.leonard.computeCollisionSetsAABB(bodies, aabbs)
        mock_sweeping.assert_called_with(correct, 'x')

        # Single body at an offset with two AABBs.
        bodies = {5: RBS(position=(0, 1, 2))}
        aabbs = {5: [(0, 0, 0, 1, 1, 1),
                     (2, 3, 4, 2, 4, 8)]}
        correct = {5: {'x': [[-1, 1], [0, 4]],
                       'y': [[0, 2], [0, 8]],
                       'z': [[1, 3], [-2, 14]]}}
        azrael.leonard.computeCollisionSetsAABB(bodies, aabbs)
        mock_sweeping.assert_called_with(correct, 'x')

        # Three bodies with 0, 1, and 2 AABBs, respectively.
        bodies = {6: RBS(position=(0, 0, 0)),
                  7: RBS(position=(0, 0, 0)),
                  8: RBS(position=(0, 0, 0))}
        aabbs = {6: [],
                 7: [(0, 0, 0, 1, 1, 1)],
                 8: [(0, 0, 0, 1, 1, 1),
                     (2, 3, 4, 2, 4, 8)]}
        correct = {6: {'x': [],
                       'y': [],
                       'z': []},
                   7: {'x': [[-1, 1]],
                       'y': [[-1, 1]],
                       'z': [[-1, 1]]},
                   8: {'x': [[-1, 1], [0, 4]],
                       'y': [[-1, 1], [-1, 7]],
                       'z': [[-1, 1], [-4, 12]]}}
        azrael.leonard.computeCollisionSetsAABB(bodies, aabbs)
        mock_sweeping.assert_called_with(correct, 'x')

    @pytest.mark.parametrize('dim', [0, 1, 2])
    def test_computeCollisionSetsAABB_basic(self, dim):
        """
        Create three bodies. Then alter their AABBs to create various
        combinations of overlap.
        """
        # Get a Leonard instance.
        leo = getLeonard(azrael.leonard.LeonardBase)

        # Convenience.
        RBS = rb_state.RigidBodyState

        def testCCS(pos, AABBs, expected_objIDs):
            """
            Compute broadphase results for bodies  at ``pos`` with ``AABBs``
            verify that the ``expected_objIDs`` sets were produced.

            This function assumes that every body has exactly one AABB and with
            no relative offset to the body's position.
            """
            # Compile the set of bodies- and their AABBs for this test run.
            assert len(pos) == len(aabbs)
            bodies = [RBS(position=_) for _ in pos]

            # By assumption, this function, every object has exactly one AABB
            # centered at zero.
            AABBs = [[(0, 0, 0, _[0], _[1], _[2])] for _ in AABBs]

            # Convert to dictionaries: the key is the bodyID in Azrael; here it
            # is a simple enumeration.
            bodies = {idx: val for (idx, val) in enumerate(bodies)}
            AABBs = {idx: val for (idx, val) in enumerate(AABBs)}

            # Determine the list of broadphase collision sets.
            ret = azrael.leonard.computeCollisionSetsAABB(bodies, AABBs)
            assert ret.ok

            # Convert the reference data to a sorted list of sets.
            expected_objIDs = sorted([sorted(tuple(_)) for _ in expected_objIDs])
            computed_objIDs = sorted([sorted(tuple(_)) for _ in ret.data])

            # Return the equality of the two list of lists.
            assert expected_objIDs == computed_objIDs
            del bodies, AABBs, ret, expected_objIDs, computed_objIDs

        # First overlaps with second, second with third, but first not with
        # third. This must result in a single broadphase set containing all
        # three bodies.
        pos = [(0, 0, 0), (1, 1, 1), (2, 2, 2)]
        aabbs = [(0.9, 0.9, 0.9), (0.9, 0.9, 0.9), (0.9, 0.9, 0.9)]
        correct_answer = ([0, 1, 2], )
        testCCS(pos, aabbs, correct_answer)

        # Move the middle object away: three independent objects.
        pos = [(0, 0, 0), (1, 10, 1), (2, 2, 2)]
        aabbs = [(0.9, 0.9, 0.9), (0.9, 0.9, 0.9), (0.9, 0.9, 0.9)]
        correct_answer = ([0], [1], [2])
        testCCS(pos, aabbs, correct_answer)

        # Move the middle object back but make it so small in 'y' direction
        # that it does not intersect with the other two: three independent
        # objects.
        pos = [(0, 0, 0), (1, 1, 1), (2, 2, 2)]
        aabbs = [(0.9, 0.9, 0.9), (0.05, 0.05, 0.05), (0.9, 0.9, 0.9)]
        correct_answer = ([0], [1], [2])
        testCCS(pos, aabbs, correct_answer)

        # Second and third overlap, but first is by itself.
        pos = [(0, 0, 0), (1, 1, 1), (2, 2, 2)]
        aabbs = ([0.1, 0.1, 0.1], [0.1, 0.1, 0.1], [1, 1, 1])
        correct_answer = ([0], [1, 2])
        testCCS(pos, aabbs, correct_answer)

        # Objects overlap in 'x' and 'z', but not 'y': three independent
        # objects.
        pos = [(0, 0, 0), (1, 1, 1), (2, 2, 2)]
        aabbs = ([1, 0.4, 1], [1, 0.4, 1], [1, 0.4, 1])
        correct_answer = ([0], [1], [2])
        testCCS(pos, aabbs, correct_answer)

        # Middle object has no size, but the first/third objects are large
        # enough to touch each other: First/third must be connected, middle one
        # must be by itself.
        pos = [(0, 0, 0), (1, 1, 1), (2, 2, 2)]
        aabbs = ([1.01, 1.01, 1.01], [0, 0, 0], [1.01, 1.01, 1.01])
        correct_answer = ([0, 2], [1])
        testCCS(pos, aabbs, correct_answer)

    @pytest.mark.parametrize('dim', [0, 1, 2])
    def test_computeCollisionSetsAABB_viaLeonard(self, dim):
        """
        Create a sequence of 10 test objects and sync them to Leonard. Their
        positions only differ in the ``dim`` dimension.

        Then use subsets of these 10 objects to test basic collision detection.

        This uses the Azrael toolchain to create objects and sync them the
        Leonard. This ensures the data propagates coorectly from the
        interfaces, via Leonard, to the broadphase algorithm.
        """
        # Get a Leonard instance.
        leo = getLeonard(azrael.leonard.LeonardBase)

        # Create the IDs for the test bodies.
        all_IDs = range(10)

        RBS = rb_state.RigidBodyState
        if dim == 0:
            states = [RBS(position=[_, 0, 0]) for _ in range(10)]
        elif dim == 1:
            states = [RBS(position=[0, _, 0]) for _ in range(10)]
        elif dim == 2:
            states = [RBS(position=[0, 0, _]) for _ in range(10)]
        else:
            print('Invalid dimension for this test')
            assert False

        # Add all objects to the Body State DB and sync with Leonard.
        aabb = [(0, 0, 0, 1, 1, 1)]
        for objID, bs in zip(all_IDs, states):
            assert leoAPI.addCmdSpawn([(objID, bs, aabb)]).ok
        del states
        leo.processCommandsAndSync()

        # Sanity check: the number of test IDs must match the number of objects
        # in Leonard.
        assert len(all_IDs) == len(leo.allObjects)

        def ccsWrapper(test_objIDs, expected_objIDs):
            """
            Assert that all ``test_objIDs`` are ``expected_objIDs``.

            This is a convenience wrapper to facilitate readable tests.

            This wrapper converts the human readable entries in
            ``IDs_hr`` into the internally used binary format. It then
            passes this new list, along with the corresponding body
            states, to the collision detection algorithm. Finally, it
            converts the returned list of object sets back into human
            readable list of object sets and compares them for equality.
            """
            # Compile the set of bodies- and their AABBs for this test run.
            bodies = {_: leo.allObjects[_] for _ in test_objIDs}
            AABBs = {_: leo.allAABBs[_] for _ in test_objIDs}

            # Determine the list of broadphase collision sets.
            ret = azrael.leonard.computeCollisionSetsAABB(bodies, AABBs)
            assert ret.ok

            # Convert the reference data to a sorted list of sets.
            expected_objIDs = sorted([set(_) for _ in expected_objIDs])
            computed_objIDs = sorted([set(_) for _ in ret.data])

            # Return the equality of the two list of lists.
            assert expected_objIDs == computed_objIDs

        # Two non-overlapping objects.
        ccsWrapper([0, 9], [[0], [9]])

        # Two overlapping objects.
        ccsWrapper([0, 1], [[0, 1]])

        # Three sets.
        ccsWrapper([0, 1, 5, 8, 9], [[0, 1], [5], [8, 9]])

        # Same test, but objects are passed in a different sequence. This must
        # not alter the test outcome.
        ccsWrapper([0, 5, 1, 9, 8], [[0, 1], [5], [8, 9]])

        # All objects must form one connected set.
        ccsWrapper(list(range(10)), [list(range(10))])
