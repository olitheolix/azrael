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
Specify and implement the necessary functions to create, access and manipulate
state variables.
"""

import sys
import logging
import pymongo
import IPython
import numpy as np
import azrael.util
import azrael.config as config

from collections import namedtuple
from azrael.typecheck import typecheck

ipshell = IPython.embed

# Global database handles.
_DB_SV = None
_DB_WP = None

# All relevant physics data.
BulletData = namedtuple('BulletData',
                'radius scale imass restitution orientation position '
                'velocityLin velocityRot cshape')

# Work package related.
WPData = namedtuple('WPRecord', 'id sv force sugPos')
WPAdmin = namedtuple('WPAdmin', 'token dt maxsteps')


# Create module logger.
logit = logging.getLogger('azrael.' + __name__)


@typecheck
def initSVDB(reset=True):
    """
    Connect to the State Variable database. Flush it if ``reset`` is **True**.

    :param bool reset: flush the database.
    """
    global _DB_SV, _DB_WP
    client = pymongo.MongoClient()
    _DB_SV = client['azrael']['sv']
    _DB_WP = client['azrael']['wp']
    if reset:
        _DB_SV.drop()
        _DB_WP.drop()
        _DB_WP.insert({'name': 'wpcnt', 'cnt': 0})


def getNumObjects():
    """
    Return the number of objects in the simulation.

    :returns int: number of objects in simulation.
    """
    return _DB_SV.count()
    

@typecheck
def spawn(objID: bytes, sv: bytes, templateID: bytes):
    """
    Add the new ``objID`` and return success.

    Returns **False** if ``objID`` already exists in the simulation.

    :param bytes objID: object ID to insert.
    :param bytes sv: encoded state variable data.
    :param bytes templateID: the template from which the object is spawned.
    :return bool: success.
    """
    # Sanity checks.
    if (len(objID) != config.LEN_ID) or (len(sv) != config.LEN_SV_BYTES):
        return False
    
    # Dummy variable to specify the initial force and its relative position.
    z = np.zeros(3).tostring()

    # Add the document. The find_and_modify command below implements the
    # fictional 'insert_if_not_exists' command.
    doc = _DB_SV.find_and_modify(
        {'objid': objID},
        {'$setOnInsert': {'sv': sv, 'force': z, 'relpos': z, 'sugPos': None,
                          'templateID': templateID}},
        upsert=True, new=True)

    # The SV in the returned document will only match ``sv`` if either no
    # object with objID existed before the call, or the objID existed but with
    # identical SV. In any other case there will be no match because the
    # objID already existed.
    return doc['sv'] == sv
    

@typecheck
def getStateVariables(objIDs: (list, tuple)):
    """
    Retrieve the state variables for all ``objIDs``.

    This function returns either all requested ``objIDs`` or None. The latter
    case usually only happens if one or more object IDs in ``objIDs`` do not
    exist.

    :param iterable objIDs: list of object ID for which to return the SV.
    :return list: list of binary state variables.
    """
    # Sanity check.
    for _ in objIDs:
        if not isinstance(_, bytes) or (len(_) != config.LEN_ID):
            logit.warning('Object ID has invalid type')
            return False, []

    # Retrieve the state variables.
    out = [_DB_SV.find_one({'objid': _}) for _ in objIDs]

    # Return with an error if one or more documents were unavailable.
    if None in out:
        return False, []

    # Return the list of state variables.
    out = [_['sv'] for _ in out]
    return True, out
    

@typecheck
def update(objID: bytes, sv: bytes):
    """
    Update the ``sv`` data for object ``objID`` return the success.
    fixme: `sv` must be of type `BulletData`

    Return **False** if the update failed, most likely because the ``objID``
    was invalid.

    :param bytes objID: the object for which to update the state variables.
    :param bytes sv: encoded state variables.
    :return bool: success.
    """
    # Sanity check.
    if (len(objID) != config.LEN_ID) or (len(sv) != config.LEN_SV_BYTES):
        return False

    # Update an existing object only.
    doc = _DB_SV.update({'objid': objID}, {'$set': {'sv': sv}})

    # This function was successful if exactly one document was updated.
    return doc['n'] == 1
    

def getAllStateVariables():
    """
    Return the state variables for all objects in a dictionary.

    The keys and values of the returned dictionary correspond to the object ID
    and its associated state variables, respectively.

    :return: (ok, dictionary of state variables)
    :rtype: (bool, dict)
    """
    # Compile all objects IDs and state variables into a dictionary.
    out = {}
    for doc in _DB_SV.find():
        key, value = doc['objid'], doc['sv']
        out[key] = value
    return True, out
    

def getAllObjectIDs():
    """
    Return all object IDs.

    Unlike ``getAllStateVariables`` this function merely returns object IDs but
    no associated data (eg. state variables).

    :return: (ok, list-of-IDs).
    :rtype: (bool, list)
    """
    # Compile and return the list of all object IDs.
    return True, [_['objid'] for _ in _DB_SV.find()]
    

@typecheck
def getForce(objID: bytes):
    """
    Return the force and its relative position with respect to the centre of
    mass.

    :param bytes objID: object ID for which to query the force.
    :return: (True, force, relpos) if the query was successful, otherwise
             (False, None, None).
    :rtype: (ok, ndarray, ndarray)
    """
    # Sanity check.
    if (len(objID) != config.LEN_ID):
        return False, None, None

    # Query the object.
    doc = _DB_SV.find_one({'objid': objID})
    if doc is None:
        return False, None, None

    # Unpack the force and its position relative to the center of mass.
    force, relpos = doc['force'], doc['relpos']
    force, relpos = np.fromstring(force), np.fromstring(relpos)

    # Return the result.
    return True, force, relpos
    

@typecheck
def setForce(objID: bytes, force: np.ndarray, relpos: np.ndarray):
    """
    Update the ``force`` acting on ``objID``.

    The force applies at positions ``relpos`` relative to the centre of mass.

    :param bytes objID: the object to which the force applies.
    :param np.ndarray force: force
    :param np.ndarray relpos: relative position of force
    :return bool: success.
    """
    # Sanity check.
    if (len(objID) != config.LEN_ID):
        return False
    if not (len(force) == len(relpos) == 3):
        return False

    # Serialise the force and position.
    force = force.astype(np.float64).tostring()
    relpos = relpos.astype(np.float64).tostring()

    # Update the DB.
    ret = _DB_SV.update({'objid': objID},
                        {'$set': {'force': force, 'relpos': relpos}})

    # This function was successful if exactly one document was updated.
    return ret['n'] == 1
    

@typecheck
def getForceAndTorque(objID: bytes):
    """
    Return the force and torque for ``objID``.

    :param bytes objID: object for which to query the force and torque.
    :returns: (True, force, torque) if the query was successful and (False,
               None, None) if not.
    :rtype: (bool, ndarray, ndarray)
    """
    # Sanity check.
    if (len(objID) != config.LEN_ID):
        return False, None, None

    # Query the object.
    doc = _DB_SV.find_one({'objid': objID})
    if doc is None:
        return False, None, None

    # Unpack the force.
    try:
        force = np.fromstring(doc['central_force'])
    except KeyError:
        force = np.zeros(3)

    # Unpack the torque.
    try:
        torque = np.fromstring(doc['torque'])
    except KeyError:
        torque = np.zeros(3)

    # Return the result.
    return True, force, torque
    

@typecheck
def setForceAndTorque(objID: bytes, force: np.ndarray, torque: np.ndarray):
    """
    Set the central ``force`` and ``torque`` acting on ``objID``.

    .. note::
       The force always applies to the centre of the mass only, unlike the
       ``setForce`` function which allows for position relative to the centre
       of mass.

    :param bytes objID: the object 
    :param ndarray force: central force to apply
    :param ndarray torque: torque to apply
    :return bool: Success
    """
    # Sanity check.
    if (len(objID) != config.LEN_ID):
        return False
    if not (len(force) == len(torque) == 3):
        return False
    
    # Serialise the force and torque.
    force = force.astype(np.float64).tostring()
    torque = torque.astype(np.float64).tostring()

    # Update the DB.
    ret = _DB_SV.update({'objid': objID},
                        {'$set': {'central_force': force, 'torque': torque}})

    # This function was successful if exactly one document was updated.
    return ret['n'] == 1
    

@typecheck
def setSuggestedPosition(objID: bytes, pos: np.ndarray):
    """
    Suggest to place ``objID`` at ``pos`` in the world.

    Clear any previously suggested position with ``pos``=None.

    :param bytes objID: suggest a position for this object.
    :param ndarray pos: place the object at that position.
    :return bool: Success
    """
    # Sanity check.
    if (len(objID) != config.LEN_ID):
        return False

    if pos is not None:
        if len(pos) != 3:
            return False

        # Serialise the position and add the suggested position to the DB.
        pos = pos.astype(np.float64).tostring()
        ret = _DB_SV.update({'objid': objID}, {'$set': {'sugPos': pos}})
    else:
        # If ``pos`` is None then clear any previously suggested positions.
        ret = _DB_SV.update({'objid': objID}, {'$set': {'sugPos': None}})

    # This function was successful if exactly one document was updated.
    return ret['n'] == 1
    

@typecheck
def getSuggestedPosition(objID: bytes):
    """
    Retrieve the suggested position for ``objID``.

    This function returns **None** if no position suggestion is available.

    :param bytes objID: get the suggested position for this object.
    :param ndarray pos: place the object at that position.
    :return: (ok, suggest-position)
    :rtype: (bool, ndarray or None)
    """
    # Sanity check.
    if len(objID) != config.LEN_ID:
        return False, None

    # Query the object.
    doc = _DB_SV.find_one({'objid': objID})
    if doc is None:
        return False, None

    # There may, or may not be a recommended position for this object.
    if doc['sugPos'] is None:
        return True, None
    else:
        return True, np.fromstring(doc['sugPos'])
    

@typecheck
def getTemplateID(objID: bytes):
    """
    Retrieve the template ID for object ``objID``.

    :param bytes objID: get the template ID of this object.
    :return: (ok, templateID)
    :rtype: (bool, bytes)
    """
    # Sanity check.
    if len(objID) != config.LEN_ID:
        return False, None

    # Query the document.
    doc = _DB_SV.find_one({'objid': objID})
    if doc is None:
        return False, 'Could not query objID={}'.format(objID)
    else:
        return True, doc['templateID']
    

@typecheck
def defaultData(
        radius: (int, float)=1, scale: (int, float)=1, imass: (int, float)=1,
        restitution: (int, float)=0.9,
        orientation: (list, np.ndarray)=[0,0,0,1],
        position: (list, np.ndarray)=[0,0,0],
        vlin: (list, np.ndarray)=[0,0,0],
        vrot: (list, np.ndarray)=[0,0,0],
        cshape: (list, np.ndarray)=[0,1,1,1]):
    """
    Return a ``BulletData`` object.

    Without any arguments this function will return a valid ``BulletData``
    specimen with sensible defaults.
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

    # Sanity checks.
    assert len(data.orientation) == 4
    assert len(data.position) == 3
    assert len(data.velocityLin) == 3
    assert len(data.velocityRot) == 3
    assert len(data.cshape) == 4
    return data


