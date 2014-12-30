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

"""
Physics manager.
"""
import sys
import zmq
import time
import IPython
import logging
import setproctitle
import multiprocessing
import numpy as np

import azrael.vectorgrid
import azrael.util as util
import azrael.config as config
import azrael.bullet.boost_bullet
import azrael.bullet.btInterface as btInterface
import azrael.bullet.bullet_data as bullet_data

from azrael.typecheck import typecheck

ipshell = IPython.embed


@typecheck
def sweeping(data: list, labels: np.ndarray, dim: str):
    """
    Return sets of overlapping AABBs in the dimension ``dim``.

    This function implements the 'Sweeping' algorithm to determine which sets
    of AABBs overlap.

    Sweeping is straightforward: sort all start/stop positions and determine
    the overlapping sets.

    The returned sets does not contain the elements of data, but their
    corresponding label from the list of ``labels``.

    :param list data: list of dictionaries which must contain ['aabb']
    :param np.int64 labels: integer array to label the elements in data.
    :param str dim: the axis to check (must be one of ['x', 'y', 'z'])
    """
    assert len(labels) == len(data)

    # Convenience.
    N = 2 * len(data)

    # Pre-allocate arrays for start/stop position, objID, and an
    # increment/decrement array used for convenient processing afterwards.
    arr_pos = np.zeros(N, np.float64)
    arr_lab = np.zeros(N, np.int64)
    arr_inc = np.zeros(N, np.int8)

    # Fill the arrays.
    for ii in range(len(data)):
        arr_pos[2 * ii: 2 * ii + 2] = np.array(data[ii][dim])
        arr_lab[2 * ii: 2 * ii + 2] = labels[ii]
        arr_inc[2 * ii: 2 * ii + 2] = [+1, -1]

    # Sort all three arrays according to the start/stop positions.
    idx = np.argsort(arr_pos)
    arr_lab = arr_lab[idx]
    arr_inc = arr_inc[idx]

    # Output array.
    out = []

    # Sweep over the sorted data and compile the list of object sets.
    sumVal = 0
    setObjs = set()
    for (inc, objID) in zip(arr_inc, arr_lab):
        # Update the index variable and add the current object to the set.
        sumVal += inc
        setObjs.add(objID)

        # A new set of overlapping AABBs is complete whenever `sumVal`
        # reaches zero.
        if sumVal == 0:
            out.append(setObjs)
            setObjs = set()

        # Safety check: this must never happen.
        assert sumVal >= 0
    return out


@typecheck
def computeCollisionSetsAABB(IDs: list, SVs: list):
    """
    Return potential collision sets among all ``IDs`` and associated ``SVs``.

    :param IDs: list of object IDs.
    :param SVs: list of object BulletData instances. Corresponds to IDs.
    """
    # Sanity check.
    if len(IDs) != len(SVs):
        return False, None

    # Fetch all AABBs.
    ok, aabbs = btInterface.getAABB(IDs)
    if not ok:
        return False, None

    # The 'sweeping' function requires a list of dictionaries. Each dictionary
    # must contain the min/max spatial extent in x/y/z direction.
    data = []
    IDs_new = []
    for objID, sv, aabb in zip(IDs, SVs, aabbs):
        if (sv is None) or (aabb is None):
            continue
        IDs_new.append(objID)
        pos = sv.position
        x0, x1 = pos[0] - aabb, pos[0] + aabb
        y0, y1 = pos[1] - aabb, pos[1] + aabb
        z0, z1 = pos[2] - aabb, pos[2] + aabb

        data.append({'x': [x0, x1], 'y': [y0, y1], 'z': [z0, z1]})
    IDs = IDs_new
    del IDs_new, SVs, aabbs

    # Enumerate the objects.
    labels = np.arange(len(IDs))

    # Determine the overlapping objects in 'x' direction.
    stage_0 = sweeping(data, labels, 'x')

    # Determine which of the objects that overlap in 'x' also overlap in 'y'.
    stage_1 = []
    for subset in stage_0:
        tmpData = [data[_] for _ in subset]
        tmpLabels = np.array(tuple(subset), np.int64)
        stage_1.extend(sweeping(tmpData, tmpLabels, 'y'))

    # Now determine the objects that overlap in all three dimensions.
    stage_2 = []
    for subset in stage_1:
        tmpData = [data[_] for _ in subset]
        tmpLabels = np.array(tuple(subset), np.int64)
        stage_2.extend(sweeping(tmpData, tmpLabels, 'z'))

    # Convert the labels back to object IDs.
    out = [[IDs[_] for _ in __] for __ in stage_2]
    return True, out


