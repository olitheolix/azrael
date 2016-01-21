import os
import re
import time
import collections

import pymongo
import numpy as np

from IPython import embed as ipshell

# Global handle to the collection for timing metrics.
dbTiming = None


def resetTiming(host, port):
    """
    Flush existing timing metrics and create a new capped collection.
    """
    global dbTiming

    # Drop existing collection.
    client = pymongo.MongoClient(host=host, port=port)
    col = client['timing']
    col.drop_collection('timing')

    # Create a new capped collection and update the dbTiming variable.
    col.create_collection(name='timing', size=100000000, capped=True)
    dbTiming = col['timing']


def logMetricQty(metric, value, ts=None):
    """
    Log a Quantity ``metric`` and its integer ``value``.

    The time stamp ``ts`` is optional and defaults to the time when this
    function is called.

    :param str metric: name of metric
    :param int value: value
    :param float value: unix time stamp as supplied by eg. time.time()
    """
    if dbTiming is None:
        return

    if ts is None:
        ts = time.time()

    if not isinstance(metric, str):
        return
    if not isinstance(value, int):
        return
    if not isinstance(value, float) and (value > 1413435882):
        return

    doc = {'Timestamp': ts,
           'Metric': metric,
           'Value': value,
           'Type': 'Quantity'}
    dbTiming.insert(doc, j=False)


class Timeit(object):
    """
    Context manager to measure execution time.

    The elapsed time will automatically be added to the timing database.
    """
    def __init__(self, name, show=False):
        self.name = name
        self.show = show
        self.cpCnt = 0

    def __enter__(self):
        self.start = time.time()
        self.last_tick = time.time()
        return self

    def tick(self, suffix=''):
        """
        Save an intermediate timinig result.

        The name of this tick is the concatenation of the original name (passed
        to constructore) plus ``suffix``.
        """
        elapsed = time.time() - self.last_tick
        name = self.name + suffix
        self.save(name, elapsed)
        self.last_tick = time.time()

    def save(self, name, elapsed):
        """
        Write the measurement to the DB.
        """
        if dbTiming is None:
            return

        doc = {'Timestamp': self.start,
               'Metric': name,
               'Value': elapsed,
               'Type': 'Time'}
        dbTiming.insert(doc, j=False)

        if self.show:
            # Print the value to screen.
            print('-- TIMING {}: {:,}ms'.format(name, int(1000 * elapsed)))

    def __exit__(self, *args):
        self.save(self.name, time.time() - self.start)


def timefunc(func):
    """
    Profile execution time of entire function.
    """
    def wrapper(*args, **kwargs):
        with Timeit(func.__name__, False):
            res = func(*args, **kwargs)
        return res

    # Return a new function that wrapped the original with a Timeit instance.
    return wrapper


class Quaternion:
    """
    A Quaternion class.

    This class implements a sub-set of the available Quaternion
    algebra. The operations should suffice for most 3D related tasks.
    """
    def __init__(self, x, y, z, w):
        """
        Construct Quaternion with scalar ``w`` and vector ``v``.
        """
        self.vec = np.array([x, y, z, w], np.float64)

    def __mul__(self, q):
        """
        Multiplication.

        The following combination of (Q)uaternions, (V)ectors, and (S)calars
        are supported:

        * Q * S
        * Q * V
        * Q * Q2

        Note that V * Q and S * Q are *not* supported.
        """
        v, w = self.vec[:3], self.vec[3]
        if isinstance(q, Quaternion):
            # Q * Q2:
            out_w = w * q.w - np.inner(v, q.v)
            out_v = w * q.v + q.w * v + np.cross(v, q.v)
            return Quaternion(*np.hstack([out_v, out_w]))
        elif isinstance(q, (int, float)):
            # Q * S:
            return Quaternion(*np.hstack([q * v, q * w]))
        elif isinstance(q, (np.ndarray, tuple, list)):
            # Q * V: convert Quaternion to 4x4 matrix and multiply it
            # with the input vector.
            assert len(q) == 3
            tmp = np.zeros(4, dtype=np.float64)
            tmp[:3] = np.array(q)
            res = np.inner(self.toMatrix(), tmp)
            return res[:3]
        else:
            print('Unsupported Quaternion product.')
            return None

    def __repr__(self):
        """
        Represent Quaternion as a vector with 4 elements.
        """
        return str(self.vec)

    def length(self):
        """
        Return length of Quaternion.
        """
        return np.linalg.norm(self.vec)

    def normalise(self):
        """
        Return normalised version of this Quaternion.
        """
        arg = self.vec / self.length()
        return Quaternion(*arg)

    def toMatrix(self):
        """
        Return the corresponding rotation matrix for this Quaternion.
        """
        # Shorthands.
        x, y, z, w = self.vec

        # Elements of the Rotation Matrix based on the Quaternion elements.
        a11 = 1 - 2 * y * y - 2 * z * z
        a12 = 2 * x * y - 2 * z * w
        a13 = 2 * x * z + 2 * y * w
        a21 = 2 * x * y + 2 * z * w
        a22 = 1 - 2 * x * x - 2 * z * z
        a23 = 2 * y * z - 2 * x * w
        a31 = 2 * x * z - 2 * y * w
        a32 = 2 * y * z + 2 * x * w
        a33 = 1 - 2 * x * x - 2 * y * y

        # Arrange- and return in matrix form.
        return np.array([
            [a11, a12, a13, 0],
            [a21, a22, a23, 0],
            [a31, a32, a33, 0],
            [0, 0, 0, 1]], np.float32)


