import json
import pytest
import time
import azrael.igor
import azrael.aztypes
import azrael.leonard
import azrael.datastore
import azrael.vectorgrid
import azrael.eventstore

import numpy as np
import unittest.mock as mock
import azrael.leo_api as leoAPI

from azrael.aztypes import RetVal
from IPython import embed as ipshell
from azrael.test.test import getCSBox, getCSSphere, getCSEmpty
from azrael.test.test import getP2P, getLeonard, getRigidBody


# List all available engines. This simplifies the parameterisation of those
# tests that must pass for all engines.
allEngines = [
    azrael.leonard.LeonardBase,
    azrael.leonard.LeonardBullet,
    azrael.leonard.LeonardSweeping,
    azrael.leonard.LeonardDistributedZeroMQ,
]


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
        azrael.datastore.init(flush=True)

    def teardown_method(self, method):
        azrael.test.test.shutdownLeonard()

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
    def test_setRigidBody_basic(self, clsLeonard):
        """
        Spawn an object, specify its State Variables explicitly, and verify the
        change propagated through Azrael.
        """
        # Get a Leonard instance.
        leo = getLeonard(clsLeonard)

        # Parameters and constants for this test.
        id_1 = '1'

        # Body data.
        p = np.array([1, 2, 5])
        vl = np.array([8, 9, 10.5])
        vr = vl + 1
        body = {'position': p, 'velocityLin': vl, 'velocityRot': vr}
        del p, vl, vr

        # Spawn a new object. It must have ID=1.
        assert leoAPI.addCmdSpawn([(id_1, getRigidBody())]).ok

        # Update the object's body.
        assert leoAPI.addCmdModifyBodyState(id_1, body).ok

        # Sync the commands to Leonard.
        leo.processCommandsAndSync()

        # Verify that the attributes were correctly updated.
        ret = leo.allBodies[id_1]
        assert np.array_equal(ret.position, body['position'])
        assert np.array_equal(ret.velocityLin, body['velocityLin'])
        assert np.array_equal(ret.velocityRot, body['velocityRot'])

    @pytest.mark.parametrize('clsLeonard', allEngines)
    def test_setRigidBody_advanced(self, clsLeonard):
        """
        Similar to test_setRigidBody_basic but modify the collision shape
        information as well, namely their mass- and type.
        """
        # Get a Leonard instance.
        leo = getLeonard(clsLeonard)

        # Parameters and constants for this test.
        cshape_box = {'1': getCSBox()}
        cshape_sphere = {'1': getCSSphere()}
        body = getRigidBody(imass=2, scale=3, cshapes=cshape_sphere)

        # Spawn an object.
        objID = '1'
        assert leoAPI.addCmdSpawn([(objID, body)]).ok
        del body

        # Verify the body data.
        leo.processCommandsAndSync()
        assert leo.allBodies[objID].imass == 2
        assert leo.allBodies[objID].scale == 3
        assert leo.allBodies[objID].cshapes == cshape_sphere

        # Update the body.
        cs_new = {'imass': 4, 'scale': 5, 'cshapes': cshape_box}
        assert leoAPI.addCmdModifyBodyState(objID, cs_new).ok

        # Verify the body data.
        leo.processCommandsAndSync()
        ret = leo.allBodies[objID]
        assert (ret.imass == 4) and (ret.scale == 5)
        assert ret.cshapes == cshape_box

    @pytest.mark.parametrize('clsLeonard', allEngines)
    def test_move_single_object(self, clsLeonard):
        """
        Create a single object with non-zero initial speed and ensure
        Leonard moves it accordingly.
        """
        # Get a Leonard instance.
        leo = getLeonard(clsLeonard)

        # Constants and parameters for this test.
        id_0 = '0'

        # Spawn an object.
        assert leoAPI.addCmdSpawn([(id_0, getRigidBody())]).ok

        # Advance the simulation by 1s and verify that nothing has moved.
        leo.step(1.0, 60)
        assert np.array_equal(leo.allBodies[id_0].position, [0, 0, 0])

        # Give the object a velocity.
        body = {'velocityLin': np.array([1, 0, 0])}
        assert leoAPI.addCmdModifyBodyState(id_0, body).ok
        del body

        # Advance the simulation by another second and verify the objects have
        # moved accordingly.
        leo.step(1.0, 60)
        body = leo.allBodies[id_0]
        assert 0.9 <= body.position[0] < 1.1
        assert body.position[1] == body.position[2] == 0

    @pytest.mark.parametrize('clsLeonard', allEngines)
    def test_move_two_objects_no_collision(self, clsLeonard):
        """
        Same as previous test but with two objects.
        """
        # Get a Leonard instance.
        leo = getLeonard(clsLeonard)

        # Constants and parameters for this test.
        id_0, id_1 = '0', '1'
        body_0 = getRigidBody(position=[0, 0, 0], velocityLin=[1, 0, 0])
        body_1 = getRigidBody(position=[0, 10, 0], velocityLin=[0, -1, 0])

        # Create two objects.
        tmp = [(id_0, body_0), (id_1, body_1)]
        assert leoAPI.addCmdSpawn(tmp).ok

        # Advance the simulation by 1s.
        leo.step(1.0, 60)

        # The objects must have moved according to their initial velocity.
        pos_0 = leo.allBodies[id_0].position
        pos_1 = leo.allBodies[id_1].position
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
        leo = getLeonard(clsLeonard)

        # Constants and parameters for this test.
        id_0 = '0'

        # Spawn one object.
        assert leoAPI.addCmdSpawn([(id_0, getRigidBody())]).ok

        # Advance the simulation by 1s and verify that nothing has moved.
        leo.step(1.0, 60)
        assert np.array_equal(leo.allBodies[id_0].position, [0, 0, 0])

        # Define a force grid.
        assert vg.defineGrid(name='force', vecDim=3, granularity=1).ok

        # Specify a non-zero value somewhere away from the object. This means
        # the object must still not move.
        pos = np.array([1, 2, 3], np.float64)
        value = np.ones(3, np.float64)
        assert vg.setValues('force', [(pos, value)]).ok

        # Step the simulation and verify the object remained where it was.
        leo.step(1.0, 60)
        assert np.array_equal(leo.allBodies[id_0].position, [0, 0, 0])

        # Specify a grid value of 1 Newton in x-direction.
        pos = np.array([0, 0, 0], np.float64)
        value = np.array([1, 0, 0], np.float64)
        assert vg.setValues('force', [(pos, value)]).ok

        # Step the simulation and verify the object moved accordingly.
        leo.step(1.0, 60)
        body = leo.allBodies[id_0]
        assert 0.4 <= body.position[0] < 0.6
        assert body.position[1] == body.position[2] == 0

    @pytest.mark.parametrize('clsLeonard', allEngines)
    def test_collision_contacts_mock(self, clsLeonard):
        """
        Create two touching objects and verify that Bullet dispatches the
        event. This test uses a mock to intercept the exact information to
        dispatch.
        """
        # Get a Leonard instance and verify it has an EventStore instance.
        leo = getLeonard(clsLeonard)
        assert hasattr(leo, 'events')

        # Install the mock.
        mock_es = mock.create_autospec(azrael.eventstore.EventStore)
        mock_es.publish.return_value = RetVal(True, None, None)
        leo.events = mock_es

        # Constants and parameters for this test.
        id_0, id_1 = '0', '1'

        # Step the empty simulation, spawn one object, step it again. Verify
        # that 'publish' is never called because no collisions have occurred.
        assert mock_es.publish.call_count == 0
        leo.step(1, 1)
        assert mock_es.publish.call_count == 0
        assert leoAPI.addCmdSpawn([(id_0, getRigidBody())]).ok
        assert mock_es.publish.call_count == 0
        leo.step(1, 1)
        assert mock_es.publish.call_count == 0

        # Duplicate the object at the same location. This implies they collide
        # and 'publish' must be triggered *after* stepping the simulation.
        assert leoAPI.addCmdSpawn([(id_1, getRigidBody())]).ok
        assert mock_es.publish.call_count == 0
        leo.step(1, 1)

        if clsLeonard == azrael.leonard.LeonardBase:
            # The Base class does not compute collisions and therefore must
            # never publish anything.
            assert mock_es.publish.call_count == 0
        else:
            assert mock_es.publish.call_count == 1

            # Unpack the keyword arguments with which 'publish' was called.
            _, kwargs = mock_es.publish.call_args

            # Verify the argument values.
            assert kwargs['topic'] == 'phys.collisions'
            msg = json.loads(kwargs['msg'].decode('utf8'))
            assert len(msg) == 1

            # Unpack the constutents of the one collision contact entry.
            bodyA, bodyB, colldata = msg[0]

            # Verify the IDs of the bodies that collided. Verify further that
            # each body has exactly one collision point. The collision point
            # itself we cannot check because it is difficult to
            # deterministically predict where Bullet will think they touch. As
            # such, we only verify that there are two contacts (one for each
            # object) and that it is a 3-Vector.
            assert bodyA == id_0, bodyB == id_1
            assert len(colldata) == 2
            assert len(colldata[0]) == len(colldata[1]) == 3

    @pytest.mark.parametrize('clsLeonard', allEngines)
    def test_collision_contacts_eventstore(self, clsLeonard):
        """
        Create two touching bodies and step the simulation. Verify the
        collision event via the event store API.
        """
        # Skip this test for LeonardBase because it does not emit any messages.
        if clsLeonard == azrael.leonard.LeonardBase:
            return

        # Instantiate the message store API and start it in a thread.
        es = azrael.eventstore.EventStore(topics=['#'])
        es.start()

        # Instantiate Leonard.
        leo = getLeonard(clsLeonard)

        # Spawn two identical objects and step the simulation.
        assert leoAPI.addCmdSpawn([('0', getRigidBody()), ('1', getRigidBody())]).ok
        leo.step(1, 1)

        # Wait for the message to arrive.
        for ii in range(10):
            time.sleep(0.1)
            if len(es.messages) > 0:
                break
            assert ii < 9
        ret = es.getMessages()
        assert ret.ok

        # Verify there is exactly one message. That message must have been
        # published to the 'phys.collisions' topic.
        assert len(ret.data) == 1
        topic, msg = ret.data[0]
        assert topic == 'phys.collisions'

        # The payload must be JSON.
        msg = json.loads(msg.decode('utf8'))

        # The payload is a list of lists. Since only one pair of objects must
        # have collided, that list must contain only one element.
        assert len(msg) == 1
        msg = msg[0]

        # The content of the list comprises the AIDs of the two objects first,
        # followed by information about the position of the collisions (which
        # we ignore here because we cannot safely predict their values).
        assert (msg[0] == '0') and (msg[1] == '1')

        # Stop the thread.
        es.stop()
        es.join()