class LeonardBase(multiprocessing.Process):
    """
    Base class for Physics manager.

    No physics is actually computed here. The class serves mostly as an
    interface for the actual Leonard implementations, as well as a test
    framework.
    """
    def __init__(self):
        super().__init__()

        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)
        self.logit.debug('mydebug')
        self.logit.info('myinfo')

    def setup(self):
        """
        Stub for initialisation code that cannot go into the constructor.

        Since Leonard is a process not everything can be initialised in the
        constructor because it executes before the process forks.
        """
        pass

    def applyGridForce(self, force, pos):
        """
        Return updated ``force`` that takes the force grid value at ``pos``
        into account.

        Covenience function to minimise code duplication.

        :param 3d-vec force: original force value.
        :param 3d-vec pos: position in world coordinates.
        :return: updated ``force`` value.
        :rtype: 3d-vec.
        """
        # Convenience.
        vg = azrael.vectorgrid

        # Add the force from the grid.
        tmp = vg.getValue('force', pos)
        if tmp.ok and len(tmp.data) == 3:
            return force + tmp.data
        else:
            return force

    @typecheck
    def step(self, dt: (int, float), maxsteps: int):
        """
        Advance the simulation by ``dt`` using at most ``maxsteps``.

        This method will use a primitive Euler step to update the state
        variables. This suffices as a proof of concept.

        :param float dt: time step in seconds.
        :param int maxsteps: maximum number of sub-steps to simulate for one
                             ``dt`` update.
        """
        # Retrieve the SV for all objects.
        ok, all_ids = btInterface.getAllObjectIDs()
        ok, all_sv = btInterface.getStateVariables(all_ids)

        # Iterate over all objects and update their SV information in Bullet.
        for objID, sv in zip(all_ids, all_sv):
            # Fetch the force vector for the current object from the DB.
            ok, force, torque = btInterface.getForceAndTorque(objID)
            if not ok:
                continue

            # Add the force defined on the 'force' grid.
            force = self.applyGridForce(force, sv.position)

            # Update velocity and position.
            sv.velocityLin[:] += 0.5 * force
            sv.position[:] += dt * sv.velocityLin

            # Override SV with user specified values (if there are any).
            sv = self.setObjectAttributes(objID, sv)

            # Serialise the state variables and update them in the DB.
            btInterface.update(objID, sv)

    def setObjectAttributes(self, objID, sv):
        """
        Return update SV if the user wants to override some of them.

        This method does nothing if the user did not override any values via a
        call to 'overrideAttributes'.

        :param bytes objID: object ID
        :param BulletData sv: SV for objID.
        """
        # Determine if the user actually specified any attributes.
        ok, tmp = btInterface.getOverrideAttributes(objID)
        if not ok:
            return sv

        # Apply the specified values.
        if tmp.pos is not None:
            sv.position[:] = tmp.pos
        if tmp.vLin is not None:
            sv.velocityLin[:] = tmp.vLin
        if tmp.vRot is not None:
            sv.velocityRot[:] = tmp.vRot
        if tmp.orient is not None:
            sv.orientation[:] = tmp.orient

        # Clear the DB entry (they would otherwise be applied
        # at every frame).
        btInterface.overrideAttributes(objID, None)
        return sv

    def run(self):
        """
        Drive the periodic physics updates.
        """
        setproctitle.setproctitle('killme ' + self.__class__.__name__)

        # Initialisation.
        self.setup()
        self.logit.debug('Setup complete.')

        # Reset the database.
        btInterface.initSVDB(reset=False)

        # Trigger the `step` method every 10ms, if possible.
        t0 = time.time()
        while True:
            # Wait, if less than 10ms have passed, or proceed immediately.
            sleep_time = 0.01 - (time.time() - t0)
            if sleep_time > 0:
                time.sleep(sleep_time)

            # Backup the time stamp.
            t0 = time.time()

            # Trigger the physics update step.
            with util.Timeit('step') as timeit:
                self.step(0.1, 10)


