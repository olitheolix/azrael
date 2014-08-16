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

import sys
import time
import pika
import logging
import pymongo
import setproctitle
import multiprocessing
import numpy as np

import azrael.util as util
import azrael.config as config
import azrael.bullet.cython_bullet
import azrael.bullet.btInterface as btInterface


class LeonardBase(multiprocessing.Process):
    def __init__(self):
        super().__init__()

        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)
        self.logit.debug('mydebug')
        self.logit.info('myinfo')

    def setup(self):
        pass
    
    def step(self, dt, max_sub_steps):
        # Retrieve the SV for all objects.
        ok, allSV = btInterface.getAll()
        ok, all_ids = btInterface.getAllObjectIDs()
        ok, all_sv = btInterface.getStateVariables(all_ids)

        # Iterate over all SV entries and update them.
        for obj_id, sv in zip(all_ids, all_sv):
            # Convert the SV Bytes into a dictionary.
            sv = btInterface.unpack(np.fromstring(sv))

            # Retrieve the force vector.
            ok, force, relpos = btInterface.getForce(obj_id)
            if not ok:
                continue

            # Update velocity and position.
            sv.velocityLin[:] += force * 0.001
            sv.position[:] += dt * sv.velocityLin

            # See if there is a suggested position available for this
            # object. If so, use it.
            ok, sug_pos = btInterface.getSuggestedPosition(obj_id)
            if ok and sug_pos is not None:
                # Assign the position, then delete the suggestion.
                sv.position[:] = sug_pos
                btInterface.setSuggestedPosition(obj_id, None)

            # Serialise the state variables and update them in the DB.
            sv = btInterface.pack(sv).tostring()
            btInterface.update(obj_id, sv)

    def run(self):
        setproctitle.setproctitle('killme Leonard')

        # Initialisation.
        self.setup()
        self.logit.debug('Setup complete.')
        
        client = pymongo.MongoClient()
        btInterface.initSVDB(reset=False)

        t0 = time.time()

        # Run the loop forever. Ideally, the loop runs once every 10ms.
        while True:
            # Wait until 10ms have passed since we were here, or proceed
            # immediately if more than 10ms have already passed.
            sleep_time = 0.01 - (time.time() - t0)
            if sleep_time > 0:
                time.sleep(sleep_time)

            # Take the current time.
            t0 = time.time()
            self.step(0.1, 10)


class LeonardBaseWorkpackages(LeonardBase):
    """
    A variaton of LeonardBase that uses Work Packages.

    This class is a test dummy and should not be used in production.
    """
    def __init__(self):
        super().__init__()
        self.token = 0
        
    def step(self, dt, maxsteps):
        # Retrieve the SV for all objects.
        ok, allSV = btInterface.getAll()

        # --------------------------------------------------------------------
        # Create a single work list that features all objects.
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
        for value in worklist:
            # Convert the SV Bytes into a dictionary.
            sv = btInterface.unpack(np.fromstring(value.sv))

            # Retrieve the force vector.
            force = np.fromstring(value.force)

            # Update velocity and position.
            sv.velocityLin[:] += force * 0.001
            sv.position[:] += dt * sv.velocityLin

            # See if there is a suggested position available for this
            # object. If so, use it. The next call to updateWorkPackage will
            # void it.
            if value.sugPos is not None:
                sv.position[:] = np.fromstring(value.sugPos)

            # Overwrite the content of the worklist with just the serialised SV
            # data because this is how updateWorkPackage expects it.
            out[value.id] = btInterface.pack(sv).tostring()

        # --------------------------------------------------------------------
        # Update the work list and mark it as completed.
        # --------------------------------------------------------------------
        btInterface.updateWorkPackage(wpid, admin.token, out)


