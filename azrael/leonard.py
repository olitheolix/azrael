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
import os
import sys
import zmq
import time
import pickle
import pymongo
import IPython
import logging
import setproctitle
import multiprocessing
import numpy as np

import azrael.database
import azrael.vectorgrid
import azrael.util as util
import azrael.config as config
import azrael.bullet.boost_bullet
import azrael.physics_interface as physAPI
import azrael.bullet.bullet_data as bullet_data

from collections import namedtuple
from azrael.typecheck import typecheck

ipshell = IPython.embed
RetVal = azrael.util.RetVal

# Work package related.
WPData = namedtuple('WPRecord', 'id sv force torque')
WPMeta = namedtuple('WPAdmin', 'wpid dt maxsteps')

# Convenience.
BulletData = bullet_data.BulletData
_BulletData = bullet_data._BulletData
BulletDataOverride = bullet_data.BulletDataOverride


@typecheck
def sweeping(data: list, labels: np.ndarray, dim: str):
    """
    Return sets of overlapping AABBs in the dimension ``dim``.

    This function implements the 'Sweeping' algorithm to determine which sets
    of AABBs overlap.

    Sweeping is straightforward: sort all start/stop positions and determine
    the overlapping sets.

    The returned sets do not contain the ``data`` elements but their
    corresponding ``labels`` to be more memory efficient.

    :param list data: list of dictionaries which must contain ['aabb']
    :param np.int64 labels: integer array to label the elements in data.
    :param str dim: the axis to check (must be one of ['x', 'y', 'z'])
    :return: list of sets. Each set contains elements from ``labels``.
    :rtype: list of sets
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
    return RetVal(True, None, out)


@typecheck
def computeCollisionSetsAABB(SVs: dict, AABBs: dict):
    """
    Return potential collision sets among all objects in ``SVs``.

    :param dict SVs: Dictionary of State Vectors.
    :param dict AABBs: Dictionary of AABBs.
    :return: each list contains a unique set of overlapping objects.
    :rtype: list of lists
    """
    # Sanity check.
    if set(SVs.keys()) != set(AABBs.keys()):
        return RetVal(False, 'SVs and AABBs are inconsisten', None)

    # The 'sweeping' function requires a list of dictionaries. Each dictionary
    # must contain the min/max spatial extent in x/y/z direction.
    data = []
    IDs = list(SVs.keys())
    for objID in IDs:
        if (SVs[objID] is None) or (AABBs[objID] is None):
            continue
        sv, aabb = SVs[objID], AABBs[objID]
        pos = sv.position
        x0, x1 = pos[0] - aabb, pos[0] + aabb
        y0, y1 = pos[1] - aabb, pos[1] + aabb
        z0, z1 = pos[2] - aabb, pos[2] + aabb

        data.append({'x': [x0, x1], 'y': [y0, y1], 'z': [z0, z1]})
    del SVs, AABBs

    # Enumerate the objects.
    labels = np.arange(len(IDs))

    # Determine the overlapping objects in 'x' direction.
    stage_0 = sweeping(data, labels, 'x').data

    # Determine which of the objects that overlap in 'x' also overlap in 'y'.
    stage_1 = []
    for subset in stage_0:
        tmpData = [data[_] for _ in subset]
        tmpLabels = np.array(tuple(subset), np.int64)
        stage_1.extend(sweeping(tmpData, tmpLabels, 'y').data)

    # Now determine the objects that overlap in all three dimensions.
    stage_2 = []
    for subset in stage_1:
        tmpData = [data[_] for _ in subset]
        tmpLabels = np.array(tuple(subset), np.int64)
        stage_2.extend(sweeping(tmpData, tmpLabels, 'z').data)

    # Convert the labels back to object IDs.
    out = [[IDs[objID] for objID in objIDs] for objIDs in stage_2]
    return RetVal(True, None, out)


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

        # Create the DB handles.
        self._DB_SV = azrael.database.dbHandles['SV']

        self.allObjects = {}
        self.allAABBs = {}
        self.directForces = {}
        self.directTorques = {}
        self.boosterForces = {}
        self.boosterTorques = {}

    def setup(self):
        """
        Stub for initialisation code that cannot go into the constructor.

        Since Leonard is a process not everything can be initialised in the
        constructor because it executes before the process forks.
        """
        pass

    def getGridForces(self, idPos: dict):
        """
        Return dictionary of force values for every object in ``idPos``.

        The ``idPos`` argument is a {objID_1: sv_1, objID_2, sv_2, ...}
        dictionary.

        The returned dictionary has the same keys as ``idPos``.

        :param dict idPos: dictionary with objIDs and corresponding SVs.
        :return dict: {objID_k: force_k}
        """
        # Convenience.
        vg = azrael.vectorgrid

        # Extract the keys and values in the same order.
        objIDs = list(idPos.keys())
        positions = [idPos[_] for _ in objIDs]

        # Query the grid values at all positions.
        ret = vg.getValues('force', positions)
        if not ret.ok:
            return RetVal(False, ret.msg, None)

        # Overwrite the default values.
        gridForces = {objID: val for objID, val in zip(objIDs, ret.data)}
        return RetVal(True, None, gridForces)

    def totalForceAndTorque(self, objID):
        sv = self.allObjects[objID]
        
        # Fetch the force vector for the current object from the DB.
        force = np.array(self.directForces[objID], np.float64)
        torque = np.array(self.directTorques[objID], np.float64)

        # Add the forces and torques added by the bootster.
        quat = util.Quaternion(sv.orientation[3], sv.orientation[:3])
        force += quat * self.boosterForces[objID]
        torque += quat * self.boosterTorques[objID]

        return force.tolist(), torque.tolist()

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
        self.processCommandQueue()

        # Fetch the forces for all object positions.
        idPos = {k: v.position for (k, v) in self.allObjects.items()}
        ret = self.getGridForces(idPos)
        if not ret.ok:
            self.logit.info(ret.msg)
            z = np.float64(0)
            gridForces = {_: z for _ in idPos}
        else:
            gridForces = ret.data
        del ret, idPos

        # Iterate over all objects and update their SV information in Bullet.
        for objID, sv in self.allObjects.items():
            # Compute direct- and booster forces on object.
            force, torque = self.totalForceAndTorque(objID)

            # Add the force defined on the 'force' grid.
            force += gridForces[objID]

            # Update velocity and position.
            vel = np.array(sv.velocityLin, np.float64) + 0.5 * force
            pos = np.array(sv.position, np.float64)
            sv.velocityLin[:] = vel.tolist()
            sv.position[:] = (pos + dt * vel).tolist()

            self.allObjects[objID] = sv

        # Synchronise the local object cache back to the database.
        self.syncObjects(writeconcern=False)

    def processCommandQueue(self):
        """
        Apply commands from queue to objects in local cache.

        Applied commands are automatically removed.

        :return bool: Success.
        """
        # Fetch (and de-queue) all pending commands.
        ret = physAPI.dequeueCommands()
        if not ret.ok:
            msg = 'Cannot fetch commands'
            self.logit.error(msg)
            return RetVal(False, msg, None)

        # Convenience.
        cmds = ret.data
        fields = BulletDataOverride._fields

        # Remove objects.
        for doc in cmds['remove']:
            objID = doc['objID']
            if objID in self.allObjects:
                self._DB_SV.remove({'objID': objID})
                del self.allObjects[objID]
                del self.directForces[objID]
                del self.directTorques[objID]
                del self.boosterForces[objID]
                del self.boosterTorques[objID]
                del self.allAABBs[objID]

        # Spawn objects.
        for doc in cmds['spawn']:
            objID = doc['objID']
            if objID in self.allObjects:
                msg = 'Cannot spawn object since objID={} already exists'
                self.logit.warning(msg.format(objID))
            else:
                sv_old = doc['sv']
                self.allObjects[objID] = _BulletData(*sv_old)
                self.directForces[objID] = [0, 0, 0]
                self.directTorques[objID] = [0, 0, 0]
                self.boosterForces[objID] = [0, 0, 0]
                self.boosterTorques[objID] = [0, 0, 0]
                self.allAABBs[objID] = float(doc['AABB'])

        # Update State Vectors.
        fun = physAPI._updateBulletDataTuple
        for doc in cmds['modify']:
            objID, sv_new = doc['objID'], doc['sv']
            if objID in self.allObjects:
                sv_new = BulletDataOverride(**dict(zip(fields, sv_new)))
                sv_old = self.allObjects[objID]
                sv_old = [getattr(sv_old, _) for _ in fields]
                sv_old = BulletData(*sv_old)
                self.allObjects[objID] = fun(sv_old, sv_new)

        # Update direct force- and torque values.
        for doc in cmds['direct_force']:
            objID, force, torque = doc['objID'], doc['force'], doc['torque']
            if (objID in self.directForces) and (objID in self.directTorques):
                self.directForces[objID] = force
                self.directTorques[objID] = torque

        # Update booster force- and torque values.
        for doc in cmds['booster_force']:
            objID, force, torque = doc['objID'], doc['force'], doc['torque']
            if (objID in self.boosterForces) and (objID in self.boosterTorques):
                self.boosterForces[objID] = force
                self.boosterTorques[objID] = torque

        return RetVal(True, None, None)

    def syncObjects(self, writeconcern: bool):
        """
        Copy all local SVs to DB.

        The ``writeconcern`` flag is mostly for performance tuning. If set to
        *False* then the sync will not wait for an acknowledgement from the
        database after the write opration.

        :param bool writeconcern: disable write concern when set to *False*.
        """
        # Return immediately if we have no objects to begin with.
        if len(self.allObjects) == 0:
            return

        # Update (or insert if not exist) all objects. Use a Bulk operator to
        # speed up the query.
        bulk = self._DB_SV.initialize_unordered_bulk_op()
        for objID, sv in self.allObjects.items():
            query = {'objID': objID}
            data = {'objID': objID, 'sv': sv, 'AABB': self.allAABBs[objID]}
            bulk.find(query).upsert().update({'$set': data})

        if writeconcern:
            bulk.execute()
        else:
            bulk.execute({'w': 0, 'j': False})

    def processCommandsAndSync(self):
        """
        Process all pending commands and syncronise the cache to the DB.

        This method is useful for unit tests but probably not much else. It
        also ensures that the synchronisation of the objects from the local
        cache to the database is acknowledged by the database (this is turned
        off in production because it slows down Leonard an the information is
        not critical).
        """
        self.processCommandQueue()
        self.syncObjects(writeconcern=True)

    def run(self):
        """
        Drive the periodic physics updates.
        """
        setproctitle.setproctitle('killme ' + self.__class__.__name__)

        # Initialisation.
        self.setup()
        self.logit.debug('Setup complete.')

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
            with util.Timeit('Leonard:1.0 Step') as timeit:
                self.step(0.1, 10)


class LeonardBullet(LeonardBase):
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

        # Process pending commands.
        self.processCommandQueue()

        # Fetch the forces for all object positions.
        idPos = {k: v.position for (k, v) in self.allObjects.items()}
        ret = self.getGridForces(idPos)
        if not ret.ok:
            self.logit.info(ret.msg)
            z = np.float64(0)
            gridForces = {_: z for _ in idPos}
        else:
            gridForces = ret.data
        del ret, idPos

        # Iterate over all objects and update them.
        for objID, sv in self.allObjects.items():
            # Pass the SV data from the DB to Bullet.
            self.bullet.setObjectData(objID, sv)

            # Compute direct- and booster forces on object.
            force, torque = self.totalForceAndTorque(objID)

            # Add the force defined on the 'force' grid.
            force += gridForces[objID]

            # Apply the force to the object.
            self.bullet.applyForceAndTorque(objID, force, torque)

        # Wait for Bullet to advance the simulation by one step.
        with util.Timeit('compute') as timeit:
            self.bullet.compute(list(self.allObjects.keys()), dt, maxsteps)

        # Retrieve all objects from Bullet, overwrite the state variables that
        # the user wanted to change explicitly (if any)
        for objID in self.allObjects:
            ret = self.bullet.getObjectData([objID])
            if ret.ok:
                self.allObjects[objID] = ret.data

        # Synchronise the local object cache back to the database.
        self.syncObjects(writeconcern=False)


class LeonardSweeping(LeonardBullet):
    """
    Compute physics on independent collision sets.

    This is a modified version of ``LeonardBullet`` that uses
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
        self.processCommandQueue()

        # Compute the collision sets.
        with util.Timeit('CCS') as timeit:
            collSets = computeCollisionSetsAABB(self.allObjects, self.allAABBs)
        if not collSets.ok:
            self.logit.error('ComputeCollisionSetsAABB returned an error')
            sys.exit(1)
        collSets = collSets.data

        # Log the number of created collision sets.
        util.logMetricQty('#CollSets', len(collSets))

        # Convenience.
        vg = azrael.vectorgrid

        # Process all subsets individually.
        for subset in collSets:
            # Compile the subset dictionary for the current collision set.
            coll_SV = {_: self.allObjects[_] for _ in subset}

            # Fetch the forces for all object positions.
            idPos = {k: v.position for (k, v) in coll_SV.items()}
            ret = self.getGridForces(idPos)
            if not ret.ok:
                self.logit.info(ret.msg)
                z = np.float64(0)
                gridForces = {_: z for _ in idPos}
            else:
                gridForces = ret.data
            del ret, idPos

            # Iterate over all objects and update them.
            for objID, sv in coll_SV.items():
                # Pass the SV data from the DB to Bullet.
                self.bullet.setObjectData(objID, sv)

                # Compute direct- and booster forces on object.
                force, torque = self.totalForceAndTorque(objID)

                # Add the force defined on the 'force' grid.
                force += gridForces[objID]

                # Apply the final force to the object.
                self.bullet.applyForceAndTorque(objID, force, torque)

            # Wait for Bullet to advance the simulation by one step.
            with util.Timeit('compute') as timeit:
                self.bullet.compute(list(coll_SV.keys()), dt, maxsteps)

            # Retrieve all objects from Bullet.
            for objID, sv in coll_SV.items():
                ret = self.bullet.getObjectData([objID])
                if ret.ok:
                    self.allObjects[objID] = ret.data

        # Synchronise the local object cache back to the database.
        self.syncObjects(writeconcern=False)


