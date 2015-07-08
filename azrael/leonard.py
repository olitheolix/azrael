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
import signal
import pickle
import logging
import networkx
import itertools
import numpy as np

import azrael.igor
import azrael.database
import azrael.vectorgrid
import azrael.bullet_api
import azrael.util as util
import azrael.types as types
import azrael.config as config
import azrael.leo_api as leoAPI

from IPython import embed as ipshell
from azrael.types import _RigidBodyState
from azrael.types import typecheck, RetVal, WPData, WPMeta, Forces

# Convenience.
RigidBodyState = types.RigidBodyState

# Create module logger.
logit = logging.getLogger('azrael.' + __name__)


@typecheck
def sweeping(data: dict, dim: str):
    """
    Return sets of overlapping AABBs in the dimension ``dim``.

    This function implements the 'Sweeping' algorithm to determine which sets
    of AABBs overlap.

    Sweeping is straightforward: sort all start/stop positions and determine
    the overlapping sets.

    The `data` is a list of dictionaries that denotes the half widths of the
    AABBs in the respective direction::

        data = {ID_0: {'x': [[xmin_0, xmax_0], [xmin_1, xmax_1], ...],
                       'y': [[ymin_0, ymax_0], [ymin_1, ymax_1], ...],
                       'z': [[zmin_0, zmax_0], [zmin_1, zmax_1], ...]},
                ID_1: {'x': [[xmin_0, xmax_0], ...],
                       'y': [[ymin_0, ymax_0], ...],
                       'z': [[zmin_0, zmax_0], ...],},
                ...}

    The dictionary keys 'x', 'y', and 'z' are (more or less) hard coded,
    and `dim` must refer to one of them (eg dim = 'y' to find the sets that
    overlap in the 'y' dimension).

    :param dict{dict} data: dictionary of AABBs in 'x', 'y', 'z' dimension for
       each body.
    :param str dim: the axis to check (must be one of ['x', 'y', 'z'])
    :return: list of bodyID lists (eg [[1], [2, 3, 4]])
    :rtype: list[list]
    """
    # Determine how many (xmin, xmax) tuples there will be to sort.
    N = 0
    try:
        for v in data.values():
            if len(v[dim]) == 0:
                continue

            # Sanity check: the AABB data must correspond to a matrix (this
            # check is pretty much redundant because the sanity checks must
            # happen in the calling function for performance reasons).
            assert np.array(v[dim], np.float64).ndim == 2
            N += len(v[dim])
    except (ValueError, TypeError):
        return RetVal(False, 'Invalid Sweeping inputs', None)
    N *= 2

    # Pre-allocate arrays for start/stop position, objID, and an
    # increment/decrement array used for convenient processing afterwards.
    arr_pos = np.zeros(N, np.float64)
    arr_ids = np.zeros(N, np.int64)
    arr_inc = np.zeros(N, np.int8)

    # Fill the arrays.
    start = 0
    for k, v in data.items():
        for min_max_tuple in v[dim]:
            stop = start + 2
            arr_pos[start:stop] = min_max_tuple
            arr_ids[start:stop] = k
            arr_inc[start:stop] = [+1, -1]
            start += 2

    # Sort all three arrays according to the start/stop positions.
    idx = np.argsort(arr_pos)
    arr_ids = arr_ids[idx]
    arr_inc = arr_inc[idx]

    # Sweep over the sorted data and compile the list of object sets.
    out = []
    sumVal = 0
    setObjs = set()
    for (inc, objID) in zip(arr_inc, arr_ids):
        # Update the index variable and add the current object to the set (need
        # to convert it from NumPy int to Python int first).
        sumVal += inc
        setObjs.add(int(objID))

        # A new set of overlapping AABBs is complete whenever `sumVal`
        # reaches zero.
        if sumVal == 0:
            out.append(setObjs)
            setObjs = set()

        # Safety check: sumVal can never be negative.
        assert sumVal >= 0

    # Find all connected graphs. This will ensure that each body is in exactly
    # only collision set only, whereas right now this is not necessarily the
    # case. The reason for this is that a body may have multiple AABBs, and not
    # all of them may touch with the same group of objects. Therefore,
    # amalgamate those sets (ie find all connected sets with the NetworkX
    # library).
    g = networkx.Graph()
    for cs in out:
        if len(cs) == 0:
            continue
        elif len(cs) == 1:
            g.add_node(cs.pop())
        else:
            g.add_path(cs)
    result = list(networkx.connected_components(g))
    return RetVal(True, None, result)


