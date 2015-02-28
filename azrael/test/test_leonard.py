import sys
import time
import pytest
import IPython
import subprocess
import azrael.clerk
import azrael.client
import azrael.clacks
import azrael.leonard
import azrael.database
import azrael.vectorgrid
import azrael.physics_interface as physAPI
import azrael.bullet.bullet_data as bullet_data

from azrael.test.test_clacks import killAzrael
from azrael.bullet.test_boost_bullet import isEqualBD

import numpy as np

ipshell = IPython.embed

# List all available engines. This simplifies the parameterisation of those
# tests that must pass for all engines.
allEngines = [
    azrael.leonard.LeonardBase,
    azrael.leonard.LeonardBullet,
    azrael.leonard.LeonardSweeping,
    azrael.leonard.LeonardDistributedZeroMQ]


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


@pytest.mark.parametrize('clsLeonard', allEngines)
def test_getGridForces(clsLeonard):
    """
    Spawn an object, specify its State Variables explicitly, and verify the
    change propagated through Azrael.
    """
    killAzrael()

    # Convenience.
    vg = azrael.vectorgrid

    # Create pristince force grid.
    assert vg.deleteAllGrids().ok
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
                # Assign integer values (allows for equality comparisions later
                # on without having to worry about rounding effects).
                force[x, y, z] = [val, val + 1, val + 2]

                # Build the input dictionary for ``getGridForces``.
                idPos[objID] = np.array([x + ofs[0], y + ofs[1], z + ofs[2]])

                # Keep track of the value assigned to this position.
                idVal[objID] = force[x, y, z]

                # Update the counters.
                val += 3
                objID += 1

    # Set the grid values with a region operator.
    ret = vg.setRegion('force', ofs, force)

    # Query the grid values at the positions specified in the idPos dictionary.
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

    print('Test passed')


@pytest.mark.parametrize('clsLeonard', allEngines)
def test_setStateVariable_basic(clsLeonard):
    """
    Spawn an object, specify its State Variables explicitly, and verify the
    change propagated through Azrael.
    """
    killAzrael()

    # Get a Leonard instance.
    leo = getLeonard(clsLeonard)

    # Parameters and constants for this test.
    id_0, id_1, aabb = 0, 1, 1.0
    sv = bullet_data.BulletData()
    templateID = '_templateSphere'.encode('utf8')

    # State Vector.
    p = np.array([1, 2, 5])
    vl = np.array([8, 9, 10.5])
    vr = vl + 1
    data = bullet_data.BulletDataOverride(
        position=p, velocityLin=vl, velocityRot=vr)
    del p, vl, vr

    # Spawn a new object. It must have ID=1.
    assert physAPI.addCmdSpawn([(id_1, sv, aabb)]).ok

    # Update the object's State Vector.
    assert physAPI.addCmdModifyStateVariable(id_1, data).ok

    # Step the simulation by 0 seconds. This will not change the simulation
    # state but pick up all the queued commands.
    leo.processCommandsAndSync()

    # Verify that the attributes were correctly updated.
    ret = physAPI.getStateVariables([id_1])
    assert (ret.ok, len(ret.data)) == (True, 1)
    sv = ret.data[id_1]
    assert np.array_equal(sv.position, data.position)
    assert np.array_equal(sv.velocityLin, data.velocityLin)
    assert np.array_equal(sv.velocityRot, data.velocityRot)

    print('Test passed')


