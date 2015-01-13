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
import pymongo
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

from collections import namedtuple
from azrael.typecheck import typecheck

ipshell = IPython.embed
RetVal = azrael.util.RetVal

# Work package related.
WPData = namedtuple('WPRecord', 'id sv central_force torque')
WPMeta = namedtuple('WPAdmin', 'token dt maxsteps')


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
def computeCollisionSetsAABB(IDs: list, SVs: list, aabbs: list):
    """
    Return potential collision sets among all ``IDs`` and associated ``SVs``.

    :param IDs: list of object IDs.
    :param SVs: list of object BulletData instances. Corresponds to IDs.
    :return: each list contains a unique set of overlapping objects.
    :rtype: list of lists
    """
    # Sanity check.
    if len(IDs) != len(SVs):
        return RetVal(False, 'Inconsistent parameters', None)

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
    out = [[IDs[_] for _ in __] for __ in stage_2]
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
        client = pymongo.MongoClient()
        self._DB_SV = client['azrael']['sv']
        self._DB_CMDSpawn = client['azrael']['CmdSpawn']
        self._DB_CMDRemove = client['azrael']['CmdRemove']
        self._DB_CMDModify = client['azrael']['CmdModify']

        self.allObjects = {}
        self.allAABBs = {}
        self.allForces = {}
        self.allTorques = {}

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
        self.processCommandQueue()

        # Iterate over all objects and update their SV information in Bullet.
        for objID, sv in self.allObjects.items():
            # Fetch the force vector for the current object from the DB.
            force = np.array(self.allForces[objID], np.float64)

            # Add the force defined on the 'force' grid.
            force = self.applyGridForce(force, sv.position)

            # Update velocity and position.
            sv.velocityLin[:] += 0.5 * force
            sv.position[:] += dt * sv.velocityLin

            self.allForces[objID] = [0, 0, 0]
            self.allTorques[objID] = [0, 0, 0]
            self.allObjects[objID] = sv

        self.syncObjects()

    def processCommandQueue(self):
        """
        Apply commands from queue to objects in local cache.

        Applied commands are automatically removed.

        :return bool: Success.
        """
        # Fetch all commands currently in queue.
        docsModify = btInterface.getCmdModify()
        if not docsModify.ok:
            msg = 'Cannot fetch "Modify" commands'
            self.logit.error(msg)
            return RetVal(False, msg, None)
        docsRemove = btInterface.getCmdRemove()
        if not docsRemove.ok:
            msg = 'Cannot fetch "Remove" commands'
            self.logit.error(msg)
            return RetVal(False, msg, None)
        docsSpawn = btInterface.getCmdSpawn()
        if not docsSpawn.ok:
            msg = 'Cannot fetch "Spawn" commands'
            self.logit.error(msg)
            return RetVal(False, msg, None)

        # Remove the fetched commands from queue.
        tmp = [_['objid'] for _ in docsSpawn.data]
        btInterface.dequeueCmdSpawn(tmp)
        tmp = [_['objid'] for _ in docsModify.data]
        btInterface.dequeueCmdModify( tmp)
        tmp = [_['objid'] for _ in docsRemove.data]
        btInterface.dequeueCmdRemove(tmp)
        del tmp

        # Convenience.
        docsSpawn = docsSpawn.data
        docsModify = docsModify.data
        docsRemove = docsRemove.data

        BulletData = bullet_data.BulletData
        BulletDataOverride = bullet_data.BulletDataOverride
        fields = BulletDataOverride._fields

        # Remove objects.
        for doc in docsRemove:
            objID = doc['objid']
            if objID in self.allObjects:
                self._DB_SV.remove({'objid': objID})
                del self.allObjects[objID]

        # Spawn objects.
        for doc in docsSpawn:
            objID = doc['objid']
            if objID in self.allObjects:
                msg = 'Cannot spawn object since objID={} already exists'
                self.logit.warning(msg.format(objID))
            else:
                sv_old = doc['sv']
                self.allObjects[objID] = BulletData(**sv_old)
                self.allAABBs[objID] = float(doc['AABB'])
                self.allForces[objID] = [0, 0, 0]
                self.allTorques[objID] = [0, 0, 0]

        # Update State Vectors.
        fun = btInterface._updateBulletDataTuple
        for doc in docsModify:
            objID, sv_new = doc['objid'], doc['sv']
            if objID in self.allObjects:
                sv_new = BulletDataOverride(**dict(zip(fields, sv_new)))
                sv_old = self.allObjects[objID]
                sv_old = [getattr(sv_old, _) for _ in fields]
                sv_old = BulletData(*sv_old)
                self.allObjects[objID] = fun(sv_old, sv_new)

        return RetVal(True, None, None)

    def syncObjects(self):
        """
        Copy all local SVs to DB.
        """
        for objID, sv in self.allObjects.items():
            doc = self._DB_SV.update(
                {'objid': objID},
                {'$set': {'objid': objID, 'sv': sv.toJsonDict(),
                          'AABB': self.allAABBs[objID]}},
                upsert=True)

    def processCommandsAndSync(self):
        self.processCommandQueue()
        self.syncObjects()                    
        
    @typecheck
    def countWorkPackages(self, token):
        """
        Return the number of unprocessed work packages.
    
        fixme: should this method really be in this class?

        :param int token: token value associated with this work package.
        :return bool: Success.
        """
        cnt = self._DB_WP.find({'token': token}).count()
        return RetVal(True, None, cnt)
    
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
            with util.Timeit('Leonard.step') as timeit:
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

        self.processCommandQueue()

        # Iterate over all objects and update them.
        for objID, sv in self.allObjects.items():
            # Convert the objID to an integer.
            btID = util.id2int(objID)

            # Pass the SV data from the DB to Bullet.
            self.bullet.setObjectData(btID, sv)

            # Convenience.
            force = np.array(self.allForces[objID], np.float64)
            torque = np.array(self.allTorques[objID], np.float64)

            # Add the force defined on the 'force' grid.
            force = self.applyGridForce(force, sv.position)

            # Apply the force to the object.
            self.bullet.applyForceAndTorque(btID, force, torque)

        # Wait for Bullet to advance the simulation by one step.
        IDs = [util.id2int(_) for _ in self.allObjects.keys()]
        with util.Timeit('compute') as timeit:
            self.bullet.compute(IDs, dt, maxsteps)

        # Retrieve all objects from Bullet, overwrite the state variables that
        # the user wanted to change explicitly (if any)
        for objID in self.allObjects:
            ret = self.bullet.getObjectData([util.id2int(objID)])
            if ret.ok:
                self.allObjects[objID] = ret.data
            self.allForces[objID] = [0, 0, 0]
            self.allTorques[objID] = [0, 0, 0]

        self.syncObjects()


