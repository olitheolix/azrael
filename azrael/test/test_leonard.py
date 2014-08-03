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

import numpy as np

ipshell = IPython.embed


def killall():
    subprocess.call(['pkill', 'killme'])


@pytest.mark.parametrize('clsLeonard',
   [azrael.leonard.LeonardBase,
    azrael.leonard.LeonardBaseWorkpackages,
    azrael.leonard.LeonardBaseWPRMQ,
    azrael.leonard.LeonardBulletMonolithic])
def test_move_single_object(clsLeonard):
    """
    Create a single object and ensure Leonard moves it according
    to the initial speed.
    """
    killall()
    
    # Start server and client.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    clacks = azrael.clacks.ClacksServer()
    clacks.start()

    # Get a controller.
    ctrl = azrael.controller.ControllerBase()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    leonard = clsLeonard()
    leonard.setup()
    
    # Create a spherical object (a default spherical object exists by default
    # and is associated with objdesc=2).
    objdesc = np.int64(2).tostring()
    id_0, ok = ctrl.spawn('Echo', objdesc, [0, 0, 0], [0, 0, 0])
    assert ok

    # Advance the simulation by 1s and check that nothing has moved.
    leonard.step(1, 60)
    sv, ok = btInterface.get(id_0)
    assert ok
    sv = btInterface.unpack(np.fromstring(sv))
    np.array_equal(sv.position, [0, 0, 0])

    # Give the object a velocity.
    sv, ok = btInterface.get(id_0)
    assert ok
    sv = btInterface.unpack(np.fromstring(sv))
    sv.velocityLin[:] = [1, 0, 0]
    sv = btInterface.pack(sv).tostring()
    assert btInterface.update(id_0, sv)

    # Advance the simulation by another second and test if the object moved
    # accordingly.
    leonard.step(1, 60)
    sv, ok = btInterface.get(id_0)
    assert ok
    sv = btInterface.unpack(np.fromstring(sv))
    assert 0.9 <= sv.position[0] < 1.1
    assert sv.position[1] == sv.position[2] == 0

    # Shutdown.
    clacks.terminate()
    clerk.terminate()
    clacks.join()
    clerk.join()

    print('Test passed')


@pytest.mark.parametrize('clsLeonard',
   [azrael.leonard.LeonardBase,
    azrael.leonard.LeonardBaseWorkpackages,
    azrael.leonard.LeonardBaseWPRMQ,
    azrael.leonard.LeonardBulletMonolithic])
def test_move_two_objects_no_collision(clsLeonard):
    """
    Create two objects with different initial velocity and make sure they move
    accordingly.
    """
    killall()
    
    # Start server and client.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    clacks = azrael.clacks.ClacksServer()
    clacks.start()

    # Get a controller.
    ctrl = azrael.controller.ControllerBase()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    # Instantiate Leonard.
    leonard = clsLeonard()
    leonard.setup()
    
    # Create two spherical object.
    objdesc = np.int64(2).tostring()
    id_0, ok = ctrl.spawn('Echo', objdesc, [0, 0, 0], [1, 0, 0])
    assert ok
    id_1, ok = ctrl.spawn('Echo', objdesc, [0, 10, 0], [0, -1, 0])
    assert ok

    # Advance the simulation by one second and test if the objects moved
    # accordingly.
    leonard.step(1, 60)
    sv, ok = btInterface.get(id_0)
    assert ok
    pos_0 = btInterface.unpack(np.fromstring(sv)).position
    sv, ok = btInterface.get(id_1)
    assert ok
    pos_1 = btInterface.unpack(np.fromstring(sv)).position
    
    assert pos_0[1] == pos_0[2] == 0
    assert 0.9 <= pos_0[0] <= 1.1
    assert pos_1[0] == pos_1[2] == 0
    assert pos_1[1] < 9.6

    # Shutdown.
    clacks.terminate()
    clerk.terminate()
    clacks.join()
    clerk.join()

    print('Test passed')


@pytest.mark.parametrize('clsWorker',
   [azrael.leonard.LeonardRMQWorker,
    azrael.leonard.LeonardRMQWorkerBullet])
def test_multiple_workers(clsWorker):
    """
    Create several objects on parallel trajectories and advance their positions
    with multiple LeonardWorkers.
    """
    killall()
    
    # Start server and client.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    clacks = azrael.clacks.ClacksServer()
    clacks.start()

    # Get a controller.
    ctrl = azrael.controller.ControllerBase()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    # Specify the number of objects and workers.
    num_workers, num_objects = 10, 20
    assert num_objects >= num_workers

    # Instantiate Leonard.
    leonard = azrael.leonard.LeonardBaseWPRMQ(num_workers, clsWorker)
    leonard.setup()
    
    # Create several spherical objects.
    objdesc = np.int64(2).tostring()
    list_ids = []

    for ii in range(num_objects):
        cur_id, ok = ctrl.spawn('Echo', objdesc, pos=[0, 10 * ii, 0],
                                vel=[1,0, 0])
        assert ok
        list_ids.append(cur_id)
    del cur_id, ok

    # Advance the simulation by one second.
    leonard.step(1, 60)

    # All objects must have moved the same distance.
    for ii, cur_id in enumerate(list_ids):
        sv, ok = btInterface.get(cur_id)
        assert ok
        cur_pos = btInterface.unpack(np.fromstring(sv)).position
        assert 0.9 <= cur_pos[0] <= 1.1
        assert cur_pos[1] == 10 * ii
        assert cur_pos[2] == 0

    # All workers should have been utilised.
    assert len(leonard.used_workers) == num_workers

    # Shutdown.
    clacks.terminate()
    clerk.terminate()
    clacks.join()
    clerk.join()

    print('Test passed')


if __name__ == '__main__':
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