@pytest.mark.parametrize('clsLeonard', allEngines)
def test_setStateVariable_advanced(clsLeonard):
    """
    Similar to test_setStateVariable_basic but modify the collision shape
    information as well, namely mass and the collision shape itself.
    """
    killAzrael()

    # Get a Leonard instance.
    leo = getLeonard(clsLeonard)

    # Parameters and constants for this test.
    cs_cube = [3, 1, 1, 1]
    cs_sphere = [3, 1, 1, 1]
    sv = bullet_data.BulletData(imass=2, scale=3, cshape=cs_sphere)
    templateID = '_templateSphere'.encode('utf8')

    # Spawn an object.
    objID, aabb = 1, 1
    assert physAPI.addCmdSpawn([(objID, sv, aabb)]).ok

    # Verify the SV data.
    leo.processCommandsAndSync()
    ret = physAPI.getStateVariables([objID])
    assert ret.ok
    assert ret.data[objID].imass == 2
    assert ret.data[objID].scale == 3
    assert np.array_equal(ret.data[objID].cshape, cs_sphere)

    # Update the object's SV data.
    sv_new = bullet_data.BulletDataOverride(imass=4, scale=5, cshape=cs_cube)
    assert physAPI.addCmdModifyStateVariable(objID, sv_new).ok

    # Verify the SV data.
    leo.processCommandsAndSync()
    ret = physAPI.getStateVariables([objID])
    assert (ret.ok, len(ret.data)) == (True, 1)
    sv = ret.data[objID]
    assert (sv.imass == 4) and (sv.scale == 5)
    assert np.array_equal(sv.cshape, cs_cube)

    print('Test passed')


@pytest.mark.parametrize('clsLeonard', allEngines)
def test_move_single_object(clsLeonard):
    """
    Create a single object with non-zero initial speed and ensure Leonard moves
    it accordingly.
    """
    killAzrael()

    # Get a Leonard instance.
    leonard = getLeonard(clsLeonard)

    # Constants and parameters for this test.
    id_0, aabb = 0, 1
    sv = bullet_data.BulletData()

    # Spawn an object.
    assert physAPI.addCmdSpawn([(id_0, sv, aabb)]).ok

    # Advance the simulation by 1s and verify that nothing has moved.
    leonard.step(1.0, 60)
    ret = physAPI.getStateVariables([id_0])
    assert ret.ok
    assert np.array_equal(ret.data[id_0].position, [0, 0, 0])

    # Give the object a velocity.
    sv = bullet_data.BulletDataOverride(velocityLin=np.array([1, 0, 0]))
    assert physAPI.addCmdModifyStateVariable(id_0, sv).ok

    # Advance the simulation by another second and verify the objects have
    # moved accordingly.
    leonard.step(1.0, 60)
    ret = physAPI.getStateVariables([id_0])
    assert ret.ok
    assert 0.9 <= ret.data[id_0].position[0] < 1.1
    assert ret.data[id_0].position[1] == ret.data[id_0].position[2] == 0

    print('Test passed')


@pytest.mark.parametrize('clsLeonard', allEngines)
def test_move_two_objects_no_collision(clsLeonard):
    """
    Same as previous test but with two objects.
    """
    killAzrael()

    # Get a Leonard instance.
    leonard = getLeonard(clsLeonard)

    # Constants and parameters for this test.
    id_0, id_1, aabb = 0, 1, 1
    sv_0 = bullet_data.BulletData(position=[0, 0, 0], velocityLin=[1, 0, 0])
    sv_1 = bullet_data.BulletData(position=[0, 10, 0], velocityLin=[0, -1, 0])

    # Create two objects.
    tmp = [(id_0, sv_0, aabb), (id_1, sv_1, aabb)]
    assert physAPI.addCmdSpawn(tmp).ok

    # Advance the simulation by 1s and query the states of both objects.
    leonard.step(1.0, 60)
    ret = physAPI.getStateVariables([id_0])
    assert ret.ok
    pos_0 = ret.data[id_0].position
    ret = physAPI.getStateVariables([id_1])
    assert ret.ok
    pos_1 = ret.data[id_1].position

    # Verify that the objects have moved according to their initial velocity.
    assert pos_0[1] == pos_0[2] == 0
    assert pos_1[0] == pos_1[2] == 0
    assert 0.9 <= pos_0[0] <= 1.1
    assert 8.9 <= pos_1[1] <= 9.1

    killAzrael()
    print('Test passed')