class LeonardBulletMonolithic(LeonardBase):
    def __init__(self):
        super().__init__()
        self.bullet = None

    def step(self, dt, max_sub_steps):
        if self.bullet is None:
            self.bullet = azrael.bullet.cython_bullet.PyBulletPhys(1, 0)

        # Retrieve the SV for all objects.
        ok, allSV = btInterface.getAll()

        # Iterate over all SV entries and update them.
        for obj_id, sv in allSV.items():
            # Convert the SV Bytes into a dictionary.
            sv = btInterface.unpack(np.fromstring(sv))

            # See if there is a suggested position available for this
            # object. If so, use it.
            ok, sug_pos = btInterface.getSuggestedPosition(obj_id)
            if ok and sug_pos is not None:
                # Assign the position, then delete the suggestion.
                sv.position[:] = sug_pos
                btInterface.setSuggestedPosition(obj_id, None)

            btID = util.id2int(obj_id)
            self.bullet.setObjectData([btID], btInterface.pack(sv))

            # Retrieve the force vector.
            ok, force, relpos = btInterface.getForce(obj_id)
            if ok:
                self.bullet.applyForce(btID, 0.01 * force, relpos)

        # Update velocity and position.
        IDs = [util.id2int(_) for _ in allSV.keys()]
        self.bullet.compute(IDs, dt, max_sub_steps)
        
        for obj_id, sv in allSV.items():
            ok, sv = self.bullet.getObjectData([util.id2int(obj_id)])
            if ok == 0:
                # Serialise the state variables and update them in the DB.
                btInterface.update(obj_id, sv.tostring())


class LeonardRMQWorker(multiprocessing.Process):
    """
    """
    def __init__(self, worker_id):
        super().__init__()
        self.id = np.int64(worker_id)
        self.id_binary = self.id.tostring()
        
        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

    def advanceSimulation(self, wpid):
        # Convert work package ID to integer and fetch the work list.
        ok, worklist, admin = btInterface.getWorkPackage(wpid)
        if not ok:
            return

        # Process the objects one by one. The `out` dict will hold the updated
        # SV information.
        out = {}
        for value in worklist:
            # Convert the SV Bytes into a dictionary.
            sv = btInterface.unpack(np.fromstring(value.sv))

            # Retrieve the force vector.
            force = np.fromstring(value.force)

            # Update velocity and position.
            sv.velocityLin[:] += force * 0.001
            sv.position[:] += admin.dt * sv.velocityLin

            # See if there is a suggested position available for this
            # object. If so, use it. The next call to updateWorkPackage will
            # void it.
            if value.sugPos is not None:
                sv.position[:] = np.fromstring(value.sugPos)

            # Overwrite the content of the worklist with just the serialised SV
            # data because this is how updateWorkPackage expects it.
            out[value.id] = btInterface.pack(sv).tostring()

        # --------------------------------------------------------------------
        # Update the work list and mark it as completed.
        # --------------------------------------------------------------------
        # Update the data and delete the WP.
        btInterface.updateWorkPackage(wpid, admin.token, out)

    def run(self):
        """
        Start RabbitMQ event loop and process work packages dispatched by
        Leonard. This function will not return.
        """
        setproctitle.setproctitle('killme LeonardWorker')
        btInterface.initSVDB(reset=False)
        
        # Create a RabbitMQ exchange.
        param = pika.ConnectionParameters(host=config.rabbitMQ_host)
        self.rmqconn = pika.BlockingConnection(param)
        del param
        
        # Create (or attach to) a named channel. The name is 'config.ex_msg'.
        self.rmq = self.rmqconn.channel()
        self.rmq.queue_declare(queue=config.rmq_wp, durable=False)
        self.rmq.queue_declare(queue=config.rmq_ack, durable=False)

        # Ensure the worker does not pre-fetch additional message. This
        # basically ensures that only an idle Worker instance can fetch a work
        # package.
        #self.rmq.basic_qos(prefetch_count=1)

        def callback(ch, method, properties, body):
            # Unpack the work package ID and update the physics.
            wpid = util.id2int(body)
            self.advanceSimulation(wpid)

            # Acknowledge message receipt and tell Leonard which worker
            # finished which work package.
            ch.basic_ack(delivery_tag=method.delivery_tag)
            ch.basic_publish(exchange='', routing_key=config.rmq_ack,
                             body=util.int2id(wpid) + self.id_binary)

        # Install the callback and start the event loop. The execution path
        # ends here.
        self.rmq.basic_consume(callback, queue=config.rmq_wp)
        self.rmq.start_consuming()


