import sys
import time
import pytest
import IPython
import subprocess
import azrael.clerk
import azrael.clacks
import azrael.leonard
import azrael.controller
import azrael.bullet.btInterface as btInterface
import azrael.bullet.bullet_data as bullet_data

import numpy as np

ipshell = IPython.embed


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

    # Start Clerk and instantiate Controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()

    if ctrl_type == 'ZeroMQ':
        # Instantiate the ZeroMQ version of the Controller.
        ctrl = azrael.controller.ControllerBase()
        ctrl.setupZMQ()
        ctrl.connectToClerk()

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


@pytest.mark.parametrize(
    'clsLeonard',
    [azrael.leonard.LeonardBase,
     azrael.leonard.LeonardBaseWorkpackages,
     azrael.leonard.LeonardBaseWPRMQ,
     azrael.leonard.LeonardBulletMonolithic])
def test_move_single_object(clsLeonard):
    """
    Create a single object with non-zero initial speed and ensure Leonard moves
    it accordingly.
    """
    # Start the necessary services.
    clerk, ctrl, clacks = startAzrael('ZeroMQ')

    # Instantiate Leonard.
    leonard = clsLeonard()
    leonard.setup()

    # Constants and parameters for this test.
    templateID = '_templateCube'.encode('utf8')

    # Create a cube (a cube always exists in Azrael's template database).
    ok, id_0 = ctrl.spawn(None, templateID, pos=[0, 0, 0], vel=[0, 0, 0])
    assert ok

    # Advance the simulation by 1s and verify that nothing moved.
    leonard.step(1.0, 60)
    ok, sv = btInterface.getStateVariables([id_0])
    assert ok
    np.array_equal(sv[0].position, [0, 0, 0])

    # Give the object a velocity.
    ok, sv = btInterface.getStateVariables([id_0])
    assert ok
    sv[0].velocityLin[:] = [1, 0, 0]
    assert btInterface.update(id_0, sv[0])

    # Advance the simulation by 1s and verify the objects moved accordingly.
    leonard.step(1.0, 60)
    ok, sv = btInterface.getStateVariables([id_0])
    assert ok
    assert 0.9 <= sv[0].position[0] < 1.1
    assert sv[0].position[1] == sv[0].position[2] == 0

    # Shutdown the services.
    stopAzrael(clerk, clacks)
    print('Test passed')


@pytest.mark.parametrize(
    'clsLeonard',
    [azrael.leonard.LeonardBase,
     azrael.leonard.LeonardBaseWorkpackages,
     azrael.leonard.LeonardBaseWPRMQ,
     azrael.leonard.LeonardBulletMonolithic])
def test_move_two_objects_no_collision(clsLeonard):
    """
    Same as previous test but with two objects.
    """
    # Start the necessary services.
    clerk, ctrl, clacks = startAzrael('ZeroMQ')

    # Instantiate Leonard.
    leonard = clsLeonard()
    leonard.setup()

    # Constants and parameters for this test.
    templateID = '_templateCube'.encode('utf8')

    # Create two cubic objects.
    ok, id_0 = ctrl.spawn(None, templateID, pos=[0, 0, 0], vel=[1, 0, 0])
    assert ok
    ok, id_1 = ctrl.spawn(None, templateID, pos=[0, 10, 0], vel=[0, -1, 0])
    assert ok

    # Advance the simulation by 1s and verify the objects moved accordingly.
    leonard.step(1.0, 60)
    ok, sv = btInterface.getStateVariables([id_0])
    assert ok
    pos_0 = sv[0].position

    ok, sv = btInterface.getStateVariables([id_1])
    assert ok
    pos_1 = sv[0].position

    assert pos_0[1] == pos_0[2] == 0
    assert pos_1[0] == pos_1[2] == 0
    assert 0.9 <= pos_0[0] <= 1.1
    assert 8.9 <= pos_1[1] <= 9.1

    # Shutdown the services.
    stopAzrael(clerk, clacks)
    print('Test passed')


@pytest.mark.parametrize(
    'clsWorker',
    [azrael.leonard.LeonardRMQWorker,
     azrael.leonard.LeonardRMQWorkerBullet])