def test_worker_respawn():
    """
    Ensure the objects move correctly even though the Workers will restart
    themselves after every step.

    The test code is similar to ``test_move_two_objects_no_collision``.
    """
    killAzrael()

    # Instantiate Leonard.
    leonard = azrael.leonard.LeonardDistributedZeroMQ()
    leonard.workerStepsUntilQuit = (1, 10)
    leonard.setup()

    # Define a force grid (not used in this test but prevent a plethora
    # of meaningleass warning messages).
    vg = azrael.vectorgrid
    assert vg.defineGrid(name='force', vecDim=3, granularity=1).ok

    # Constants and parameters for this test.
    id_0, id_1 = 0, 1
    cshape = [3, 1, 1, 1]
    aabb = 1

    # Two State Vectors for this test.
    sv_0 = bullet_data.BulletData(
        position=[0, 0, 0], velocityLin=[1, 0, 0], cshape=cshape)
    sv_1 = bullet_data.BulletData(
        position=[0, 10, 0], velocityLin=[0, -1, 0], cshape=cshape)

    # Create two objects.
    tmp = [(id_0, sv_0, aabb), (id_1, sv_1, aabb)]
    assert physAPI.addCmdSpawn(tmp).ok

    # Advance the simulation by 1s, but use many small time steps. This ensures
    # that the Workers will restart themselves frequently.
    for ii in range(60):
        leonard.step(1.0 / 60, 1)

    # Query the states of both objects.
    ret = physAPI.getStateVariables([id_0])
    assert ret.ok
    pos_0 = ret.data[id_0].position
    ret = physAPI.getStateVariables([id_1])
    assert ret.ok
    pos_1 = ret.data[id_1].position

    # Verify that the objects have moved according to their initial velocity.
    assert pos_0[1] == pos_0[2] == 0
    assert pos_1[0] == pos_1[2] == 0
    assert 0.9 <= pos_0[0] <= 1.1
    assert 8.9 <= pos_1[1] <= 9.1

    # Clean up.
    killAzrael()
    print('Test passed')


def test_sweeping_2objects():
    """
    Ensure the Sweeping algorithm finds the correct sets.

    The algorithm takes a list of dictionarys and returns a list of lists.

    The input dictionary each contains the AABB coordinates. The output list
    contains the set of overlapping AABBs.
    """
    killAzrael()

    # Define a force grid (not used in this test but prevent a plethora
    # of meaningleass warning messages).
    vg = azrael.vectorgrid
    assert vg.defineGrid(name='force', vecDim=3, granularity=1).ok

    # Convenience variables.
    sweeping = azrael.leonard.sweeping
    labels = np.arange(2)

    # Two orthogonal objects.
    aabbs = [{'x': [4, 5], 'y': [3.5, 4], 'z': [5, 6.5]},
             {'x': [1, 2], 'y': [3.5, 4], 'z': [5, 6.5]}]
    res = sweeping(aabbs, labels, 'x').data
    assert sorted(res) == sorted([set([1]), set([0])])

    # Repeat the test but use a different set of labels.
    res = sweeping(aabbs, np.array([3, 10], np.int64), 'x').data
    assert sorted(res) == sorted([set([10]), set([3])])

    # One object inside the other.
    aabbs = [{'x': [2, 4], 'y': [3.5, 4], 'z': [5, 6.5]},
             {'x': [1, 5], 'y': [3.5, 4], 'z': [5, 6.5]}]
    res = sweeping(aabbs, labels, 'x').data
    assert sorted(res) == sorted([set([1, 0])])

    # Partially overlapping to the right of the first object.
    aabbs = [{'x': [1, 5], 'y': [3.5, 4], 'z': [5, 6.5]},
             {'x': [2, 4], 'y': [3.5, 4], 'z': [5, 6.5]}]
    res = sweeping(aabbs, labels, 'x').data
    assert sorted(res) == sorted([set([1, 0])])

    # Partially overlapping to the left of the first object.
    aabbs = [{'x': [1, 5], 'y': [3.5, 4], 'z': [5, 6.5]},
             {'x': [2, 4], 'y': [3.5, 4], 'z': [5, 6.5]}]
    res = sweeping(aabbs, labels, 'x').data
    assert sorted(res) == sorted([set([1, 0])])

    # Test Sweeping in the 'y' and 'z' dimension as well.
    aabbs = [{'x': [1, 5], 'y': [1, 5], 'z': [1, 5]},
             {'x': [2, 4], 'y': [2, 4], 'z': [2, 4]}]
    assert sweeping(aabbs, labels, 'x') == sweeping(aabbs, labels, 'y')
    assert sweeping(aabbs, labels, 'x') == sweeping(aabbs, labels, 'z')

    # Pass no object to the Sweeping algorithm.
    assert sweeping([], np.array([], np.int64), 'x').data == []

    # Pass only a single object to the Sweeping algorithm.
    aabbs = [{'x': [1, 5], 'y': [3.5, 4], 'z': [5, 6.5]}]
    res = sweeping(aabbs, np.array([0], np.int64), 'x').data
    assert sorted(res) == sorted([set([0])])

    print('Test passed')


