import sys
import time
import pytest
import IPython
import subprocess
import azrael.clerk
import azrael.clacks
import azrael.leonard
import azrael.controller
import azrael.vectorgrid
import azrael.bullet.btInterface as btInterface
import azrael.bullet.bullet_data as bullet_data

from azrael.util import int2id, id2int

import numpy as np

ipshell = IPython.embed

# List all available engines. This simplifies the parameterisation of those
# tests that must pass for all engines.
allEngines = [
    azrael.leonard.LeonardBase,
    azrael.leonard.LeonardBulletMonolithic,
    azrael.leonard.LeonardBulletSweeping,
    azrael.leonard.LeonardBulletSweepingMultiST,
    azrael.leonard.LeonardBulletSweepingMultiMT]


def killAzrael():
    subprocess.call(['pkill', 'killme'])


def startAzrael(ctrl_type):
    """
    Start all Azrael services and return their handles.

    ``ctrl_type`` may be  either 'ZeroMQ' or 'Websocket'. The only difference
    this makes is that the 'Websocket' version will also start a Clacks server,
    whereas for 'ZeroMQ' the respective handle will be **None**.

    :param str ctrl_type: the controller type ('ZeroMQ' or 'Websocket').
    :return: handles to (clerk, ctrl, clacks)
    """
    killAzrael()

    # Delete all grids used in this test.
    assert azrael.vectorgrid.deleteAllGrids().ok

    # Start Clerk and instantiate Controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()

    if ctrl_type == 'ZeroMQ':
        # Instantiate the ZeroMQ version of the Controller.
        ctrl = azrael.controller.ControllerBase()
        ctrl.setupZMQ()

        # Do not start a Clacks process.
        clacks = None
    elif ctrl_type == 'Websocket':
        # Start a Clacks process.
        clacks = azrael.clacks.ClacksServer()
        clacks.start()

        # Instantiate the Websocket version of the Controller.
        ctrl = azrael.wscontroller.WSControllerBase(
            'ws://127.0.0.1:8080/websocket', 1)
        assert ctrl.ping()
    else:
        print('Unknown controller type <{}>'.format(ctrl_type))
        assert False
    return clerk, ctrl, clacks


def stopAzrael(clerk, clacks):
    """
    Kill all processes related to Azrael.

    :param clerk: handle to Clerk process.
    :param clacks: handle to Clacks process.
    """
    # Terminate the Clerk.
    clerk.terminate()
    clerk.join(timeout=3)

    # Terminate Clacks (if one was started).
    if clacks is not None:
        clacks.terminate()
        clacks.join(timeout=3)

    # Forcefully terminate everything.
    killAzrael()