class LeonardBulletMonolithic(LeonardBase):
    """
    An extension of ``LeonardBase`` that uses Bullet for the physics.

    Unlike ``LeonardBase`` this class actually *does* update the physics.
    """
    def __init__(self):
        super().__init__()
        self.bullet = None

    def setup(self):
        # Instantiate the Bullet engine. The (1, 0) parameters mean
        # the engine has ID '1' and does not build explicit pair caches.
        self.bullet = azrael.bullet.boost_bullet.PyBulletPhys(1)

    @typecheck
    def step(self, dt, maxsteps):
        """
        Advance the simulation by ``dt`` using at most ``maxsteps``.

        This method will query all SV objects from the database and updates
        them in the Bullet engine. Then it defers to Bullet for the physics
        update.  Finally it copies the updated values in Bullet back to the
        database.

        :param float dt: time step in seconds.
        :param int maxsteps: maximum number of sub-steps to simulate for one
                             ``dt`` update.
        """

        # Convenience.
        vg = azrael.vectorgrid

        # Retrieve the SV for all objects.
        ok, allSV = btInterface.getAllStateVariables()

        # Iterate over all objects and update them.
        for objID, sv in allSV.items():
            # Convert the objID to an integer.
            btID = util.id2int(objID)

            # Pass the SV data from the DB to Bullet.
            self.bullet.setObjectData([btID], sv)

            # Retrieve the force vector and tell Bullet to apply it.
            ok, force, torque = btInterface.getForceAndTorque(objID)
            if ok:
                # Add the force defined on the 'force' grid.
                force = self.applyGridForce(force, sv.position)

                # Apply the force to the object.
                self.bullet.applyForceAndTorque(btID, force, torque)

        # Wait for Bullet to advance the simulation by one step.
        IDs = [util.id2int(_) for _ in allSV.keys()]
        with util.Timeit('compute') as timeit:
            self.bullet.compute(IDs, dt, maxsteps)

        # Retrieve all objects from Bullet and write them back to the database.
        for objID, sv in allSV.items():
            ok, sv = self.bullet.getObjectData([util.id2int(objID)])

            # Override SV with user specified values (if there are any).
            sv = self.setObjectAttributes(objID, sv)

            if ok == 0:
                # Restore the original cshape because Bullet will always
                # return zeros here.
                sv.cshape[:] = allSV[objID].cshape[:]
                btInterface.update(objID, sv)