@typecheck
def computeCollisionSetsAABB(bodies: dict, AABBs: dict):
    """
    Return broadphase collision sets for all ``bodies``.

    Bodies with empty AABBs, or AABBs where at least one half length is zero do
    not collide with anything.

    ..note:: *Every* static body will be added to *every* collision set. This
             will improved in the future when it becomes a bottle neck.

    :param dict[RigidBodyStates] bodies: the bodies to check.
    :param dict[AABBs]: dictionary of AABBs.
    :return: each list contains a unique set of overlapping objects.
    :rtype: list of lists
    """
    # Sanity check: SV and AABB must contain the same object IDs.
    if bodies.keys() != AABBs.keys():
        return RetVal(False, 'Bodies and AABBs are inconsistent', None)

    # The 'sweeping' function requires a list of dictionaries. Each dictionary
    # must contain the position of the AABB (object local coordinates), as well
    # as the min/max spatial extent in x/y/z direction.
    sweep_data = {}
    bodies_ignored = []
    bodies_static = []

    # Compile the necessary information for the Sweeping algorithm for each
    # object provided to this function.
    for objID in bodies:
        if bodies[objID].imass == 0:
            bodies_static.append(objID)
            continue

        # Convenience: unpack the body parameters needed here.
        pos_rb = bodies[objID].position
        scale = bodies[objID].scale
        rot = bodies[objID].orientation
        quat = util.Quaternion(rot[3], rot[:3])

        # Create an empty data structure (will be populated below).
        sweep_data[objID] = {'x': [], 'y': [], 'z': []}

        # If the object has no AABBs then add it to the 'ignore' list (this
        # means it will be an object that does not collide with anything).
        if len(AABBs[objID]) == 0:
            bodies_ignored.append(objID)
            continue

        # Sanity check: the AABBs must be tantamount to a matrix (ie a list of
        # lists). Since every AABB is described a position and 3 half lengths,
        # the number of columns in the matrix must be an integer multiple of 6.
        aabbs = np.array(AABBs[objID], np.float64)
        assert aabbs.ndim == 2
        assert aabbs.shape[1] % 6 == 0
        num_aabbs = aabbs.shape[1] // 6

        # Iterate over all AABBs, rotate- and translate them in accordance with
        # the body theyt are attached to, and compile the AABB boundaries.
        # Note: the AABBs are not re-computed here. The assumption is that the
        # AABB is large enough to contain their body at any rotation.
        for aabb in aabbs:
            # Convenience: unpack the AABB positions and half lengths. Apply
            # the 'scale' to the half lengths.
            pos_aabb, half_lengths = aabb[:3], aabb[3:]
            half_lengths *= scale

            # Skip the current AABB if at least on of its half lengths is zero.
            if 0 in half_lengths:
                continue

            # Compute the AABB position in world coordinates. This takes into
            # account the position-, orientation, and scale of the body.
            pos = pos_rb + scale * (quat * pos_aabb)

            # Compute the min/max value of the AABB value in world coordinates.
            pmin = pos - half_lengths
            pmax = pos + half_lengths

            # Store the result for this AABB.
            sweep_data[objID]['x'].append([pmin[0], pmax[0]])
            sweep_data[objID]['y'].append([pmin[1], pmax[1]])
            sweep_data[objID]['z'].append([pmin[2], pmax[2]])

        # If no AABB was constructed (ie all AABBs contained at least one half
        # length that was zero) then merely add the object to the 'ignore'
        # list. It will thus, by definition, not collide with anything.
        if len(sweep_data[objID]['x']) == 0:
            bodies_ignored.append(objID)
            continue
    del bodies, AABBs

    # Determine the sets of objects that overlap 'x' direction.
    stage_0 = sweeping(sweep_data, 'x').data

    # Iterate over all the just found sets. For each, determine the sets that
    # overlap in the 'y' dimension.
    stage_1 = []
    for subset in stage_0:
        res = sweeping({k: sweep_data[k] for k in subset}, 'y')
        stage_1.extend(res.data)

    # Iterate over all the sets that overlap in 'x' and 'y' dimension. For
    # each, determine which also overalp in the 'z' dimension.
    stage_2 = []
    for subset in stage_1:
        res = sweeping({k: sweep_data[k] for k in subset}, 'z')
        stage_2.extend(res.data)

    # Add the ignored objects which, by definition, do not collide with
    # anything. In other words, each ignored body creates a dedicated collision
    # set with itself as the only member.
    coll_sets = stage_2 + [[_] for _ in bodies_ignored]

    # Append every static body to every collision set. This may not be very
    # efficient for large scale simulations but has not affect on smaller
    # simulations. The main advantage is that Azrael can now support static
    # bodies with infinite extent, most notably 'Plane' shapes without
    # the extra logic that the sweeping algorithm would otherwise require to
    # deal with such infinite objects.
    out = [_.extend(bodies_static) for _ in coll_sets]

    return RetVal(True, None, coll_sets)


