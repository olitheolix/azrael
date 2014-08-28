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
import time
import pika
import logging
import setproctitle
import multiprocessing
import numpy as np

import azrael.util as util
import azrael.config as config
import azrael.bullet.cython_bullet
import azrael.bullet.btInterface as btInterface

from azrael.typecheck import typecheck

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
    
    @typecheck
    def step(self, dt: (int, float), maxsteps: int):
        """
        Advance the simulation by ``dt`` using at most ``maxsteps``.

        This method will query all SV objects from the database and update the
        Bullet engine. Then it defers the to Bullet to do the
        update. Afterwards, it queries all objects from Bullet and updates the
        values in the database.

        :param float dt: time step in seconds.
        :param int maxsteps: maximum number of sub-steps to simulate for one
        ``dt`` update.
        """
        # Retrieve the SV for all objects.
        ok, allSV = btInterface.getAllStateVariables()
        ok, all_ids = btInterface.getAllObjectIDs()
        ok, all_sv = btInterface.getStateVariables(all_ids)

        # Iterate over all objects and update their SV information in Bullet.
        for objID, sv in zip(all_ids, all_sv):
            # Convert the SV Bytes into a named tuple.
            sv = btInterface.unpack(np.fromstring(sv))

            # Retrieve the force vector for the current object.
            ok, force, relpos = btInterface.getForce(objID)
            if not ok:
                continue

            # Update velocity and position.
            sv.velocityLin[:] += force * 0.001
            sv.position[:] += dt * sv.velocityLin

            # See if there is a suggested position available for this
            # object. If so, use it.
            ok, sug_pos = btInterface.getSuggestedPosition(objID)
            if ok and sug_pos is not None:
                # Assign the position and delete the suggestion.
                sv.position[:] = sug_pos
                btInterface.setSuggestedPosition(objID, None)

            # Serialise the state variables and update them in the DB.
            sv = btInterface.pack(sv).tostring()
            btInterface.update(objID, sv)

    def run(self):
        """
        Update loop.
        
        Execute once Leonard has been spawned as its own process.
        """
        setproctitle.setproctitle('killme Leonard')

        # Initialisation.
        self.setup()
        self.logit.debug('Setup complete.')
        
        # Reset the database.
        btInterface.initSVDB(reset=False)

        # Run the loop forever and trigger the `step` method every 10ms, if
        # possible.
        t0 = time.time()
        while True:
            # Wait until 10ms have passed since we were here last. Proceed
            # immediately if more than 10ms have already passed.
            sleep_time = 0.01 - (time.time() - t0)
            if sleep_time > 0:
                time.sleep(sleep_time)

            # Take the current time.
            t0 = time.time()
            self.step(0.1, 10)