def parseHostsFile(lines: list):
    """
    Return a dictionary of {hostname: ip} based on ``lines``.

    Ignores every line that does not strictly adhere to the /etc/hosts format.

    :param list[str] lines: typically the lines of the local /etc/hosts file.
    :return: dict of (ip, port) tuples.
    """
    # Sanity checks.
    try:
        assert isinstance(lines, list)
        for line in lines:
            assert isinstance(line, str)
    except AssertionError:
        return []

    # A valid line looks like this: '127.0.0.1    hostname alias1 alias2'.
    # Compile the regular expression to parse the IP and hostname part of that
    # line.
    e = re.compile(r'^(\d+\.\d+\.\d+\.\d+)[ \t]+([a-zA-Z0-9]+).*')

    # Parse each line.
    hosts = [e.match(_) for _ in lines]

    # Remove all those lines that did not fit the expected pattern.
    hosts = [_.groups() for _ in hosts if _ is not None]

    # Rearrange the results as a {hostname: IP} dictionary.
    hosts = {_[1]: _[0] for _ in hosts}
    return hosts


def getAzraelServiceHosts(etchosts: str):
    """
    Return the hosts/ports for all Azrael services.

    The ``etchosts`` parameter specifies the file from which to parse the
    addresses of the services. This file will almost always be the
    system/container local /etc/hosts file. If not it must still adhere to the
    same format.

    :param str etchosts: location of hosts file.
    :return: dict eg {'clerk': ('localhost', 5555)}
    """
    # Put the host/port into a named tuple.
    AddrPort = collections.namedtuple('AddrPort', 'ip port')

    # All services reside on the local host by default.
    hosts_default = {
        'clerk': AddrPort('localhost', 5555),
        'database': AddrPort('localhost', 27017),
        'rabbitmq': AddrPort('localhost', 5672),
        'webapi': AddrPort('localhost', 8080),
        'dibbler': AddrPort('localhost', 8081),
        'leonard': AddrPort('localhost', 5556),
    }

    # If we are not inside a docker container then we assume all services run
    # on this very host.
    if os.getenv('INSIDEDOCKER', None) is None:
        return dict(hosts_default)

    # ---------------------------------------------------------------------------
    # If we get to here it means we are running inside a Docker container. We
    # therefore read the /etc/hosts file (or whatever we got given in the
    # `etchosts` argument) and parse it.
    # ---------------------------------------------------------------------------

    # Read the hosts file.
    try:
        lines = open(etchosts, 'r').readlines()
        hosts_system = parseHostsFile(lines)
    except (TypeError, FileNotFoundError):
        hosts_system = {}

    # Host names are case insensitive, but docker-compose adheres to the case
    # specified by the user. Therefore, ensure all host names are lower case.
    hosts_system = {k.lower(): v for (k, v) in hosts_system.items()}

    # If the host file contains an entry for any of the services Azrael has to
    # offer then replace the derault ('localhost') with the entry from the
    # hosts file.
    hosts = {}
    for (name, (addr, port)) in hosts_default.items():
        if name in hosts_system:
            addr = hosts_system[name]
        hosts[name] = AddrPort(addr, port)
    return hosts
