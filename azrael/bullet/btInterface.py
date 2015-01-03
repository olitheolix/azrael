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
import azrael.util as util
import azrael.config as config
import azrael.bullet.bullet_data as bullet_data

from collections import namedtuple
from azrael.typecheck import typecheck

ipshell = IPython.embed

# Global database handles.
_DB_SV = None
_DB_WP = None


# Work package related.
WPData = namedtuple('WPRecord', 'id sv central_force torque attrOverride')
WPAdmin = namedtuple('WPAdmin', 'token dt maxsteps')
BulletDataOverride = bullet_data.BulletDataOverride

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
def spawn(objID: bytes, sv: bullet_data.BulletData, templateID: bytes,
          aabb: (int, float)):
    """
    Add the new ``objID`` to the physics DB and return success.

    Contrary to the name ``aabb``, it actually denotes a bounding sphere and
    thus requires only a scalar argument instead of 3 side lengths. This will
    change eventually.

    Returns **False** if ``objID`` already exists in the simulation.

    :param bytes objID: object ID to insert.
    :param bytes sv: encoded state variable data.
    :param bytes templateID: the template from which the object is spawned.
    :param float aabb: size of AABB.
    :return bool: success.
    """
    # Serialise SV.
    sv = sv.toJsonDict()

    # Sanity checks.
    if len(objID) != config.LEN_ID:
        return False
    if aabb < 0:
        logit.warning('AABB must be non-negative')
        return False

    # Dummy variable to specify the initial force and its relative position.
    z = np.zeros(3).tostring()

    # Add the document. The find_and_modify command below implements the
    # fictional 'insert_if_not_exists' command. This ensures that we will not
    # overwrite any possibly existing object.
    doc = _DB_SV.find_and_modify(
        {'objid': objID},
        {'$setOnInsert': {'sv': sv, 'templateID': templateID,
                          'central_force': z, 'torque': z,
                          'attrOverride': BulletDataOverride(),
                          'AABB': float(aabb)}},
        upsert=True, new=True)

    # The SV in the returned document will only match ``sv`` if either no
    # object with objID existed before the call, or the objID existed but with
    # identical SV. In any other case there will be no match because the
    # objID already existed.
    return doc['sv'] == sv


@typecheck
def deleteObject(objID: bytes):
    """
    Delete ``objID`` from the physics simulation.

    :param bytes objID: ID of object to delete.
    :return: (ok, msg)
    :rtype: tuple
    """
    ret = _DB_SV.remove({'objid': objID})
    if ret['n'] == 1:
        return True, ''
    else:
        return False, 'Object not found'


@typecheck
def getStateVariables(objIDs: (list, tuple)):
    """
    Retrieve the state variables for all ``objIDs``.

    If one or more objIDs int ``objIDs`` do not not exist then the respective
    entry will return *None*.

    :param iterable objIDs: list of object IDs for which to return the SV.
    :return list: list of BulletData instances.
    """
    # Sanity check.
    for _ in objIDs:
        if not isinstance(_, bytes) or (len(_) != config.LEN_ID):
            logit.warning('Object ID has invalid type')
            return False, []

    # Retrieve the state variables.
    out = list(_DB_SV.find({'objid': {'$in': objIDs}}))

    # Put all SV into a dictionary to simplify sorting afterwards.
    out = {_['objid']: _ for _ in out}
    out = [out[_] if _ in out else None for _ in objIDs]

    # Compile a list of SVs in the order of the supplied ``objIDs``.
    fun = bullet_data.fromJsonDict
    out = [fun(_['sv']) if _ is not None else None for _ in out]
    return True, out


@typecheck
def getAABB(objIDs: (list, tuple)):
    """
    Retrieve the AABBs for all ``objIDs``.

    This function returns the AABBs (or *None* if it does not exist) for all
    ``objIDs``.

    :param iterable objIDs: list of object ID for which to return the SV.
    :return list: list of *floats*.
    """
    # Sanity check.
    for _ in objIDs:
        if not isinstance(_, bytes) or (len(_) != config.LEN_ID):
            logit.warning('Object ID has invalid type')
            return False, []

    # Retrieve the state variables.
    out = list(_DB_SV.find({'objid': {'$in': objIDs}}))

    # Put all AABBs into a dictionary to simplify sorting afterwards.
    out = {_['objid']: np.array(_['AABB'], np.float64) for _ in out}

    # Compile the AABB values into a list ordered by ``objIDs``. Insert a None
    # element if a particular objID has not AABB (probably means the object was
    # recently deleted).
    out = [out[_] if _ in out else None for _ in objIDs]

    # Return the AABB values.
    return True, out