def mergeConstraintSets(constraintPairs: tuple,
                        collSets: (tuple, list)):
    """
    Merge all the sets in ``collSets`` that contain any of the
    ``constraintPairs``.

    The purpose of this function is to merge those collision sets that are
    connected via a constraint. Typically, this function takes the output of
    ``computeCollisionSets`` as the ``collSets`` argument.

    :param list[vec2] constraintPairs: eg [(1, 2), (1, 5), ...].
    :param list[set] collSets: list of collision sets
    :return: the new list of collision sets.
    :rtype: list[set]
    """
    # Merge the collision sets that are linked via constraints.
    for (a, b) in constraintPairs:
        # Find (and remove) the set(s) that contain object_a or object_b (or
        # both).
        s_a = [collSets.pop(ii) for ii, v in enumerate(collSets) if a in v]
        s_b = [collSets.pop(ii) for ii, v in enumerate(collSets) if b in v]

        # Sanity check: each element can be in at most one set.
        assert 0 <= len(s_a) < 2
        assert 0 <= len(s_b) < 2

        # Unpack the list returned by the list comprehension (it contains zero
        # or one element).
        s_a = s_a[0] if len(s_a) == 1 else []
        s_b = s_b[0] if len(s_b) == 1 else []

        # Merge the collision sets.
        new_set = set(s_a).union(s_b)
        collSets.append(new_set)
    return RetVal(True, None, collSets)


def getFinalCollisionSets(constraintPairs: list,
                          allBodies: list,
                          allAABBs: list):
    """
    Return the collision sets.

    This function calls the broadphase solver and then merges those collision
    sets that are connected via a constraint.

    .. note:: this function is tightly coupled to the inner working of Leonard.
              Possibly it should not be a standalone function.

    :param list constraintPairs: list of 2-tuples eg [(1, 2), (1, 5), ...].
    :param list allBodies: Leonard's object cache.
    :param list allAABBs: Leonard's AABB cache.
    :return: list of non-overlapping collision sets.
    """
    # Broadphase based on AABB only.
    ret = computeCollisionSetsAABB(allBodies, allAABBs)
    if not ret.ok:
        msg = 'ComputeCollisionSetsAABB returned an error'
        logit.error(msg)
        return RetVal(False, msg, None)

    # Sanity checks: constraints must not be attached to static objects. This
    # is currently a shortcoming due to the broadphase implementation where all
    # static bodies are added to every collision set. Therefore, if only a
    # single constraint connects to a static body the 'mergeConstraintSets'
    # function will automatically merge *all* collision sets. This is currently
    # a known (but acceptable) shortcoming of the current broadphase algorithm.
    for (a, b) in constraintPairs:
        if (allBodies[a].imass == 0) or (allBodies[b].imass == 0):
            msg = 'Constraint attached to rigid body {}-{}'.format(a, b)
            logit.error(msg)

    # Merge all collision sets that have objects which are connected by a
    # constraint.
    collSets = ret.data
    ret = mergeConstraintSets(constraintPairs, collSets)
    if not ret.ok:
        msg = 'mergeConstraintSets returned an error'
        logit.error(msg)
        return RetVal(False, msg, None)
    return ret