class LeonardRMQWorkerBullet(LeonardRMQWorker):
    """
    """
    def __init__(self, *args):
        super().__init__(*args)
        self.bullet = None
        
        # Create a Class-specific logger.
        self.logit = logging.getLogger(
            __name__ + '.' + self.__class__.__name__)

    def advanceSimulation(self, wpid):
        if self.bullet is None:
            self.bullet = azrael.bullet.cython_bullet.PyBulletPhys(self.id, 0)

        # Fetch the work package.
        ok, worklist, admin = btInterface.getWorkPackage(wpid)
        if not ok:
            return

        # Download the information into Bullet.
        for value in worklist:
            # Convert the SV Bytes into a dictionary.
            sv = btInterface.unpack(np.fromstring(value.sv))

            # See if there is a suggested position available for this
            # object. If so, use it. The next call to updateWorkPackage will
            # void it.
            if value.sugPos is not None:
                sv.position[:] = np.fromstring(value.sugPos)

            # Update the object cache in Bullet.
            btID = util.id2int(value.id)
            self.bullet.setObjectData([btID], btInterface.pack(sv))

            # Retrieve the force vector and apply it.
            force = np.fromstring(value.force)
            relpos = np.zeros(3, np.float64)
            self.bullet.applyForce(btID, 0.01 * force, relpos)

        # Let Bullet advance the computation for all the objects we just
        # retrieved.
        IDs = [util.id2int(_.id) for _ in worklist]
        self.bullet.compute(IDs, admin.dt, admin.maxsteps)
        
        # Retrieve all the objects again.
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
    A variaton of LeonardWorkpackages that uses RabbitMQ.

    This class is a test dummy and should not be used in production.

    This class is tailor made to test the communication between Leonard and a
    separate Worker process via RabbitMQ and work packages. To this end, this
    class will spawn a single LeonardRMQWorker and create an individual work
    package for every object to compute.
    """
    def __init__(self, num_workers=1, clsWorker=LeonardRMQWorker):
        super().__init__()
        self.token = 0
        self.workers = []
        self.num_workers = num_workers
        self.used_workers = set()
        self.clsWorker = clsWorker

        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

    def __del__(self):
        for worker in self.workers:
            if worker.is_alive():
                worker.terminate()
                worker.join()
        
    def announceWorkpackage(self, wpid):
        self.rmq.basic_publish(exchange='',
                                 routing_key=config.rmq_wp,
                                 body=util.int2id(wpid))

    def step(self, dt, maxsteps):
        # Retrieve the SV for all objects.
        ok, allSV = btInterface.getAll()
        IDs = list(allSV.keys())
        
        # Update the token value for this iteration.
        self.token += 1

        # Create one work package for every object. This is inefficent but
        # ensures that multiple work packages work as expected.
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

    def waitUntilWorkpackagesComplete(self, all_wpids):
        """
        Wait until all Work packages have been acknowledged.
        """
        self.used_workers.clear()

        def callback(ch, method, properties, body):
            # Unpack the IDs of the completed WP and engine.
            wpid, workerid = body[:config.LEN_ID], body[config.LEN_ID:]
            wpid = util.id2int(wpid)

            # Remove the WP from the set if it is still in there. Also track the
            # Worker engine ID that completed the job. Note that other workers
            # which completed the same job will not be added the the
            # 'used_workers' list.
            if wpid in all_wpids:
                all_wpids.discard(wpid)
                self.used_workers.add(int(np.fromstring(workerid, dtype=int)))

            # Acknowledge message receipt.
            ch.basic_ack(delivery_tag=method.delivery_tag)

            # Quit the event loop if all WPs have been processed.
            if len(all_wpids) == 0:
                ch.stop_consuming()

        # Use Pika event loop to consume all messages in the ACK channel.
        self.rmq.basic_consume(callback, queue=config.rmq_ack)
        self.rmq.start_consuming()

    def setup(self):
        # Create a RabbitMQ exchange.
        param = pika.ConnectionParameters(host=config.rabbitMQ_host)
        self.rmqconn = pika.BlockingConnection(param)
        del param
        
        # Create the channel.
        self.rmq = self.rmqconn.channel()

        # Delete the queues if they still exist from previous runs.
        try:
            self.rmq.queue_delete(queue=config.rmq_wp)
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