@pytest.mark.parametrize('clsLeonard', allEngines)
def test_setStateVariables_basic(clsLeonard):
    """
    Spawn an object, specify its State Variables explicitly, and verify the
    change propagated through Azrael.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    btInterface.initSVDB(reset=True)
    leo = clsLeonard()
    leo.setup()

    # Parameters and constants for this test.
    id_0 = int2id(0)
    id_1 = int2id(1)
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
    assert btInterface.spawn(id_1, sv, np.int64(1).tostring(), 1.0).ok
    
    # Update the object's State Vector.
    assert btInterface.setStateVariables(id_1, data).ok

    # Step the simulation by 0 seconds. This will not change the simulation
    # state but pick up all the queued commands.
    leo.step(0, 10)

    # Verify that the attributes were correctly updated.
    ret = btInterface.getStateVariables([id_1])
    assert (ret.ok, len(ret.data)) == (True, 1)
    sv = ret.data[id_1]
    assert np.array_equal(sv.position, data.position)
    assert np.array_equal(sv.velocityLin, data.velocityLin)
    assert np.array_equal(sv.velocityRot, data.velocityRot)

    print('Test passed')


@pytest.mark.parametrize('clsLeonard', allEngines)
def test_setStateVariables_advanced(clsLeonard):
    """
    Similar to test_setStateVariables_basic but modify the collision shape
    information as well, namely mass and the collision shape itself.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    btInterface.initSVDB(reset=True)
    leo = clsLeonard()
    leo.setup()

    # Parameters and constants for this test.
    cs_cube = [3, 1, 1, 1]
    cs_sphere = [3, 1, 1, 1]
    sv = bullet_data.BulletData(imass=2, scale=3, cshape=cs_sphere)
    templateID = '_templateSphere'.encode('utf8')

    # Spawn an object.
    objID = int2id(1)
    assert btInterface.spawn(objID, sv, np.int64(1).tostring(), 1.0).ok

    # Verify the SV data.
    leo.step(0, 10)
    ret = btInterface.getStateVariables([objID])
    assert ret.ok
    assert ret.data[objID].imass == 2
    assert ret.data[objID].scale == 3
    assert np.array_equal(ret.data[objID].cshape, cs_sphere)

    # Update the object's SV data.
    sv_new = bullet_data.BulletDataOverride(imass=4, scale=5, cshape=cs_cube)
    assert btInterface.setStateVariables(objID, sv_new).ok

    # Verify the SV data.
    leo.step(0, 10)
    ret = btInterface.getStateVariables([objID])
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
    # Start the necessary services.
    clerk, ctrl, clacks = startAzrael('ZeroMQ')

    # Instantiate Leonard.
    btInterface.initSVDB(reset=True)
    leonard = clsLeonard()
    leonard.setup()

    # Constants and parameters for this test.
    templateID = '_templateCube'.encode('utf8')

    # Create a cube (a cube always exists in Azrael's template database).
    ok, id_0 = ctrl.spawn(templateID, pos=[0, 0, 0], vel=[0, 0, 0])
    assert ok

    # Advance the simulation by 1s and verify that nothing has moved.
    leonard.step(1.0, 60)
    ret = btInterface.getStateVariables([id_0])
    assert ret.ok
    assert np.array_equal(ret.data[id_0].position, [0, 0, 0])

    # Give the object a velocity.
    sv = bullet_data.BulletDataOverride(velocityLin=np.array([1, 0, 0]))
    assert btInterface.setStateVariables(id_0, sv).ok

    # Advance the simulation by another second and verify the objects have
    # moved accordingly.
    leonard.step(1.0, 60)
    ret = btInterface.getStateVariables([id_0])
    assert ret.ok
    assert 0.9 <= ret.data[id_0].position[0] < 1.1
    assert ret.data[id_0].position[1] == ret.data[id_0].position[2] == 0

    # Shutdown the services.
    stopAzrael(clerk, clacks)
    print('Test passed')


@pytest.mark.parametrize('clsLeonard', allEngines)
def test_move_two_objects_no_collision(clsLeonard):
    """
    Same as previous test but with two objects.
    """
    # Start the necessary services.
    clerk, ctrl, clacks = startAzrael('ZeroMQ')

    # Instantiate Leonard.
    btInterface.initSVDB(reset=True)
    leonard = clsLeonard()
    leonard.setup()

    # Constants and parameters for this test.
    templateID = '_templateCube'.encode('utf8')

    # Create two cubic objects.
    ok, id_0 = ctrl.spawn(templateID, pos=[0, 0, 0], vel=[1, 0, 0])
    assert ok
    ok, id_1 = ctrl.spawn(templateID, pos=[0, 10, 0], vel=[0, -1, 0])
    assert ok

    # Advance the simulation by 1s and query the states of both objects.
    leonard.step(1.0, 60)
    ret = btInterface.getStateVariables([id_0])
    assert ret.ok
    pos_0 = ret.data[id_0].position
    ret = btInterface.getStateVariables([id_1])
    assert ret.ok
    pos_1 = ret.data[id_1].position

    # Verify that the objects have moved according to their initial velocity.
    assert pos_0[1] == pos_0[2] == 0
    assert pos_1[0] == pos_1[2] == 0
    assert 0.9 <= pos_0[0] <= 1.1
    assert 8.9 <= pos_1[1] <= 9.1

    # Shutdown the services.
    stopAzrael(clerk, clacks)
    print('Test passed')