class TestWorkerManager:
    @classmethod
    def setup_class(cls):
        pass

    @classmethod
    def teardown_class(cls):
        pass

    def setup_method(self, method):
        pass
        #azrael.datastore.init(flush=True)

    def teardown_method(self, method):
        azrael.test.test.shutdownLeonard()

    def test_workerManager_basic(self):
        """
        """
        # Convenience.
        m_workerCls = mock.MagicMock()
        m_worker = mock.MagicMock()
        m_workerCls.return_value = m_worker
        WM = azrael.leonard.WorkerManager

        # Number of workers and/or steps can be zero but not negative.
        with pytest.raises(AssertionError):
            WM(numWorkers=-1, minSteps=5, maxSteps=10, workerCls=m_workerCls)
        with pytest.raises(AssertionError):
            WM(numWorkers=1, minSteps=-5, maxSteps=10, workerCls=m_workerCls)
        with pytest.raises(AssertionError):
            WM(numWorkers=1, minSteps=5, maxSteps=-10, workerCls=m_workerCls)

        # 'minSteps' must be smaller or equal than 'maxSteps'.
        WM(numWorkers=1, minSteps=50, maxSteps=50, workerCls=m_workerCls)
        with pytest.raises(AssertionError):
            WM(numWorkers=1, minSteps=50, maxSteps=10, workerCls=m_workerCls)

        # Start a fleet of zero workers and verify that the WorkerManager did
        # not make any attempts to instantiate the WorkerCls.
        assert not m_workerCls.called
        wm = WM(numWorkers=0, minSteps=10, maxSteps=50, workerCls=m_workerCls)
        assert wm.workers == []
        wm.maintainFleet()
        assert not m_workerCls.called
        del m_worker

        # Start a fleet of two (mock) workers.
        m_workerCls.reset_mock()
        m_worker1, m_worker2 = mock.MagicMock(), mock.MagicMock()
        m_workerCls.side_effect = [m_worker1, m_worker2]
        assert not m_workerCls.called
        wm = WM(numWorkers=2, minSteps=10, maxSteps=50, workerCls=m_workerCls)
        assert wm.workers == [None, None]
        wm.maintainFleet()
        assert m_worker1.start.called
        assert m_worker2.start.called

    @mock.patch.object(azrael.leonard.os, 'kill')
    def test_workerManager_stop(self, m_oskill):
        """
        """
        WM = azrael.leonard.WorkerManager

        # Create mocked Workers, one alive, one already terminated.
        m_worker_alive, m_worker_dead = mock.MagicMock(), mock.MagicMock()
        m_worker_alive.is_alive.return_value = True
        m_worker_alive.pid = 1
        m_worker_dead.is_alive.return_value = False
        m_worker_dead.pid = 2

        # Create a WorkerManager and install a list of mocked Worker instances.
        m_workerCls = mock.MagicMock()
        wm = WM(numWorkers=2, minSteps=1, maxSteps=5, workerCls=m_workerCls)
        assert wm.workers == [None, None]
        wm.workers = [m_worker_alive, m_worker_dead]

        # Call the 'stop' method. This must first send SIGTERM to all children
        # still alive and then join them.
        assert m_oskill.call_count == 0
        wm.stopAll()
        assert m_worker_alive.is_alive.called
        assert m_worker_dead.is_alive.called
        assert m_oskill.call_count == 1
        assert m_oskill.called_with(m_worker_alive.pid, azrael.leonard.signal.SIGTERM)
        assert m_worker_alive.join.called
        assert m_worker_dead.join.called
        assert wm.workers == [None, None]

    def test_worker_respawn(self):
        """
        Ensure the objects move correctly even though the Workers will restart
        themselves after every step.

        The test code is similar to ``test_move_two_objects_no_collision``.
        """
        # Instantiate Leonard.
        leo = getLeonard(azrael.leonard.LeonardDistributedZeroMQ)

        # Define a force grid (not used in this test but prevents a plethora
        # of meaningless warning messages).
        vg = azrael.vectorgrid
        assert vg.defineGrid(name='force', vecDim=3, granularity=1).ok

        # Constants and parameters for this test.
        id_0, id_1 = '0', '1'
        cshapes = {'cssphere': getCSSphere(radius=1)}

        # Define two bodies and create the objects.
        body_0 = getRigidBody(
            position=[0, 0, 0], velocityLin=[1, 0, 0], cshapes=cshapes)
        body_1 = getRigidBody(
            position=[0, 10, 0], velocityLin=[0, -1, 0], cshapes=cshapes)
        tmp = [(id_0, body_0), (id_1, body_1)]
        assert leoAPI.addCmdSpawn(tmp).ok

        # Advance the simulation by 1s via many small time steps. This
        # ensures the Workers will restart themselves frequently.
        for ii in range(60):
            leo.step(1.0 / 60, 1)

        # The objects must have moved according to their initial velocity.
        pos_0 = leo.allBodies[id_0].position
        pos_1 = leo.allBodies[id_1].position
        assert pos_0[1] == pos_0[2] == 0
        assert pos_1[0] == pos_1[2] == 0
        assert 0.9 <= pos_0[0] <= 1.1
        assert 8.9 <= pos_1[1] <= 9.1