@typecheck
def update(objID: bytes, sv: bullet_data.BulletData):
    """
    Update the ``sv`` data for object ``objID`` return the success.

    Return **False** if the update failed, most likely because the ``objID``
    was invalid.

    :param bytes objID: the object for which to update the state variables.
    :param bytes sv: encoded state variables.
    :return bool: success.
    """
    # Sanity check.
    if len(objID) != config.LEN_ID:
        return False

    # Update an existing object only.
    doc = _DB_SV.update({'objid': objID}, {'$set': {'sv': sv.toJsonDict()}})

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
    # Compile all object IDs and state variables into a dictionary.
    out = {}
    for doc in _DB_SV.find():
        key, value = doc['objid'], bullet_data.fromJsonDict(doc['sv'])
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
def setForce(objID: bytes, force: np.ndarray, relpos: np.ndarray):
    """
    Update the ``force`` acting on ``objID``.

    This function is a wrapper around ``setForceAndTorque``.

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

    # Compute the torque and then call setForceAndTorque.
    torque = np.cross(relpos, force)
    return setForceAndTorque(objID, force, torque)


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
def setOverrideAttributes(objID: bytes, data: BulletDataOverride):
    """
    Request to manually update the attributes of ``objID``.

    This function will merely place the request into the SV database.
    Leonard will read the request and apply it during the next update.

    Use ``pos``=None to void the request for overwriting attributes.

    :param bytes objID: object to update.
    :param BulletDataOverride pos: new object attributes.
    :return bool: Success
    """
    # Sanity check.
    if (len(objID) != config.LEN_ID):
        return False

    if data is None:
        # If ``data`` is None then the user wants us to clear any pending
        # attribute updates for ``objID``. Hence void the respective entry in
        # the DB.
        ret = _DB_SV.update({'objid': objID},
                            {'$set': {'attrOverride': BulletDataOverride()}})
        return ret['n'] == 1

    # Make sure that ``data`` is really valid by constructing a new
    # BulletDataOverride instance from it.
    data = BulletDataOverride(*data)
    if data is None:
        return False

    # All fields in ``data`` (a BulletDataOverride instance) are, by
    # definition, one of {None, int, float, np.ndarray}. The following code
    # merely converts the  NumPy arrays to normal lists so that Mongo can store
    # them.. For example, BulletDataOverride(None, 2, array([1,2,3]), ...)
    # would become [None, 2, [1,2,3], ...].
    data = list(data)
    for idx, val in enumerate(data):
        if isinstance(val, np.ndarray):
            data[idx] = val.tolist()

    # Serialise the position and add it to the DB.
    ret = _DB_SV.update({'objid': objID}, {'$set': {'attrOverride': data}})

    # This function was successful if exactly one document was updated.
    return ret['n'] == 1


@typecheck
def getOverrideAttributes(objID: bytes):
    """
    Retrieve the explicitly specified State Variable for ``objID``.

    This function returns **None** if no attributes are available for
    ``objID``.

    :param bytes objID: object for which to return the attribute request.
    :return: (ok, attributes)
    :rtype: (bool, ndarray or None)
    """
    # Sanity check.
    if len(objID) != config.LEN_ID:
        return False, None

    # Query the object.
    doc = _DB_SV.find_one({'objid': objID})
    if doc is None:
        return False, None

    # If no 'attrOverride' field exists then return the default
    # ``BulletDataOverride`` instance (it will have all values set to *None*).
    if doc['attrOverride'] is None:
        return True, BulletDataOverride()

    # Convert the data into a ``BulletDataOverride`` instance which means all
    # values that are not *None* must be converted to a NumPy array.
    tmp = dict(zip(BulletDataOverride._fields, doc['attrOverride']))
    try:
        for k, v in tmp.items():
            if isinstance(v, (list, tuple)):
                tmp[k] = np.array(v, np.float64)
    except TypeError:
        return False, None

    # Construct the BulletDataOverride instance and verify it was really
    # created.
    val = BulletDataOverride(**tmp)
    if val is None:
        # 'attrOverride' is valid.
        return False, None
    else:
        # 'attrOverride' is invalid.
        return True, val


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
def createWorkPackage(
        objIDs: (tuple, list), token: int, dt: (int, float), maxsteps: int):
    """
    Create a new Work Package (WP) and return its ID.

    The work package has an associated ``token`` value and all ``objIDs`` in
    the work list will be marked with it to prevent accidental updates.

    The ``dt`` and ``maxsteps`` arguments are for the underlying physics
    engine.

    .. note::
       A work package contains only the objIDs but not their SV. The
       ``getWorkPackage`` function takes care of compiling this information.

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

    def aux(data):
        """
        Place ``data`` into a BulletDataOverride structure.
        """
        fields = BulletDataOverride._fields
        return BulletDataOverride(**dict(zip(fields, data)))

    # Compile a list of WPData objects; one for every object in the WP. Skip
    # non-existing objects.
    data = [_DB_SV.find_one({'objid': _}) for _ in objIDs]
    data = [_ for _ in data if _ is not None]
    data = [WPData(_['objid'], bullet_data.fromJsonDict(_['sv']),
                   _['central_force'], _['torque'], aux(_['attrOverride']))
            for _ in data]

    # Put the meta data of the work package into another named tuple.
    admin = WPAdmin(doc['token'], doc['dt'], doc['maxsteps'])
    return True, data, admin


@typecheck
def updateWorkPackage(wpid: int, token, svdict: dict):
    """
    Update the objects in ``wpid`` with the values in ``svdict``.

    This function only makes changes to objects defined in the WP ``wpid``, and
    even then only if the ``token`` value matches.

    This function will also clear the token value and reset the
    BulletDataOverride information in the DB.

    :param int wpid: work package ID.
    :param int token: token value associated with this work package.
    :param dict svdict: {objID: sv} dictionary
    :return bool: Success.
    """
    # Iterate over all object IDs and update the state variables.
    for objID in svdict:
        _DB_SV.update(
            {'objid': objID, 'token': token},
            {'$set': {'sv': svdict[objID].toJsonDict(),
                      'attrOverride': BulletDataOverride()},
             '$unset': {'token': 1}})

    # Remove the specified work package. This MUST happen AFTER the SVs were
    # updated because btInterface.countWorkPackages will count the number of WP
    # to determine if all objects have been updated.
    ret = _DB_WP.remove({'wpid': wpid, 'token': token}, multi=True)
    if ret['n'] == 0:
        return False

    return True


@typecheck
def countWorkPackages(token):
    """
    Return the number of unprocessed work packages.

    :param int token: token value associated with this work package.
    :return bool: Success.
    """
    return True, _DB_WP.find({'token': token}).count()