class LeonardBulletSweeping(LeonardBulletMonolithic):
    """
    Compute physics on independent collision sets.

    This is a modified version of ``LeonardBulletMonolithic`` that uses
    Sweeping to compile the collision sets and then updates the physics for
    each set independently.

    This class is single threaded and uses a single Bullet instance to
    sequentially update the physics for each collision set.
    """
    @typecheck
    def step(self, dt, maxsteps):
        """
        Advance the simulation by ``dt`` using at most ``maxsteps``.

        This method will query all SV objects from the database and updates
        them in the Bullet engine. Then it defers to Bullet for the physics
        update.  Finally it copies the updated values in Bullet back to the
        database.

        :param float dt: time step in seconds.
        :param int maxsteps: maximum number of sub-steps to simulate for one
                             ``dt`` update.
        """

        # Retrieve the SV for all objects.
        ok, allSV = btInterface.getAllStateVariables()

        # Compile a dedicated list of IDs and their SVs for the collision
        # detection algorithm.
        IDs = list(allSV.keys())
        sv = [allSV[_] for _ in IDs]

        # Compute the collision sets.
        with util.Timeit('CCS') as timeit:
            ok, res = computeCollisionSetsAABB(IDs, sv)
        assert ok

        # Log the number of created collision sets.
        util.logMetricQty('#CollSets', len(res))

        # Convenience.
        vg = azrael.vectorgrid

        # Process all subsets individually.
        for subset in res:
            # Compile the subset dictionary for the current collision set.
            coll_SV = {_: allSV[_] for _ in subset}

            # Iterate over all objects and update them.
            for objID, sv in coll_SV.items():
                # Convert the objID to an integer.
                btID = util.id2int(objID)

                # Pass the SV data from the DB to Bullet.
                self.bullet.setObjectData([btID], sv)

                # Retrieve the force vector and tell Bullet to apply it.
                ok, force, torque = btInterface.getForceAndTorque(objID)
                if ok:
                    # Add the force defined on the 'force' grid.
                    force = self.applyGridForce(force, sv.position)

                    # Apply the final force to the object.
                    self.bullet.applyForceAndTorque(btID, force, torque)

            # Wait for Bullet to advance the simulation by one step.
            IDs = [util.id2int(_) for _ in coll_SV.keys()]
            with util.Timeit('compute') as timeit:
                self.bullet.compute(IDs, dt, maxsteps)

            # Retrieve all objects from Bullet and write them back to the
            # database.
            for objID, sv in coll_SV.items():
                ok, sv = self.bullet.getObjectData([util.id2int(objID)])

                # Override SV with user specified values (if there are any).
                sv = self.setObjectAttributes(objID, sv)
                if ok == 0:
                    # Restore the original cshape because Bullet will always
                    # return zeros here.
                    sv.cshape[:] = coll_SV[objID].cshape[:]
                    btInterface.update(objID, sv)


