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
import IPython
import numpy as np
import azrael.util as util
import azrael.config as config
import azrael.bullet.bullet_data as bullet_data

from collections import namedtuple
from azrael.typecheck import typecheck

ipshell = IPython.embed

# Global database handle.
_DB_Grid = pymongo.MongoClient()['azrael_grid']


# Return value specification.
RetVal = namedtuple('RetVal', 'ok msg data')


# Create module logger.
logit = logging.getLogger('azrael.' + __name__)


def deleteAllGrids():
    """
    Delete all currently defined grids.

    :return: None
    """
    global _DB_Grid
    client = pymongo.MongoClient()
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
def defineGrid(name: str, elDim: int, granularity: (int, float)):
    """
    Define a new grid with ``name``.

    Every element of the grid is a vector with ``elDim`` elements. The grid has
    the spatial ``granularity`` (in meters). The minimum granularity is 1E-9m.

    :param str name: grid name
    :param int elDim: number of data dimensions.
    :param float granularity: spatial granularity in Meters.
    :return: None
    """
    # DB handle must have been initialised.
    if _DB_Grid is None:
        return RetVal(False, 'Not initialised', None)

    # Sanity check.
    if granularity < 1E-9:
        return RetVal(False, 'Granularity must be >1E-9', None)

    # Sanity check.
    if elDim <= 0:
        return RetVal(False, 'Vector dimension must be positive integer', None)

    # Return with an error if the grid ``name`` is already defined.
    if name in _DB_Grid.collection_names():
        msg = 'Grid <{}> already exists'.format(name)
        logit.info(msg)
        return RetVal(False, msg, None)

    # Flush the DB (just a pre-caution) and add the admin element.
    db = _DB_Grid[name]
    db.drop()
    db.insert({'admin': 'admin', 'elDim': elDim, 'gran': granularity})
    db.ensure_index([('x', 1), ('y', 1), ('z', 1)])

    # All good.
    return RetVal(True, None, None)


@typecheck
def resetGrid(name: str):
    """
    Reset all values of the grid ``name``.

    :param str name: grid name to reset.
    :return: None
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
    :return: None
    """
    # DB handle must have been initialised.
    if _DB_Grid is None:
        return RetVal(False, 'Not initialised', None)

    # Return with an error if the grid ``name`` does not exist.
    if name not in _DB_Grid.collection_names():
        msg = 'Unknown grid <{}>'.format(name)
        logit.info(msg)
        return RetVal(False, msg, None)

    # Flush the collection and insert the admin element again.
    _DB_Grid.drop_collection(name)

    # All good.
    return RetVal(True, None, None)


@typecheck
def getValue(name: str, pos: np.ndarray):
    """
    Return the value at ``pos``.

    :param str name: grid name
    :param 3D-vec pos: position in grid
    :return: data vector at ``pos``.
    """
    # Leverage 'getRegion' to do the actual work.
    ret = getRegion(name, pos, (1, 1, 1))
    if ret.ok:
        return RetVal(True, None, ret.data[0, 0, 0])
    else:
        return ret


@typecheck
def setValue(name: str, pos: np.ndarray, value: np.ndarray):
    """
    Update the value at ``pos`` to ``value``.

    :param str name: grid name
    :param 3D-vec pos: position in grid
    :param vector value: the value to insert at ``pos``.
    :return: None
    """
    # Leverage 'setRegion' to do the actual work. Wrap the ``value`` into a
    # 4-D data structure (the first three denote the position, the fourth holds
    # the actual value).
    tmp = np.zeros((1, 1, 1, len(value)), np.float64)
    tmp[0, 0, 0] = value
    return setRegion(name, pos, tmp)