class LeonardBulletSweeping(LeonardBullet):
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
            labels = list(self.allObjects.keys())
            SVs = list(self.allObjects.values())
            AABBs = list(self.allAABBs.values())
            collSets = computeCollisionSetsAABB(labels, SVs, AABBs)
            del labels, SVs, AABBs
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

            # Iterate over all objects and update them.
            for objID, sv in coll_SV.items():
                # Convert the objID to an integer.
                btID = util.id2int(objID)

                # Pass the SV data from the DB to Bullet.
                self.bullet.setObjectData(btID, sv)

                # Convenience.
                force = np.array(self.allForces[objID], np.float64)
                torque = np.array(self.allTorques[objID], np.float64)

                # Add the force defined on the 'force' grid.
                force = self.applyGridForce(force, sv.position)

                # Apply the final force to the object.
                self.bullet.applyForceAndTorque(btID, force, torque)

            # Wait for Bullet to advance the simulation by one step.
            IDs = [util.id2int(_) for _ in coll_SV.keys()]
            with util.Timeit('compute') as timeit:
                self.bullet.compute(IDs, dt, maxsteps)

            # Retrieve all objects from Bullet.
            for objID, sv in coll_SV.items():
                ret = self.bullet.getObjectData([util.id2int(objID)])
                if ret.ok:
                    self.allObjects[objID] = ret.data
                self.allForces[objID] = [0, 0, 0]
                self.allTorques[objID] = [0, 0, 0]
        self.syncObjects()