def test_multiple_workers(clsWorker):
    """
    Create several objects on parallel trajectories. Use multiple
    instances of LeonardWorkers.
    """
    # Start the necessary services.
    clerk, ctrl, clacks = startAzrael('ZeroMQ')

    # Constants and parameters for this test.
    templateID = '_templateCube'.encode('utf8')
    num_workers, num_objects = 10, 20
    assert num_objects >= num_workers

    # Instantiate Leonard.
    leonard = azrael.leonard.LeonardBaseWPRMQ(num_workers, clsWorker)
    leonard.setup()

    # Create several cubic objects.
    templateID = '_templateCube'.encode('utf8')
    list_ids = []
    for ii in range(num_objects):
        ok, cur_id = ctrl.spawn(
            None, templateID, pos=[0, 10 * ii, 0], vel=[1, 0, 0])
        assert ok
        list_ids.append(cur_id)
    del cur_id, ok

    # Advance the simulation by one second.
    leonard.step(1.0, 60)

    # All objects must have moved the same distance.
    for ii, cur_id in enumerate(list_ids):
        ok, sv = btInterface.getStateVariables([cur_id])
        assert ok
        cur_pos = sv[0].position
        assert 0.9 <= cur_pos[0] <= 1.1
        assert cur_pos[1] == 10 * ii
        assert cur_pos[2] == 0

    # All workers should have been utilised.
    assert len(leonard.used_workers) == num_workers

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
    sweeping = azrael.leonard.sweeping

    aabbs = [{'x': [4, 5], 'y': [3.5, 4], 'z': [5, 6.5]},
             {'x': [1, 2], 'y': [3.5, 4], 'z': [5, 6.5]}]
    aabbs = [{'aabb': _} for _ in aabbs]
    res = sweeping(aabbs, 'x')
    assert sorted(res) == sorted([set([1]), set([0])])
    
    aabbs = [{'x': [2, 4], 'y': [3.5, 4], 'z': [5, 6.5]},
             {'x': [1, 5], 'y': [3.5, 4], 'z': [5, 6.5]}]
    aabbs = [{'aabb': _} for _ in aabbs]
    res = sweeping(aabbs, 'x')
    assert sorted(res) == sorted([set([1, 0])])
    
    aabbs = [{'x': [1, 5], 'y': [3.5, 4], 'z': [5, 6.5]},
             {'x': [2, 4], 'y': [3.5, 4], 'z': [5, 6.5]}]
    aabbs = [{'aabb': _} for _ in aabbs]
    res = sweeping(aabbs, 'x')
    assert sorted(res) == sorted([set([1, 0])])
    
    aabbs = [{'x': [1, 5], 'y': [3.5, 4], 'z': [5, 6.5]},
             {'x': [2, 4], 'y': [3.5, 4], 'z': [5, 6.5]}]
    aabbs = [{'aabb': _} for _ in aabbs]
    res = sweeping(aabbs, 'x')
    assert sorted(res) == sorted([set([1, 0])])

    # Test the other dimensions.
    aabbs = [{'x': [1, 5], 'y': [1, 5], 'z': [1, 5]},
             {'x': [2, 4], 'y': [2, 4], 'z': [2, 4]}]
    aabbs = [{'aabb': _} for _ in aabbs]
    assert sweeping(aabbs, 'x') == sweeping(aabbs, 'y')
    assert sweeping(aabbs, 'x') == sweeping(aabbs, 'z')

    print('Test passed')
    
    
def test_sweeping_3objects():
    """
    Same as test_sweeping_2objects but with three objects.
    """
    sweeping = azrael.leonard.sweeping

    # Three non-overlapping objects.
    aabbs = [{'x': [1, 2]}, {'x': [3, 4]}, {'x': [5, 6]}]
    aabbs = [{'aabb': _} for _ in aabbs]
    res = sweeping(aabbs, 'x')
    assert sorted(res) == sorted([set([0]), set([1]), set([2])])
    
    # First and second overlap.
    aabbs = [{'x': [1, 2]}, {'x': [1.5, 4]}, {'x': [5, 6]}]
    aabbs = [{'aabb': _} for _ in aabbs]
    res = sweeping(aabbs, 'x')
    assert sorted(res) == sorted([set([0, 1]), set([2])])
    
    # First overlaps with second, second overlaps with third, but third does
    # not overlap with first. The algorithm must nevertheless return all three
    # in a single set.
    aabbs = [{'x': [1, 2]}, {'x': [1.5, 4]}, {'x': [3, 6]}]
    aabbs = [{'aabb': _} for _ in aabbs]
    res = sweeping(aabbs, 'x')
    assert sorted(res) == sorted([set([0, 1, 2])])
    
    # First and third overlap.
    aabbs = [{'x': [1, 2]}, {'x': [10, 11]}, {'x': [0, 1.5]}]
    aabbs = [{'aabb': _} for _ in aabbs]
    res = sweeping(aabbs, 'x')
    assert sorted(res) == sorted([set([0, 2]), set([1])])
    
    print('Test passed')
    

if __name__ == '__main__':
    test_sweeping_2objects()
    test_sweeping_3objects()
    sys.exit()
    test_multiple_workers(azrael.leonard.LeonardRMQWorker)
    test_multiple_workers(azrael.leonard.LeonardRMQWorkerBullet)
    test_move_single_object(azrael.leonard.LeonardBaseWPRMQ)
    test_move_two_objects_no_collision(azrael.leonard.LeonardBaseWPRMQ)
    test_move_single_object(azrael.leonard.LeonardBaseWorkpackages)
    test_move_two_objects_no_collision(azrael.leonard.LeonardBaseWorkpackages)
    test_move_single_object(azrael.leonard.LeonardBulletMonolithic)
    test_move_two_objects_no_collision(azrael.leonard.LeonardBulletMonolithic)
    test_move_single_object(azrael.leonard.LeonardBase)
    test_move_two_objects_no_collision(azrael.leonard.LeonardBase)