def test_worker_respawn():
    """
    Ensure the objects move correctly even though the Workers will restart
    themselves after every step.

    The test code is similar to ``test_move_two_objects_no_collision``.
    """
    # Start the necessary services.
    clerk, ctrl, clacks = startAzrael('ZeroMQ')

    # Instantiate Leonard.
    leonard = azrael.leonard.LeonardBulletSweepingMultiMT()
    leonard.workerStepsUntilQuit = (1, 10)
    leonard.setup()

    # Constants and parameters for this test.
    templateID = '_templateCube'.encode('utf8')

    # Create two cubic objects.
    ok, id_0 = ctrl.spawn(templateID, pos=[0, 0, 0], vel=[1, 0, 0])
    assert ok
    ok, id_1 = ctrl.spawn(templateID, pos=[0, 10, 0], vel=[0, -1, 0])
    assert ok

    # Advance the simulation by 1s, but use many small time steps. This ensures
    # that the Workers will restart themselves many times.
    for ii in range(60):
        leonard.step(1.0 / 60, 1)

    # Query the states of both objects.
    ret = btInterface.getStateVariables([id_0])
    assert ret.ok
    pos_0 = ret.data[id_0].position
    ret = btInterface.getStateVariables([id_1])
    assert ret.ok
    pos_1 = ret.data[id_1].position

    # Verify that the objects have moved according to their initial velocity.
    assert pos_0[1] == pos_0[2] == 0
    assert pos_1[0] == pos_1[2] == 0
    assert 0.9 <= pos_0[0] <= 1.1
    assert 8.9 <= pos_1[1] <= 9.1

    # Shutdown the services.
    stopAzrael(clerk, clacks)
    print('Test passed')


def test_sweeping_2objects():
    """
    Ensure the Sweeping algorithm finds the correct sets.

    The algorithm takes a list of dictionarys and returns a list of lists.

    The input dictionary each contains the AABB coordinates. The output list
    contains the set of overlapping AABBs.
    """
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
    # Reset the SV database and instantiate a Leonard.
    btInterface.initSVDB(reset=True)
    leo = azrael.leonard.LeonardBase()
    leo.setup()

    # Create several objects for this test.
    all_id = [int2id(_) for _ in range(10)]

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
    for objID, sv in zip(all_id, SVs):
        assert btInterface.spawn(objID, sv, np.int64(1).tostring(), 1.0).ok
    del SVs

    # Retrieve all SVs as Leonard does.
    leo.step(0, 60)
    assert len(all_id) == len(leo.allObjects)

    def ccsWrapper(IDs_hr, expected_hr):
        """
        Assert that the ``IDs_hr`` were split into the ``expected_hr`` lists.

        This is merely a convenience wrapper to facilitate readable tests.

        This wrapper converts the human readable entries in ``IDs_hr``  into
        the internally used binary format. It then passes this new list, along
        with the corresponding SVs, to the collision detection algorithm.
        Finally, it converts the returned list of object sets back into human
        readable list of object sets and compares them for equality.
        """
        # Convert the human readable IDs to the binary format.
        test_objIDs = [int2id(_) for _ in IDs_hr]

        # Compile the set of SVs for curIDs.
        sv = [leo.allObjects[_] for _ in test_objIDs]
        aabb = [leo.allAABBs[_] for _ in test_objIDs]

        # Determine the list of potential collision sets.
        ret = azrael.leonard.computeCollisionSetsAABB(test_objIDs, sv, aabb)
        assert ret.ok

        # Convert the IDs in res back to human readable format.
        res_hr = [[id2int(_) for _ in __] for __ in ret.data]

        # Convert the reference data to a sorted list of sets.
        expected_hr = sorted([set(_) for _ in expected_hr])
        res_hr = sorted([set(_) for _ in res_hr])

        # Return the equality of the two list of lists.
        assert expected_hr == res_hr

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
    # Convenience.
    vg = azrael.vectorgrid

    # Start the necessary services.
    clerk, ctrl, clacks = startAzrael('ZeroMQ')

    # Instantiate Leonard.
    btInterface.initSVDB(reset=True)
    leonard = clsLeonard()
    leonard.setup()

    # Constants and parameters for this test.
    templateID = '_templateCube'.encode('utf8')

    # Create a cube (a cube always exists in Azrael's template database).
    ok, id_0 = ctrl.spawn(templateID, pos=[0, 0, 0], vel=[0, 0, 0])
    assert ok

    # Advance the simulation by 1s and verify that nothing has moved.
    leonard.step(1.0, 60)
    ret = btInterface.getStateVariables([id_0])
    assert ret.ok
    assert np.array_equal(ret.data[id_0].position, [0, 0, 0])

    # Define a force grid.
    assert vg.defineGrid(name='force', elDim=3, granularity=1).ok

    # Specify a non-zero value somewhere away from the object. This means the
    # object must still not move.
    pos = np.array([1, 2, 3], np.float64)
    value = np.ones(3, np.float64)
    assert vg.setValue('force', pos, value).ok

    # Step the simulation and verify the object remained where it was.
    leonard.step(1.0, 60)
    ret = btInterface.getStateVariables([id_0])
    assert ret.ok
    assert np.array_equal(ret.data[id_0].position, [0, 0, 0])

    # Specify a grid value of 1 Newton in x-direction.
    pos = np.array([0, 0, 0], np.float64)
    value = np.array([1, 0, 0], np.float64)
    assert vg.setValue('force', pos, value).ok

    # Step the simulation and verify the object moved accordingly.
    leonard.step(1.0, 60)

    ret = btInterface.getStateVariables([id_0])
    assert ret.ok
    assert 0.4 <= ret.data[id_0].position[0] < 0.6
    assert ret.data[id_0].position[1] == ret.data[id_0].position[2] == 0

    # Shutdown the services.
    stopAzrael(clerk, clacks)
    print('Test passed')