@typecheck
def getRegion(name: str, ofs: np.ndarray,
              regionDim: (np.ndarray, list, tuple)):
    """
    Return the grid values starting at ``ofs``.

    The dimension of the returned depends on ``regionDim`` and the elDim
    parameter used to define the grid. For instance, if regionDim=(1, 2, 3) and
    the elDim=4, then the shape of the returned NumPy array is (1, 2, 3, 4).

    :param str name: grid name.
    :param 3D-vector ofs: start position in grid from where to read values.
    :param 3D-vector regionDim: number of values to read in each dimension.
    :return: 4D matrix.
    """
    # DB handle must have been initialised.
    if _DB_Grid is None:
        return RetVal(False, 'Not initialised', None)

    # Return with an error if the grid ``name`` does not exist.
    if name not in _DB_Grid.collection_names():
        msg = 'Unknown grid <{}>'.format(name)
        logit.info(msg)
        return RetVal(False, msg, None)
    else:
        db = _DB_Grid[name]

    # Ensure ``ofs`` and ``regionDim`` have the correct size.
    if (len(ofs) != 3) or (len(regionDim) != 3):
        return RetVal(False, 'Invalid parameter values', None)

    # Ensure the region dimensions are positive integers.
    regionDim = np.array(regionDim, np.int64)
    if np.amin(regionDim) < 1:
        return RetVal(False, 'Dimensions must be positive', None)

    # Retrieve the admin field for later use.
    admin = db.find_one({'admin': 'admin'})
    if admin is None:
        return RetVal(False, 'Bug: could not find admin element', None)

    # Allocate the output array.
    out = np.zeros(np.hstack((regionDim, admin['elDim'])), np.float64)

    # Compute the grid index of ``ofs``. That index is
    # determined uniquly by the position (``ofs``) and the grid granularity.
    gran = admin['gran']
    x0 = int(ofs[0] / gran)
    y0 = int(ofs[1] / gran)
    z0 = int(ofs[2] / gran)

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
    for doc in res:
        # Convert the grid index to an array index, ie simply compute all grid
        # indices relative to the ``ofs`` position.
        x = int(doc['x'] - x0)
        y = int(doc['y'] - y0)
        z = int(doc['z'] - z0)
        out[x, y, z, :] = np.array(doc['val'], np.float64)

    return RetVal(True, None, out)


@typecheck
def setRegion(name: str, ofs: np.ndarray, value: np.ndarray):
    """
    Update the grid values starting at ``ofs`` with ``value``.

    :param str name: grid name.
    :param 3D-vector ofs: start position in grid from where to read values.
    :param 4D-vector value: the data values.
    :return: None
    """
    # DB handle must have been initialised.
    if _DB_Grid is None:
        return RetVal(False, 'Not initialised', None)

    # Return with an error if the grid ``name`` does not exist.
    if name not in _DB_Grid.collection_names():
        msg = 'Unknown grid <{}>'.format(name)
        logit.info(msg)
        return RetVal(False, msg, None)
    else:
        db = _DB_Grid[name]

    # Ensure ``ofs`` has the correct size.
    if len(ofs) != 3:
        return RetVal(False, 'Invalid parameter values', None)

    # Retrieve the admin field for later use.
    admin = db.find_one({'admin': 'admin'})
    if admin is None:
        return RetVal(False, 'Bug: could not find admin element', None)

    # Ensure ``value`` has the correct number of dimensions. To elaborate,
    # every ``value`` needs at least 3 spatial dimensions, plus an additional
    # dimension that holds the actual data vector, which must have length
    # ``elDim``.
    if (len(value.shape) != 4) or (value.shape[3] != admin['elDim']):
        return RetVal(False, 'Invalid data dimension', None)

    # Populate the output array.
    for x in range(value.shape[0]):
        for y in range(value.shape[1]):
            for z in range(value.shape[2]):
                # Compute the grid position of the current data value.
                pos = ofs + np.array([x, y, z])
                pos = (pos / admin['gran']).astype(np.int64)

                # Convenience.
                px, py, pz = pos.tolist()
                val = value[x, y, z, :]

                # Either update the value in the DB (|value| != 0) or delete
                # all documents (there should only be one....) for this
                # position (|value| = 0).
                if np.sum(np.abs(val)) < 1E-9:
                    db.remove({'x': px, 'y': py, 'z': pz}, multi=True)
                else:
                    ret = db.update({'x': px, 'y': py, 'z': pz},
                                    {'x': px, 'y': py, 'z': pz,
                                     'val': val.tolist()},
                                    upsert=True)

    return RetVal(True, None, None)