def test_sweeping_3objects():
    """
    Same as test_sweeping_2objects but with three objects.
    """
    killAzrael()

    # Define a force grid (not used in this test but prevent a plethora
    # of meaningleass warning messages).
    vg = azrael.vectorgrid
    assert vg.defineGrid(name='force', vecDim=3, granularity=1).ok

    # Convenience variable.
    sweeping = azrael.leonard.sweeping
    labels = np.arange(3)

    # Three non-overlapping objects.
    aabbs = [{'x': [1, 2]}, {'x': [3, 4]}, {'x': [5, 6]}]
    res = sweeping(aabbs, labels, 'x').data
    assert sorted(res) == sorted([set([0]), set([1]), set([2])])

    # First and second overlap.
    aabbs = [{'x': [1, 2]}, {'x': [1.5, 4]}, {'x': [5, 6]}]
    res = sweeping(aabbs, labels, 'x').data
    assert sorted(res) == sorted([set([0, 1]), set([2])])

    # Repeat test with different labels.
    res = sweeping(aabbs, np.array([2, 4, 10], np.int64), 'x').data
    assert sorted(res) == sorted([set([2, 4]), set([10])])

    # First overlaps with second, second overlaps with third, but third does
    # not overlap with first. The algorithm must nevertheless return all three
    # in a single set.
    aabbs = [{'x': [1, 2]}, {'x': [1.5, 4]}, {'x': [3, 6]}]
    res = sweeping(aabbs, labels, 'x').data
    assert sorted(res) == sorted([set([0, 1, 2])])

    # First and third overlap.
    aabbs = [{'x': [1, 2]}, {'x': [10, 11]}, {'x': [0, 1.5]}]
    res = sweeping(aabbs, labels, 'x').data
    assert sorted(res) == sorted([set([0, 2]), set([1])])

    print('Test passed')


@pytest.mark.parametrize('dim', [0, 1, 2])
def test_computeCollisionSetsAABB(dim):
    """
    Create a sequence of 10 test objects. Their position only differs in the
    ``dim`` dimension.

    Then use subsets of these 10 objects to test basic collision detection.
    """
    killAzrael()

    # Get a Leonard instance.
    leo = getLeonard(azrael.leonard.LeonardBase)

    # Create several objects for this test.
    all_id = list(range(10))

    if dim == 0:
        SVs = [bullet_data.BulletData(position=[_, 0, 0]) for _ in range(10)]
    elif dim == 1:
        SVs = [bullet_data.BulletData(position=[0, _, 0]) for _ in range(10)]
    elif dim == 2:
        SVs = [bullet_data.BulletData(position=[0, 0, _]) for _ in range(10)]
    else:
        print('Invalid dimension for this test')
        assert False

    # Add all objects to the SV DB.
    aabb = 1
    for objID, sv in zip(all_id, SVs):
        assert physAPI.addCmdSpawn([(objID, sv, aabb)]).ok
    del SVs

    # Retrieve all SVs as Leonard does.
    leo.processCommandsAndSync()
    assert len(all_id) == len(leo.allObjects)

    def ccsWrapper(test_objIDs, expected_objIDs):
        """
        Assert that all ``test_objIDs`` resulted in the ``expected_objIDs``.

        This is merely a convenience wrapper to facilitate readable tests.

        This wrapper converts the human readable entries in ``IDs_hr``  into
        the internally used binary format. It then passes this new list, along
        with the corresponding SVs, to the collision detection algorithm.
        Finally, it converts the returned list of object sets back into human
        readable list of object sets and compares them for equality.
        """
        # Compile the set of SVs for curIDs.
        SVs = {_: leo.allObjects[_] for _ in test_objIDs}
        AABBs = {_: leo.allAABBs[_] for _ in test_objIDs}

        # Determine the list of potential collision sets.
        ret = azrael.leonard.computeCollisionSetsAABB(SVs, AABBs)
        assert ret.ok

        # Convert the reference data to a sorted list of sets.
        expected_objIDs = sorted([set(_) for _ in expected_objIDs])
        res = sorted([set(_) for _ in ret.data])

        # Return the equality of the two list of lists.
        assert expected_objIDs == res

    # Two non-overlapping objects.
    ccsWrapper([0, 9], [[0], [9]])

    # Two overlapping objects.
    ccsWrapper([0, 1], [[0, 1]])

    # Three sets.
    ccsWrapper([0, 1, 5, 8, 9], [[0, 1], [5], [8, 9]])

    # Same test, but objects are passed in a different sequence. This must not
    # alter the test outcome.
    ccsWrapper([0, 5, 1, 9, 8], [[0, 1], [5], [8, 9]])

    # All objects must form one connected set.
    ccsWrapper(list(range(10)), [list(range(10))])

    print('Test passed')


