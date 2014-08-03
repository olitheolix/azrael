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
import logging
import pymongo
import IPython
import numpy as np
import azrael.util
import azrael.config as config

from collections import namedtuple


ipshell = IPython.embed
_DB_SV = None
_DB_WP = None

BulletData = namedtuple('BulletData',
                'radius scale imass restitution orientation position '
                'velocityLin velocityRot cshape')

# Create module logger.
logit = logging.getLogger('azrael.' + __name__)


def initSVDB(reset=True):
    global _DB_SV, _DB_WP
    client = pymongo.MongoClient()
    _DB_SV = client['azrael']['sv']
    _DB_WP = client['azrael']['wp']
    if reset:
        _DB_SV.drop()
        _DB_WP.drop()
        _DB_WP.insert({'name': 'wpcnt', 'cnt': 0})


def count():
    """
    Return the number of objects in the SV DB.
    """
    return _DB_SV.count()
    

def add(ID, data, objdesc):
    """
    Add new ``ID`` with associated data and return the success.
    """
    assert isinstance(ID, bytes)
    assert len(ID) == config.LEN_ID
    assert isinstance(data, bytes)
    assert len(data) == config.LEN_SV_BYTES

    # Add the document. The find_and_modify command below implements the
    # fictional 'insert_if_not_exists' command.
    z = np.zeros(3).tostring()
    doc = _DB_SV.find_and_modify(
        {'objid': ID},
        {'$setOnInsert': {'sv': data, 'force': z, 'relpos': z, 'sugPos': None,
                          'objdesc': objdesc}},
        upsert=True, new=True)
    # The SV in the returned document will only match ``data`` if either no
    # object with ID existed before the call, or the ID existed but with
    # identical data. Conversely, if the ID already existed but with different
    # SV data then return False.
    return doc['sv'] == data
    

def get(IDs):
    """
    Retrieve one or more ``IDs``.

    The function either returns all requested ``IDs`` or None. The latter case
    usually happens when one or more ``IDs`` do not exist.
    """
    if isinstance(IDs, bytes):
        scalar = True
        IDs = (IDs,)
    else:
        scalar = False
    assert isinstance(IDs, (tuple, list))
    for _ in IDs:
        assert isinstance(_, bytes)
        assert len(_) == config.LEN_ID

    # Retrieve all objects.
    out = [_DB_SV.find_one({'objid': _}) for _ in IDs]

    # Return with an error if one or more documents were unavailable.
    if None in out:
        return [], False
    else:
        out = [_['sv'] for _ in out]

    # Return the retrieved SV data either in a list or a single byte
    # stream, depending on whether ``IDs`` was a list or not.
    if scalar:
        return out[0], True
    else:
        return out, True
    

def update(ID, data):
    """
    Add new ``ID`` with associated data and return the success.
    """
    assert isinstance(ID, bytes)
    assert len(ID) == config.LEN_ID
    assert isinstance(data, bytes)
    assert len(data) == config.LEN_SV_BYTES

    doc = _DB_SV.update({'objid': ID}, {'$set': {'sv': data}})

    # The SV in the returned document will only match ``data`` if either no
    # object with ID existed before the call, or the ID existed but with
    # identical data. Conversely, if the ID already existed but with different
    # SV data then return False.
    return doc['n'] == 1
    

def getAll():
    """
    Return all objects in a dictionary with 'objid' as the key.
    """
    # Retrieve all objects.
    out = {}
    for doc in _DB_SV.find():
        objid = doc['objid']
        del doc['objid']
        out[objid] = doc['sv']
    return out, True
    

def getForce(ID):
    """
    Return the force and its relative position wrt to center of mass.

    Return (force, relpos, True) if the query was successfull, otherwise
    return (None, None, False).
    """
    # Sanity check.
    assert isinstance(ID, bytes)
    assert len(ID) == config.LEN_ID

    # Query the object.
    doc = _DB_SV.find_one({'objid': ID})
    if doc is None:
        return None, None, False

    # Extract and unpack the force and its position relative to the center of
    # mass.
    force, relpos = doc['force'], doc['relpos']
    force, relpos = np.fromstring(force), np.fromstring(relpos)

    # Return the result.
    return force, relpos, True
    