class LeonardWorkPackages(LeonardBase):
    """
    Compute physics on independent collision sets with multiple engines.

    This version is similar to ``LeonardBulletSweeping`` but employs dedicated
    Worker instances.

    This class is single threaded. All Bullet engines run sequentially in the
    main thread. The work packages are distributed at random to the engines.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.token = 0

        # Database handles.
        client = pymongo.MongoClient()
        self._DB_WP = client['azrael']['wp']
        self._DB_WP.drop()
        self._DB_WP.insert({'name': 'wpcnt', 'cnt': 0})

    def setup(self):
        """
        No setup required.
        """
        pass

    @typecheck
    def step(self, dt, maxsteps):
        """
        Advance the simulation by ``dt`` using at most ``maxsteps``.

        This method moves all SV objects from the database to the Bullet
        engine. Then it defers to Bullet for the physics update. Finally, it
        replaces the SV fields with the user specified values (only applies if
        the user called 'setStateVariables') and writes the results back to the
        database.

        :param float dt: time step in seconds.
        :param int maxsteps: maximum number of sub-steps to simulate for one
                             ``dt`` update.
        """
        self.processCommandQueue()        

        # Compute the collision sets.
        with util.Timeit('Leonard.CCS') as timeit:
            labels = list(self.allObjects.keys())
            SVs = list(self.allObjects.values())
            AABBs = list(self.allAABBs.values())
            collSets = computeCollisionSetsAABB(labels, SVs, AABBs)
            del labels, SVs, AABBs
        if not collSets.ok:
            self.logit.error('ComputeCollisionSetsAABB returned an error')
            sys.exit(1)
        collSets = collSets.data

        # Log the number of created collision sets.
        util.logMetricQty('#CollSets', len(collSets))

        # Update the token value for this iteration.
        self.token += 1

        # Put each collision set into its own Work Package.
        with util.Timeit('Leonard.CreateWPs') as timeit:
            all_wpids = []
            cwp = self.createWorkPackage
            for subset in collSets:
                ret = cwp(list(subset), self.token, dt, maxsteps)
                if ret.ok:
                    all_wpids.append(ret.data)

        # Schedule all Work Packages for processing and wait until it is done.
        with util.Timeit('Leonard.ProcessWPs_1') as timeit:
            for wpid in all_wpids:
                # Create a dedicated engine. This is slow but ok because the
                # single threaded version is only useful for testing anyway.
                engine = LeonardWorker(1, 1)
                engine.processWorkPackage(wpid)
                
        with util.Timeit('Leonard.ProcessWPs_2') as timeit:
            self.waitUntilWorkpackagesComplete(all_wpids, self.token)

        # Synchronise the objects with the DB.
        self.syncObjects()

    def waitUntilWorkpackagesComplete(self, all_wpids, token):
        """
        Block until all work packages have been completed.
        """
        while self._DB_WP.find({'wpid': {'$exists': 1}}).count() > 0:
            self.pullCompletedWorkPackages()
            time.sleep(0.001)

    @typecheck
    def createWorkPackage(self, objIDs: (tuple, list), token: int,
                          dt: (int, float), maxsteps: int):
        """
        Create a new Work Package (WP) and return its ID.
    
        The work package has an associated ``token`` value and all ``objIDs`` in
        the work list will be marked with it to prevent accidental updates.
    
        The ``dt`` and ``maxsteps`` arguments are for the underlying physics
        engine.
    
        .. note::
           A work package contains only the objIDs but not their SV. The
           ``getWorkPackage`` function takes care of compiling this information.
    
        :param iterable objIDs: list of object IDs in the new work package.
        :param int token: token value associated with this work package.
        :param float dt: time step for this work package.
        :param int maxsteps: number of sub-steps for the time step.
        :return: Work package ID
        :rtype: int
        """
        # Sanity check.
        if len(objIDs) == 0:
            return RetVal(False, 'Work package is empty', None)
    
        # Create a new work package.
        try:
            wpdata = [WPData(objID,
                                 self.allObjects[objID].toJsonDict(),
                                 self.allForces[objID],
                                 self.allTorques[objID])
                              for objID in objIDs]
        except KeyError as err:
            return RetVal(False, 'Cannot form WP', None)

        # Obtain a new and unique work package ID.
        wpid = self._DB_WP.find_and_modify(
            {'name': 'wpcnt'}, {'$inc': {'cnt': 1}}, new=True)
        if wpid is None:
            self.logit.error('Could not fetch WPID counter - this is a bug!')
            return RetVal(False, 'Could not get new WP counter', None)
        wpid = wpid['cnt']
    
        # Remove all WP with the current ID. This is a precaution since there
        # should not be any to begin with.
        ret = self._DB_WP.remove({'wpid': wpid}, multi=True)
        if ret['n'] > 0:
            self.logit.warning('A previous WP with ID={} already existed'.format(wpid))
    
        data = {'wpid': wpid, 'token': token, 'dt': dt, 'maxsteps': maxsteps,
                'wpdata': wpdata}
        
        ret = self._DB_WP.insert(data)
        return RetVal(True, None, wpid)
    
    def pullCompletedWorkPackages(self):
        """
        Fetch newly available Work Packages.

        fixme: most of this function is a duplicate of getWorkPackage
        fixme: docu and parameters

        All fetched work packages will be immediately removed from the DB and
        all objects updated in the local cache. This method will also clear the
        force and torque values.

        :return int: number of fetched WPs.
        """
        cnt = 0
        while True:
            # fixme: improve this query once the counters were outsourced.
            # Retrieve the work package.
            doc = self._DB_WP.find_and_modify(
                {'token': {'$exists': 0},
                 'name': {'$exists': 0}},
                remove=True)
            if doc is None:
                break
        
            # fixme: simplify
            wpdata = [WPData(*_) for _ in doc['wpdata']]
            for idx, val in enumerate(wpdata):
                objID = val.id
                self.allObjects[objID] = bullet_data.fromJsonDict(val.sv)
                self.allForces[objID] = [0, 0, 0]
                self.allTorques[objID] = [0, 0, 0]
            cnt += 1
        return RetVal(True, None, cnt)


class LeonardBulletSweepingMultiMT(LeonardWorkPackages):
    """
    Compute physics on independent collision sets with multiple engines.

    Leverage ``LeonardWorkPackages`` but process the work packages in
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
            self.maxSteps, LeonardWorker)
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
        cls = LeonardWorker
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


