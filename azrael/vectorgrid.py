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
Vector grid engine.

All grids extend to infinity with a default value of zero. The basic usage
pattern is to define a new grid and then set/query values on it.

All grids have a spatial granularity. It is possible to set/query values at any
(floating point) position but the set/get functions will always round it to the
nearest granularity multiple.

Internally, the engine only adds non-zero values to the database, and removes
all those set to zero.
"""
import sys
import logging
import pymongo
import numpy as np
import azrael.config as config
import azrael.bullet_data as bullet_data

from IPython import embed as ipshell
from azrael.types import typecheck, RetVal

# Global database handle.
_DB_Grid = config.getMongoClient()['azrael_grid']


# Create module logger.
logit = logging.getLogger('azrael.' + __name__)


def deleteAllGrids():
    """
    Delete all currently defined grids.

    :return: Success
    """
    global _DB_Grid
    client = config.getMongoClient()
    name = 'azrael_grid'
    client.drop_database(name)
    _DB_Grid = client[name]

    return RetVal(True, None, None)


def getAllGridNames():
    """
    Return all the names of all currently defined grids.

    :return: grid names.
    :rtype: tuple of strings.
    """
    if _DB_Grid is None:
        return RetVal(False, 'Not initialised', None)
    else:
        # Every grid sits in its own collection. The grid names are hence the
        # grid names save 'system.indexes' which Mongo creates internally
        # itself.
        names = set(_DB_Grid.collection_names())
        names.discard('system.indexes')
        return RetVal(True, None, tuple(names))


@typecheck
def defineGrid(name: str, vecDim: int, granularity: (int, float)):
    """
    Define a new grid with ``name``.

    Every grid element is a vector with ``vecDim`` elements. The grid has the
    spatial ``granularity`` (in meters). The minimum granularity is 1E-9m.

    :param str name: grid name
    :param int vecDim: number of data dimensions.
    :param float granularity: spatial granularity in Meters.
    :return: Success
    """
    # DB handle must have been initialised.
    if _DB_Grid is None:
        return RetVal(False, 'Not initialised', None)

    # Sanity check.
    if granularity < 1E-9:
        return RetVal(False, 'Granularity must be >1E-9', None)

    # Sanity check.
    if vecDim <= 0:
        return RetVal(False, 'Vector dimension must be positive integer', None)

    # Return with an error if the grid ``name`` is already defined.
    if name in _DB_Grid.collection_names():
        msg = 'Grid <{}> already exists'.format(name)
        logit.info(msg)
        return RetVal(False, msg, None)

    # Flush the DB (just a pre-caution) and add the admin element.
    db = _DB_Grid[name]
    db.drop()
    db.insert({'admin': 'admin', 'vecDim': vecDim, 'gran': granularity})

    # Create indexes for fast lookups.
    db.ensure_index([('x', 1), ('y', 1), ('z', 1)])
    db.ensure_index([('strPos', 1)])

    # All good.
    return RetVal(True, None, None)


def getGridDB(name: str):
    """
    Return the database handle and admin field of the ``name`` grid.

    :param str name: name of grid.
    :return: (db, admin)
    """
    # DB handle must have been initialised.
    if _DB_Grid is None:
        return RetVal(False, 'Not initialised', None)

    # Return with an error if the grid ``name`` does not exist.
    if name not in _DB_Grid.collection_names():
        msg = 'Unknown grid <{}>'.format(name)
        logit.info(msg)
        return RetVal(False, msg, None)

    # Ensure the admin element exists.
    db = _DB_Grid[name]
    admin = db.find_one({'admin': 'admin'})
    if admin is None:
        return RetVal(False, 'Bug: could not find admin element', None)
    return RetVal(True, None, (db, admin))


@typecheck
def resetGrid(name: str):
    """
    Reset all values of the grid ``name``.

    :param str name: grid name to reset.
    :return: Success
    """
    # Fetch the database handle.
    ret = getGridDB(name)
    if not ret.ok:
        return ret
    db, admin = ret.data

    # Resetting a grid equates to deleting all values in the collection so that
    # all values assume their default again. We therefore simply drop the
    # entire collection and re-insert the admin element.
    db.drop()
    db.insert(admin)
    return RetVal(True, None, None)


@typecheck
def deleteGrid(name: str):
    """
    Delete the grid ``name``.

    :param str name: grid name.
    :return: Success
    """
    # Fetch the database handle (we will not use it but this function call does
    # all the error checking for us already).
    ret = getGridDB(name)
    if not ret.ok:
        return ret

    # Flush the collection and insert the admin element again.
    _DB_Grid.drop_collection(name)

    # All good.
    return RetVal(True, None, None)


def _encodePosition(pos: np.ndarray, granularity: float):
    """
    Return the grid index based on ``pos`` and ``granularity``.

    :param array pos: 3-element vector.
    :param float granularity: positive scalar to specify the grid granularity.
    :return: (px, py, pz, strPos)
    """
    # Enforce NumPy types to ensure consistent rounding/truncatio behaviour.
    pos = np.array(pos, np.float64)
    granularity = float(granularity)

    # Compute the array index in each dimension.
    px, py, pz = [int(_ // granularity) for _ in pos]

    # Compute a string representation of the array index.
    strPos = '{}:{}:{}'.format(px, py, pz)

    # Return the indexes.
    return px, py, pz, strPos


def _encodeData(px: int, py: int, pz: int, strPos, val: list):
    query = {'strPos': strPos}
    data = {'x': px, 'y': py, 'z': pz,
            'val': val, 'strPos': strPos}
    return query, data


@typecheck
def getValues(name: str, positions: (tuple, list)):
    """
    Return the value at ``positions`` in a tuple of NumPy arrays.

    :param str name: grid name
    :param list positions: grid positions (in string format)
    :return: list of grid values at ``positions``.
    """
    # Return immediately if we did not get any values.
    if len(positions) == 0:
        return RetVal(False, '<setValues> received no arguments', None)

    # Fetch the database handle.
    ret = getGridDB(name)
    if not ret.ok:
        return ret
    db, admin = ret.data
    gran, vecDim = admin['gran'], admin['vecDim']
    del admin, ret

    # Ensure the positions are valid.
    strPositions = []
    try:
        for pos in positions:
            assert isinstance(pos, (tuple, list, np.ndarray))
            assert len(pos) == 3
            px, py, pz, strPos = _encodePosition(pos, gran)
            strPositions.append(strPos)
    except AssertionError:
        return RetVal(False, '<getValues> received invalid positions', None)

    # Find all values and compile the output list.
    values = {_['strPos']: _['val']
              for _ in db.find({'strPos': {'$in': strPositions}})}

    # Put the grid values into the output list. The ``positions`` argument (or
    # ``strPositions``) uniquely specifies their order. User zeros whenever a
    # grid value was unavailable.
    out = np.zeros((len(strPositions), vecDim), np.float64)
    for idx, pos in enumerate(strPositions):
        if pos in values:
            out[idx, :] = np.array(values[pos], np.float64)

    return RetVal(True, None, out)


@typecheck
def setValues(name: str, posVals: (tuple, list)):
    """
    Update the grid values as specified in ``posVals``.

    :param list posVals: list of (pos, val) tuples.
    :return: Success
    """
    # Return immediately if we did not get any values.
    if len(posVals) == 0:
        return RetVal(False, '<setValues> received no arguments', None)

    # Fetch the database handle.
    ret = getGridDB(name)
    if not ret.ok:
        return ret
    db, admin = ret.data
    gran, vecDim = admin['gran'], admin['vecDim']
    del admin, ret

    # Ensure the region dimensions are positive integers.
    indexes = []
    bulk = db.initialize_unordered_bulk_op()
    try:
        for pv in posVals:
            assert isinstance(pv, (tuple, list, np.ndarray))
            assert len(pv) == 2
            assert isinstance(pv[0], (tuple, np.ndarray))
            assert isinstance(pv[1], (tuple, np.ndarray))
            pos, val = pv
            assert len(pos) == 3
            assert len(val) == vecDim

            # Convert the position to grid indexes.
            px, py, pz, strPos = _encodePosition(pos, gran)

            # Get database- query and entry.
            query, data = _encodeData(px, py, pz, strPos, val.tolist())

            # Update the value in the DB, unless it is essentially zero, in
            # which case remove it to free up space.
            if np.sum(np.abs(val)) < 1E-9:
                bulk.find(query).remove()
            else:
                bulk.find(query).upsert().update({'$set': data})
    except AssertionError:
        return RetVal(False, '<setValues> received invalid arguments', None)

    bulk.execute()
    return RetVal(True, None, None)


@typecheck
def getRegion(name: str, ofs: np.ndarray,
              regionDim: (np.ndarray, list, tuple)):
    """
    Return the grid values starting at 3D position ``ofs``.

    The returned array comprises foure dimensions. The first three correspond
    to x/y/z position and the fourth contains the data. That data is itself a
    vector. The size of that vector was specified when the grid was created.
    The dimension of the returned region depends on ``regionDim`` and the
    ``vecDim`` of the grid. For instance, if regionDim=(1, 2, 3) and the
    vecDim=4, then the shape of the returned NumPy array is (1, 2, 3, 4).

    :param str name: grid name.
    :param 3D-vector ofs: start position in grid from where to read values.
    :param 3D-vector regionDim: number of values to read in each dimension.
    :return: 4D matrix.
    """
    # Fetch the database handle.
    ret = getGridDB(name)
    if not ret.ok:
        return ret
    db, admin = ret.data
    gran, vecDim = admin['gran'], admin['vecDim']
    del admin, ret

    # Sanity check: ``ofs`` and ``regionDim`` must have 3 entries each.
    if (len(ofs) != 3) or (len(regionDim) != 3):
        return RetVal(False, 'Invalid parameter values', None)

    # Sanity check: ``regionDim`` must only contain positive integers.
    regionDim = np.array(regionDim, np.int64)
    if np.amin(regionDim) < 1:
        return RetVal(False, 'Dimensions must be positive', None)

    # Compute the grid index of ``ofs``.
    x0, y0, z0, strPos = _encodePosition(ofs, gran)

    # Convenience: the ``regionDim`` parameter uniquely specifies the number of
    # grid positions to query in each dimension.
    x1 = int(x0 + regionDim[0])
    y1 = int(y0 + regionDim[1])
    z1 = int(z0 + regionDim[2])

    # Query the values of all the specified grid positions.
    res = db.find({'x': {'$gte': x0, '$lt': x1},
                   'y': {'$gte': y0, '$lt': y1},
                   'z': {'$gte': z0, '$lt': z1}})

    # Populate the output data structure.
    out = np.zeros(np.hstack((regionDim, vecDim)), np.float64)
    for doc in res:
        # Convert the grid index to an array index, ie simply compute all grid
        # indices relative to the ``ofs`` position.
        x = int(doc['x'] - x0)
        y = int(doc['y'] - y0)
        z = int(doc['z'] - z0)
        out[x, y, z, :] = np.array(doc['val'], np.float64)

    return RetVal(True, None, out)


@typecheck
def setRegion(name: str, ofs: np.ndarray, gridValues: np.ndarray):
    """
    Update the grid values starting at ``ofs`` with ``gridValues``.

    :param str name: grid name.
    :param 3D-vector ofs: the values are inserted relative to this ``ofs``.
    :param 4D-vector gridValues: the data values to set.
    :return: Success
    """
    # Fetch the database handle.
    ret = getGridDB(name)
    if not ret.ok:
        return ret
    db, admin = ret.data
    gran, vecDim = admin['gran'], admin['vecDim']
    del admin, ret

    # Sanity check: ``ofs`` must denote a position in 3D space.
    if len(ofs) != 3:
        return RetVal(False, 'Invalid parameter values', None)

    # Sanity check: every ``gridValues`` must be a 3D matrix where every entry
    # is a vector with ``vecDim`` elements.
    if (len(gridValues.shape) != 4) or (gridValues.shape[3] != vecDim):
        return RetVal(False, 'Invalid gridValues dimension', None)

    # Populate the output array.
    bulk = db.initialize_unordered_bulk_op()
    for x in range(gridValues.shape[0]):
        for y in range(gridValues.shape[1]):
            for z in range(gridValues.shape[2]):
                # Convenience.
                val = gridValues[x, y, z, :]

                # Compute the grid position of the current data value and
                # convert it to integer indexes.
                pos = ofs + np.array([x, y, z])
                px, py, pz, strPos = _encodePosition(pos, gran)

                # Get database- query and entry.
                query, data = _encodeData(px, py, pz, strPos, val.tolist())

                if np.sum(np.abs(val)) < 1E-9:
                    bulk.find(query).remove()
                else:
                    bulk.find(query).upsert().update({'$set': data})

    # Execute the Mongo query. Don't bother with the return value.
    bulk.execute()
    return RetVal(True, None, None)