class LeonardBaseWorkpackages(LeonardBase):
    """
    A variation of ``LeonardBase`` that uses Work Packages.

    This class is a test dummy and should not be used in production. Like
    ``LeonardBase`` it does not actually compute any physics but only creates
    and processes the work packages, all in a single process.

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
            # Convert the SV to a named tuple.
            sv = btInterface.unpack(np.fromstring(obj.sv))

            # Retrieve the force vector.
            force = np.fromstring(obj.force)

            # Update the velocity and position.
            sv.velocityLin[:] += force * 0.001
            sv.position[:] += dt * sv.velocityLin

            # See if there is a suggested position available for this
            # object. If so, use it because the next call to updateWorkPackage
            # will void it.
            if obj.sugPos is not None:
                sv.position[:] = np.fromstring(obj.sugPos)

            # Add the new SV data to the output dictionary.
            out[obj.id] = btInterface.pack(sv).tostring()

        # --------------------------------------------------------------------
        # Update the work list and mark it as completed.
        # --------------------------------------------------------------------
        btInterface.updateWorkPackage(wpid, admin.token, out)


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
        self.bullet = azrael.bullet.cython_bullet.PyBulletPhys(1, 0)

    @typecheck
    def step(self, dt, maxsteps):
        """
        Advance the simulation by ``dt`` using at most ``maxsteps``.

        :param float dt: time step in seconds.
        :param int maxsteps: maximum number of sub-steps to simulate for one
        ``dt`` update.
        """

        # Retrieve the SV for all objects.
        ok, allSV = btInterface.getAllStateVariables()

        # Iterate over all objects and update them.
        for objID, sv in allSV.items():
            # Convert the SV Bytes into a named tuple.
            sv = btInterface.unpack(np.fromstring(sv))

            # See if there is a suggested position available for this
            # object. If so, use it.
            ok, sug_pos = btInterface.getSuggestedPosition(objID)
            if ok and sug_pos is not None:
                # Assign the position and delete the suggestion.
                sv.position[:] = sug_pos
                btInterface.setSuggestedPosition(objID, None)

            # Convert the objID to an integer.
            btID = util.id2int(objID)

            # Pass the SV data from the DB to Bullet.
            self.bullet.setObjectData([btID], btInterface.pack(sv))

            # Retrieve the force vector and tell Bullet to apply it.
            ok, force, relpos = btInterface.getForce(objID)
            if ok:
                self.bullet.applyForce(btID, 0.01 * force, relpos)

        # Wait for Bullet to advance the simulation by one step.
        IDs = [util.id2int(_) for _ in allSV.keys()]
        self.bullet.compute(IDs, dt, maxsteps)
        
        # Retrieve all objects from Bullet and write them back to the database.
        for objID, sv in allSV.items():
            ok, sv = self.bullet.getObjectData([util.id2int(objID)])
            if ok == 0:
                btInterface.update(objID, sv.tostring())


class LeonardRMQWorker(multiprocessing.Process):
    """
    A dedicated worker process attached to RabbitMQ.

    This worker runs independently of any Leonard process, possibly even on a
    different machine.

    .. note::
       Like ``LeonardBase`` this worker does not actually compute any
       physics. It just implements the framework for testing.
    """
    @typecheck
    def __init__(self, worker_id: int):
        super().__init__()

        # ID of this worker. Keep both the integer and binary version handy.
        self.id = np.int64(worker_id)
        self.id_binary = self.id.tostring()
        
        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

    @typecheck
    def advanceSimulation(self, wpid: int):
        """
        Retrieve the work package and process all objects in it.

        This function does not actually compute any physics on the objects. It
        just retrieves the work package and queries all objects specified
        therein.

        :param int wpid: work package ID to fetch and process.
        """
        # Convert work package ID to integer and fetch the work list.
        ok, worklist, admin = btInterface.getWorkPackage(wpid)
        if not ok:
            return

        # Process the objects one by one. The `out` dict will contain the
        # SV data after Bullet updated it.
        out = {}
        for obj in worklist:
            # Convert the SV Bytes to a named tuple.
            sv = btInterface.unpack(np.fromstring(obj.sv))

            # Retrieve the force vector.
            force = np.fromstring(obj.force)

            # Update the velocity and position.
            sv.velocityLin[:] += force * 0.001
            sv.position[:] += admin.dt * sv.velocityLin

            # See if there is a suggested position available for this
            # object. If so, use it. The next call to updateWorkPackage will
            # void it.
            if obj.sugPos is not None:
                sv.position[:] = np.fromstring(obj.sugPos)

            # Add the processed SV into the output dictionary.
            out[obj.id] = btInterface.pack(sv).tostring()

        # --------------------------------------------------------------------
        # Update the work list and mark it as completed.
        # --------------------------------------------------------------------
        # Update the data and delete the WP.
        btInterface.updateWorkPackage(wpid, admin.token, out)

    def setup(self):
        """
        Stub for initialisation code that cannot go into the constructor.

        Since Leonard is a process not everything can be initialised in the
        constructor because it executes before the process forks.
        """
        pass

    def run(self):
        """
        Start the RabbitMQ event loop and wait for work packages.

        Leonard will dispatched its work packages via RabbitMQ and this method
        will pick them up and process them.
        """
        setproctitle.setproctitle('killme LeonardWorker')
        btInterface.initSVDB(reset=False)
        
        # Perform any pending initialisation.
        self.setup()

        # Create a RabbitMQ exchange.
        param = pika.ConnectionParameters(host=config.rabbitMQ_host)
        self.rmqconn = pika.BlockingConnection(param)
        del param
        
        # Create (or attach to) a named channel. The name is 'config.ex_msg'.
        self.rmq = self.rmqconn.channel()
        self.rmq.queue_declare(queue=config.rmq_wp, durable=False)
        self.rmq.queue_declare(queue=config.rmq_ack, durable=False)

        # Ensure workers do not pre-fetch additional message to implement load
        # balancing instead of a round-robin or greedy message retrieval.
        #self.rmq.basic_qos(prefetch_count=1)

        def callback(ch, method, properties, body):
            """
            Callback for when RabbitMQ receives a message.
            """
            # Unpack the work package ID and update the physics.
            wpid = util.id2int(body)
            self.advanceSimulation(wpid)

            # Acknowledge message receipt and tell Leonard which worker
            # finished which work package.
            ch.basic_ack(delivery_tag=method.delivery_tag)
            ch.basic_publish(exchange='', routing_key=config.rmq_ack,
                             body=util.int2id(wpid) + self.id_binary)

        # Install the callback and start the event loop. start_consuming will
        # not return.
        self.rmq.basic_consume(callback, queue=config.rmq_wp)
        self.rmq.start_consuming()


class LeonardRMQWorkerBullet(LeonardRMQWorker):
    """
    Extend ``LeonardRMQWorker`` with Bullet physics.
    """
    def __init__(self, *args):
        super().__init__(*args)

        # No Bullet engine is attached by default.
        self.bullet = None
        
        # Create a Class-specific logger.
        self.logit = logging.getLogger(
            __name__ + '.' + self.__class__.__name__)

    def setup(self):
        # Instantiate Bullet engine.
        self.bullet = azrael.bullet.cython_bullet.PyBulletPhys(self.id, 0)
        
    def advanceSimulation(self, wpid):
        # Fetch the work package.
        ok, worklist, admin = btInterface.getWorkPackage(wpid)
        if not ok:
            return

        # Download the information into Bullet.
        for obj in worklist:
            # Convert the SV Bytes into a named tuple.
            sv = btInterface.unpack(np.fromstring(obj.sv))

            # See if there is a suggested position available for this
            # object. If so, use it because the next call to updateWorkPackage
            # will void it.
            if obj.sugPos is not None:
                sv.position[:] = np.fromstring(obj.sugPos)

            # Update the object in Bullet.
            btID = util.id2int(obj.id)
            self.bullet.setObjectData([btID], btInterface.pack(sv))

            # Retrieve the force vector and tell Bullet to apply it.
            force = np.fromstring(obj.force)
            relpos = np.zeros(3, np.float64)
            self.bullet.applyForce(btID, 0.01 * force, relpos)

        # Let Bullet advance the simulation for all the objects in the current
        # work list.
        IDs = [util.id2int(_.id) for _ in worklist]
        self.bullet.compute(IDs, admin.dt, admin.maxsteps)
        
        # Retrieve these objects again and update their values in the database.
        out = {}
        for cur_id in IDs:
            ok, sv = self.bullet.getObjectData([cur_id])
            if ok != 0:
                self.logit.error('Could not retrieve all objects from Bullet')
                sv = worklist[cur_id].sv
            cur_id = util.int2id(cur_id)
            out[cur_id] = sv.tostring()

        # Update the data and delete the WP.
        ok = btInterface.updateWorkPackage(wpid, admin.token, out)
        if not ok:
            self.logit.warning('Update for work package {} failed'.format(wpid))


class LeonardBaseWPRMQ(LeonardBase):
    """
    A variation of ``LeonardWorkpackages`` with RabbitMQ and work packages.

    This class is a test dummy and should not be used in production.

    This class is tailor made to test

    * RabbitMQ communication between Leonard and a separate Worker process
    * work packages.

    To this end it spawn a single ``LeonardRMQWorker`` and wraps every single
    object into a dedicated work package.
    """
    @typecheck
    def __init__(self, num_workers: int=1, clsWorker=LeonardRMQWorker):
        super().__init__()

        # Current token.
        self.token = 0
        self.workers = []
        self.num_workers = num_workers
        self.used_workers = set()
        self.clsWorker = clsWorker

        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

    def __del__(self):
        """
        Kill all worker processes.
        """
        for worker in self.workers:
            if worker.is_alive():
                worker.terminate()
                worker.join()
        
    @typecheck
    def announceWorkpackage(self, wpid: int):
        """
        Tell everyone that a new work package with ``wpid`` has become
        available.

        :param int wpid: work package ID.
        """
        self.rmq.basic_publish(
            exchange='', routing_key=config.rmq_wp, body=util.int2id(wpid))

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
        IDs = list(allSV.keys())
        
        # Update the token value for this iteration.
        self.token += 1

        # Create one work package for every object. This is inefficient but
        # useful as a test to ensure nothing breaks when there are many work
        # packages available at the same time.
        all_wpids = set()
        cwp = btInterface.createWorkPackage
        for cur_id in IDs:
            # Upload the work package into the DB.
            ok, wpid = cwp([cur_id], self.token, dt, maxsteps)
            if not ok:
                continue

            # Announce that a new WP is available and add its ID to the set.
            self.announceWorkpackage(wpid)
            all_wpids.add(wpid)
            del cur_id, wpid, ok
        del IDs, allSV

        # Wait until all work packages have been processed.
        self.waitUntilWorkpackagesComplete(all_wpids)

    @typecheck
    def waitUntilWorkpackagesComplete(self, all_wpids: set):
        """
        Wait until ``all_wpids`` have been acknowledged.

        :param set all_wpids: set of all work packages.
        """
        self.used_workers.clear()

        def callback(ch, method, properties, body):
            # Unpack the ID of the WP and the worker which processed it.
            wpid, workerid = body[:config.LEN_ID], body[config.LEN_ID:]
            wpid = util.id2int(wpid)

            # Remove the WP from the set if it is still in there. Also track
            # the Worker which completed the job. Note that other workers which
            # completed the same job will not be added to the 'used_workers'
            # list. This is mostly for debug reasons.
            if wpid in all_wpids:
                all_wpids.discard(wpid)
                self.used_workers.add(int(np.fromstring(workerid, dtype=int)))

            # Acknowledge message receipt to RabbitMQ server.
            ch.basic_ack(delivery_tag=method.delivery_tag)

            # Quit the event loop when all WPs have been processed.
            if len(all_wpids) == 0:
                ch.stop_consuming()

        # Start Pika event loop to consume all messages in the ACK channel.
        self.rmq.basic_consume(callback, queue=config.rmq_ack)
        self.rmq.start_consuming()

    def setup(self):
        """
        Setup RabbitMQ and spawn the worker processes.
        """
        # Create a RabbitMQ exchange.
        param = pika.ConnectionParameters(host=config.rabbitMQ_host)
        self.rmqconn = pika.BlockingConnection(param)
        del param
        
        # Create the channel.
        self.rmq = self.rmqconn.channel()

        # Delete the queues if they happen to already exist.
        try:
            self.rmq.queue_delete(queue=config.rmq_wp)
        except pika.exceptions.ChannelClosed as err:
            pass
        try:
            self.rmq.queue_delete(queue=config.rmq_ack)
        except pika.exceptions.ChannelClosed as err:
            pass
            
        # Declare the queues and give RabbitMQ some time to setup.
        self.rmq.queue_declare(queue=config.rmq_wp, durable=False)
        self.rmq.queue_declare(queue=config.rmq_ack, durable=False)
        time.sleep(0.2)

        # Spawn the workers.
        for ii in range(self.num_workers):
            self.workers.append(self.clsWorker(ii + 1))
            self.workers[-1].start()
        self.logit.debug('Setup complete.')
