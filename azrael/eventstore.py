# Copyright 2016, Oliver Nagy <olitheolix@gmail.com>
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
Provide a uniform API to publish events and subscribes to topics.
"""

import os
import pika
import logging
import threading

import azrael.config as config
from azrael.aztypes import typecheck, RetVal

from IPython import embed as ipshell

# Create module logger.
logit = logging.getLogger('azrael.' + __name__)


class EventStore(threading.Thread):
    """
    Provide functionality to publish and receive messages.

    This class is a thin wrapper around the Pika bindings for RabbitMQ. It
    is implemented as a thread to queue up messages in the background. Use
    ``getMessages`` to fetch those messages and remove them from the queue.

    The ``topics`` parameter specifies the topics to which this instance will
    subscribe. However, this only affects which message can be received. It
    does not affect the ``publish`` method at all.

    :param list[str] topics: the topics to subscribe.
    """
    @typecheck
    def __init__(self, topics: (tuple, list)):
        super().__init__(daemon=True)

        # Create an empty message list.
        self.messages = []

        # This thread will periodically chack this flag and terminate once it
        # is True.
        self._terminate = False

        # Event parameters.
        self.topics = topics

        # Specify polling timeout. Smaller values make the class more
        # responsive in the event of a shutdown. However, smaller values also
        # means invoking the GIL more frequently which slows down the main
        # thread.
        self._timeout = 0.2

        # Setup the RabbitMQ exchange.
        self.setupRabbitMQ()

    def __del__(self):
        """
        Attempt to shut down cleanly.
        """
        if self.is_alive():
            # Thread is still running. Stop and join. This may block
            # indefinitely.
            self.stop()
            self.join()

        # Close the channel if it is still open.
        if self.chan is not None:
            try:
                self.chan.close()
            except pika.exceptions.ChannelClosed:
                pass
            self.chan = None

        # Close the connection to RabbitMQ if it is still open.
        if self.rmq['conn'] is not None:
            try:
                self.rmq['conn'].close()
            except pika.exceptions.ConnectionClosed:
                pass
            self.rmq['conn'] = None

    def setupRabbitMQ(self):
        """
        fixme: docu
        """
        exchange_name = 'azevents'
        conn_param = pika.ConnectionParameters(
            host=config.azService['rabbitmq'].ip,
            port=config.azService['rabbitmq'].port,
        )

        # Connect to RabbitMQ. Raise a generic RunTime error if that is not
        # possible. This is a band-aid solution for now since I am still unsure
        # how to handle connection errors in general. Wrapping every call to
        # the EventStore in a try/except block seems inelegant.
        try:
            conn = pika.BlockingConnection(conn_param)
        except (pika.exceptions.ConnectionClosed,
                pika.exceptions.ChannelClosed,
                pika.exceptions.IncompatibleProtocolError):
            chan = conn = None
            raise RuntimeError

        # Create and configure the channel. All deliveries must be confirmed.
        chan = conn.channel()
        chan.confirm_delivery()
        chan.basic_qos(prefetch_size=0, prefetch_count=0, all_channels=False)

        # Create a Topic exchange.
        chan.exchange_declare(exchange='azevents', type='topic')
        queue_name = chan.queue_declare(exclusive=True).method.queue

        # Setup the callbacks.
        for topic in self.topics:
            chan.queue_bind(
                exchange=exchange_name,
                queue=queue_name,
                routing_key=topic,
            )
        self.chan = chan
        self.rmq = {'conn': conn, 'chan': chan, 'name_queue':
            queue_name, 'name_exchange': exchange_name}

    def onMessage(self):
        """
        For user to overload. Triggers after a message was received.
        """
        pass

    def onTimeout(self):
        """
        For user to overload. Triggers after the periodic timer expired.
        """
        pass

    def _onMessage(self, ch, method, properties, body):
        """
        Add messages to the local cache whenever they arrive.
        """
        self.messages.append((method.routing_key, body))
        self.onMessage()
        if self._terminate is True:
            self.chan.stop_consuming()

    def _onTimeout(self):
        """
        Periodically checks if the thread should terminate itself.
        """
        self.onTimeout()
        if self._terminate is True:
            self.chan.stop_consuming()
        else:
            self.rmq['conn'].add_timeout(self._timeout, self._onTimeout)

    def stop(self):
        """
        Signal the thread to terminate itself.
        """
        self._terminate = True

    def getMessages(self):
        """
        Return all messages that have arrived since the last call.

        Subsequent calls to this method will only return newer messages.

        :return: list of (topic, message) tuple.
        """
        msg = list(self.messages)
        self.messages = self.messages[len(msg):]
        return RetVal(True, None, msg)

    @typecheck
    def publish(self, topic: str, msg: bytes):
        """
        Publish the binary ``msg`` to ``topic``.

        The ``topic`` must be a '.' delimited string, for instance
        'foo.bar.something'.

        :param str topic: topic string
        :param bytes msg: message to publish.
        """
        self.chan.basic_publish(
            exchange=self.rmq['name_exchange'],
            routing_key=topic,
            body=msg,
        )
        return RetVal(True, None, None)

    def blockingConsume(self):
        """
        Connect to RabbitMQ and commence the message consumption.

        This method also installs callbacks for when messages arrive or the
        timeout counter expires.

        Note: this method does not return of its own accord. The only two
        scenarios where it does return is if an exception is thrown or one of
        the callbacks explicitly terminates the event loop.
        """
        # Install timeout callback.
        self.rmq['conn'].add_timeout(self._timeout, self._onTimeout)

        # Install message callback for the subscribed keys.
        self.chan.basic_consume(
            self._onMessage,
            queue=self.rmq['name_queue'], no_ack=False
        )

        # Commence Pika's event loop. This will block indefinitely. To stop it,
        # another thread must call the 'stop' method.
        ret = RetVal(True, None, None)
        try:
            self.chan.start_consuming()
            self.chan.close()
            self.rmq['conn'].close()
        except pika.exceptions.ChannelClosed:
            ret = RetVal(False, 'Channel Closed', None)
        except pika.exceptions.ChannelError:
            ret = RetVal(False, 'Channel Error', None)
        except pika.exceptions.ConnectionClosed:
            ret = RetVal(False, 'Connection Closed', None)
        finally:
            self.chan = None
            self.rmq['conn'] = None
        return ret

    def run(self):
        self.blockingConsume()
