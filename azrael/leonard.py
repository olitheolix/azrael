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
import json
import signal
import pickle
import logging
import networkx
import numpy as np

import azrael.igor
import azrael.datastore
import azrael.eventstore
import azrael.vectorgrid
import azrael.bullet_api
import azutils as util
import azrael.config as config
import azrael.leo_api as leoAPI

from IPython import embed as ipshell
from azrael.aztypes import _RigidBodyData, RigidBodyData
from azrael.aztypes import typecheck, RetVal, WPMeta, WPDataOut, WPDataRet, Forces

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
        setObjs.add(objID)

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
    result = networkx.connected_components(g)

    # NetworkX returned a generator yet the calling code
    # expects a list of lists. Rectify.
    result = [[str(a) for a in _] for _ in result]

    return RetVal(True, None, result)


@typecheck
def computeCollisionSetsAABB(bodies: dict, AABBs: dict):
    """
    Return broadphase collision sets for all ``bodies``.

    Bodies with empty AABBs, or AABBs where at least one half length is zero do
    not collide with anything.

    ..note:: *Every* static body will be added to *every* collision set. This
             will improved in the future when it becomes a bottle neck.

    :param dict[RigidBodyDatas] bodies: the bodies to check.
    :param dict[AABBs]: dictionary of AABBs.
    :return: each list contains a unique set of overlapping objects.
    :rtype: list of lists
    """
    # Ensure we have an AABB for every body.
    try:
        AABBs = {k: AABBs[k] for k in bodies}
    except KeyError:
        return RetVal(False, 'Some AABBs are missing', None)

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
        rot = bodies[objID].rotation
        quat = util.Quaternion(*rot)

        # Create an empty data structure (will be populated below).
        sweep_data[objID] = {'x': [], 'y': [], 'z': []}

        # If the object has no AABBs then add it to the 'ignore' list (this
        # means it will be an object that does not collide with anything).
        if len(AABBs[objID]) == 0:
            bodies_ignored.append(objID)
            continue

        # Iterate over all AABBs, rotate- and translate them in accordance with
        # the body theyt are attached to, and compile the AABB boundaries.
        # Note: the AABBs are not re-computed here. The assumption is that the
        # AABB is large enough to contain their body at any rotation.
        for aabb in sorted(AABBs[objID].values()):
            # Sanity check: each AABB has exactly 6 entries. Since any given
            # body can have multiple of them the number of values in the array
            # must be an integer multiple of 6.
            aabb = np.array(aabb, np.float64)
            assert aabb.ndim == 1
            assert len(aabb) % 6 == 0

            # Convenience: unpack the AABB positions and half lengths. Apply
            # the 'scale' to the half lengths.
            pos_aabb, half_lengths = aabb[:3], aabb[3:]
            half_lengths *= scale

            # Skip the current AABB if at least on of its half lengths is zero.
            if 0 in half_lengths:
                continue

            # Compute the AABB position in world coordinates. This takes into
            # account the position-, rotation, and scale of the body.
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

    # Determine the sets of objects that overlap in 'x' direction.
    stage_0 = sweeping(sweep_data, 'x').data

    # Iterate over all the just found sets. For each, determine the sets that
    # overlap in the 'y' dimension.
    stage_1 = []
    for subset in stage_0:
        res = sweeping({k: sweep_data[k] for k in subset}, 'y')
        stage_1.extend(res.data)

    # Iterate over all the sets that overlap in 'x' and 'y' dimension. For
    # each, determine which also overlap in the 'z' dimension.
    stage_2 = []
    for subset in stage_1:
        res = sweeping({k: sweep_data[k] for k in subset}, 'z')
        stage_2.extend(res.data)

    # Add the ignored objects which, by definition, do not collide with
    # anything. In other words, each ignored body creates a dedicated collision
    # set with itself as the only member.
    coll_sets = stage_2 + [[_] for _ in bodies_ignored]

    # Append every static body to every collision set. This may not be very
    # efficient for large scale simulations but has a negligible penalty for
    # smaller simulations. The main advantage is that Azrael can now support
    # static bodies with infinite extent, most notably 'Plane' shapes without
    # the extra logic that the sweeping algorithm would otherwise require to
    # deal with such infinite objects.
    for collset in coll_sets:
        collset.extend(bodies_static)

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