@pytest.mark.parametrize('clsLeonard', allEngines)
def test_force_grid(clsLeonard):
    """
    Create a force grid and ensure Leonard applies its values to the center of
    the mass.
    """
    killAzrael()

    # Convenience.
    vg = azrael.vectorgrid

    # Get a Leonard instance.
    leonard = getLeonard(clsLeonard)

    # Constants and parameters for this test.
    id_0, aabb = 0, 1
    sv = bullet_data.BulletData()

    # Spawn one object.
    assert physAPI.addCmdSpawn([(id_0, sv, aabb)]).ok

    # Advance the simulation by 1s and verify that nothing has moved.
    leonard.step(1.0, 60)
    ret = physAPI.getStateVariables([id_0])
    assert ret.ok
    assert np.array_equal(ret.data[id_0].position, [0, 0, 0])

    # Define a force grid.
    assert vg.defineGrid(name='force', vecDim=3, granularity=1).ok

    # Specify a non-zero value somewhere away from the object. This means the
    # object must still not move.
    pos = np.array([1, 2, 3], np.float64)
    value = np.ones(3, np.float64)
    assert vg.setValues('force', [(pos, value)]).ok

    # Step the simulation and verify the object remained where it was.
    leonard.step(1.0, 60)
    ret = physAPI.getStateVariables([id_0])
    assert ret.ok
    assert np.array_equal(ret.data[id_0].position, [0, 0, 0])

    # Specify a grid value of 1 Newton in x-direction.
    pos = np.array([0, 0, 0], np.float64)
    value = np.array([1, 0, 0], np.float64)
    assert vg.setValues('force', [(pos, value)]).ok

    # Step the simulation and verify the object moved accordingly.
    leonard.step(1.0, 60)

    ret = physAPI.getStateVariables([id_0])
    assert ret.ok
    assert 0.4 <= ret.data[id_0].position[0] < 0.6
    assert ret.data[id_0].position[1] == ret.data[id_0].position[2] == 0

    # Cleanup.
    killAzrael()
    print('Test passed')


def test_createWorkPackages():
    """
    Create a Work Package and verify its content.
    """
    killAzrael()

    # Get a Leonard instance.
    leo = getLeonard(azrael.leonard.LeonardDistributedZeroMQ)

    # Constants.
    id_1, id_2 = 1, 2
    aabb, dt, maxsteps = 1, 2, 3

    # Invalid call: list of IDs must not be empty.
    assert not leo.createWorkPackage([], dt, maxsteps).ok

    # Invalid call: Leonard has no object with ID 10.
    assert not leo.createWorkPackage([10], dt, maxsteps).ok

    # Test data.
    sv_1 = bullet_data.BulletData(imass=1)
    sv_2 = bullet_data.BulletData(imass=2)

    # Add two new objects to Leonard.
    tmp = [(id_1, sv_1, aabb), (id_2, sv_2, aabb)]
    assert physAPI.addCmdSpawn(tmp).ok
    leo.processCommandsAndSync()

    # Create a Work Package with two objects. The WPID must be 1.
    ret = leo.createWorkPackage([id_1], dt, maxsteps)
    ret_wpid, ret_wpdata = ret.data['wpid'], ret.data['wpdata']
    assert (ret.ok, ret_wpid, len(ret_wpdata)) == (True, 0, 1)

    # Create a second WP. This one must have WPID=2 and contain two objects.
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
    assert (data[0].id, data[1].id) == (id_1, id_2)
    assert isEqualBD(data[0].sv, sv_1)
    assert isEqualBD(data[1].sv, sv_2)
    assert np.array_equal(data[0].force, [0, 0, 0])
    assert np.array_equal(data[1].force, [0, 0, 0])

    # Cleanup.
    killAzrael()
    print('Test passed')