def test_create_work_package_without_objects():
    """
    Create, fetch, update, and count Bullet work packages.

    This test does not insert any objects into the simulation. It only tests
    the general functionality to add, retrieve, and update work packages.
    """
    # Reset the SV database and instantiate a Leonard.
    btInterface.initSVDB(reset=True)
    leo = azrael.leonard.LeonardBulletSweepingMultiST()
    worker = azrael.leonard.LeonardBulletSweepingMultiMTWorker(1, 100000)

    # The token to use for this test.
    token = 1

    # There must not be any work packages yet.
    ret = leo.countWorkPackages(token)
    assert (ret.ok, ret.data) == (True, 0)

    # This call is invalid because the IDs must be a non-empty list.
    assert not leo.createWorkPackage([], token, 1, 2).ok

    # This call is invalid because the Leo has not object with this ID
    assert not leo.createWorkPackage([10], token, 1, 2).ok

    # There must still not be any work packages.
    ret = leo.countWorkPackages(token)
    assert (ret.ok, ret.data) == (True, 0)

    # Test data.
    data_0 = bullet_data.BulletData(imass=1)
    id_1, id_2 = int2id(1), int2id(2)
    templateID = np.int64(1).tostring()
    aabb, dt, maxsteps = 1, 2, 3 

    # Add two new objects to Leonard.
    assert btInterface.spawn(id_1, data_0, templateID, aabb).ok
    assert btInterface.spawn(id_2, data_0, templateID, aabb).ok
    leo.processCommandsAndSync()

    # Create a work package for two object IDs. The WPID must be 1.
    ret = leo.createWorkPackage([id_1], token, dt, maxsteps)
    assert (ret.ok, ret.data) == (True, 1)

    # There must now be exactly one work package.
    ret = leo.countWorkPackages(token)
    assert (ret.ok, ret.data) == (True, 1)

    # Create a second WP. This one must have WPID=2.
    ret = leo.createWorkPackage([id_2], token, dt, maxsteps)
    assert (ret.ok, ret.data) == (True, 2)

    # There must now be exactly two work packages.
    ret = leo.countWorkPackages(token)
    assert (ret.ok, ret.data) == (True, 2)

    # Attempt to fetch a non-existing ID. This must fail and the number of Work
    # Packages must remain at 2.
    assert not worker.getWorkPackage(0).ok
    ret = leo.countWorkPackages(token)
    assert (ret.ok, ret.data) == (True, 2)

    # Retrieve first WP. It must return a list with one entry.
    ret = worker.getWorkPackage(1)
    assert (ret.ok, len(ret.data['wpdata'])) == (True, 1)
    meta = ret.data['wpmeta']
    assert (meta.token, meta.dt, meta.maxsteps) == (token, dt, maxsteps)

    # There must still be two work packages because none has been updated yet.
    ret = leo.countWorkPackages(token)
    assert (ret.ok, ret.data) == (True, 2)

    z = [0, 0, 0]
    WPData = azrael.leonard.WPData
    newWP = [WPData(id_1, data_0.toJsonDict(), z, z)]
    del z

    # Update a non-existing work package. The newWP argument is irrelevant
    # for this test.
    assert not worker.updateWorkPackage(10, token, newWP).ok
    ret = leo.countWorkPackages(token)
    assert (ret.ok, ret.data) == (True, 2)

    # The WP count must be zero for an invalid token value.
    ret = leo.countWorkPackages(token + 1)
    assert (ret.ok, ret.data) == (True, 0)

    # Update the first WP. Once again, the newWP argument is irrelevant for
    # this test.
    assert worker.updateWorkPackage(1, token, newWP).ok
    ret = leo.countWorkPackages(token)
    assert (ret.ok, ret.data) == (True, 1)

    # Try to update the same WP once more. This must fail since the WPID was
    # already updated.
    assert not worker.updateWorkPackage(1, token, newWP).ok
    ret = leo.countWorkPackages(token)
    assert (ret.ok, ret.data) == (True, 1)

    # Update (and thus mark as completed) the other work package.
    assert worker.updateWorkPackage(2, token, newWP).ok
    ret = leo.countWorkPackages(token)
    assert (ret.ok, ret.data) == (True, 0)

    print('Test passed')