def _skipEmptyBodies(bodies):
    """
    Return only those ``bodies`` that have an actual collision shape.

    If a body has only EMPTY type collision shapes then remove it from the
    list because they physics engine will not have to compute anything for it.

    This is a convenience function to avoid computing physics for objects that
    are not supposed to collide with anything.

    ..note:: the ``bodies`` dictinoary will *not* be modified by this function.

    :param dict bodies: dictionary of bodies (typically the dictionary of
        bodies passed to `getFinalCollisionSets`.
    :return: shallow copy of ``bodies`` with all empty bodies removed.
    """
    # Create a shallow copy of the input to avoid changing the original data.
    bak_bodies = dict(bodies)

    # Remove every body whose collision shapes have type EMPTY.
    for objID, body in bodies.items():
        tmp = [_.cstype.upper() for _ in body.cshapes.values()]
        if set(tmp) == {'EMPTY'}:
            del bak_bodies[objID]

    # Return the pruned dictionary of bodies.
    return bak_bodies


def getFinalCollisionSets(constraintPairs: list,
                          allBodies: dict,
                          allAABBs: dict):
    """
    Return the collision sets.

    This function calls the broadphase solver and then merges those collision
    sets that are connected via a constraint.

    .. note:: this function is tightly coupled to the inner working of Leonard.
              Possibly it should not be a standalone function.

    :param list constraintPairs: list of 2-tuples eg [(1, 2), (1, 5), ...].
    :param dict allBodies: Leonard's object cache.
    :param dict allAABBs: Leonard's AABB cache.
    :return: list of non-overlapping collision sets.
    """
    allBodies = _skipEmptyBodies(allBodies)

    # Broadphase based on AABB only.
    ret = computeCollisionSetsAABB(allBodies, allAABBs)
    if not ret.ok:
        msg = 'ComputeCollisionSetsAABB returned an error: {}'
        logit.error(msg.format(ret.msg))
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

        # Create an Igor instance.
        self.igor = azrael.igor.Igor()

        self.allBodies = {}
        self.allAABBs = {}
        self.allForces = {}
        self.events = azrael.eventstore.EventStore(topics=['phys'])

    def setup(self):
        """
        Stub for initialisation code that cannot go into the constructor.

        This is typically necessary for code that must not execute until
        *after* the class forked into a new process. ZeroMQ contexts are a good
        example for this - *never* fork processes *after* creating the context.
        """
        pass

    def shutdown(self):
        """
        Stub for shutdown code that cannot go into the destructor.

        The typical use case is to close ZeroMQ sockets.
        """
        pass

    def getGridForces(self, idPos: dict):
        """
        Return dictionary of force values for every object in ``idPos``.

        The ``idPos`` argument is a {objID_1: body_1, objID_2, body_2, ...}
        dictionary.

        The returned dictionary has the same keys as ``idPos``.

        :param dict idPos: dictionary with objIDs and corresponding bodies.
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
    def totalForceAndTorque(self, objID: str):
        """
        Return the total force- and torque on the object.

        The returned values are the sum of all booster forces (correctly
        oriented relative to the object) and the force a user may have specifed
        directly.

        Note that this function does not account for the forces from the 'force
        grid'.

        :param str objID: return the force and torque for this object.
        :return: the force and torque as two Python lists (not NumPy arrays)
        :rtype: (list, list)
        """
        # Convenience.
        body = self.allBodies[objID]
        f = self.allForces[objID]

        # Construct the Quaternion of the object based on its rotation.
        quat = util.Quaternion(*body.rotation)

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

        # Iterate over all objects and update their body information in Bullet.
        for objID, body in self.allBodies.items():
            # Compute direct- and booster forces on object.
            force, torque = self.totalForceAndTorque(objID)

            # Add the force defined on the 'force' grid.
            force += gridForces[objID]

            # Update velocity and position.
            vel = np.array(body.velocityLin, np.float64) + 0.5 * force
            pos = np.array(body.position, np.float64)
            pos += dt * vel
            vel, pos = tuple(vel), tuple(pos)
            self.allBodies[objID] = body._replace(position=pos, velocityLin=vel)

        # Synchronise the local object cache back to the database.
        self.syncObjects(collisions=None)

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
            body_old = doc['rbs']
            self.allBodies[objID] = RigidBodyData(**body_old)
            self.allForces[objID] = Forces(*(([0, 0, 0], ) * 4))
            self.allAABBs[objID] = doc['AABBs']

        # Update Body States.
        for doc in cmds['modify']:
            objID, new, aabbs_new = doc['objID'], doc['rbs'], doc['AABBs']
            if objID in self.allBodies:
                # Convert the original body state into a dictionary and update
                # it with the new values.
                old = self.allBodies[objID]._asdict()
                old.update(new)

                # Attempt to construct a new RigidBody with the new body that
                # now includes the updated values. If it fails skip this body
                # altogether.
                try:
                    self.allBodies[objID] = RigidBodyData(**old)
                except TypeError:
                    self.logit.warning('Could not update body state in Leonard.')
                    continue

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

    def syncObjects(self, collisions: list):
        """
        Sync the bodies from Leonard's local cache to the datastore.

        This method will also publish the `collisions`, the format of which is
        determined entirely by `PyBulletDynamicsWorld.getLastContacts`.

        :param list collisions: collisions to publish.
        """
        # Return immediately if we have no objects to begin with.
        if len(self.allBodies) == 0:
            return

        # Publish the collision contacts (if there are any).
        if (collisions is not None) and (len(collisions) > 0):
            msg = json.dumps(collisions).encode('utf8')
            self.events.publish(topic='phys.collisions', msg=msg)

        # Update the RBS data in the master record.
        db = azrael.datastore.getDSHandle('ObjInstances')
        ops = {}
        for aid, body in self.allBodies.items():
            ops[aid] = {
                'inc': {},
                'set': {('template', 'rbs'): body._asdict()},
                'unset': [],
                'exists': {('template', 'rbs'): True},
            }
        db.modify(ops)

    def processCommandsAndSync(self):
        """
        Process all pending commands and synchronise the cache to the DB.

        This method is useful for unit tests but probably not much else. It
        also ensures that the synchronisation of the objects from the local
        cache to the database is acknowledged by the database (this is turned
        off in production because it slows down Leonard an the information is
        not critical).
        """
        self.processCommandQueue()
        self.syncObjects(collisions=None)

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

        try:
            while True:
                # Wait if <10ms have passed. Proceed immediately otherwise.
                sleep_time = stepinterval - (time.time() - t0)
                if sleep_time > 0:
                    time.sleep(sleep_time)

                # Backup the time stamp.
                t0 = time.time()

                # Trigger the physics update step.
                # Note: 'maxsteps' *must* be 1 to obtain all collision
                # contacts from the `PyBulletDynamicsWorld` instance. The
                # reason is that Bullet may create and and clear contacts
                # during the sub-steps, but we can only query them after the
                # last update.
                with util.Timeit('Leonard:1.0 Step'):
                    self.step(stepinterval, maxsteps=10)
        except KeyboardInterrupt:
            self.logit.warning('Leonard was aborted')


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

        This method will query all bodies from the database and updates
        them in the Bullet engine. Then it defers to Bullet for the physics
        update.  Finally it copies the updated values in Bullet back to the
        database.

        :param float dt: time step in seconds.
        :param int maxsteps: maximum number of sub-steps to simulate for one
                             ``dt`` update.
        """
        # Process pending commands.
        self.processCommandQueue()

        # Update the constraint cache in our local Igor instance.
        self.igor.updateLocalCache()
        allConstraints = self.igor.getConstraints(None).data

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
        for objID, body in self.allBodies.items():
            # Copy the body from the DB to Bullet.
            self.bullet.setRigidBodyData(objID, body)

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
        with util.Timeit('compute'):
            self.bullet.compute(list(self.allBodies.keys()), dt, maxsteps)

            # Remove all constraints.
            self.bullet.clearAllConstraints()

        # Retrieve all collisions generated during the last step.
        collisions = self.bullet.getLastContacts().data

        # Retrieve all objects from Bullet and overwrite the state variables
        # that the user explicilty wanted to change (if any).
        for objID in self.allBodies:
            ret = self.bullet.getRigidBodyData(objID)

            # Assign the new object properties only if the call succeeded. Keep
            # the old body otherwise.
            if ret.ok is True:
                body = self.allBodies[objID]
                self.allBodies[objID] = body._replace(
                    position=ret.data.position,
                    rotation=ret.data.rotation,
                    velocityLin=ret.data.vLin,
                    velocityRot=ret.data.vRot
                )

        # Synchronise the local object cache back to the database.
        self.syncObjects(collisions)


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

        This method will query all bodies from the database and updates
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

        # Compute all collision sets.
        with util.Timeit('CCS'):
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

        # Create empty set of collisions. This is a precaution in case the
        # for-loop below does not run (ie there are no bodies to simulate).
        collisions = []

        # Process all subsets individually.
        for subset in collSets:
            # Compile the subset dictionary for the current collision set.
            coll_bodies = {_: self.allBodies[_] for _ in subset}

            # Fetch the forces for all object positions.
            idPos = {k: v.position for (k, v) in coll_bodies.items()}
            ret = self.getGridForces(idPos)
            if not ret.ok:
                self.logit.info(ret.msg)
                z = np.float64(0)
                gridForces = {_: z for _ in idPos}
            else:
                gridForces = ret.data
            del ret, idPos

            # Iterate over all objects and update them.
            for objID, body in coll_bodies.items():
                # Copy the body from the DB to Bullet.
                self.bullet.setRigidBodyData(objID, body)

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
            tmp = self.igor.getConstraints(coll_bodies.keys()).data

            # Apply all constraints. Log any errors but ignore them otherwise
            # as they are harmless (simply means no constraints were applied).
            ret = self.bullet.setConstraints(tmp)
            if not ret.ok:
                self.logit.warning(ret.msg)
            del tmp

            # Wait for Bullet to advance the simulation by one step.
            with util.Timeit('compute'):
                self.bullet.compute(list(coll_bodies.keys()), dt, maxsteps)

            # Remove all constraints.
            self.bullet.clearAllConstraints()

            # Retrieve all collisions generated during the last step.
            collisions = self.bullet.getLastContacts().data

            # Retrieve all objects from Bullet.
            for objID, body in coll_bodies.items():
                ret = self.bullet.getRigidBodyData(objID)

                # Assign the new object properties only if the call succeeded. Keep
                # the old body otherwise.
                if ret.ok is True:
                    body = self.allBodies[objID]
                    self.allBodies[objID] = body._replace(
                        position=ret.data.position,
                        rotation=ret.data.rotation,
                        velocityLin=ret.data.vLin,
                        velocityRot=ret.data.vRot
                    )

        # Synchronise the local object cache back to the database.
        self.syncObjects(collisions)


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
        self.wpid_counter = 0
        self.ctx = None
        self.sock = None

        # Local cache of collision contacts. This one will be filled up as the
        # minions return their result. Only when all results are in will the
        # collision contacts be dispatched.
        self.collisions = []