def test_updateLocalCache():
    """
    Update the local object cache in Leonard based on a Work Package.
    """
    killAzrael()

    # Get a Leonard instance.
    leo = getLeonard(azrael.leonard.LeonardDistributedZeroMQ)

    # Convenience.
    WPData = azrael.leonard.WPData
    data_1 = bullet_data.BulletData(imass=1)
    data_2 = bullet_data.BulletData(imass=2)
    id_1, id_2, aabb = 1, 2, 1

    # Spawn new objects.
    tmp = [(id_1, data_1, aabb), (id_2, data_2, aabb)]
    assert physAPI.addCmdSpawn(tmp).ok
    leo.processCommandsAndSync()

    # Create a Work Package and verify its content.
    ret = leo.createWorkPackage([id_1, id_2], dt=3, maxsteps=4)

    # Create a new State Vector to replace the old one.
    data_3 = bullet_data.BulletData(imass=4, position=[1, 2, 3])
    newWP = [(id_1, data_3)]

    # Check the State Vector for objID=id_1 before and after the update.
    assert isEqualBD(leo.allObjects[id_1], data_1)
    leo.updateLocalCache(newWP)
    assert isEqualBD(leo.allObjects[id_1], data_3)

    # Cleanup.
    killAzrael()
    print('Test passed')


def test_processCommandQueue():
    """
    Create commands to spawn-, delete, and modify objects or their booster
    values. Then verify that ``processCommandQueue`` corrently updates
    Leonard's object cache.
    """
    killAzrael()

    # Get a Leonard instance.
    leo = getLeonard(azrael.leonard.LeonardDistributedZeroMQ)

    # Convenience.
    sv_1 = bullet_data.BulletData(imass=1)
    sv_2 = bullet_data.BulletData(imass=2)
    id_1, id_2, aabb = 1, 2, 1

    # Cache must be empty.
    assert len(leo.allObjects) == len(leo.allForces) == 0

    # Spawn two objects.
    tmp = [(id_1, sv_1, aabb), (id_2, sv_2, aabb)]
    assert physAPI.addCmdSpawn(tmp).ok
    leo.processCommandsAndSync()

    # Verify the local cache (forces and torques must default to zero).
    assert isEqualBD(leo.allObjects[id_1], sv_1)
    assert isEqualBD(leo.allObjects[id_2], sv_2)
    tmp = leo.allForces[id_1]
    assert tmp.forceDirect == tmp.torqueDirect == [0, 0, 0]
    assert tmp.forceBoost == tmp.torqueBoost == [0, 0, 0]
    del tmp

    # Remove first object.
    assert physAPI.addCmdRemoveObject(id_1).ok
    leo.processCommandsAndSync()
    assert id_1 not in leo.allObjects
    assert id_1 not in leo.allForces

    # Change the State Vector of id_2.
    pos = [10, 11.5, 12]
    sv_3 = bullet_data.BulletDataOverride(position=pos)
    assert leo.allObjects[id_2].position == [0, 0, 0]
    assert physAPI.addCmdModifyStateVariable(id_2, sv_3).ok
    leo.processCommandsAndSync()
    assert leo.allObjects[id_2].position == pos

    # Apply a direct force and torque to id_2.
    force, torque = [1, 2, 3], [4, 5, 6]
    assert physAPI.addCmdDirectForce(id_2, force, torque).ok
    leo.processCommandsAndSync()
    assert leo.allForces[id_2].forceDirect == force
    assert leo.allForces[id_2].torqueDirect == torque

    # Specify a new force- and torque value due to booster activity.
    force, torque = [1, 2, 3], [4, 5, 6]
    assert physAPI.addCmdBoosterForce(id_2, force, torque).ok
    leo.processCommandsAndSync()
    assert leo.allForces[id_2].forceBoost == force
    assert leo.allForces[id_2].torqueBoost == torque

    # Cleanup.
    killAzrael()
    print('Test passed')