class LeonardBulletSweepingMultiST(LeonardBulletMonolithic):
    """
    Compute physics on independent collision sets with multiple engines.

    This is a modified version of ``LeonardBulletMonolithic`` and similar to
    ``LeonardBulletSweeping``. It employs work packages and multiple engines,
    all of which run in the same thread.

    This class is single threaded. All Bullet engines run sequentially in the
    main thread. The work packages are distributed at random to the engines.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.token = 0

    def setup(self):
        # Instantiate several Bullet engines. The (1, 0) parameters mean
        # the engine has ID '1' and does not build explicit pair caches.
        engine = azrael.bullet.boost_bullet.PyBulletPhys
        self.bulletEngines = [engine(_ + 1) for _ in range(5)]

    @typecheck
    def step(self, dt, maxsteps):
        """
        Advance the simulation by ``dt`` using at most ``maxsteps``.

        This method will query all SV objects from the database and updates
        them in the Bullet engine. Then it defers to Bullet for the physics
        update.  Finally it copies the updated values in Bullet back to the
        database.

        :param float dt: time step in seconds.
        :param int maxsteps: maximum number of sub-steps to simulate for one
                             ``dt`` update.
        """

        # Retrieve the SV for all objects.
        ok, allSV = btInterface.getAllStateVariables()

        # Compile a dedicated list of IDs and their SVs for the collision
        # detection algorithm.
        IDs = list(allSV.keys())
        sv = [allSV[_] for _ in IDs]

        # Compute the collision sets.
        with util.Timeit('CCS') as timeit:
            ok, res = computeCollisionSetsAABB(IDs, sv)
        if not ok:
            self.logit.error('ComputeCollisionSetsAABB returned an error')
            sys.exit(1)

        # Log the number of created collision sets.
        util.logMetricQty('#CollSets', len(res))

        # Convenience.
        cwp = btInterface.createWorkPackage

        # Update the token value for this iteration.
        self.token += 1

        all_wpids = []
        # Process all subsets individually.
        for subset in res:
            # Compile the subset dictionary for the current collision set.
            coll_SV = {_: allSV[_] for _ in subset}

            # Upload the work package into the DB.
            ok, wpid = cwp(list(subset), self.token, dt, maxsteps)

            # Keep track of the WPID.
            all_wpids.append(wpid)

        # Process each WP individually.
        for wpid in all_wpids:
            self.processWorkPackage(wpid)

        self.waitUntilWorkpackagesComplete(all_wpids, self.token)

    def waitUntilWorkpackagesComplete(self, all_wpids, token):
        """
        Block until all work packages have been completed.
        """
        while btInterface.countWorkPackages(token)[1] > 0:
            time.sleep(0.001)

    def setObjectAttributes(self, obj, sv):
        """
        Return updated SV if the user wants to override some of them.

        This method does nothing if the user did not override any values via a
        call to 'overrideAttributes'.

        .. note::
           It is unnecessary to explicitly clear the attribute override request
           because ``btInterface.updateWorkPackage`` will take care of this
           automatically.

        :param bytes objID: object ID
        :param BulletData sv: SV for objID.
        """
        tmp = obj.attrOverride

        # Apply the specified values.
        if tmp.pos is not None:
            sv.position[:] = tmp.pos
        if tmp.vLin is not None:
            sv.velocityLin[:] = tmp.vLin
        if tmp.vRot is not None:
            sv.velocityRot[:] = tmp.vRot
        if tmp.orient is not None:
            sv.orientation[:] = tmp.orient
        return sv

    @typecheck
    def processWorkPackage(self, wpid: int):
        """
        Update the physics for all objects in ``wpid``.

        The Bullet engine is picked at random.

        :param int wpid: work package ID.
        """
        ok, worklist, admin = btInterface.getWorkPackage(wpid)
        assert ok

        # Pick an engine at random.
        engineIdx = int(np.random.randint(len(self.bulletEngines)))
        engine = self.bulletEngines[engineIdx]

        # Log the number of created collision sets.
        util.logMetricQty('Engine_{}'.format(engineIdx), len(worklist))

        # Iterate over all objects and update them.
        for obj in worklist:
            sv = obj.sv

            # Update the object in Bullet.
            btID = util.id2int(obj.id)
            engine.setObjectData([btID], sv)

            # Retrieve the force vector and tell Bullet to apply it.
            force = np.fromstring(obj.central_force)
            torque = np.fromstring(obj.torque)

            # Add the force defined on the 'force' grid.
            force = self.applyGridForce(force, sv.position)

            # Apply all forces and torques.
            engine.applyForceAndTorque(btID, force, torque)

        # Tell Bullet to advance the simulation for all objects in the
        # current work list.
        IDs = [util.id2int(_.id) for _ in worklist]
        engine.compute(IDs, admin.dt, admin.maxsteps)

        # Retrieve the objects from Bullet again and update them in the DB.
        out = {}
        for obj in worklist:
            ok, sv = engine.getObjectData([util.id2int(obj.id)])

            if ok != 0:
                # Something went wrong. Reuse the old SV.
                sv = obj.sv
                self.logit.error('Unable to get all objects from Bullet')

            # Override SV with user specified values (if there are any).
            sv = self.setObjectAttributes(obj, sv)

            # Restore the original cshape because Bullet will always return
            # zeros here.
            sv.cshape[:] = obj.sv.cshape[:]
            out[obj.id] = sv

        # Update the data and delete the WP.
        ok = btInterface.updateWorkPackage(wpid, admin.token, out)
        if not ok:
            msg = 'Failed to update work package {}'.format(wpid)
            self.logit.warning(msg)


class WorkerManager(multiprocessing.Process):
    """
    Launch Worker processes and restart them as necessary.

    This class merely launches the inital set of workers and periodically
    checks if any have died. If so, it joins these processes and replaces it
    with a new Worker that has the same ID.

    :param int numWorker: number of Workers processes to spawn.
    :param int minSteps: see Worker
    :param int maxSteps: see Worker
    :param class workerCls: the class to instantiate.
    """
    def __init__(self, numWorkers: int, minSteps: int, maxSteps: int,
                 workerCls):
        super().__init__()

        # Sanity checks.
        assert numWorkers > 0
        assert isinstance(minSteps, int)
        assert isinstance(maxSteps, int)
        assert 0 < minSteps <= maxSteps

        # Backup the arguments.
        self.numWorkers = numWorkers
        self.workerCls = workerCls
        self.minSteps, self.maxSteps = minSteps, maxSteps

    def _run(self):
        """
        Start the inital collection of Workers and ensure the remain alive.
        """
        # Rename the process.
        setproctitle.setproctitle('killme ' + self.__class__.__name__)

        # Spawn the initial collection of Workers.
        workers = []
        delta = self.maxSteps - self.minSteps
        cls = LeonardBulletSweepingMultiMTWorker
        for ii in range(self.numWorkers):
            # Random number in [minSteps, maxSteps]. The process will
            # automatically terminate after `suq` steps.
            suq = self.minSteps + int(np.random.rand() * delta)

            # Instantiate the process and add it to the list.
            workers.append(cls(ii + 1, suq))
            workers[-1].start()

        # Periodically monitor the processes and restart any that have died.
        while True:
            # Only check once a second.
            time.sleep(1)
            for workerID, proc in enumerate(workers):
                # Skip current process if it is still running.
                if proc.is_alive():
                    continue

                # Process has died --> join it to clear up the process table.
                proc.join()

                # Create a new Worker with the same ID but a (possibly)
                # different number of steps after which it must terminate.
                suq = self.minSteps + int(np.random.rand() * delta)
                proc = cls(workerID, suq)
                proc.start()
                workers[workerID] = proc
                print('Restarted Worker {}'.format(workerID))

    def run(self):
        """
        Wrapper around ``_run`` to intercept SIGTERM.
        """
        try:
            self._run()
        except KeyboardInterrupt:
            pass


class LeonardBulletSweepingMultiMT(LeonardBulletSweepingMultiST):
    """
    Compute physics on independent collision sets with multiple engines.

    Leverage ``LeonardBulletSweepingMultiST`` but process the work packages in
    dedicated Worker processes.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.workers = []
        self.numWorkers = 3

        # Every Worker will respawn after somewhere between [minSteps,
        # maxSteps] physics updates. The ``ManageWorker`` instance will
        # randomly pick a number from this interval to decorrelate the restart
        # times of the Workers.
        self.minSteps, self.maxSteps = (500, 700)

    def __del__(self):
        """
        Kill all worker processes.
        """
        for worker in self.workers:
            if worker.is_alive():
                worker.terminate()
                worker.join()

    def setup(self):
        self.ctx = zmq.Context()
        self.sock = self.ctx.socket(zmq.REP)
        self.sock.bind(config.addr_leonard_pushpull)

        # Spawn the workers.
        workermanager = WorkerManager(
            self.numWorkers, self.minSteps,
            self.maxSteps, LeonardBulletSweepingMultiMTWorker)
        workermanager.start()
        self.logit.info('Setup complete')

    def processWorkPackage(self, wpid: int):
        """
        Ensure "someone" processes the work package with ID ``wpid``.

        This method will usually be overloaded in sub-classes to actually send
        the WPs to a Bullet engine or worker processes.

        :param int wpid: work package ID to process.
        """
        self.sock.recv()
        self.sock.send(np.int64(wpid).tostring())