#    def __del__(self):
#        self.shutdown()

    def shutdown(self):
        """
        Kill all worker processes.
        """
        # Close the Leonard <---> Worker socket.
        if self.sock is not None:
            addr = 'tcp://{}:{}'.format('*', config.azService['leonard'].port)
            try:
                self.sock.unbind(addr)
            except zmq.error.ZMQError:
                # This is to mask a bug in ZeroMQ where the 'unbind' method
                # does not accept the '*' wildcard.
                pass
            del addr
            self.sock.close(linger=100)
            self.sock = None

        # Terminate the ZeroMQ context.
        if self.ctx is not None:
            self.ctx.term()
            self.ctx.destroy()
            self.ctx = None

    def setup(self):
        # Create the ZeroMQ context. Note: this MUST happen AFTER the Worker
        # Manager was started, because otherwise the child processes will get a
        # copy of the ZeroMQ context with the already bound address, which it
        # may never release.
        self.ctx = zmq.Context()
        self.sock = self.ctx.socket(zmq.REP)

        # Bind the socket to the specified address. Retry a few times if
        # necessary.
        addr = 'tcp://{}:{}'.format('*', config.azService['leonard'].port)
        for ii in range(10):
            try:
                self.sock.bind(addr)
                break
            except zmq.error.ZMQError:
                time.sleep(0.2)
            assert ii < 9
        self.logit.info('Setup complete - listening on <{}>'.format(addr))

    @typecheck
    def step(self, dt, maxsteps):
        """
        Advance the simulation by ``dt`` using at most ``maxsteps``.

        This method copies all bodies from the database to the Bullet
        engine. Then it defers to Bullet for the physics update. Finally, it
        replaces the body fields with the user specified values (only applies if
        the user called 'setRigidBody') and writes the results back to the
        database.

        :param float dt: time step in seconds.
        :param int maxsteps: maximum number of sub-steps to simulate for one
                             ``dt`` update.
        """
        # Flush the collision contacts from the previous iteration.
        self.collisions.clear()

        # Read queued commands and update the local object cache accordingly.
        with util.Timeit('Leonard:1.1  processCmdQueue'):
            self.processCommandQueue()

        # Update the constraint cache in our local Igor instance.
        self.igor.updateLocalCache()

        # Compute the collision sets.
        with util.Timeit('Leonard:1.2  CCS'):
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
        with util.Timeit('Leonard:1.3  CreateWPs'):
            all_WPs = {}
            for subset in collSets:
                # Compile the Work Package. Skip this physics step altogether
                # if an error occurs.
                ret = self.createWorkPackage(list(subset), dt, maxsteps)
                if not ret.ok:
                    self.logit.error(ret.msg)
                    return
                all_WPs[ret.data['wpid']] = ret.data

        with util.Timeit('Leonard:1.4  WPSendRecv'):
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
                    # the same Work Package and one of the others already
                    # returned it).
                    if wpid in all_WPs:
                        self.updateLocalCache(msg['wpdata'], msg['collisions'])

                        # Decrement the Work Package index if the wpIdx counter
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
        with util.Timeit('Leonard:1.5  syncObjects'):
            self.syncObjects(self.collisions)

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

        :param iterable objIDs: list of object IDs in the new work package.
        :param float dt: time step for this work package.
        :param int maxsteps: number of sub-steps for the time step.
        :return: Work package ID
        :rtype: int
        """
        # Sanity check.
        if len(objIDs) == 0:
            return RetVal(False, 'Work package is empty', None)

        # Compile the Body States and forces into a list of ``WPDataOut`` tuples.
        try:
            wpdata = []
            for objID in objIDs:
                body = self.allBodies[objID]
                force, torque = self.totalForceAndTorque(objID)
                wpdata.append(WPDataOut(objID, body, force, torque))
        except KeyError:
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

    def updateLocalCache(self, wp_data_ret, collisions):
        """
        Copy every object from ``wp_data_ret`` to the local cache.

        The ``wp_data_ret`` argument is a list of (objID, body) tuples.

        The implicit assumption of this method is that ``wpdata`` is the
        output of ``computePhysicsForWorkPackage`` from a Worker.

        This method will also publish all `collisions`, the format of which is
        determined entirely by `PyBulletDynamicsWorld.getLastContacts`.

        :param list[Wp_data_ret] wp_data_ret: data returned by Minion.
        :param list collisions: collisions to publish.
        """
        # Reset force and torque for all objects in the WP, and overwrite
        # the old Body States with the new one from the processed WP.
        for wp in wp_data_ret:
            self.allBodies[wp.aid] = _RigidBodyData(*wp.body)

        # Extend the list of collision contacts if any were provided.
        if (collisions is not None) and len(collisions) > 0:
            self.collisions.extend(collisions)


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

        The ``idPos`` argument is a {objID_1: body_1, objID_2, body_2, ...}
        dictionary.

        The returned dictionary has the same keys as ``idPos``.

        :param dict idPos: dictionary with objIDs and corresponding body data.
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
        :return dict: {'wpdata': list_of_bodies, 'wpid': wpid}
        """
        worklist, meta = wp['wpdata'], WPMeta(*wp['wpmeta'])
        constraints = wp['wpconstraints']

        # Log the number of collision-sets in the current Work Package.
        util.logMetricQty('Engine_{}'.format(self.workerID), len(worklist))

        # Convenience: the WPDataOut elements make the code more readable.
        worklist = [WPDataOut(*_) for _ in worklist]

        # Convenience.
        applyForceAndTorque = self.bullet.applyForceAndTorque
        setRB = self.bullet.setRigidBodyData

        # Add every object to the Bullet engine and set the force/torque.
        with util.Timeit('Worker:1.1.0  applyforce'):
            with util.Timeit('Worker:1.1.1   grid'):
                # Fetch the grid force for all object positions.
                idPos = {_.aid: _.rbs.position for _ in worklist}
                ret = self.getGridForces(idPos)
                if not ret.ok:
                    self.logit.info(ret.msg)
                    z = np.float64(0)
                    gridForces = {_: z for _ in idPos}
                else:
                    gridForces = ret.data
                del ret, idPos

            with util.Timeit('Worker:1.1.1   updateGeo'):
                for obj in worklist:
                    # Load all objects into Bullet.
                    setRB(obj.aid, obj.rbs)

            with util.Timeit('Worker:1.1.1   updateForce'):
                for obj in worklist:
                    # Tally up and apply the combined grid + user specified
                    # force for each object.
                    force = obj.force + gridForces[obj.aid]
                    applyForceAndTorque(obj.aid, force, obj.torque)

        # Apply all constraints. Log any errors but ignore them otherwise as
        # they are harmless (simply means no constraints were applied).
        ret = self.bullet.setConstraints(constraints)
        if not ret.ok:
            self.logit.warning(ret.msg)

        # Tell Bullet to advance the simulation for all objects in the
        # current work list.
        with util.Timeit('Worker:1.2.0  compute'):
            IDs = [_.aid for _ in worklist]
            self.bullet.compute(IDs, meta.dt, meta.maxsteps)

            # Remove all constraints.
            self.bullet.clearAllConstraints()

        # Retrieve all collision contacts generated during the last step.
        collisions = self.bullet.getLastContacts().data

        with util.Timeit('Worker:1.3.0  fetchFromBullet'):
            # Compile the new state variables into a list. This list will be
            # sent back to the caller later on.
            out = []
            for obj in worklist:
                ret = self.bullet.getRigidBodyData(obj.aid)
                if ret.ok is True:
                    body = obj.rbs._replace(
                        position=ret.data.position,
                        rotation=ret.data.rotation,
                        velocityLin=ret.data.vLin,
                        velocityRot=ret.data.vRot
                    )
                else:
                    # Something went wrong. Reuse the old body.
                    body = obj.rbs
                    self.logit.error('Unable to get all objects from Bullet')
                out.append(WPDataRet(obj.aid, body))

        # Return the updated WP data.
        return {'wpid': meta.wpid, 'wpdata': out, 'collisions': collisions}

    def sighandler(self, signum, frame):
        """
        Signal handler for SIGTERM.

        Intercept the termination signal (including the one sent by the
        'terminate' method of the 'multiprocessing.Process' module) and shut
        down all minions.

        See `signal module <https://docs.python.org/3/library/signal.html>`_
        for the specific meaning of the arguments.
        """
        msg = 'Minion {} intercepted signal {}'.format(self.workerID, signum)
        self.logit.info(msg)
        self.sock.close(linger=0)
        self.ctx.destroy()
        self.logit.info('Minion exited cleanly')
        sys.exit(0)

    @typecheck
    def run(self):
        """
        Wait for Work Packages, process them, and return the results.
        """
        # Call `run` method of `AzraelProcess` base class.
        super().run()

        # Install the signal handler to facilitate a clean shutdown.
        signal.signal(signal.SIGTERM, self.sighandler)
        signal.signal(signal.SIGINT, self.sighandler)

        # Setup ZeroMQ.
        ctx = zmq.Context()
        sock = ctx.socket(zmq.REQ)
        host = config.azService['leonard']
        addr = 'tcp://{}:{}'.format(host.ip, host.port)
        sock.connect(addr)
        self.logit.info(
            'Worker {} connected to <{}>'.format(self.workerID, addr)
        )

        # Store as instance variables for signal handler.
        self.ctx = ctx
        self.sock = sock

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
            with util.Timeit('Worker:1.0.0 WPTotal'):
                wpdata = self.computePhysicsForWorkPackage(wpdata)

            # Pack up the Work Package and send it back to Leonard.
            sock.send(pickle.dumps(wpdata))

            # Count the number of Work Packages we have processed.
            numSteps += 1

        # Log a last status message before terminating.
        self.logit.info('Worker {} terminated itself after {} steps'
                            .format(self.workerID, numSteps))