@typecheck
def createWorkPackage(
        objIDs: (tuple, list), token: int, dt: (int, float), maxsteps: int):
    """
    Create a new Work Package (WP) and return its ID.

    The work package has an associated ``token`` value and all ``objIDs`` in
    the work list will be marked with it to prevent accidental updates.

    The ``dt`` and ``maxsteps`` arguments are for the underlying physics
    engine.

    :param iterable objIDs: list of object IDs in the new work package.
    :param int token: token value associated with this work package.
    :param float dt: time step for this work package.
    :param int maxsteps: number of sub-steps for the time step.
    :return: (ok, WPID)
    :rtype: (bool, int)
    """
    # Sanity check.
    if len(objIDs) == 0:
        return False, None

    # Obtain a new and unique work package ID.
    wpid = _DB_WP.find_and_modify(
        {'name': 'wpcnt'}, {'$inc': {'cnt': 1}}, new=True)
    if wpid is None:
        logit.error('Could not fetch WPID counter - this is a bug!')
        sys.exit(1)
    wpid = wpid['cnt']

    # Remove all WP with the current ID. This is a precaution since there
    # should not be any to begin with.
    ret = _DB_WP.remove({'wpid': wpid}, multi=True)
    if ret['n'] > 0:
        logit.warning('A previous WP with ID={} already existed'.format(wpid))

    # Create a new work package.
    ret = _DB_WP.insert({'wpid': wpid, 'ids': objIDs, 'token': token,
                         'dt': dt, 'maxsteps': maxsteps})
    if ret is None:
        return False, wpid

    # Update the token value of every object in the work package.
    for objid in objIDs:
        _DB_SV.update({'objid': objid}, {'$set': {'token': token}})
    return True, wpid