def test_create_work_package_with_objects():
    """
    Create, fetch, and update Bullet work packages.

    Similar to test_create_work_package_without_objects but now the there are
    actual objects in the simulation.
    """
    # Reset the SV database and instantiate a Leonard.
    btInterface.initSVDB(reset=True)
    leo = azrael.leonard.LeonardBulletSweepingMultiST()
    worker = azrael.leonard.LeonardBulletSweepingMultiMTWorker(1, 100000)
    leo.setup()

    # The token to use in this test.
    token = 1

    # Convenience.
    data_1 = bullet_data.BulletData(imass=1)
    data_2 = bullet_data.BulletData(imass=2)
    data_3 = bullet_data.BulletData(imass=3)
    templateID = np.int64(1).tostring()
    aabb = 1
    id_1, id_2, id_3 = int2id(1), int2id(2), int2id(3)
    
    # Spawn new objects.
    assert btInterface.spawn(id_1, data_1, templateID, aabb)
    assert btInterface.spawn(id_2, data_2, templateID, aabb)
    assert btInterface.spawn(id_3, data_3, templateID, aabb)
    leo.processCommandsAndSync()

    # Add ID1 to the WP. The WPID must be 1.
    ret = leo.createWorkPackage([id_1], token, dt=1, maxsteps=2)
    assert (ret.ok, ret.data) == (True, 1)
    wpid_1 = ret.data

    # Add ID1 and ID2 to the second WP. The WPID must be 2.
    ret = leo.createWorkPackage([id_1, id_2], token, dt=3, maxsteps=4)
    assert (ret.ok, ret.data) == (True, 2)
    wpid_2 = ret.data

    # Retrieve the first work package.
    ret = worker.getWorkPackage(wpid_1)
    assert (ret.ok, len(ret.data['wpdata'])) == (True, 1)
    data = ret.data['wpdata']
    meta = ret.data['wpmeta']
    assert (meta.token, meta.dt, meta.maxsteps) == (token, 1, 2)
    assert data[0].id == id_1
    assert data[0].sv == data_1
    assert np.array_equal(data[0].central_force, [0, 0, 0])

    # Retrieve the second work package.
    ret = worker.getWorkPackage(wpid_2)
    data = ret.data['wpdata']
    meta = ret.data['wpmeta']
    assert (meta.token, meta.dt, meta.maxsteps) == (token, 3, 4)
    assert (ret.ok, len(data)) == (True, 2)
    assert (data[0].id, data[1].id) == (id_1, id_2)
    assert (data[0].sv, data[1].sv) == (data_1, data_2)
    assert np.array_equal(data[0].central_force, [0, 0, 0])
    assert np.array_equal(data[1].central_force, [0, 0, 0])

    # Create a new SV data to replace the old one.
    data_4 = bullet_data.BulletData(imass=4)
    z = [0, 0, 0]
    WPData = azrael.leonard.WPData
    newWP = [WPData(id_1, data_4.toJsonDict(), z, z)]
    del z

    # Leonard must still have the original object.
    assert leo.allObjects[id_1] == data_1

    # Update the first work package with the wrong token. The call must fail
    # and the data in Leonard must remain intact.
    assert not worker.updateWorkPackage(wpid_1, token + 1, newWP).ok
    assert leo.allObjects[id_1] == data_1

    # Update the first work package with the correct token. This must succeed
    # and update the value in Leonard's instance variable.
    assert worker.updateWorkPackage(wpid_1, token, newWP).ok
    assert leo.pullCompletedWorkPackages().ok
    assert leo.allObjects[id_1] == data_4

    print('Test passed')


if __name__ == '__main__':
    test_create_work_package_with_objects()
    test_create_work_package_without_objects()

    test_worker_respawn()
    test_sweeping_2objects()
    test_sweeping_3objects()
    test_computeCollisionSetsAABB(0)

    for _engine in allEngines:
        print('\nEngine: {}'.format(_engine))
        test_force_grid(_engine)
        test_setStateVariables_advanced(_engine)
        test_setStateVariables_basic(_engine)
        test_move_single_object(_engine)
        test_move_two_objects_no_collision(_engine)