class LeonardBase(config.AzraelProcess):
    """
    Base class for Physics manager.

    No physics is actually computed here. The class serves mostly as an
    interface for the actual Leonard implementations, as well as a test
    framework.
    """
    def __init__(self):
        super().__init__()

        # Create the DB handles.
        self._DB_SV = azrael.database.dbHandles['RBS']

        # Create an Igor instance.
        self.igor = azrael.igor.Igor()

        self.allBodies = {}
        self.allAABBs = {}
        self.allForces = {}

    def setup(self):
        """
        Stub for initialisation code that cannot go into the constructor.

        This is typically necessary for code that must not execute until
        *after* the class forked into a new process. ZeroMQ contexts are a good
        example for this - *never* fork processes *after* creating the context.
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

    @typecheck
    def totalForceAndTorque(self, objID: int):
        """
        Return the total force- and torque on the object.

        The returned values are the sum of all booster forces (correctly
        oriented relative to the object) and the force a user may have specifed
        directly.

        Note that this function does not account for the forces from the 'force
        grid'.

        :param int objID: return the force and torque for this object.
        :return: the force and torque as two Python lists (not NumPy arrays)
        :rtype: (list, list)
        """
        # Convenience.
        sv = self.allBodies[objID]
        f = self.allForces[objID]

        # Construct the Quaternion of the object based on its orientation.
        quat = util.Quaternion(sv.orientation[3], sv.orientation[:3])

        # Fetch the force vector for the current object from the DB.
        force = np.array(f.forceDirect, np.float64)
        torque = np.array(f.torqueDirect, np.float64)

        # Add the booster's contribution to force and torque.
        # Note: We cannot do this directly since the booster force/torque were
        # specified in object coordinates. We thus rotate them to world
        # coordinates before adding them to the total force.
        force += quat * f.forceBoost
        torque += quat * f.torqueBoost

        # Convert to Python lists.
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
        idPos = {k: v.position for (k, v) in self.allBodies.items()}
        ret = self.getGridForces(idPos)
        if not ret.ok:
            self.logit.info(ret.msg)
            z = np.float64(0)
            gridForces = {_: z for _ in idPos}
        else:
            gridForces = ret.data
        del ret, idPos

        # Iterate over all objects and update their SV information in Bullet.
        for objID, sv in self.allBodies.items():
            # Compute direct- and booster forces on object.
            force, torque = self.totalForceAndTorque(objID)

            # Add the force defined on the 'force' grid.
            force += gridForces[objID]

            # Update velocity and position.
            vel = np.array(sv.velocityLin, np.float64) + 0.5 * force
            pos = np.array(sv.position, np.float64)
            pos += dt * vel
            vel, pos = tuple(vel), tuple(pos)
            self.allBodies[objID] = sv._replace(position=pos, velocityLin=vel)

        # Synchronise the local object cache back to the database.
        self.syncObjects(writeconcern=False)

    def processCommandQueue(self):
        """
        Apply commands from queue to objects in local cache.

        Applied commands are automatically removed.

        :return bool: Success.
        """
        # Fetch (and de-queue) all pending commands.
        ret = leoAPI.dequeueCommands()
        if not ret.ok:
            msg = 'Cannot fetch commands'
            self.logit.error(msg)
            return RetVal(False, msg, None)

        # Convenience.
        cmds = ret.data

        # Remove objects.
        for doc in cmds['remove']:
            objID = doc['objID']
            if objID in self.allBodies:
                self._DB_SV.remove({'objID': objID})
                del self.allBodies[objID]
                del self.allForces[objID]
                del self.allAABBs[objID]

        # Spawn objects.
        for doc in cmds['spawn']:
            objID = doc['objID']
            if objID in self.allBodies:
                msg = 'Cannot spawn object since objID={} already exists'
                self.logit.warning(msg.format(objID))
                continue

            # Add the body and its AABB to Leonard's cache. Furthermore, add
            # (and initialise) the entry for the forces on this body.
            sv_old = doc['rbs']
            self.allBodies[objID] = RigidBodyState(**sv_old)
            self.allForces[objID] = Forces(*(([0, 0, 0], ) * 4))
            self.allAABBs[objID] = doc['AABBs']

        # Update Body States.
        for doc in cmds['modify']:
            objID, sv_new, aabbs_new = doc['objID'], doc['rbs'], doc['AABBs']
            if objID in self.allBodies:
                # fixme; document this code fragment. add error check in next line.
                tmp = types.DefaultRigidBody(**sv_new)._asdict()
                tmp = {k: v for (k, v) in tmp.items() if k in sv_new}
                sv_old = self.allBodies[objID]
                sv_old = RigidBodyState(*sv_old)._asdict()

                sv_old.update(sv_new)
                sv_old = RigidBodyState(**sv_old)
                self.allBodies[objID] = sv_old

                # Assign the new AABB if it is not None (note: a value of
                # *None* explicitly means that there is no AABB update,
                # whereas the AABBs for eg an empty shape would be []).
                if aabbs_new is not None:
                    self.allAABBs[objID] = aabbs_new

        # Update direct force- and torque values.
        for doc in cmds['direct_force']:
            objID, force, torque = doc['objID'], doc['force'], doc['torque']
            try:
                self.allForces[objID] = self.allForces[objID]._replace(
                    forceDirect=force, torqueDirect=torque)
            except KeyError:
                pass

        # Update booster force- and torque values.
        for doc in cmds['booster_force']:
            objID, force, torque = doc['objID'], doc['force'], doc['torque']
            try:
                self.allForces[objID] = self.allForces[objID]._replace(
                    forceBoost=force, torqueBoost=torque)
            except KeyError:
                pass

        return RetVal(True, None, None)

    def syncObjects(self, writeconcern: bool):
        """
        Sync the local BodyStates to Leonard's DB and the master record.

        The ``writeconcern`` flag is mostly for performance tuning. If set to
        *False* then the sync will not wait for an acknowledgement from the
        database after the write opration.

        :param bool writeconcern: disable write concern when set to *False*.
        """
        # Return immediately if we have no objects to begin with.
        if len(self.allBodies) == 0:
            return

        # Update (or insert non-existing) bodies. Use a MongoDB Bulk operator
        # for the update to improve the performance.
        bulk = self._DB_SV.initialize_unordered_bulk_op()
        for objID, body in self.allBodies.items():
            query = {'objID': objID}
            data = {'objID': objID, 'rbs': body, 'AABBs': self.allAABBs[objID]}
            bulk.find(query).upsert().update({'$set': data})
        if writeconcern:
            bulk.execute()
        else:
            bulk.execute({'w': 0, 'j': False})

        # Update the RBS data in the master record.
        db = azrael.database.dbHandles['ObjInstances']
        bulk = db.initialize_unordered_bulk_op()
        for objID, body in self.allBodies.items():
            query = {'objID': objID}
            data = {'objID': objID, 'template.rbs': body._asdict()}
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
        # Call `run` method of `AzraelProcess` base class.
        super().run()

        # Initialisation.
        self.setup()
        self.logit.debug('Setup complete.')

        # Trigger the `step` method every `stepinterval` seconds, if possible.
        t0 = time.time()
        stepinterval = 0.050

        while True:
            # Wait, if less than 10ms have passed, or proceed immediately.
            sleep_time = stepinterval - (time.time() - t0)
            if sleep_time > 0:
                time.sleep(sleep_time)

            # Backup the time stamp.
            t0 = time.time()

            # Trigger the physics update step.
            with util.Timeit('Leonard:1.0 Step') as timeit:
                self.step(stepinterval, 10)


class LeonardBullet(LeonardBase):
    """
    An extension of ``LeonardBase`` that uses Bullet for the physics.

    Unlike ``LeonardBase`` this class actually *does* update the physics.
    """
    def __init__(self):
        super().__init__()
        self.bullet = None

    def setup(self):
        # Instantiate the Bullet engine with ID=1.
        self.bullet = azrael.bullet_api.PyBulletDynamicsWorld(1)

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

        # Update the constraint cache in our local Igor instance.
        self.igor.updateLocalCache()
        allConstraints = self.igor.getAllConstraints().data

        # Fetch the forces for all object positions.
        idPos = {k: v.position for (k, v) in self.allBodies.items()}
        ret = self.getGridForces(idPos)
        if not ret.ok:
            self.logit.info(ret.msg)
            z = np.float64(0)
            gridForces = {_: z for _ in idPos}
        else:
            gridForces = ret.data
        del ret, idPos

        # Iterate over all objects and update them.
        for objID, sv in self.allBodies.items():
            # Pass the SV data from the DB to Bullet.
            self.bullet.setRigidBodyData(objID, sv)

            # Compute direct- and booster forces on object.
            force, torque = self.totalForceAndTorque(objID)

            # Add the force defined on the 'force' grid.
            force += gridForces[objID]

            # Apply the force to the object.
            self.bullet.applyForceAndTorque(objID, force, torque)

        # Apply all constraints. Log any errors but ignore them otherwise as
        # they are harmless (simply means no constraints were applied).
        ret = self.bullet.setConstraints(allConstraints)
        if not ret.ok:
            self.logit.warning(ret.msg)

        # Advance the simulation by one time step.
        with util.Timeit('compute') as timeit:
            self.bullet.compute(list(self.allBodies.keys()), dt, maxsteps)

            # Remove all constraints.
            self.bullet.clearAllConstraints()

        # Retrieve all objects from Bullet and overwrite the state variables
        # that the user explicilty wanted to change (if any).
        for objID in self.allBodies:
            ret = self.bullet.getRigidBodyData(objID)
            if ret.ok:
                self.allBodies[objID] = ret.data

        # Synchronise the local object cache back to the database.
        self.syncObjects(writeconcern=False)


class LeonardSweeping(LeonardBase):
    """
    Compute physics on independent collision sets.

    This is a modified version of ``LeonardBullet`` that uses
    Sweeping to compile the collision sets and then updates the physics for
    each set independently.

    This class is single threaded and uses a single Bullet instance to
    sequentially update the physics for each collision set.
    """
    def setup(self):
        # Instantiate the Bullet engine with ID=1.
        self.bullet = azrael.bullet_api.PyBulletDynamicsWorld(1)

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

        # Update the constraint cache in our local Igor instance.
        self.igor.updateLocalCache()
        allConstraints = self.igor.getAllConstraints().data

        # Compute all collision sets.
        with util.Timeit('CCS') as timeit:
            ret = self.igor.uniquePairs()
            if not ret.ok:
                return
            uniquePairs = ret.data

            ret = getFinalCollisionSets(
                uniquePairs, self.allBodies, self.allAABBs)
            if not ret.ok:
                return
            collSets = ret.data
            del ret, uniquePairs

        # Log the number of created collision sets.
        util.logMetricQty('#CollSets', len(collSets))

        # Convenience.
        vg = azrael.vectorgrid

        # Process all subsets individually.
        for subset in collSets:
            # Compile the subset dictionary for the current collision set.
            coll_SV = {_: self.allBodies[_] for _ in subset}

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
            constr = []
            for objID, sv in coll_SV.items():
                # Pass the SV data from the DB to Bullet.
                self.bullet.setRigidBodyData(objID, sv)

                # Compute direct- and booster forces on object.
                force, torque = self.totalForceAndTorque(objID)

                # Add the force defined on the 'force' grid.
                force += gridForces[objID]

                # Apply the final force to the object.
                self.bullet.applyForceAndTorque(objID, force, torque)

            # Query all constraints and apply them in the next step (this
            # duplicates the code from LeonardBullet but I do not know of a
            # simple way to avoid it without major changes to the class
            # structure - for now this is acceptable, especially because this
            # class is mostly for testing).
            tmp = self.igor.getConstraints(coll_SV.keys()).data

            # Apply all constraints. Log any errors but ignore them otherwise
            # as they are harmless (simply means no constraints were applied).
            ret = self.bullet.setConstraints(tmp)
            if not ret.ok:
                self.logit.warning(ret.msg)
            del tmp

            # Wait for Bullet to advance the simulation by one step.
            with util.Timeit('compute') as timeit:
                self.bullet.compute(list(coll_SV.keys()), dt, maxsteps)

            # Remove all constraints.
            self.bullet.clearAllConstraints()

            # Retrieve all objects from Bullet.
            for objID, sv in coll_SV.items():
                ret = self.bullet.getRigidBodyData(objID)
                if ret.ok:
                    self.allBodies[objID] = ret.data

        # Synchronise the local object cache back to the database.
        self.syncObjects(writeconcern=False)


class LeonardDistributedZeroMQ(LeonardBase):
    """
    Compute physics with separate engines.

    This class uses the concept of Work Packages to distribute work. Every Work
    Package is self contained and holds all the information Bullet requires to
    step the simulation.

    This class uses the sweeping algorithm to determine collision sets, just
    like ``LeonardSweeping`` does.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.numWorkers = 3
        self.wpid_counter = 0
        self.ctx = None
        self.sock = None

        # Worker terminate automatically after a certain number of processed
        # Work Packages. The precise number is a constructor argument and the
        # following two variables simply specify the range. The final number
        # will be chosen randomly from this interval (different for every
        # Worker instance to minimise the probability that all terminate
        # simultaneously).
        self.minSteps, self.maxSteps = (500, 700)

        # Initialise worker manager handle.
        self.workermanager = None

    def __del__(self):
        """
        Kill all worker processes.
        """
        if self.workermanager is not None:
            # Send Keyboard interrupt to Worker manager and try to join it.
            os.kill(self.workermanager.pid, signal.SIGINT)
            self.workermanager.join(1)

            # Kill the Worker Manager if we could not join it.
            if self.workermanager.is_alive():
                self.workermanager.terminate()
                self.workermanager.join()

        # Close the Leonard <---> Worker socket.
        if self.sock is not None:
            self.sock.unbind(config.addr_leonard_repreq)
            self.sock.close(linger=100)

        # Terminate the ZeroMQ context.
        if self.ctx is not None:
            self.ctx.term()
            self.ctx.destroy()

    def setup(self):
        # Start the WorkerManager which, in turn, will spawn the workers.
        self.workermanager = WorkerManager(
            self.numWorkers, self.minSteps,
            self.maxSteps, LeonardWorkerZeroMQ)
        self.workermanager.start()

        # Create the ZeroMQ context. Note: this MUST happen AFTER the Worker
        # Manager was started, because otherwise the child processes will get a
        # copy of the ZeroMQ context with the already bound address, which it
        # may never release.
        self.ctx = zmq.Context()
        self.sock = self.ctx.socket(zmq.REP)

        # Bind the socket to the specified address. Retry a few times if
        # necessary.
        for ii in range(10):
            try:
                self.sock.bind(config.addr_leonard_repreq)
                break
            except zmq.error.ZMQError:
                time.sleep(0.2)
            assert ii < 9
        self.logit.info('Setup complete')

    @typecheck
    def step(self, dt, maxsteps):
        """
        Advance the simulation by ``dt`` using at most ``maxsteps``.

        This method moves all SV objects from the database to the Bullet
        engine. Then it defers to Bullet for the physics update. Finally, it
        replaces the SV fields with the user specified values (only applies if
        the user called 'setBodyState') and writes the results back to the
        database.

        :param float dt: time step in seconds.
        :param int maxsteps: maximum number of sub-steps to simulate for one
                             ``dt`` update.
        """
        # Read queued commands and update the local object cache accordingly.
        with util.Timeit('Leonard:1.1  processCmdQueue') as timeit:
            self.processCommandQueue()

        # Update the constraint cache in our local Igor instance.
        self.igor.updateLocalCache()
        allConstraints = self.igor.getAllConstraints().data

        # Compute the collision sets.
        with util.Timeit('Leonard:1.2  CCS') as timeit:
            ret = self.igor.uniquePairs()
            if not ret.ok:
                return
            uniquePairs = ret.data

            ret = getFinalCollisionSets(
                uniquePairs, self.allBodies, self.allAABBs)
            if not ret.ok:
                return
            collSets = ret.data
            del ret, uniquePairs

        # Log the number of created collision sets.
        util.logMetricQty('#CollSets', len(collSets))

        # Put each collision set into its own Work Package.
        with util.Timeit('Leonard:1.3  CreateWPs') as timeit:
            all_WPs = {}
            for subset in collSets:
                # Compile the Work Package. Skip this physics step altogether
                # if an error occurs.
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

                # Send an empty message to the Worker if no Work Packages are
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

        # Compile the Body States and forces into a list of ``WPData`` tuples.
        try:
            wpdata = []
            for objID in objIDs:
                sv = self.allBodies[objID]
                force, torque = self.totalForceAndTorque(objID)
                wpdata.append(WPData(objID, sv, force, torque))
        except KeyError as err:
            return RetVal(False, 'Cannot compile WP', None)

        # Query all constraints.
        constraints = self.igor.getConstraints(objIDs).data

        # Form the content of the Work Package as it will appear in the DB.
        data = {'wpid': self.wpid_counter,
                'wpmeta': (self.wpid_counter, dt, maxsteps),
                'wpdata': wpdata,
                'wpconstraints': constraints,
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
        # the old Body States with the new one from the processed WP.
        for (objID, sv) in wpdata:
            self.allBodies[objID] = _RigidBodyState(*sv)


class LeonardWorkerZeroMQ(config.AzraelProcess):
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

        # Instantiate a Bullet engine.
        engine = azrael.bullet_api.PyBulletDynamicsWorld
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
        constraints = wp['wpconstraints']

        # Log the number of collision-sets in the current Work Package.
        util.logMetricQty('Engine_{}'.format(self.workerID), len(worklist))

        # Convenience: the WPData elements make the code more readable.
        worklist = [WPData(*_) for _ in worklist]

        # Convenience.
        applyForceAndTorque = self.bullet.applyForceAndTorque
        setRigidBodyData = self.bullet.setRigidBodyData

        # Add every object to the Bullet engine and set the force/torque.
        with util.Timeit('Worker:1.1.0  applyforce') as timeit:
            with util.Timeit('Worker:1.1.1   grid') as timeit:
                # Fetch the forces for all object positions.
                idPos = {_.aid: _.sv.position for _ in worklist}
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
                    setRigidBodyData(obj.aid, obj.sv)

            with util.Timeit('Worker:1.1.1   updateForce') as timeit:
                for obj in worklist:
                    # Add the force defined on the 'force' grid.
                    force = obj.force + gridForces[obj.aid]
                    applyForceAndTorque(obj.aid, force, obj.torque)

        # Apply all constraints. Log any errors but ignore them otherwise as
        # they are harmless (simply means no constraints were applied).
        ret = self.bullet.setConstraints(constraints)
        if not ret.ok:
            self.logit.warning(ret.msg)

        # Tell Bullet to advance the simulation for all objects in the
        # current work list.
        with util.Timeit('Worker:1.2.0  compute') as timeit:
            IDs = [_.aid for _ in worklist]
            self.bullet.compute(IDs, meta.dt, meta.maxsteps)

            # Remove all constraints.
            self.bullet.clearAllConstraints()

        with util.Timeit('Worker:1.3.0  fetchFromBullet') as timeit:
            # Retrieve the objects from Bullet again and update them in the DB.
            out = []
            for obj in worklist:
                ret = self.bullet.getRigidBodyData(obj.aid)
                sv = ret.data
                if not ret.ok:
                    # Something went wrong. Reuse the old SV.
                    sv = obj.sv
                    self.logit.error('Unable to get all objects from Bullet')
                out.append((obj.aid, sv))

        # Return the updated WP data.
        return {'wpid': meta.wpid, 'wpdata': out}

    @typecheck
    def run(self):
        """
        Wait for Work Packages, process them, and return the results.
        """
        # Call `run` method of `AzraelProcess` base class.
        super().run()

        try:
            # Setup ZeroMQ.
            ctx = zmq.Context()
            sock = ctx.socket(zmq.REQ)
            sock.connect(config.addr_leonard_repreq)
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
        print('Worker {} exited cleanly'.format(self.workerID))


class WorkerManager(config.AzraelProcess):
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

        # Initialise the list of workers.
        self.workers = []

    def _run(self):
        """
        Start the initial collection of Workers and ensure they remain alive.
        """
        # Spawn the initial collection of Workers.
        delta = self.maxSteps - self.minSteps
        for ii in range(self.numWorkers):
            # Random number in [minSteps, maxSteps]. The process will
            # automatically terminate after `suq` steps.
            suq = self.minSteps + int(np.random.rand() * delta)

            # Instantiate the process and add it to the list.
            self.workers.append(self.workerCls(ii + 1, suq))
            self.workers[-1].start()

        # Periodically monitor the processes and restart any that have died.
        while True:
            # Only check once a second.
            time.sleep(1)
            for workerID, proc in enumerate(self.workers):
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
                self.workers[workerID] = proc
                self.logit.info('Restarted Worker {}'.format(workerID))

    def run(self):
        """
        Wrapper around ``_run`` to intercept SIGTERM.
        """
        # Call `run` method of `AzraelProcess` base class.
        super().run()

        try:
            self._run()
        except KeyboardInterrupt:
            print('Worker Manager was aborted')

        # Terminate all workers.
        for w in self.workers:
            if w is not None and w.is_alive():
                w.terminate()
                w.join()
        print('Worker manager finished')