@typecheck
def getWorkPackage(wpid: int):
    """
    Return the SV data for all objects specified in the ``wpid`` list.

    :param int wpid: work package ID.
    :return: (ok, object-data, WP-admin-data)
    :rtype: (bool, list-of-WPData, WPAdmin)
    """

    # Retrieve the work package.
    doc = _DB_WP.find_one({'wpid': wpid})
    if doc is None:
        return False, None, None
    else:
        objIDs = doc['ids']

    # Compile a list of WPData objects; one for every object in the WP. Skip
    # non-existing objects.
    data = [_DB_SV.find_one({'objid': _}) for _ in objIDs]
    data = [_ for _ in data if _ is not None]
    data = [WPData(_['objid'], _['sv'], _['force'], _['sugPos']) for _ in data]

    # Put the meta data of the work package into another named tuple.
    admin = WPAdmin(doc['token'], doc['dt'], doc['maxsteps'])
    return True, data, admin


@typecheck
def updateWorkPackage(wpid: int, token, svdict: dict):
    """
    Update the SV data for all objects in ``svdict``.

    Only those objects in the work package with ID ``wpid`` will be processed,
    and even then only if their ``token`` value matches.

    :param int wpid: work package ID.
    :param int token: token value associated with this work package.
    :param dict svdict: {objID: sv} dictionary
    :return bool: Success.
    """
    # Remove the specified work package.
    ret = _DB_WP.remove({'wpid': wpid, 'token': token}, multi=True)
    if ret['n'] == 0:
        return False

    # Iterate over all object IDs and update the state variable with the
    # provided values.
    for objID in svdict:
        _DB_SV.update({'objid': objID, 'token': token},
                      {'$set': {'sv': svdict[objID], 'sugPos': None},
                       '$unset': {'token': 1}})
    return True


