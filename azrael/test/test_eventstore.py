# Copyright 2015, Oliver Nagy <olitheolix@gmail.com>
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
import json
import time
import pika
import pytest
import unittest.mock as mock

from IPython import embed as ipshell
import azrael.eventstore as eventstore


class TestEventStore:
    @classmethod
    def setup_class(cls):
        pass

    @classmethod
    def teardown_class(cls):
        pass

    def setup_method(self, method):
        pass

    def teardown_method(self, method):
        pass

    def test_connection_closed_error(self):
        # Create one EventStore instance and subscribed it to all topics.
        possible_exceptions = [
            pika.exceptions.ChannelClosed,
            pika.exceptions.ChannelError,
            pika.exceptions.ConnectionClosed,
        ]

        # Create an EventStore instance, mock out the RabbitMQ channel, and let
        # the 'start_consuming' method raise one of the various RabbitMQ errors
        # we want to intercept.
        for err in possible_exceptions:
            es = eventstore.EventStore(topics=['#'])
            es.chan = mock.MagicMock()
            es.chan.start_consuming.side_effect = err
            assert not es.blockingConsume().ok

    def test_shutdown(self):
        """
        Verify that the EventStore threads shut down properly. Threads must be
        cooperative in this regard because Python lacks the mechanism to
        forcefully terminate them.
        """
        # Create one EventStore instance and subscribed it to all topics.
        es = eventstore.EventStore(topics=['#'])
        es.start()

        # Tell the thread to stop. Wait at most one Second, then verify it has
        # really stopped.
        es.stop()
        es.join(1.0)
        assert not es.is_alive()

        # Repeat the above test with many threads.
        threads = [eventstore.EventStore(topics=['#']) for _ in range(100)]
        [_.start() for _ in threads]
        time.sleep(0.2)
        [_.stop() for _ in threads]
        [_.join(1.0) for _ in threads]
        for thread in threads:
            assert not thread.is_alive()
        del threads

    def test_destructor(self):
        """
        The destructor must clean up properly, irrespective of whether the
        thread never ran, is still running, or has been stopped already.
        """
        # Test destructor: unstarted thread.
        es = eventstore.EventStore(topics=['#'])
        es.__del__()

        # Test destructor: started thread.
        es = eventstore.EventStore(topics=['#'])
        es.start()
        es.__del__()

        # Test destructor: stopped thread.
        es = eventstore.EventStore(topics=['#'])
        es.start()
        es.stop()
        es.join()
        es.__del__()

    def test_basic_publishing(self):
        """
        Create an EventStore instance that listens for all messages. Then
        publish some messages and verify they arrive as expected.
        """
        # Create an EventStore instance and subscribe it to all messages.
        es = eventstore.EventStore(topics=['#'])
        es.start()

        # No messages must have arrived yet.
        assert es.getMessages() == (True, None, [])

        # Publish our test messages.
        es.publish(topic='foo', msg='bar0'.encode('utf8'))
        es.publish(topic='foo', msg='bar1'.encode('utf8'))

        # Wait until the client received at least two messages (RabbitMQ incurs
        # some latency).
        for ii in range(10):
            time.sleep(0.1)
            if len(es.messages) >= 2:
                break
            assert ii < 9

        # Verify we got both messages.
        ret = es.getMessages()
        assert ret.ok
        assert ret.data == [
            ('foo', 'bar0'.encode('utf8')),
            ('foo', 'bar1'.encode('utf8')),
        ]

        # There must be no new messages.
        assert es.getMessages() == (True, None, [])

        # Stop the thread.
        es.stop()
        es.join()

    def test_invalid_key(self):
        """
        Similar test as before, but this time we subscribe to a particular
        topic instead of all topics. That is, publish three message, two to
        the topic we subscribed to, and one to another topic. We should only
        receive two messages.
        """
        # Create an EventStore instance and subscribe it to the 'foo' topic.
        es = eventstore.EventStore(topics=['foo'])
        es.start()

        # No messages must have arrived yet.
        assert es.getMessages() == (True, None, [])

        # Publish our test messages.
        es.publish(topic='foo', msg='bar0'.encode('utf8'))
        es.publish(topic='blah', msg='bar1'.encode('utf8'))
        es.publish(topic='foo', msg='bar2'.encode('utf8'))

        # Wait until the client received at least two messages (RabbitMQ incurs
        # some latency).
        for ii in range(10):
            time.sleep(0.1)
            if len(es.messages) >= 2:
                break
            assert ii < 9

        # Verify that we got the two messages for our topic.
        ret = es.getMessages()
        assert ret.ok
        assert ret.data == [
            ('foo', 'bar0'.encode('utf8')),
            ('foo', 'bar2'.encode('utf8')),
        ]

        # Stop the thread.
        es.stop()
        es.join()

    def test_multiple_receivers(self):
        """
        Create several listeners and verify they all receive the message.
        """
        # Start several event store threads and subscribe them to 'foo'.
        es = [eventstore.EventStore(topics=['foo']) for _ in range(3)]
        [_.start() for _ in es]

        # Create a dedicated publisher instance.
        pub = eventstore.EventStore(topics=['foo'])

        # Publish our test messages.
        pub.publish(topic='foo', msg='bar0'.encode('utf8'))
        pub.publish(topic='blah', msg='bar1'.encode('utf8'))
        pub.publish(topic='foo', msg='bar2'.encode('utf8'))

        # Wait until each client received at least two messages (RabbitMQ incurs
        # some latency).
        for ii in range(10):
            time.sleep(0.1)
            if min([len(_.messages) for _ in es]) >= 2:
                break
            assert ii < 9

        # Verify each client got both messages.
        for thread in es:
            ret = thread.getMessages()
            assert ret.ok
            assert ret.data == [
                ('foo', 'bar0'.encode('utf8')),
                ('foo', 'bar2'.encode('utf8')),
            ]

        # Stop the threads.
        [_.stop() for _ in es]
        [_.join() for _ in es]

    def test_listen_for_multiple_topic(self):
        """
        Subscribe two multiple topics at once.
        """
        # Create an EventStore instance and subscribe it to all messages.
        es = eventstore.EventStore(topics=['foo', 'bar'])
        es.start()

        # Publish our test messages.
        es.publish(topic='foo', msg='0'.encode('utf8'))
        es.publish(topic='blah', msg='1'.encode('utf8'))
        es.publish(topic='bar', msg='2'.encode('utf8'))

        # Wait until the client received at least two messages (RabbitMQ incurs
        # some latency).
        for ii in range(10):
            time.sleep(0.1)
            if len(es.messages) >= 2:
                break
            assert ii < 9

        # Verify we got the message published for 'foo' and 'bar'.
        ret = es.getMessages()
        assert ret.ok
        assert ret.data == [
            ('foo', '0'.encode('utf8')),
            ('bar', '2'.encode('utf8')),
        ]

        # Stop the thread.
        es.stop()
        es.join()
