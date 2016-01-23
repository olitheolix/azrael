# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

import azutils
import builtins
import unittest.mock as mock
from IPython import embed as ipshell


class TestClerk:
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

    def test_parseHostsFile_valid(self):
        """
        Test parseHostsFile with valid entries.
        """
        lines_parse = [
            '127.0.0.1       localhost',
            '127.0.1.2       foo',
            '127.0.1.3       bar123',
            '127.0.1.4       foobar alias1 alias2',
        ]
        assert azutils.parseHostsFile(lines_parse) == {
            'localhost': '127.0.0.1',
            'foo': '127.0.1.2',
            'bar123': '127.0.1.3',
            'foobar': '127.0.1.4',
        }

    def test_parseHostsFile_invalid(self):
        """
        Test parseHostsFile with entries it must ignore.
        """
        lines_ignore = [
            '127.0.0.1',
            '127.0.0.1   ',
            '127.0.0.1   #localhost',
            '',
            'xxx.0.1.1       wrong',
            ' 127.0.1.1      wrong',
            '# The following lines are desirable for IPv6 capable hosts',
            '::1     ip6-localhost ip6-loopback',
            'fe00::0 ip6-localnet',
            'ff00::0 ip6-mcastprefix',
            'ff02::1 ip6-allnodes',
            'ff02::2 ip6-allrouters',
        ]

        assert len(azutils.parseHostsFile(lines_ignore)) == 0

    @mock.patch.object(azutils.os, 'getenv')
    def test_getAzraelServiceHosts_outside_docker(self, m_getenv):
        """
        When outside a container all services must point to localhost.
        """
        # Mock os.getenv to ensure it tells getAzraelServiceHosts that we are
        # outside a container.
        m_getenv.return_value = None

        ret = azutils.getAzraelServiceHosts(etchosts=None)
        assert ret == {
            'clerk': ('127.0.0.1', 5555),
            'database': ('127.0.0.1', 27017),
            'rabbitmq': ('127.0.0.1', 5672),
            'webapi': ('127.0.0.1', 8080),
            'leonard': ('127.0.0.1', 5556),
        }
        m_getenv.assert_called_with('INSIDEDOCKER', None)

    @mock.patch.object(azutils, 'isInsideDocker')
    def test_getAzraelServiceHosts_inside_docker(self, m_isInsideDocker):
        """
        Inside a container the host names for the services must match their
        service name. For instance, the 'Leonard' service must run on a host
        called 'Leonard' (not case sensitive).
        """
        default_services = {
            'clerk': ('127.0.0.1', 5555),
            'database': ('127.0.0.1', 27017),
            'leonard': ('127.0.0.1', 5556),
            'rabbitmq': ('127.0.0.1', 5672),
            'webapi': ('127.0.0.1', 8080),
        }

        # Make getAzraelServiceHosts believe we are outside a container. In
        # that case all services are assumed to run on localhost.
        m_isInsideDocker.return_value = False
        assert m_isInsideDocker.call_count == 0
        ret = azutils.getAzraelServiceHosts(etchosts=None)
        assert m_isInsideDocker.call_count == 1

        # Make getAzraelServiceHosts believe we are inside a container.
        m_isInsideDocker.return_value = True

        # If the specified /etc/hosts file does not exists then we must get the
        # default values.
        m_isInsideDocker.reset_mock()
        ret = azutils.getAzraelServiceHosts(etchosts=None)
        assert m_isInsideDocker.call_count == 1
        assert ret == default_services
        ret = azutils.getAzraelServiceHosts(etchosts='/does_not_exist.txt')
        assert m_isInsideDocker.call_count == 2
        assert ret == default_services

        # Create a dummy hosts file and mess with the upper/lower case of the
        # strings (host names are case insensitive).
        lines = '\n'.join([
            '127.0.0.1       localhost',
            '127.0.1.2       foo',
            '127.0.1.3       wEbApI',
            '127.0.1.4       Clerk alias1 alias2',
        ]) + '\n'

        # This time the hosts for 'webapi' and 'clerk' must reflect the
        # values in the hosts file.
        with mock.patch.object(builtins, 'open',
                               mock.mock_open(read_data=lines)) as m_open:
            assert m_open.call_count == 0
            ret = azutils.getAzraelServiceHosts(etchosts='/etc/hosts')
            assert m_open.call_count == 1

        assert ret == {
            'clerk': ('127.0.1.4', 5555),
            'database': ('127.0.0.1', 27017),
            'leonard': ('127.0.0.1', 5556),
            'rabbitmq': ('127.0.0.1', 5672),
            'webapi': ('127.0.1.3', 8080),
        }

    @mock.patch.object(azutils.os, 'getenv')
    def test_isInsideDocker(self, m_getenv):
        m_getenv.return_value = '1'
        assert m_getenv.call_count == 0
        assert azutils.isInsideDocker() is True
        assert m_getenv.call_count == 1
        m_getenv.assert_called_with('INSIDEDOCKER', None)

        for retval in [None, 1, 2, '2']:
            m_getenv.reset_mock()
            m_getenv.return_value = retval
            assert m_getenv.call_count == 0
            assert azutils.isInsideDocker() is False
            assert m_getenv.call_count == 1
            m_getenv.assert_called_with('INSIDEDOCKER', None)