class WorkerManager(config.AzraelProcess):
    """
    Spawn and maintain a fleet of minion processes.

    This class launches the inital fleet minions and restart any that die.

    :param int numWorker: nonegative number of Minion processes to maintain.
    :param int minSteps: see Worker
    :param int maxSteps: see Worker
    :param class workerCls: the class to instantiate.
    """
    @typecheck
    def __init__(self, numWorkers: int, minSteps: int, maxSteps: int,
                 workerCls):
        super().__init__()

        # Sanity checks.
        assert numWorkers >= 0
        assert 0 < minSteps <= maxSteps

        # Backup the ctor arguments.
        self.numWorkers = numWorkers
        self.workerCls = workerCls
        self.minSteps, self.maxSteps = minSteps, maxSteps

        # Handles to minion processes.
        self.workers = [None] * numWorkers

    def maintainFleet(self):
        """
        Join all dead minion processes and replace them with new ones.

        Returns:
           Always succeeds.
        """
        # Check each process handle and restart those that have died.
        for workerID, proc in enumerate(self.workers):
            # Do nothing if the minion is alive and well.
            if proc is not None and proc.is_alive():
                continue

            # New worker processes will only live for a certain number of
            # steps. The exact number is a random pick from the min/max steps
            # interval.
            suq = np.random.randint(self.minSteps, self.maxSteps + 1)

            # Start a new Minion. The number of steps until quitting (suq) is a
            # random number in the specified interval.
            self.workers[workerID] = self.workerCls(workerID, suq)
            self.workers[workerID].start()
        return RetVal(True, None, None)

    def stopAll(self):
        """
        Send SIGTERM to all minions and join them.

        Returns:
           Always succeeds.
        """
        # Send SIGTERM to minons currently alive.
        for proc in self.workers:
            if proc is None or not proc.is_alive():
                continue
            os.kill(proc.pid, signal.SIGTERM)

        # Join all minions.
        for workerID, proc in enumerate(self.workers):
            if proc is None:
                continue
            proc.join()
            self.workers[workerID] = None
        return RetVal(True, None, None)

    def sighandler(self, signum, frame):
        """
        Signal handler for SIGTERM.

        Intercept the termination signal (including the one sent by the
        'terminate' method of the 'multiprocessing.Process' module) and shut
        down all minions.

        See `signal module <https://docs.python.org/3/library/signal.html>`_
        for the specific meaning of the arguments.
        """
        msg = 'Gru intercepted signal {} - inhuming Minions'.format(signum)
        self.logit.info(msg)
        self.stopAll()
        self.logit.info('Gru now exiting cleanly')
        sys.exit(0)

    def run(self):
        super().run()

        # Install the signal handler to facilitate a clean shutdown (including
        # minion processes).
        signal.signal(signal.SIGTERM, self.sighandler)

        # Periodially monitor the state of the minion fleet.
        self.logit.info('Spawning Minions')
        while True:
            self.maintainFleet()
            time.sleep(0.25)