def setForce(ID, force, relpos):
    """
    Update the ``force`` acting on ``ID``. The force applies at positions
    ``relpos`` to the center of mass.
    """
    # Sanity check.
    assert isinstance(ID, bytes)
    assert len(ID) == config.LEN_ID
    assert isinstance(force, np.ndarray)
    assert isinstance(relpos, np.ndarray)
    assert len(force) == len(relpos) == 3

    # Serialise the force and position.
    force = force.astype(np.float64)
    relpos = relpos.astype(np.float64)
    force, relpos = force.tostring(), relpos.tostring()

    # Update the DB.
    ret = _DB_SV.update({'objid': ID},
                        {'$set': {'force': force, 'relpos': relpos}})

    # Exactly one document should have been updated.
    return ret['n'] == 1
    

def setSuggestedPosition(ID, pos):
    """
    Suggest to move ``ID`` to ``pos`` in the world.
    """
    # Sanity check.
    assert isinstance(ID, bytes)
    assert len(ID) == config.LEN_ID
    if pos is not None:
        assert isinstance(pos, np.ndarray)
        assert len(pos) == 3

        # Serialise the force and position.
        pos = pos.astype(np.float64).tostring()

        # Update the DB.
        ret = _DB_SV.update({'objid': ID}, {'$set': {'sugPos': pos}})

    else:
        # If pos is None then set it directly.
        ret = _DB_SV.update({'objid': ID}, {'$set': {'sugPos': None}})

    # Exactly one document should have been updated.
    return ret['n'] == 1
    

def getSuggestedPosition(ID):
    """
    Retrieve the suggested position for ``ID``.
    """
    # Sanity check.
    assert isinstance(ID, bytes)
    assert len(ID) == config.LEN_ID

    # Query the document.
    doc = _DB_SV.find_one({'objid': ID})

    # Return an error if no document with matchin ID was found.
    if doc is None:
        return None, False

    # A matching document was found. This document may or may not contain a
    # suggested position. Either way, the call succeeded.
    if doc['sugPos'] is None:
        return None, True
    else:
        return np.fromstring(doc['sugPos']), True
    

def getTemplateID(ID):
    """
    Retrieve the template ID for object ``ID``.
    """
    # Sanity check.
    assert isinstance(ID, bytes)
    assert len(ID) == config.LEN_ID

    # Query the document.
    doc = _DB_SV.find_one({'objid': ID})

    # Return an error if no document with matchin ID was found.
    if doc is None:
        return None, False
    else:
        return doc['objdesc'], True
    

def defaultData(radius=1, scale=1, imass=1, restitution=0.9,
                orientation=[0,0,0,1], position=[0,0,0], vlin=[0,0,0],
                vrot=[0,0,0], cshape=[0,1,1,1]):
    """
    Return a valid Bullet data object with sensible defaults.

    This is a convenience function to obtain a valid Bullet data specimen.
    """

    data = BulletData(
        radius=radius,
        scale=scale,
        imass=imass,
        restitution=restitution,
        orientation=np.float64(orientation),
        position=np.float64(position),
        velocityLin=np.float64(vlin),
        velocityRot=np.float64(vrot),
        cshape=np.float64(cshape))

    assert len(data.orientation) == 4
    assert len(data.position) == 3
    assert len(data.velocityLin) == 3
    assert len(data.velocityRot) == 3
    assert len(data.cshape) == 4
    return data