class TestLeonardOther:
    @classmethod
    def setup_class(cls):
        cls.igor = azrael.igor.Igor()

    @classmethod
    def teardown_class(cls):
        pass

    def setup_method(self, method):
        assert azrael.vectorgrid.deleteAllGrids().ok
        azrael.datastore.init(flush=True)

    def teardown_method(self, method):
        azrael.test.test.shutdownLeonard()

    def test_createWorkPackages(self):
        """
        Create a Work Package and verify its content.
        """
        # Get a Leonard instance.
        leo = getLeonard(azrael.leonard.LeonardDistributedZeroMQ)

        # Constants.
        id_1, id_2 = '1', '2'
        dt, maxsteps = 2, 3

        # Invalid call: list of IDs must not be empty.
        assert not leo.createWorkPackage([], dt, maxsteps).ok

        # Invalid call: Leonard has no object with ID 10.
        assert not leo.createWorkPackage([10], dt, maxsteps).ok

        # Test data.
        body_1 = getRigidBody(imass=1)
        body_2 = getRigidBody(imass=2)

        # Add two new objects to Leonard.
        tmp = [(id_1, body_1), (id_2, body_2)]
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
        WPDataOut = azrael.aztypes.WPDataOut
        WPMeta = azrael.aztypes.WPMeta
        data = [WPDataOut(*_) for _ in ret.data['wpdata']]
        meta = WPMeta(*ret.data['wpmeta'])
        assert (meta.dt, meta.maxsteps) == (dt, maxsteps)
        assert (ret.ok, len(data)) == (True, 2)
        assert (data[0].aid, data[1].aid) == (id_1, id_2)
        assert getRigidBody(*data[0].rbs) == body_1
        assert getRigidBody(*data[1].rbs) == body_2
        assert np.array_equal(data[0].force, [0, 0, 0])
        assert np.array_equal(data[1].force, [0, 0, 0])

    def test_updateLocalCache(self):
        """
        Update the local object cache in Leonard based on a Work Package.
        """
        # Get a Leonard instance.
        leo = getLeonard(azrael.leonard.LeonardDistributedZeroMQ)

        # Convenience.
        body_1 = getRigidBody(imass=1)
        body_2 = getRigidBody(imass=2)
        id_1, id_2 = '1', '2'

        # Spawn new objects.
        tmp = [(id_1, body_1), (id_2, body_2)]
        assert leoAPI.addCmdSpawn(tmp).ok
        leo.processCommandsAndSync()

        # Create a new State Vector to replace the old one.
        body_3 = getRigidBody(imass=4, position=[1, 2, 3])
        newWP = [azrael.aztypes.WPDataRet(id_1, body_3)]

        # Check the state variables for objID=id_1 before and after the update.
        assert getRigidBody(*leo.allBodies[id_1]) == body_1
        leo.updateLocalCache(newWP, None)
        assert getRigidBody(*leo.allBodies[id_1]) == body_3

    def test_processCommandQueue(self):
        """
        Create commands to spawn-, delete, and modify objects or their booster
        values. Then verify that ``processCommandQueue`` corrently updates
        Leonard's object cache.
        """
        # Get a Leonard instance.
        leo = getLeonard(azrael.leonard.LeonardDistributedZeroMQ)

        # Convenience.
        body_1 = getRigidBody(imass=1)
        body_2 = getRigidBody(imass=2)
        id_1, id_2 = '1', '2'

        # Cache must be empty.
        assert len(leo.allBodies) == len(leo.allForces) == 0

        # Spawn two objects.
        tmp = [(id_1, body_1), (id_2, body_2)]
        assert leoAPI.addCmdSpawn(tmp).ok
        leo.processCommandsAndSync()

        # Verify the local cache (forces and torques must default to zero).
        assert getRigidBody(*leo.allBodies[id_1]) == body_1
        assert getRigidBody(*leo.allBodies[id_2]) == body_2
        tmp = leo.allForces[id_1]
        assert tmp.forceDirect == tmp.torqueDirect == [0, 0, 0]
        assert tmp.forceBoost == tmp.torqueBoost == [0, 0, 0]
        del tmp

        # Remove first object.
        assert leoAPI.addCmdRemoveObject(id_1).ok
        leo.processCommandsAndSync()
        assert id_1 not in leo.allBodies
        assert id_1 not in leo.allForces

        # Change the State Vector of id_2.
        pos = (10, 11.5, 12)
        body_3 = {'position': pos}
        assert leo.allBodies[id_2].position == (0, 0, 0)
        assert leoAPI.addCmdModifyBodyState(id_2, body_3).ok
        leo.processCommandsAndSync()
        assert leo.allBodies[id_2].position == pos

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
        sv = getRigidBody(imass=1)
        objID = '1'

        # Spawn object.
        assert leoAPI.addCmdSpawn([(objID, sv)]).ok
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
        sv = getRigidBody(imass=1, rotation=(0, 0, 0, 1))
        objID = '1'
        assert leoAPI.addCmdSpawn([(objID, sv)]).ok
        leo.processCommandsAndSync()
        del sv

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
        sv = getRigidBody(imass=1, rotation=(1, 0, 0, 0))
        objID = '1'
        assert leoAPI.addCmdSpawn([(objID, sv)]).ok
        leo.processCommandsAndSync()
        del sv

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
            """
            Assert that the ``_coll_sets`` are reduced to ``_correct_answer``
            by the `mergeConstraintSets` algorithm.
            """
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
        self.igor.reset()
        s = [['1'], ['2']]
        _verify(s, s)

        assert igor.addConstraints([getP2P()]).ok
        _verify(s, [['1', '2']])
        self.igor.reset()
        _verify(s, s)

        # Two disjoint sets but the constraint does not link them.
        self.igor.reset()
        s = [['1'], ['2']]
        _verify(s, s)
        assert igor.addConstraints([getP2P(rb_a='1', rb_b='3')]).ok
        _verify(s, s)

        # Three disjoint sets and the constraint links two of them.
        self.igor.reset()
        s = [['1', '2', '3'], ['4', '5'], ['6']]
        _verify(s, s)
        assert igor.addConstraints([getP2P(rb_a='1', rb_b='6')]).ok
        _verify(s, [['1', '2', '3', '6'], ['4', '5']])

        # Three disjoint sets and two constraint link both of them.
        self.igor.reset()
        s = [['1', '2', '3'], ['4', '5'], ['6']]
        _verify(s, s)
        assert igor.addConstraints([getP2P(rb_a='1', rb_b='6')]).ok
        assert igor.addConstraints([getP2P(rb_a='3', rb_b='4')]).ok
        _verify(s, [['1', '2', '3', '6', '4', '5']])

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
        id_a, id_b = '1', '2'
        pos_a, pos_b = (-2, 0, 0), (2, 0, 0)
        distance = abs(pos_a[0] - pos_b[0])
        assert distance >= 4

        body_a = getRigidBody(position=pos_a, cshapes={'cssphere': getCSSphere()})
        body_b = getRigidBody(position=pos_b, cshapes={'cssphere': getCSSphere()})

        # Specify the constraints.
        con = getP2P(rb_a=id_a, rb_b=id_b, pivot_a=pos_b, pivot_b=pos_a)
        assert self.igor.addConstraints([con]).ok

        # Spawn both objects.
        assert leoAPI.addCmdSpawn([(id_a, body_a), (id_b, body_b)]).ok
        leo.processCommandsAndSync()

        # Apply a force to the left sphere only.
        assert leoAPI.addCmdDirectForce(id_a, [-10, 0, 0], [0, 0, 0]).ok
        leo.processCommandsAndSync()

        # Both object must have moved the same distance 'delta' because they
        # are linked. Their distance must not have changed.
        leo.step(1.0, 60)
        allObjs = leo.allBodies
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
        assert self.igor.removeConstraints([con]) == (True, None, 1)
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
        azrael.test.test.shutdownLeonard()

    def verifySweeping(self, aabbsIn, correct_answer):
        # Create the AABB dictionaries. For this test the data is
        # identical in all three dimensions.
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
        _verify({0: [['4', '5'], ['6', '7']], 1: [['0', '1']]},
                correct_answer=[['0'], ['1']])

        # Self intersecting object: the two objects do not touch, but the AABBs
        # of the first do. This must result in to independent objects.
        _verify({0: [[4, 5], [4, 5]], 1: [[0, 1]]},
                correct_answer=[['0'], ['1']])

        # Two objects; the first has two AABS the second only one. The second
        # object touches the first AABB of the first object.
        _verify({0: [[4, 5], [6, 7]], 1: [[3, 5]]},
                correct_answer=[['0', '1']])

        # Two identical objects with two AABBs (each). This must produce one
        # set.
        _verify({0: [[4, 5], [6, 7]], 1: [[4, 5], [6, 7]]},
                correct_answer=[['0', '1']])

        # Three objects with one-, two-, and one AABB. The first touches the
        # left AABB of the middle object in 'x', whereas the third touches the
        # right AABB of the middle object in the 'y' dimensions.
        _verify({0: [[3, 5]], 1: [[4, 5], [7, 8]], 2: [[7, 9]]},
                correct_answer=[['0', '1', '2']])

        # Same as above, but the third object does not touch.
        _verify({0: [[3, 5]], 1: [[4, 5], [7, 8]], 2: [[70, 90]]},
                correct_answer=[['0', '1'], ['2']])

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
                correct_answer=[['0'], ['1']])

        # Repeat the test but use a different set of ID labels.
        _verify({3: [[4, 5]], 10: [[1, 2]]},
                correct_answer=[['3'], ['10']])

        # One object inside the other.
        _verify({0: [[2, 4]], 1: [[0, 1]]},
                correct_answer=[['0'], ['1']])

        # Partially overlapping to the right of the first object.
        _verify({0: [[1, 5]], 1: [[2, 4]]},
                correct_answer=[['0', '1']])

        # Partially overlapping to the left of the first object.
        _verify({0: [[1, 5]], 1: [[0, 2]]},
                correct_answer=[['0', '1']])

        # Pass no object to the Sweeping algorithm.
        assert azrael.leonard.sweeping({}, 'x').data == []

        # Pass only a single object to the Sweeping algorithm.
        _verify({0: [[1, 5]]},
                correct_answer=[['0']])

    def test_sweeping_3objects(self):
        """
        Same as test_sweeping_2objects but with three objects.
        """
        # Define a force grid (not used in this test but prevent a plethora
        # of meaningleass warning messages).
        vg = azrael.vectorgrid
        assert vg.defineGrid(name='force', vecDim=3, granularity=1).ok

        # Convenience variable.
        _verify = self.verifySweeping

        # Three non-overlapping objects.
        _verify({0: [[1, 2]], 1: [[3, 4]], 2: [[5, 6]]},
                correct_answer=[['0'], ['1'], ['2']])

        # First and second overlap.
        _verify({0: [[1, 2]], 1: [[1.5, 4]], 2: [[5, 6]]},
                correct_answer=[['0', '1'], ['2']])

        # Repeat test with different set of ID labels.
        _verify({2: [[1, 2]], 4: [[1.5, 4]], 10: [[5, 6]]},
                correct_answer=[['2', '4'], ['10']])

        # First overlaps with second, second overlaps with third, but third
        # does not overlap with first. The algorithm must nevertheless return
        # all three in a single set.
        _verify({0: [[1, 2]], 1: [[1.5, 4]], 2: [[3, 6]]},
                correct_answer=[['0', '1', '2']])

        # First and third overlap.
        _verify({0: [[1, 2]], 1: [[10, 11]], 2: [[0, 1.5]]},
                correct_answer=[['0', '2'], ['1']])

    @mock.patch('azrael.leonard.sweeping')
    def test_computeCollisionSetsAABB_mocksweeping(self, mock_sweeping):
        """
        Create three bodies. Then alter their AABBs to create various
        combinations of overlap.
        """
        # Install a mock for the sweeping algorithm.
        azrael.leonard.sweeping = mock_sweeping
        mock_sweeping.return_value = RetVal(True, None, [])

        # Single body with no AABBs.
        bodies = {5: getRigidBody(position=(0, 0, 0))}
        aabbs = {5: []}
        correct = {5: {'x': [], 'y': [], 'z': []}}
        azrael.leonard.computeCollisionSetsAABB(bodies, aabbs)
        mock_sweeping.assert_called_with(correct, 'x')

        # Single body with one AABB.
        bodies = {5: getRigidBody(position=(0, 0, 0))}
        aabbs = {5: {'1': (0, 0, 0, 1, 2, 3)}}
        correct = {5: {'x': [[-1, 1]],
                       'y': [[-2, 2]],
                       'z': [[-3, 3]]}}
        azrael.leonard.computeCollisionSetsAABB(bodies, aabbs)
        mock_sweeping.assert_called_with(correct, 'x')

        # Single body with two AABBs.
        bodies = {5: getRigidBody(position=(0, 0, 0))}
        aabbs = {5: {'1': (0, 0, 0, 1, 1, 1),
                     '2': (2, 3, 4, 2, 4, 8)}}
        correct = {5: {'x': [[-1, 1], [0, 4]],
                       'y': [[-1, 1], [-1, 7]],
                       'z': [[-1, 1], [-4, 12]]}}
        azrael.leonard.computeCollisionSetsAABB(bodies, aabbs)
        mock_sweeping.assert_called_with(correct, 'x')

        # Single body at an offset with two AABBs.
        bodies = {5: getRigidBody(position=(0, 1, 2))}
        aabbs = {5: {'1': (0, 0, 0, 1, 1, 1),
                     '2': (2, 3, 4, 2, 4, 8)}}
        correct = {5: {'x': [[-1, 1], [0, 4]],
                       'y': [[0, 2], [0, 8]],
                       'z': [[1, 3], [-2, 14]]}}
        azrael.leonard.computeCollisionSetsAABB(bodies, aabbs)
        mock_sweeping.assert_called_with(correct, 'x')

        # Three bodies with 0, 1, and 2 AABBs, respectively.
        bodies = {6: getRigidBody(position=(0, 0, 0)),
                  7: getRigidBody(position=(0, 0, 0)),
                  8: getRigidBody(position=(0, 0, 0))}
        aabbs = {6: {},
                 7: {'1': (0, 0, 0, 1, 1, 1)},
                 8: {'1': (0, 0, 0, 1, 1, 1),
                     '2': (2, 3, 4, 2, 4, 8)}}
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

    def test_computeCollisionSetsAABB_basic(self):
        """
        Create three bodies. Then alter their AABBs to create various
        combinations of overlap.
        """
        def testCCS(pos, AABBs, expected_objIDs):
            """
            Compute broadphase results for bodies  at ``pos`` with ``AABBs``
            and verify that the ``expected_objIDs`` sets were produced.

            This function assumes that every body has exactly one AABB and with
            no relative offset to the body's position.
            """
            # Compile the set of bodies- and their AABBs for this test run.
            assert len(pos) == len(aabbs)
            bodies = [getRigidBody(position=_) for _ in pos]

            # By assumption for this function, every object has exactly one AABB
            # centered at position zero relative to their rigid body.
            AABBs = [{'1': (0, 0, 0, _[0], _[1], _[2])} for _ in AABBs]

            # Convert to dictionaries: the key is the bodyID in Azrael; here it
            # is a simple enumeration.
            bodies = {str(idx): val for (idx, val) in enumerate(bodies)}
            AABBs = {str(idx): val for (idx, val) in enumerate(AABBs)}

            # Determine the list of broadphase collision sets.
            ret = azrael.leonard.computeCollisionSetsAABB(bodies, AABBs)
            assert ret.ok

            # Convert the reference data to a sorted list of sets.
            expected_objIDs = [sorted(tuple(_)) for _ in expected_objIDs]
            computed_objIDs = [sorted(tuple(_)) for _ in ret.data]

            # Return the equality of the two list of lists.
            assert sorted(expected_objIDs) == sorted(computed_objIDs)
            del bodies, AABBs, ret, expected_objIDs, computed_objIDs

        # First overlaps with second, second with third, but first not with
        # third. This must result in a single broadphase set containing all
        # three bodies.
        pos = [(0, 0, 0), (1, 1, 1), (2, 2, 2)]
        aabbs = [(0.9, 0.9, 0.9), (0.9, 0.9, 0.9), (0.9, 0.9, 0.9)]
        correct_answer = (['0', '1', '2'], )
        testCCS(pos, aabbs, correct_answer)

        # Move the middle object away: three independent objects.
        pos = [(0, 0, 0), (1, 10, 1), (2, 2, 2)]
        aabbs = [(0.9, 0.9, 0.9), (0.9, 0.9, 0.9), (0.9, 0.9, 0.9)]
        correct_answer = (['0'], ['1'], ['2'])
        testCCS(pos, aabbs, correct_answer)

        # Move the middle object back but make it so small in 'y' direction
        # that it does not intersect with the other two: three independent
        # objects.
        pos = [(0, 0, 0), (1, 1, 1), (2, 2, 2)]
        aabbs = [(0.9, 0.9, 0.9), (0.05, 0.05, 0.05), (0.9, 0.9, 0.9)]
        correct_answer = (['0'], ['1'], ['2'])
        testCCS(pos, aabbs, correct_answer)

        # Second and third overlap, but first is by itself.
        pos = [(0, 0, 0), (1, 1, 1), (2, 2, 2)]
        aabbs = ([0.1, 0.1, 0.1], [0.1, 0.1, 0.1], [1, 1, 1])
        correct_answer = (['0'], ['1', '2'])
        testCCS(pos, aabbs, correct_answer)

        # Objects overlap in 'x' and 'z', but not 'y': three independent
        # objects.
        pos = [(0, 0, 0), (1, 1, 1), (2, 2, 2)]
        aabbs = ([1, 0.4, 1], [1, 0.4, 1], [1, 0.4, 1])
        correct_answer = (['0'], ['1'], ['2'])
        testCCS(pos, aabbs, correct_answer)

        # Middle object has no size, but the first/third objects are large
        # enough to touch each other: First/third must be connected, middle one
        # must be by itself.
        pos = [(0, 0, 0), (1, 1, 1), (2, 2, 2)]
        aabbs = ([1.01, 1.01, 1.01], [0, 0, 0], [1.01, 1.01, 1.01])
        correct_answer = (['0', '2'], ['1'])
        testCCS(pos, aabbs, correct_answer)

    def test_computeCollisionSetsAABB_rotate_scale(self):
        """
        Test broadphase when body has a different scale and/or is rotated.

        Create two bodies with one AABB each. The AABB of the first body is
        a centered unit cube used for testing. The second body has an AABB with
        an offset. Use different scales and rotations to verify it is
        correctly taken into account during the broadphase.
        """
        # Create the test body at the center. It is a centered unit cube.
        body_a = getRigidBody(position=(0, 0, 0), cshapes={'csbox': getCSBox()})

        def _verify(rba, pos, rot, scale, intersect: bool):
            """
            Assert that body ``rba`` and a new body (specified by ``pos``,
            ``rot``, and ``scale``) ``intersect``.

            This is a convenience function to facilitate more readable tests.
            """
            # Hard code collision shape offset for second object.
            cs_ofs = (1, 0, 0)

            # Create the second body. Its collision shape is a unit cube
            # at position `cs_ofs`.
            body_b = getRigidBody(position=pos, scale=scale, rotation=rot,
                                  cshapes={'csbox': getCSBox()})

            # Compile the input dictionaries for the broadphase algorithm.
            bodies = {'1': rba, '2': body_b}
            aabbs = {'1': {'1': [0, 0, 0, 1, 1, 1]},
                     '2': {'1': [cs_ofs[0], cs_ofs[1], cs_ofs[2], 1, 1, 1]}}

            # Compute the broadphase collision sets.
            ret = azrael.leonard.computeCollisionSetsAABB(bodies, aabbs)
            assert ret.ok
            coll_sets = ret.data

            # If the bodies intersect there must be exactly one collision set
            # with two entries, otherwise it is the other way around.
            if intersect:
                assert len(coll_sets) == 1
                assert len(coll_sets[0]) == 2
            else:
                assert len(coll_sets) == 2
                assert len(coll_sets[0]) == len(coll_sets[1]) == 1

        # Test object intersects (just) to the right of probe.
        pos = (0.99, 0, 0)
        rot = (0, 0, 0, 1)
        scale = 1
        _verify(body_a, pos, rot, scale, intersect=True)

        # Test object does (just) not intersect with probe.
        pos = (1.01, 0, 0)
        rot = (0, 0, 0, 1)
        scale = 1
        _verify(body_a, pos, rot, scale, intersect=False)

        # Dummy is rotated 180 degrees around y axis. This causes the AABBs to
        # intersect again.
        pos = (2, 0, 0)
        rot = (0, 0, 0, 1)
        scale = 1
        _verify(body_a, pos, rot=(0, 0, 0, 1), scale=1, intersect=False)
        _verify(body_a, pos, rot=(0, 1, 0, 0), scale=1, intersect=True)

        # Place the dummy out of reach from the probe. However, double the
        # size of the probe wich makes the objects overlap.
        pos = (-4, 0, 0)
        rot = (0, 0, 0, 1)
        body_a_scaled = body_a._replace(scale=3)
        _verify(body_a, pos, rot, scale=1, intersect=False)
        _verify(body_a_scaled, pos, rot, scale=1, intersect=True)

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
        num_bodies = 10

        # Create several rigid bodies with a spherical collision shape.
        cs = {'1': getCSSphere(radius=1)}
        if dim == 0:
            states = [getRigidBody(position=[_, 0, 0], cshapes=cs) for _ in range(10)]
        elif dim == 1:
            states = [getRigidBody(position=[0, _, 0], cshapes=cs) for _ in range(10)]
        elif dim == 2:
            states = [getRigidBody(position=[0, 0, _], cshapes=cs) for _ in range(10)]
        else:
            print('Invalid dimension for this test')
            assert False

        # Add all objects to the Body State DB and sync with Leonard.
        for objID, bs in enumerate(states):
            assert leoAPI.addCmdSpawn([(str(objID), bs)]).ok
        del states
        leo.processCommandsAndSync()

        # Sanity check: the number of test IDs must match the number of objects
        # in Leonard.
        assert len(leo.allBodies) == num_bodies

        def ccsWrapper(test_objIDs, expected_objIDs):
            """
            Assert that ``test_objIDs`` form the ``expected_objIDs`` collision
            sets.

            This is a convenience wrapper to facilitate readable tests.
            """
            # Compile the set of bodies- and their AABBs for this test run.
            bodies = {_: leo.allBodies[_] for _ in test_objIDs}
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
        ccsWrapper(['0', '9'],
                   [['0'], ['9']])

        # Two overlapping objects.
        ccsWrapper(['0', '1'],
                   [['0', '1']])

        # Three sets.
        ccsWrapper(['0', '1', '5', '8', '9'],
                   [['0', '1'], ['5'], ['8', '9']])

        # Same test, but objects are passed in a different sequence. This must
        # not alter the test outcome.
        ccsWrapper(['0', '5', '1', '9', '8'],
                   [['0', '1'], ['5'], ['8', '9']])

        # All objects must form one connected set.
        ccsWrapper([str(_) for _ in range(10)], [[str(_) for _ in range(10)]])

    def test_computeCollisionSetsAABB_static(self):
        """
        Static bodies (ie every body with mass=0) must be added to every
        collision set.
        """
        def testCCS(pos, AABBs, imasses, expected_objIDs):
            """
            Compute broadphase results for bodies at ``pos`` with ``masses``
            and ``AABBs``, and verify that the ``expected_objIDs`` sets were
            produced.

            This function assumes that every body has exactly one AABB and with
            no relative offset to the body's position.
            """
            # Compile the set of bodies- and their AABBs for this test run.
            assert len(pos) == len(aabbs) == len(imasses)
            bodies = [getRigidBody(position=p, imass=m) for (p, m) in zip(pos, imasses)]

            # By assumption, this function, every object has exactly one AABB
            # centered at zero.
            AABBs = [{'1': (0, 0, 0, _[0], _[1], _[2])} for _ in AABBs]

            # Convert to dictionaries: the key is the bodyID in Azrael; here it
            # is a simple enumeration.
            bodies = {str(idx): val for (idx, val) in enumerate(bodies)}
            AABBs = {str(idx): val for (idx, val) in enumerate(AABBs)}

            # Determine the list of broadphase collision sets.
            ret = azrael.leonard.computeCollisionSetsAABB(bodies, AABBs)
            assert ret.ok

            # Convert the reference data to a sorted list of sets.
            expected_objIDs = [sorted(tuple(_)) for _ in expected_objIDs]
            computed_objIDs = [sorted(tuple(_)) for _ in ret.data]

            # Return the equality of the two list of lists.
            assert sorted(expected_objIDs) == sorted(computed_objIDs)
            del bodies, AABBs, ret, expected_objIDs, computed_objIDs

        # Three dynamics bodies: First overlaps with second, second with third,
        # but first not with third. This must result in a single broadphase set
        # containing all three bodies.
        pos = [(0, 0, 0), (1, 1, 1), (2, 2, 2)]
        aabbs = [(0.9, 0.9, 0.9), (0.9, 0.9, 0.9), (0.9, 0.9, 0.9)]
        imasses = [1, 1, 1]
        correct_answer = (['0', '1', '2'], )
        testCCS(pos, aabbs, imasses, correct_answer)

        # Same test, but this time the middle body is static (ie imass=0). This
        # must result in two collision sets, each containing the static body.
        pos = [(0, 0, 0), (1, 1, 1), (2, 2, 2)]
        aabbs = [(0.9, 0.9, 0.9), (0.9, 0.9, 0.9), (0.9, 0.9, 0.9)]
        imasses = [1, 0, 1]
        correct_answer = (['0', '1'], ['1', '2'])
        testCCS(pos, aabbs, imasses, correct_answer)

    def test_skipEmpty(self):
        """
        Verify that _skipEmptyBodies removes all bodies that have a) exactly
        one collision shape and b) that collision shape is empty.
        """
        # Convenience: some collision shapes.
        empty = getCSEmpty()
        sphere = getCSSphere(radius=1)

        # Create several bodies with various collision shape combinations.
        bodies = {
            1: getRigidBody(cshapes={'foo': empty}),
            2: getRigidBody(cshapes={'bar': sphere}),
            3: getRigidBody(cshapes={'foo': empty, 'bar': sphere}),
            4: getRigidBody(cshapes={'foo': empty, 'bar': empty})
        }

        # Shallow copy of the original dictionary for the comparison
        # afterwards.
        bodies_copy = dict(bodies)
        ret = azrael.leonard._skipEmptyBodies(bodies_copy)

        # Verify that the function has no side effect (ie that it does not
        # alter the dictionary we pass in).
        assert bodies == bodies_copy

        # The function must have removed the first body.
        assert ret == {2: bodies[2], 3: bodies[3]}