class LeonardBulletSweepingMultiMTWorker(multiprocessing.Process):
    """
    Distributed Physics Engine based on collision sets and work packages.

    The distribution of Work Packages happens via ZeroMQ push/pull sockets.

    :param int workerID: the ID of this worker.
    :param int stepsUntilQuit: Worker will restart after this many steps.
    """
    def __init__(self, workerID, stepsUntilQuit: int):
        super().__init__()
        self.workerID = workerID

        # After ``stepsUntilQuit`` this Worker will spawn a new Worker with the
        # same ID and quit.
        assert stepsUntilQuit > 0
        self.stepsUntilQuit = stepsUntilQuit

        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

    def applyGridForce(self, force, pos):
        """
        Return updated ``force`` that takes the force grid value at ``pos``
        into account.

        Covenience function to minimise code duplication.

        :param 3d-vec force: original force value.
        :param 3d-vec pos: position in world coordinates.
        :return: updated ``force`` value.
        :rtype: 3d-vec.
        """
        # Convenience.
        vg = azrael.vectorgrid

        # Add the force from the grid.
        tmp = vg.getValue('force', pos)
        if tmp.ok and len(tmp.data) == 3:
            return force + tmp.data
        else:
            return force

    @typecheck
    def run(self):
        """
        Update the physics for all objects in ``wpid``.

        :param int wpid: work package ID.
        """
        try:
            # Rename process to make it easy to find and kill them in the
            # process table.
            setproctitle.setproctitle('killme LeonardWorker')

            # Instantiate a Bullet engine.
            engine = azrael.bullet.boost_bullet.PyBulletPhys
            self.bullet = engine(self.workerID)

            # Setup ZeroMQ.
            ctx = zmq.Context()
            sock = ctx.socket(zmq.REQ)
            sock.connect(config.addr_leonard_pushpull)
            self.logit.info('Worker {} connected'.format(self.workerID))

            # Process work packages as they arrive.
            numSteps = 0
            suq = self.stepsUntilQuit
            while numSteps < suq:
                sock.send(b'')
                wpid = sock.recv()
                wpid = np.fromstring(wpid, np.int64)
                self.processWorkPackage(int(wpid))
                numSteps += 1

            # Log a last status message and terminate.
            self.logit.info('Worker {} terminated itself after {} steps'
                            .format(self.workerID, numSteps))
            sock.close(linger=0)
            ctx.destroy()
        except KeyboardInterrupt:
            print('Aborted Worker {}'.format(self.workerID))

    def processWorkPackage(self, wpid: int):
        ok, worklist, admin = btInterface.getWorkPackage(wpid)
        assert ok

        # Log the number of collision sets to process.
        util.logMetricQty('Engine_{}'.format(self.workerID), len(worklist))

        # Iterate over all objects and update them.
        for obj in worklist:
            sv = obj.sv

            # Update the object in Bullet.
            btID = util.id2int(obj.id)
            self.bullet.setObjectData([btID], sv)

            # Retrieve the force vector and tell Bullet to apply it.
            force = np.fromstring(obj.central_force)
            torque = np.fromstring(obj.torque)

            # Add the force defined on the 'force' grid.
            force = self.applyGridForce(force, sv.position)

            # Apply all forces and torques.
            self.bullet.applyForceAndTorque(btID, force, torque)

        # Tell Bullet to advance the simulation for all objects in the
        # current work list.
        IDs = [util.id2int(_.id) for _ in worklist]
        self.bullet.compute(IDs, admin.dt, admin.maxsteps)

        # Retrieve the objects from Bullet again and update them in the DB.
        out = {}
        for obj in worklist:
            ok, sv = self.bullet.getObjectData([util.id2int(obj.id)])
            if ok != 0:
                # Something went wrong. Reuse the old SV.
                sv = obj.sv
                self.logit.error('Unable to get all objects from Bullet')

            # Override SV with user specified values (if there are any).
            sv = self.setObjectAttributes(obj, sv)

            # Restore the original cshape because Bullet will always return
            # zeros here.
            sv.cshape[:] = obj.sv.cshape[:]
            out[obj.id] = sv

        # Update the data and delete the WP.
        ok = btInterface.updateWorkPackage(wpid, admin.token, out)
        if not ok:
            msg = 'Failed to update work package {}'.format(wpid)
            self.logit.warning(msg)

    def setObjectAttributes(self, obj, sv):
        """
        Return update SV if the user wants to override some of them.

        This method does nothing if the user did not override any values via a
        call to 'overrideAttributes'.

        .. note::
           It is unnecessary to explicitly clear the attrOverride data because
           ``btInterface.updateWorkPackage`` takes care of that automatically.

        :param bytes objID: object ID
        :param BulletData sv: SV for objID.
        """
        tmp = obj.attrOverride

        # Apply the specified values.
        if tmp.pos is not None:
            sv.position[:] = tmp.pos
        if tmp.vLin is not None:
            sv.velocityLin[:] = tmp.vLin
        if tmp.vRot is not None:
            sv.velocityRot[:] = tmp.vRot
        if tmp.orient is not None:
            sv.orientation[:] = tmp.orient
        return sv