def createWorkPackage(IDs, token, dt, maxsteps):
    """
    Create unique WP ID and associate it with all ``IDs`` and the ``token``.

    Return wpid and status.
    """
    assert isinstance(IDs, list)
    if len(IDs) == 0:
        return None, False

    wpid = _DB_WP.find_and_modify(
        {'name': 'wpcnt'}, {'$inc': {'cnt': 1}}, new=True)
    if wpid is None:
        logit.error('Could not fetch WPID counter - this is a bug!')
        sys.exit(1)
    else:
        wpid = wpid['cnt']

    # Remove all WP with the current ID. This is a precaution as there should
    # be no such WPs to begin with.
    ret = _DB_WP.remove({'wpid': wpid}, multi=True)
    if ret['n'] > 0:
        logit.warning('A previous WP with ID={} already existed'.format(wpid))

    # Create the current WP.
    ret = _DB_WP.insert({'wpid': wpid, 'ids': IDs, 'token': token,
                         'dt': dt, 'maxsteps': maxsteps})
    if ret is None:
        return wpid, False
    else:
        for objid in IDs:
            _DB_SV.update({'objid': objid}, {'$set': {'token': token}})
        return wpid, True


def getWorkPackage(wpid):
    """
    Fetch the SV data for all objects specified in wpid.
    """

    doc = _DB_WP.find_one({'wpid': wpid})
    if doc is None:
        return None, None, False
    else:
        IDs = doc['ids']

    WPData = namedtuple('WPRecord', 'id sv force sugPos')
    WPAdmin = namedtuple('WPAdmin', 'token dt maxsteps')
    data = [_DB_SV.find_one({'objid': _}) for _ in IDs]
    data = [_ for _ in data if _ is not None]
    data = [WPData(_['objid'], _['sv'], _['force'], _['sugPos']) for _ in data]
    admin = WPAdmin(doc['token'], doc['dt'], doc['maxsteps'])
    return data, admin, True


def updateWorkPackage(wpid, token, svdict):
    """
    Update the SV information in the DB, but only if the ``token`` matches.
    """
    ret = _DB_WP.remove({'wpid': wpid, 'token': token}, multi=True)
    if ret['n'] == 0:
        return False

    for objid in svdict:
        _DB_SV.update({'objid': objid, 'token': token},
                      {'$set': {'sv': svdict[objid], 'sugPos': None},
                       '$unset': {'token': 1}})
    return True


def pack(obj: dict):
    """
    Return a NumPy array that encodes ``obj``.

    The ``obj`` dictionary must contain certain fields (see source code for
    more details -- to unstable for docu at this point).

    The returned NumPy array is binary compatible with the `cython_bullet`
    wrapper and, ideally, the only way how data is encoded for Bullet.
    """
    # fixme:
    #assert isinstance(obj, dict)

    # Allocate a NumPy array for the state variable data.
    buf = np.zeros(config.LEN_SV_FLOATS, dtype=np.float64)

    # Convert the content of ``obj`` to float64 NumPy data and insert them into
    # the buffer. The order *matters*, as it is the exact order in which the
    # C++ wrappe for Bullet expects the data.
    buf[0] = np.float64(obj.radius)
    buf[1] = np.float64(obj.scale)
    buf[2] = np.float64(obj.imass)
    buf[3] = np.float64(obj.restitution)
    buf[4:8] = np.float64(obj.orientation)
    buf[8:11] = np.float64(obj.position)
    buf[11:14] = np.float64(obj.velocityLin)
    buf[14:17] = np.float64(obj.velocityRot)
    buf[17:21] = np.float64(obj.cshape)

    # Just to be sure because an error here may lead to difficulties to find
    # bugs with the Bullet C++ interface.
    assert buf.dtype == np.float64
    return buf


def unpack(buf: np.ndarray):
    """
    This is the inverse of :func:`pack`.

    It takes a NumPy array as input and converts it to the corresponding
    dictionary of state variables.
    """
    # Sanity checks.
    assert isinstance(buf, np.ndarray)
    assert buf.dtype == np.float64
    assert len(buf) == config.LEN_SV_FLOATS

    data = BulletData(
        radius=buf[0],
        scale=buf[1],
        imass=buf[2],
        restitution=buf[3],
        orientation=buf[4:8],
        position=buf[8:11],
        velocityLin=buf[11:14],
        velocityRot=buf[14:17],
        cshape=buf[17:21])
    return data