class LeonardDistributedZeroMQ(LeonardBase):
    """
    Compute physics with separate engines.

    This class uses the concept of Work Packages to distribute work. Every Work
    Package is self contained and holds all the information Bullet requires to
    step the simulation.

    This class is single threaded. All Bullet engines run sequentially in the
    main thread. The work packages are distributed at random to the engines.

    This class uses the sweeping algorithm to determine collision sets, just
    like ``LeonardSweeping`` does.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.workers = []
        self.numWorkers = 3
        self.wpid_counter = 0

        # Worker terminate automatically after a certain number of processed
        # Work Packages. The precise number is a constructor argument and the
        # following two variables simply specify the range. The final number
        # will be chosen randomly from this interval (different for every Worke
        # instance to avoid the situation where all die simultaneously).
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

        # Spawn the Workers.
        workermanager = WorkerManager(
            self.numWorkers, self.minSteps,
            self.maxSteps, LeonardWorkerZeroMQ)
        workermanager.start()
        self.logit.info('Setup complete')

    @typecheck
    def step(self, dt, maxsteps):
        """
        Advance the simulation by ``dt`` using at most ``maxsteps``.

        This method moves all SV objects from the database to the Bullet
        engine. Then it defers to Bullet for the physics update. Finally, it
        replaces the SV fields with the user specified values (only applies if
        the user called 'setStateVariable') and writes the results back to the
        database.

        :param float dt: time step in seconds.
        :param int maxsteps: maximum number of sub-steps to simulate for one
                             ``dt`` update.
        """
        # Read queued commands and update the local object cache accordingly.
        with util.Timeit('Leonard:1.1  processCmdQueue') as timeit:
            self.processCommandQueue()

        # Compute the collision sets.
        with util.Timeit('Leonard:1.2  CCS') as timeit:
            collSets = computeCollisionSetsAABB(self.allObjects, self.allAABBs)
            if not collSets.ok:
                self.logit.error('ComputeCollisionSetsAABB returned an error')
                sys.exit(1)
            collSets = collSets.data

        # Log the number of created collision sets.
        util.logMetricQty('#CollSets', len(collSets))

        # Put each collision set into its own Work Package.
        with util.Timeit('Leonard:1.3  CreateWPs') as timeit:
            all_WPs = {}
            for subset in collSets:
                # Compile the Work Package.
                ret = self.createWorkPackage(list(subset), dt, maxsteps)
                if not ret.ok:
                    self.logit.error(ret.msg)
                    return
                all_WPs[ret.data['wpid']] = ret.data

        with util.Timeit('Leonard:1.4  WPSendRecv') as timeit:
            wpIdx = 0
            worklist = list(all_WPs.keys())
            while True:
                # Wait until Worker contacts us. The message usually contains a
                # processed Work Package. However, it may also be empty, most
                # likely because the Worker has not received a Work Package
                # from us yet.
                msg = self.sock.recv()
                if msg != b'':
                    # Unpickle the message.
                    msg = pickle.loads(msg)
                    wpid = msg['wpid']

                    # Ignore the message if its Work Package is not pending
                    # anymore (most likely because multiple Workers processed
                    # the same Work Package and the other Worker has already
                    # returned it).
                    if wpid in all_WPs:
                        self.updateLocalCache(msg['wpdata'])

                        # Decrement the Work Package Index if the wpIdx counter
                        # is already past that work package. This simply
                        # ensures that no WP is skipped simply because the
                        # queue has shrunk.
                        if worklist.index(wpid) < wpIdx:
                            wpIdx -= 1

                        # Remove the WP from the work list and the WP cache.
                        worklist.remove(wpid)
                        del all_WPs[wpid]

                # Send an empty message to the Worker if now Work Packages are
                # pending anymore. This empty message is important to avoid
                # breaking the REQ/REP pattern enforced by ZeroMQ.
                if len(all_WPs) == 0:
                    self.sock.send(b'')
                    break

                # Pick the next pending Work Package and increment the index.
                if wpIdx >= len(worklist):
                    wpIdx = 0
                wp = all_WPs[worklist[wpIdx]]
                wpIdx += 1

                # Send the Work Package to the Worker.
                self.sock.send(pickle.dumps(wp))

        # Synchronise the local cache back to the database.
        with util.Timeit('Leonard:1.5  syncObjects') as timeit:
            self.syncObjects(writeconcern=False)

    @typecheck
    def createWorkPackage(self, objIDs: (tuple, list),
                          dt: (int, float), maxsteps: int):
        """
        Create a new Work Package (WP) and return its ID.

        The Work Package will not be returned but uploaded to the DB directly.

        A Work Package carries the necessary information for another rigid body
        physics steps. The Worker can thus start its work immediately, at least
        in terms of the rigid bodies (it may still want to incorporate other
        data like grid forces, but that is up to the Worker implementation).

        The ``dt`` and ``maxsteps`` arguments are for the underlying physics
        engine.

        .. note::
           A work package contains only the objIDs but not their SV. The
           ``getNextWorkPackage`` function takes care of compiling this
           information.

        :param iterable objIDs: list of object IDs in the new work package.
        :param float dt: time step for this work package.
        :param int maxsteps: number of sub-steps for the time step.
        :return: Work package ID
        :rtype: int
        """
        # Sanity check.
        if len(objIDs) == 0:
            return RetVal(False, 'Work package is empty', None)

        # Compile the State Vectors and forces for all objects into a list of
        # ``WPData`` named tuples.
        try:
            wpdata = []
            for objID in objIDs:
                sv = self.allObjects[objID]
                force, torque = self.totalForceAndTorque(objID)
                wpdata.append((objID, sv, force, torque))
        except KeyError as err:
            return RetVal(False, 'Cannot form WP', None)

        # Form the content of the Work Package as it will appear in the DB.
        data = {'wpid': self.wpid_counter,
                'wpmeta': (self.wpid_counter, dt, maxsteps),
                'wpdata': wpdata,
                'ts': None}
        self.wpid_counter += 1
        return RetVal(True, None, data)

    def updateLocalCache(self, wpdata):
        """
        Copy every object from ``wpdata`` to the local cache.

        The ``wpdata`` argument is a list of (objID, sv) tuples.

        The implicit assumption of this method is that ``wpdata`` is the
        output of ``computePhysicsForWorkPackage`` from a Worker.

        :param list wpdata: Content of Work Packge as returned by Workers.
        """
        # Reset force and torque for all objects in the WP, and overwrite
        # the old State Vector with the new one from the processed WP.
        for (objID, sv) in wpdata:
            self.allObjects[objID] = _BulletData(*sv)


class LeonardWorkerZeroMQ(multiprocessing.Process):
    """
    Dedicated Worker to process Work Packages.

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

        # Record the PID of the parent.
        self.parentPID = os.getpid()

        # Instantiate a Bullet engine.
        engine = azrael.bullet.boost_bullet.PyBulletPhys
        self.bullet = engine(self.workerID)

    def getGridForces(self, idPos: dict):
        """
        Return dictionary of force values for every object in ``idPos``.

        The ``idPos`` argument is a {objID_1: sv_1, objID_2, sv_2, ...}
        dictionary.

        The returned dictionary has the same keys as ``idPos``.

        :param dict idPos: dictionary with objIDs and corresponding SVs.
        :return dict: {objID_k: force_k}
        """
        # Convenience.
        vg = azrael.vectorgrid

        # Extract the keys and values in the same order.
        objIDs = list(idPos.keys())
        positions = [idPos[_] for _ in objIDs]

        # Query the grid values at all positions.
        ret = vg.getValues('force', positions)
        if not ret.ok:
            return RetVal(False, ret.msg, None)

        # Overwrite the default values with whatever ...
        gridForces = {objID: val for objID, val in zip(objIDs, ret.data)}
        return RetVal(True, None, gridForces)

    def computePhysicsForWorkPackage(self, wp):
        """
        Compute a physics steps for all objects in ``wp``.

        The output of this method is matched to the ``updateLocalCache`` in
        Leonard itself.

        :param dict wp: Work Package content from ``createWorkPackage``.
        :return dict: {'wpdata': list_of_SVs, 'wpid': wpid}
        """
        worklist, meta = wp['wpdata'], WPMeta(*wp['wpmeta'])

        # Log the number of collision-sets in the current Work Package.
        util.logMetricQty('Engine_{}'.format(self.workerID), len(worklist))

        # Convenience: the WPData elements make the code more readable.
        worklist = [WPData(*_) for _ in worklist]

        # Convenience.
        applyForceAndTorque = self.bullet.applyForceAndTorque
        setObjectData = self.bullet.setObjectData

        # Add every object to the Bullet engine and set the force/torque.
        with util.Timeit('Worker:1.1.0  applyforce') as timeit:
            with util.Timeit('Worker:1.1.1   grid') as timeit:
                # Fetch the forces for all object positions.
                idPos = {_.id: _.sv.position for _ in worklist}
                ret = self.getGridForces(idPos)
                if not ret.ok:
                    self.logit.info(ret.msg)
                    z = np.float64(0)
                    gridForces = {_: z for _ in idPos}
                else:
                    gridForces = ret.data
                del ret, idPos

            with util.Timeit('Worker:1.1.1   updateGeo') as timeit:
                for obj in worklist:
                    # Update the object in Bullet and apply the force/torque.
                    setObjectData(obj.id, obj.sv)

            with util.Timeit('Worker:1.1.1   updateForce') as timeit:
                for obj in worklist:
                    # Add the force defined on the 'force' grid.
                    force = obj.force + gridForces[obj.id]
                    applyForceAndTorque(obj.id, force, obj.torque)

        # Tell Bullet to advance the simulation for all objects in the
        # current work list.
        with util.Timeit('Worker:1.2.0  compute') as timeit:
            IDs = [_.id for _ in worklist]
            self.bullet.compute(IDs, meta.dt, meta.maxsteps)

        with util.Timeit('Worker:1.3.0  fetchFromBullet') as timeit:
            # Retrieve the objects from Bullet again and update them in the DB.
            out = []
            for obj in worklist:
                ret = self.bullet.getObjectData([obj.id])
                sv = ret.data
                if not ret.ok:
                    # Something went wrong. Reuse the old SV.
                    sv = obj.sv
                    self.logit.error('Unable to get all objects from Bullet')
                out.append((obj.id, sv))

        # Update the data and delete the WP.
        return {'wpid': meta.wpid, 'wpdata': out}

    @typecheck
    def run(self):
        """
        Wait for Work Packages, process them, and return the results.
        """
        try:
            # Rename process to make it easy to find and kill them in the
            # process table.
            if os.getpid() != self.parentPID:
                setproctitle.setproctitle('killme LeonardWorker')

            # Setup ZeroMQ.
            ctx = zmq.Context()
            sock = ctx.socket(zmq.REQ)
            sock.connect(config.addr_leonard_pushpull)
            self.logit.info('Worker {} connected'.format(self.workerID))

            # Contact Leonard with an empty payload.
            sock.send(b'')

            # Wait for messages from Leonard. If they contain a WP then process
            # it and return the result, otherwise reply with an empty message.
            numSteps = 0
            suq = self.stepsUntilQuit
            while numSteps < suq:
                # Wait for the next message.
                msg = sock.recv()

                # If Leonard did not send a Work Package (probably because it
                # does not have one right now) then wait for a short time
                # before asking again to avoid spamming the network.
                if msg == b'':
                    time.sleep(0.003)
                    sock.send(b'')
                    continue

                # Unpickle the Work Package.
                wpdata = pickle.loads(msg)

                # Process the Work Package.
                with util.Timeit('Worker:1.0.0 WPTotal') as timeit:
                    wpdata = self.computePhysicsForWorkPackage(wpdata)

                # Pack up the Work Package and send it back to Leonard.
                sock.send(pickle.dumps(wpdata))

                # Count the number of Work Packages we have processed.
                numSteps += 1

            # Log a last status message before terminating.
            self.logit.info('Worker {} terminated itself after {} steps'
                            .format(self.workerID, numSteps))
        except KeyboardInterrupt:
            print('Aborted Worker {}'.format(self.workerID))

        # Terminate.
        sock.close(linger=0)
        ctx.destroy()


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
        Start the initial collection of Workers and ensure they remain alive.
        """
        # Rename the process.
        setproctitle.setproctitle('killme ' + self.__class__.__name__)

        # Spawn the initial collection of Workers.
        workers = []
        delta = self.maxSteps - self.minSteps
        for ii in range(self.numWorkers):
            # Random number in [minSteps, maxSteps]. The process will
            # automatically terminate after `suq` steps.
            suq = self.minSteps + int(np.random.rand() * delta)

            # Instantiate the process and add it to the list.
            workers.append(self.workerCls(ii + 1, suq))
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
                proc = self.workerCls(workerID, suq)
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