class LeonardBaseWorkpackages(LeonardBase):
    """
    A variation of ``LeonardBase`` that uses Work Packages.

    This class is a test dummy and should not be used in production. Like
    ``LeonardBase`` it does not actually compute any physics. It only creates
    work packages and does some dummy processing for them. Everything runs in
    the same process.

    A work package contains a sub-set of all objects in the simulation and a
    token. While this class segments the world, worker nodes will retrieve the
    work packages one by one and step the simulation for the objects inside
    those work packages.
    """
    def __init__(self):
        super().__init__()
        self.token = 0

    @typecheck
    def step(self, dt: (int, float), maxsteps: int):
        """
        Advance the simulation by ``dt`` using at most ``maxsteps``.

        :param float dt: time step in seconds.
        :param int maxsteps: maximum number of sub-steps to simulate for one
                             ``dt`` update.
        """

        # Retrieve the SV for all objects.
        ok, allSV = btInterface.getAllStateVariables()

        # --------------------------------------------------------------------
        # Create a single work list containing all objects and a new token.
        # --------------------------------------------------------------------
        IDs = list(allSV.keys())
        self.token += 1
        ok, wpid = btInterface.createWorkPackage(IDs, self.token, dt, maxsteps)
        if not ok:
            return

        # --------------------------------------------------------------------
        # Process the work list.
        # --------------------------------------------------------------------
        # Fetch the work list.
        ok, worklist, admin = btInterface.getWorkPackage(wpid)
        if not ok:
            return

        # Process the objects one by one. The `out` dict will hold the updated
        # SV information.
        out = {}
        for obj in worklist:
            # Retrieve SV data.
            sv = obj.sv

            # Retrieve the force vector.
            force = np.fromstring(obj.central_force)

            # Add the force defined on the 'force' grid.
            force = self.applyGridForce(force, sv.position)

            # Update the velocity and position.
            sv.velocityLin[:] += 0.5 * force
            sv.position[:] += dt * sv.velocityLin

            # Override SV with user specified values (if there are any).
            sv = self.setObjectAttributes(obj, sv)

            # Add the new SV data to the output dictionary.
            out[obj.id] = sv

        # --------------------------------------------------------------------
        # Update the work list and mark it as completed.
        # --------------------------------------------------------------------
        btInterface.updateWorkPackage(wpid, admin.token, out)

    def setObjectAttributes(self, obj, sv):
        """
        Return update SV if the user wants to override some of them.

        This method does nothing if the user did not override any values via a
        call to 'overrideAttributes'.

        .. note::
           It is unnecessary to explicitly clear the attrOverride data because
           ``btInterface.updateWorkPackage`` takes care of that automatically.

        :param bytes objID: object ID
        :param BulletData sv: SV for objID.
        """
        tmp = obj.attrOverride

        # Apply the specified values.
        if tmp.pos is not None:
            sv.position[:] = tmp.pos
        if tmp.vLin is not None:
            sv.velocityLin[:] = tmp.vLin
        if tmp.vRot is not None:
            sv.velocityRot[:] = tmp.vRot
        if tmp.orient is not None:
            sv.orientation[:] = tmp.orient
        return sv