class LeonardWorker(multiprocessing.Process):
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

        # Database handles.
        client = pymongo.MongoClient()
        self._DB_WP = client['azrael']['wp']

        # Record the PID of the parent.
        self.parentPID = os.getpid()

        # Instantiate a Bullet engine.
        engine = azrael.bullet.boost_bullet.PyBulletPhys
        self.bullet = engine(self.workerID)

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
    def getWorkPackage(self, wpid: int):
        """
        Return the SV data for all objects specified in ``wpid``.
    
        This function returns a dictionary with two keys. The first key ('wpdata')
        contains a list of ``WPData`` instances that describe the object states and
        forces applied to them, and a 'wpmeta' field that is an instance of
        ``WPMeta``.
    
        fixme: requires test that this function only returns a WP with token
               (ie. it must never return an updated WP).

        :param int wpid: work package ID.
        :return: {'wpdata': list of WPData instances, 'wpmeta': meta information}
        :rtype: dict
        """
    
        # Retrieve the work package.
        doc = self._DB_WP.find_one({'wpid': wpid, 'token': {'$exists': 1}})
        if doc is None:
            return RetVal(False, 'Unknown work package <{}>'.format(wpid), None)
    
        wpdata = [WPData(*_) for _ in doc['wpdata']]
        for idx, val in enumerate(wpdata):
            wpdata[idx] = val._replace(sv=bullet_data.fromJsonDict(val.sv))

        # Put the meta data of the work package into another named tuple.
        meta = WPMeta(doc['token'], doc['dt'], doc['maxsteps'])
        return RetVal(True, None, {'wpdata': wpdata, 'wpmeta': meta})
    
    
    @typecheck
    def updateWorkPackage(self, wpid: int, token, wpdata: (tuple, list)):
        """
        Update the objects in ``wpid`` with the values in ``svdict``.
    
        This function only makes changes to objects defined in the WP ``wpid``,
        and even then only if the ``token`` value matches.
    
        fixme: docu (new parameter types)

        :param int wpid: work package ID.
        :param int token: token value associated with this work package.
        :param dict svdict: {objID: sv} dictionary
        :return bool: Success.
        """
        doc = self._DB_WP.find_and_modify(
            {'wpid': wpid, 'token': token},
            {'$set': {'wpdata': wpdata},
             '$unset': {'token': 1}})
        return RetVal(doc is not None, None, None)
    
    @typecheck
    def run(self):
        """
        Update the physics for all objects in ``wpid``.

        :param int wpid: work package ID.
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

            # Process work packages as they arrive.
            numSteps = 0
            suq = self.stepsUntilQuit
            while numSteps < suq:
                sock.send(b'')
                wpid = sock.recv()
                wpid = np.fromstring(wpid, np.int64)
                with util.Timeit('Worker.0_All') as timeit:
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
        with util.Timeit('Worker.1_fetchWP') as timeit:
            ret = self.getWorkPackage(wpid)

        # Skip this WP (may have been processed by another Worker already).
        if not ret.ok:
            return
        worklist, meta = ret.data['wpdata'], ret.data['wpmeta']

        # Log the number of collision-sets in the current Work Package.
        util.logMetricQty('Engine_{}'.format(self.workerID), len(worklist))

        # Iterate over all objects and update them.
        with util.Timeit('Worker.2_applyforce') as timeit:
            for obj in worklist:
                sv = obj.sv

                # Update the object in Bullet.
                btID = util.id2int(obj.id)
                self.bullet.setObjectData(btID, sv)

                # Retrieve the force vector and tell Bullet to apply it.
                force = np.array(obj.central_force, np.float64)
                torque = np.array(obj.torque, np.float64)

                # Add the force defined on the 'force' grid.
                with util.Timeit('Worker.2.2_grid') as timeit:
                    force = self.applyGridForce(force, sv.position)

                # Apply all forces and torques.
                self.bullet.applyForceAndTorque(btID, force, torque)

        # Tell Bullet to advance the simulation for all objects in the
        # current work list.
        with util.Timeit('Worker.3_compute') as timeit:
            IDs = [util.id2int(_.id) for _ in worklist]
            self.bullet.compute(IDs, meta.dt, meta.maxsteps)

        with util.Timeit('Worker.4_fetchFromBullet') as timeit:
            # Retrieve the objects from Bullet again and update them in the DB.
            out = []
            for obj in worklist:
                ret = self.bullet.getObjectData([util.id2int(obj.id)])
                sv = ret.data
                if not ret.ok:
                    # Something went wrong. Reuse the old SV.
                    sv = obj.sv
                    self.logit.error('Unable to get all objects from Bullet')
                out.append(WPData(obj.id, sv.toJsonDict(), [0, 0, 0], [0, 0, 0]))

        # Update the data and delete the WP.
        with util.Timeit('Worker.5_updateWP') as timeit:
            ret = self.updateWorkPackage(wpid, meta.token, out)
        if not ret.ok:
            msg = 'Failed to update work package {}'.format(wpid)
            self.logit.warning(msg)