@typecheck
def pack(obj: BulletData):
    """
    Return the NumPy array that corresponds to ``obj``.

    The returned NumPy array is binary compatible with the `cython_bullet`
    wrapper and, ideally, the only way how data is encoded for Bullet.

    :param BulletData obj: state variable to serialise.
    :return ndarray: ``obj`` as a NumPy.float64 array.
    """
    # Allocate a NumPy array for the state variable data.
    buf = np.zeros(config.LEN_SV_FLOATS, dtype=np.float64)

    # Convert the content of ``obj`` to float64 NumPy data and insert them into
    # the buffer. The order *matters*, as it is the exact order in which the
    # C++ wrapper for Bullet expects the data.
    buf[0] = np.float64(obj.radius)
    buf[1] = np.float64(obj.scale)
    buf[2] = np.float64(obj.imass)
    buf[3] = np.float64(obj.restitution)
    buf[4:8] = np.float64(obj.orientation)
    buf[8:11] = np.float64(obj.position)
    buf[11:14] = np.float64(obj.velocityLin)
    buf[14:17] = np.float64(obj.velocityRot)
    buf[17:21] = np.float64(obj.cshape)

    # Just to be sure because an error here may lead to subtle bugs with the
    # Bullet C++ interface.
    assert buf.dtype == np.float64
    return buf


@typecheck
def unpack(buf: np.ndarray):
    """
    Return the ``BulletData`` instance that corresponds to ``buf``.

    This is the inverse of :func:`pack`.

    :param ndarray obj: state variables as a single NumPy array.
    :return BulletData: state variables as a BulletData instance.
    """
    # Sanity checks.
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