def test_maintain_forces():
    """
    Leonard must not reset any forces from one iteration to the next (used to
    be the case at some point and thus requires a dedicated test now).
    """
    killAzrael()

    # Get a Leonard instance.
    leo = getLeonard(azrael.leonard.LeonardDistributedZeroMQ)

    # Convenience.
    sv = bullet_data.BulletData(imass=1)
    objID, aabb = 1, 1

    # Spawn two objects.
    assert physAPI.addCmdSpawn([(objID, sv, aabb)]).ok
    leo.processCommandsAndSync()

    # Initial force and torque must be zero.
    tmp = leo.allForces[objID]
    assert tmp.forceDirect == tmp.torqueDirect == [0, 0, 0]
    assert tmp.forceBoost == tmp.torqueBoost == [0, 0, 0]
    del tmp

    # Change the direct force and verify that Leonard does not reset it.
    assert physAPI.addCmdDirectForce(objID, [1, 2, 3], [4, 5, 6]).ok
    for ii in range(10):
        leo.processCommandsAndSync()
        tmp = leo.allForces[objID]
        assert tmp.forceDirect == [1, 2, 3]
        assert tmp.torqueDirect == [4, 5, 6]
        assert tmp.forceBoost == [0, 0, 0]
        assert tmp.torqueBoost == [0, 0, 0]

    # Change the booster force and verify that Leonard does not change
    # it (or the direct force specified earlier)
    assert physAPI.addCmdBoosterForce(objID, [-1, -2, -3], [-4, -5, -6]).ok
    for ii in range(10):
        leo.processCommandsAndSync()
        tmp = leo.allForces[objID]
        assert tmp.forceDirect == [1, 2, 3]
        assert tmp.torqueDirect == [4, 5, 6]
        assert tmp.forceBoost == [-1, -2, -3]
        assert tmp.torqueBoost == [-4, -5, -6]

    # Change the direct forces again.
    assert physAPI.addCmdDirectForce(objID, [3, 2, 1], [6, 5, 4]).ok
    for ii in range(10):
        leo.processCommandsAndSync()
        tmp = leo.allForces[objID]
        assert tmp.forceDirect == [3, 2, 1]
        assert tmp.torqueDirect == [6, 5, 4]
        assert tmp.forceBoost == [-1, -2, -3]
        assert tmp.torqueBoost == [-4, -5, -6]

    # Change the booster forces again.
    assert physAPI.addCmdBoosterForce(objID, [-3, -2, -1], [-6, -5, -4]).ok
    for ii in range(10):
        leo.processCommandsAndSync()
        tmp = leo.allForces[objID]
        assert tmp.forceDirect == [3, 2, 1]
        assert tmp.torqueDirect == [6, 5, 4]
        assert tmp.forceBoost == [-3, -2, -1]
        assert tmp.torqueBoost == [-6, -5, -4]

    # Cleanup.
    killAzrael()
    print('Test passed')


def test_totalForceAndTorque_no_rotation():
    """
    Verify that 'totalForceAndTorque' correctly adds up the direct- and booster
    forces for an object that is in neutral position (ie without rotation).
    """
    killAzrael()

    # Get a Leonard instance.
    leo = getLeonard(azrael.leonard.LeonardDistributedZeroMQ)

    # Spawn one object.
    orient = np.array([0, 0, 0, 1])
    sv = bullet_data.BulletData(imass=1, orientation=orient)
    objID, aabb = 1, 1
    assert physAPI.addCmdSpawn([(objID, sv, aabb)]).ok
    leo.processCommandsAndSync()
    del sv, aabb

    # Initial force and torque must be zero.
    assert leo.totalForceAndTorque(objID) == ([0, 0, 0], [0, 0, 0])

    # Change the direct force.
    assert physAPI.addCmdDirectForce(objID, [1, 2, 3], [4, 5, 6]).ok
    leo.processCommandsAndSync()
    assert leo.totalForceAndTorque(objID) == ([1, 2, 3], [4, 5, 6])

    # Change the direct force.
    assert physAPI.addCmdDirectForce(objID, [1, 2, 30], [4, 5, 60]).ok
    leo.processCommandsAndSync()
    assert leo.totalForceAndTorque(objID) == ([1, 2, 30], [4, 5, 60])

    # Reset the direct force and change the booster force.
    assert physAPI.addCmdDirectForce(objID, [0, 0, 0], [0, 0, 0]).ok
    assert physAPI.addCmdBoosterForce(objID, [-1, -2, -3], [-4, -5, -6]).ok
    leo.processCommandsAndSync()
    assert leo.totalForceAndTorque(objID) == ([-1, -2, -3], [-4, -5, -6])

    # Direct- and booste forces must perfectly balance each other.
    assert physAPI.addCmdDirectForce(objID, [1, 2, 3], [4, 5, 6]).ok
    assert physAPI.addCmdBoosterForce(objID, [-1, -2, -3], [-4, -5, -6]).ok
    leo.processCommandsAndSync()
    assert leo.totalForceAndTorque(objID) == ([0, 0, 0], [0, 0, 0])

    # Cleanup.
    killAzrael()
    print('Test passed')


def test_totalForceAndTorque_with_rotation():
    """
    Similar to the previou 'test_totalForceAndTorque_no_rotation' but this time
    the object does not have a neutral rotation in world coordinates. This must
    have no effect on the direct force values, but the booster forces must be
    re-oriented accordingly.
    """
    killAzrael()

    # Get a Leonard instance.
    leo = getLeonard(azrael.leonard.LeonardDistributedZeroMQ)

    # Spawn one object rotated 180 degress around x-axis.
    orient = np.array([1, 0, 0, 0])
    sv = bullet_data.BulletData(imass=1, orientation=orient)
    objID, aabb = 1, 1
    assert physAPI.addCmdSpawn([(objID, sv, aabb)]).ok
    leo.processCommandsAndSync()
    del sv, aabb

    # Initial force and torque must be zero.
    assert leo.totalForceAndTorque(objID) == ([0, 0, 0], [0, 0, 0])

    # Add booster force in z-direction.
    assert physAPI.addCmdBoosterForce(objID, [1, 2, 3], [-1, -2, -3]).ok
    leo.processCommandsAndSync()

    # The net forces in must have their signs flipped in the y/z directions,
    # and remain unchanged for x since the object itself is rotated 180 degrees
    # around the x-axis.
    assert leo.totalForceAndTorque(objID) == ([1, -2, -3], [-1, 2, 3])

    # The object's rotation must have not effect the direct force and torque.
    assert physAPI.addCmdBoosterForce(objID, [0, 0, 0], [0, 0, 0]).ok
    assert physAPI.addCmdDirectForce(objID, [1, 2, 3], [4, 5, 6]).ok
    leo.processCommandsAndSync()
    assert leo.totalForceAndTorque(objID) == ([1, 2, 3], [4, 5, 6])

    # Cleanup.
    killAzrael()
    print('Test passed')


if __name__ == '__main__':
    test_totalForceAndTorque_no_rotation()
    test_totalForceAndTorque_with_rotation()
    test_maintain_forces()
    test_processCommandQueue()
    test_createWorkPackages()
    test_updateLocalCache()

    test_worker_respawn()
    test_sweeping_2objects()
    test_sweeping_3objects()
    test_computeCollisionSetsAABB(0)

    for _engine in allEngines:
        print('\nEngine: {}'.format(_engine))
        test_getGridForces(_engine)
        test_force_grid(_engine)
        test_setStateVariable_advanced(_engine)
        test_setStateVariable_basic(_engine)
        test_move_single_object(_engine)
        test_move_two_objects_no_collision(_engine)
