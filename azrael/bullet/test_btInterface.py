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
import pytest
import cytoolz
import IPython
import numpy as np

import azrael.bullet.btInterface as btInterface
import azrael.bullet.bullet_data as bullet_data

from azrael.util import int2id, id2int

ipshell = IPython.embed


def test_add_get_remove_single():
    """
    Add an object to the SV database.
    """
    # Reset the SV database.
    btInterface.initSVDB(reset=True)

    # Create an object ID for the test.
    id_0 = int2id(0)
    id_1 = int2id(1)

    # The number of SV entries must now be zero.
    assert btInterface.getNumObjects() == 0

    # Query an object. Since none exists yet this must return with an error.
    assert btInterface.getStateVariables([id_0]) == (True, None, {id_0: None})

    # Create an object and serialise it.
    data = bullet_data.BulletData()

    # Add the object to the DB with ID=0.
    assert btInterface.spawn(id_0, data, np.int64(1).tostring(), 0)

    # Query the object. This must return the SV data directly.
    assert btInterface.getStateVariables([id_0]) == (True, None, {id_0: data})

    # Query the same object but supply it as a list. This must return a list
    # with one element which is the exact same object as before.
    assert btInterface.getStateVariables([id_0]) == (True, None, {id_0: data})

    # Attempt to remove non-existing ID --> must fail.
    assert not btInterface.deleteObject(id_1).ok
    assert btInterface.getStateVariables([id_0]) == (True, None, {id_0: data})
    ret = btInterface.getAllStateVariables()
    assert (ret.ok, len(ret.data)) == (True, 1)

    # Remove existing ID --> must succeed.
    assert btInterface.deleteObject(id_0).ok
    assert btInterface.getStateVariables([id_0]) == (True, None, {id_0: None})
    ret = btInterface.getAllStateVariables()
    assert (ret.ok, len(ret.data)) == (True, 0)

    print('Test passed')


def test_add_get_multiple():
    """
    Add multiple objects to the DB.
    """
    # Reset the SV database.
    btInterface.initSVDB(reset=True)

    # Create two object IDs for this test.
    id_0 = int2id(0)
    id_1 = int2id(1)

    # The number of SV entries must now be zero.
    assert btInterface.getNumObjects() == 0
    assert btInterface.getStateVariables([id_0]) == (True, None, {id_0: None})

    # Create an object and serialise it.
    data_0 = bullet_data.BulletData()
    data_0.position[:] = 0

    data_1 = bullet_data.BulletData()
    data_1.position[:] = 10 * np.ones(3)

    # Add the objects to the DB.
    assert btInterface.spawn(id_0, data_0, np.int64(1).tostring(), 0)
    assert btInterface.spawn(id_1, data_1, np.int64(1).tostring(), 0)

    # Query the objects individually.
    ret = btInterface.getStateVariables([id_0])
    assert (ret.ok, ret.data) == (True, {id_0: data_0})
    ret = btInterface.getStateVariables([id_1])
    assert (ret.ok, ret.data) == (True, {id_1: data_1})

    # Manually query multiple objects.
    ret = btInterface.getStateVariables([id_0, id_1])
    assert (ret.ok, len(ret.data)) == (True, 2)
    assert ret.data[id_0] == data_0
    assert ret.data[id_1] == data_1

    # Repeat, but change the order of the objects.
    ret = btInterface.getStateVariables([id_1, id_0])
    assert (ret.ok, len(ret.data)) == (True, 2)
    assert ret.data[id_0] == data_0
    assert ret.data[id_1] == data_1

    # Query all objects at once.
    ret = btInterface.getAllStateVariables()
    assert (ret.ok, len(ret.data)) == (True, 2)
    assert ret.data[id_0] == data_0
    assert ret.data[id_1] == data_1

    print('Test passed')


def test_add_same():
    """
    Try to add two objects with the same ID.
    """
    # Reset the SV database.
    btInterface.initSVDB(reset=True)

    # Create one object ID for this test.
    id_0 = int2id(0)

    # The number of SV entries must now be zero.
    assert btInterface.getNumObjects() == 0
    assert btInterface.getStateVariables([id_0]) == (True, None, {id_0: None})

    # Create an object and serialise it.
    data_0 = bullet_data.BulletData()
    data_0.position[:] = np.zeros(3)

    data_1 = bullet_data.BulletData()
    data_1.position[:] = 10 * np.ones(3)

    # Add the objects to the DB.
    assert btInterface.spawn(id_0, data_0, np.int64(1).tostring(), 0)

    # Add the same object with the same ID -- this must work since nothing
    # has changed.
    assert btInterface.spawn(id_0, data_0, np.int64(1).tostring(), 0)

    # Add a different object with the same ID -- this must fail.
    assert not btInterface.spawn(id_0, data_1, np.int64(1).tostring(), 0).ok

    print('Test passed')


def test_get_set_force():
    """
    Query and update the force vector for an object.
    """
    # Reset the SV database.
    btInterface.initSVDB(reset=True)

    # Create two object IDs for this test.
    id_0 = int2id(0)
    id_1 = int2id(1)

    # Create two objects and serialise them.
    data_0 = bullet_data.BulletData()
    data_0.position[:] = 0

    data_1 = bullet_data.BulletData()
    data_1.position[:] = 10 * np.ones(3)

    # Add the two objects to the DB.
    assert btInterface.spawn(id_0, data_0, np.int64(1).tostring(), 0)
    assert btInterface.spawn(id_1, data_1, np.int64(1).tostring(), 0)

    # Convenince: forces and their positions.
    f0 = np.zeros(3, np.float64)
    f1 = np.zeros(3, np.float64)
    p0 = np.zeros(3, np.float64)
    p1 = np.zeros(3, np.float64)

    # The force and positions must match the defaults.
    ret = btInterface.getForceAndTorque(id_0)
    assert ret.ok
    assert np.array_equal(ret.data['force'], f0)
    assert np.array_equal(ret.data['torque'], p0)
    ret = btInterface.getForceAndTorque(id_1)
    assert ret.ok
    assert np.array_equal(ret.data['force'], f1)
    assert np.array_equal(ret.data['torque'], p1)

    # Update the force vector of only the second object.
    f1 = np.ones(3, np.float64)
    p1 = 2 * np.ones(3, np.float64)
    assert btInterface.setForce(id_1, f1, p1).ok

    # Check again. The force of only the second object must have changed.
    ret = btInterface.getForceAndTorque(id_0)
    assert ret.ok
    assert np.array_equal(ret.data['force'], f0)
    assert np.array_equal(ret.data['torque'], p0)
    ret = btInterface.getForceAndTorque(id_1)
    assert ret.ok
    assert np.array_equal(ret.data['force'], f1)
    assert np.array_equal(ret.data['torque'], np.cross(p1, f1))

    print('Test passed')


def test_update_statevar():
    """
    Add an object to the SV database.
    """
    # Reset the SV database.
    btInterface.initSVDB(reset=True)

    # Create an object ID for the test.
    id_0 = int2id(0)

    # Create an SV object and serialise it.
    data_0 = bullet_data.BulletData()

    # Add the object to the DB with ID=0.
    assert btInterface.spawn(id_0, data_0, np.int64(1).tostring(), 0)

    # Query the object. This must return the SV data directly.
    ret = btInterface.getStateVariables([id_0])
    assert (ret.ok, ret.data) == (True, {id_0: data_0})

    # Create another SV object and serialise it as well.
    data_1 = bullet_data.BulletData()
    data_1.position[:] += 10

    # Change the SV data and check it was updated correctly.
    assert btInterface.update(id_0, data_1)
    ret = btInterface.getStateVariables([id_0])
    assert (ret.ok, ret.data) == (True, {id_0: data_1})

    # Updating an invalid object must fail.
    assert not btInterface.update(int2id(10), data_1).ok

    print('Test passed')


def test_overrideAttributes():
    """
    Set and retrieve object attributes like position, velocity, acceleration,
    and orientation.
    """
    # Convenience.
    BulletDataOverride = bullet_data.BulletDataOverride

    # Test constants.
    p = np.array([1, 2, 5])
    vl = np.array([8, 9, 10.5])
    vr = 1 + vl
    o = np.array([11, 12.5, 13, 13.5])
    data = BulletDataOverride(imass=2, scale=3, position=p, velocityLin=vl,
                              velocityRot=vr, orientation=o)
    del p, vl, vr, o

    # Reset the SV database.
    btInterface.initSVDB(reset=True)

    # Create an object ID for the test.
    id_0 = int2id(0)

    # Create an object and serialise it.
    btdata = bullet_data.BulletData()

    # Query attributes of non-existing object. This must fail.
    assert not btInterface.getOverrideAttributes(id_0).ok

    # Override attributes for a non-existing object. This must fail.
    assert not btInterface.setStateVariables(int2id(10), data).ok

    # Add the object to the DB with ID=0.
    assert btInterface.spawn(id_0, btdata, np.int64(1).tostring(), 0).ok

    # Query the attributes for ID0. This must succeed. However, the returned
    # values must all be None since no attributes have been set specifically.
    ret = btInterface.getOverrideAttributes(id_0)
    assert (ret.ok, ret.data) == (True, BulletDataOverride())

    # Set the overwrite attributes for the just created object.
    assert btInterface.setStateVariables(id_0, data)

    # Retrieve the attributes and verify they are correct.
    ret = btInterface.getOverrideAttributes(id_0)
    assert ret.ok
    assert ret is not None
    for a, b in zip(ret.data, data):
        assert np.array_equal(a, b)

    # Ensure that scalars did not become stunted NumPy types.
    assert isinstance(ret.data.imass, (int, float))
    assert isinstance(ret.data.scale, (int, float))

    # Void the request to set attributes and verify that the attributes were
    # indeed reset.
    assert btInterface.setStateVariables(id_0, None)
    ret = btInterface.getOverrideAttributes(id_0)
    assert (ret.ok, ret.data) == (True, BulletDataOverride())

    print('Test passed')


def test_BulletDataOverride():
    """
    ``BulletDataOverride`` must only accept valid input where the
    ``BulletData`` class defines what constitutes "valid".
    """
    # Convenience.
    BulletData = bullet_data.BulletData
    BulletDataOverride = bullet_data.BulletDataOverride

    # Valid BulletData and BulletDataOverride calls.
    assert BulletData() is not None
    assert BulletDataOverride() is not None

    assert BulletData(position=[1, 2, 3]) is not None
    assert BulletDataOverride(position=[1, 2, 3]) is not None

    # Pass positional arguments with None values.
    assert BulletDataOverride(None, None) is not None

    # Pass a dictionary with None values. This must still result in the default
    # structure.
    tmp = {'velocityRot': None, 'cshape': None}
    assert BulletDataOverride(**tmp) is not None
    tmp = {'velocityRot': np.array([1, 2, 3], np.float64), 'cshape': None}
    out = BulletDataOverride(**tmp)
    assert out is not None
    assert np.array_equal(out.velocityRot, tmp['velocityRot'])

    # Combine positional and keyword arguments.
    assert BulletDataOverride(None, None, **tmp) is not None

    # Pass Python- scalars and lists instead of NumPy types. The scalars must
    # remain unaffected but the lists must become NumPy arrays.
    ret = BulletData(imass=3, position=[1, 2, 3])
    assert isinstance(ret.imass, int)
    assert isinstance(ret.position, np.ndarray)

    ret = BulletDataOverride(imass=3, position=[1, 2, 3])
    assert isinstance(ret.imass, int)
    assert isinstance(ret.position, np.ndarray)

    # Invalid calls.
    assert BulletData(position=[1, 2]) is None
    assert BulletDataOverride(position=[1, 2]) is None
    assert BulletData(position=np.array([1, 2])) is None
    assert BulletDataOverride(position=np.array([1, 2])) is None

    assert BulletDataOverride(position=1) is None
    assert BulletDataOverride(position='blah') is None

    print('Test passed')


def test_create_work_package_without_objects():
    """
    Create, fetch, update, and count Bullet work packages.

    This test does not insert any objects into the simulation. It only tests
    the general functionality to add, retrieve, and update work packages.
    """
    # Reset the SV database.
    btInterface.initSVDB(reset=True)

    # The token to use for this test.
    token = 1

    # There must not be any work packages yet.
    ret = btInterface.countWorkPackages(token)
    assert (ret.ok, ret.data) == (True, 0)

    # This call is invalid because the IDs must be a non-empty list.
    assert not btInterface.createWorkPackage([], token, 1, 2).ok

    # There must still not be any work packages.
    ret = btInterface.countWorkPackages(token)
    assert (ret.ok, ret.data) == (True, 0)

    # Create a work package for two object IDs. The WPID must be 1.
    IDs = [int2id(_) for _ in range(3, 5)]
    ret = btInterface.createWorkPackage(IDs, token, 1, 2)
    assert (ret.ok, ret.data) == (True, 1)

    # There must now be exactly one work package.
    ret = btInterface.countWorkPackages(token)
    assert (ret.ok, ret.data) == (True, 1)

    # Repeat. This WPID must be 2.
    IDs = [int2id(_) for _ in range(3, 5)]
    ret = btInterface.createWorkPackage(IDs, token, 1, 2)
    assert (ret.ok, ret.data) == (True, 2)

    # There must now be exactly two work package.
    ret = btInterface.countWorkPackages(token)
    assert (ret.ok, ret.data) == (True, 2)

    # The attempt to retrie a non-existing ID must fail. The number of work
    # packages must remain unchanged.
    ok, data, _ = btInterface.getWorkPackage(0)
    assert not ok
    ret = btInterface.countWorkPackages(token)
    assert (ret.ok, ret.data) == (True, 2)
    wpid_0 = ret.data

    # Retrieve an existing WPID. It must return an empty list because no
    # objects were added to the WP.
    ret = btInterface.getWorkPackage(wpid_0)
    assert (ret.ok, ret.data['wpdata']) == (True, [])
    meta = ret.data['wpmeta']
    assert (meta.token, meta.dt, meta.maxsteps) == (token, 1, 2)

    # There must still be two work packages because retrieving one does not
    # remove it from the DB (only updating does).
    ret = btInterface.countWorkPackages(token)
    assert (ret.ok, ret.data) == (True, 2)

    # Update (and thus remove) a non-existing work package. The number of SV
    # data elements is irrelevant to this function.
    assert not btInterface.updateWorkPackage(0, token, {}).ok
    ret = btInterface.countWorkPackages(token)
    assert (ret.ok, ret.data) == (True, 2)

    # For in invalid token the count must be zero.
    ret = btInterface.countWorkPackages(token + 1)
    assert (ret.ok, ret.data) == (True, 0)

    # Update (and thus remove) an existing work package. Once again, the number
    # of SV data elements is irrelevant to the function.
    assert btInterface.updateWorkPackage(wpid_0, token, {}).ok
    ret = btInterface.countWorkPackages(token)
    assert (ret.ok, ret.data) == (True, 1)

    # Try to update it once more. This must fail since the WPID was
    # automatically removed by the previous updateWorkPackage command.
    assert not btInterface.updateWorkPackage(wpid_0, token, {}).ok
    ret = btInterface.countWorkPackages(token)
    assert (ret.ok, ret.data) == (True, 1)
    wpid_1 = ret.data

    # Update (and thus remove) the other work package.
    assert btInterface.updateWorkPackage(wpid_1, token, {}).ok
    ret = btInterface.countWorkPackages(token)
    assert (ret.ok, ret.data) == (True, 0)

    print('Test passed')


def test_create_work_package_with_objects():
    """
    Create, fetch, and update Bullet work packages.

    Similar to test_create_work_package_without_objects but now the there are
    actual objects in the simulation.
    """
    # Reset the SV database.
    btInterface.initSVDB(reset=True)

    # Convenience.
    getWorkPackage = btInterface.getWorkPackage
    createWorkPackage = btInterface.createWorkPackage
    updateWorkPackage = btInterface.updateWorkPackage
    getStateVariables = btInterface.getStateVariables

    # The token to use in this test.
    token = 1

    # Create two objects.
    data_1 = bullet_data.BulletData(imass=1)
    data_2 = bullet_data.BulletData(imass=2)

    # Spawn them.
    id_1, id_2 = int2id(1), int2id(2)
    assert btInterface.spawn(id_1, data_1, np.int64(1).tostring(), 0)
    assert btInterface.spawn(id_2, data_2, np.int64(1).tostring(), 0)

    # Add ID1 to the WP. The WPID must be 1.
    ret = createWorkPackage([id_1], token, 1, 2)
    assert (ret.ok, ret.data) == (True, 1)
    wpid_1 = ret.data
    
    # Add ID1 and ID2 to the second WP. The WPID must be 2.
    ret= createWorkPackage([id_1, id_2], token, 3, 4)
    assert (ret.ok, ret.data) == (True, 2)
    wpid_2 = ret.data

    # Retrieve the first work package.
    ret = getWorkPackage(wpid_1)
    assert (ret.ok, len(ret.data['wpdata'])) == (True, 1)
    data = ret.data['wpdata']
    meta = ret.data['wpmeta']
    assert (meta.token, meta.dt, meta.maxsteps) == (token, 1, 2)
    assert data[0].id == id_1
    assert data[0].sv == data_1
    assert np.array_equal(np.fromstring(data[0].central_force), [0, 0, 0])

    # Retrieve the second work package.
    ret = getWorkPackage(wpid_2)
    data = ret.data['wpdata']
    meta = ret.data['wpmeta']
    assert (meta.token, meta.dt, meta.maxsteps) == (token, 3, 4)
    assert (ret.ok, len(data)) == (True, 2)
    assert (data[0].id, data[1].id) == (id_1, id_2)
    assert (data[0].sv, data[1].sv) == (data_1, data_2)
    assert np.array_equal(np.fromstring(data[0].central_force), [0, 0, 0])

    # Create a new SV data to replace the old one.
    data_3 = bullet_data.BulletData(imass=3)

    # Manually retrieve the original data for id_1.
    ret = getStateVariables([id_1])
    assert (ret.ok, ret.data) == (True, {id_1: data_1})

    # Update the first work package with the wrong token. The call must fail
    # and the data must remain intact.
    assert not updateWorkPackage(wpid_1, token + 1, {id_1: data_3}).ok
    ret = getStateVariables([id_1])
    assert (ret.ok, ret.data) == (True, {id_1: data_1})

    # Update the first work package with the correct token. This must succeed.
    assert updateWorkPackage(wpid_1, token, {id_1: data_3}).ok
    ret = getStateVariables([id_1])
    assert (ret.ok, ret.data) == (True, {id_1: data_3})

    print('Test passed')


def test_get_set_forceandtorque():
    """
    Query and update the force- and torque vectors for an object.
    """
    # Reset the SV database.
    btInterface.initSVDB(reset=True)

    # Create two object IDs for this test.
    id_0 = int2id(0)
    id_1 = int2id(1)

    # Create two objects and serialise them.
    data_0 = bullet_data.BulletData()
    data_0.position[:] = 0

    data_1 = bullet_data.BulletData()
    data_1.position[:] = 10 * np.ones(3)

    # Add the two objects to the simulation.
    assert btInterface.spawn(id_0, data_0, np.int64(1).tostring(), 0)
    assert btInterface.spawn(id_1, data_1, np.int64(1).tostring(), 0)

    # Convenience: specify the forces and torques.
    f0 = np.zeros(3, np.float64)
    f1 = np.zeros(3, np.float64)
    t0 = np.zeros(3, np.float64)
    t1 = np.zeros(3, np.float64)

    # Retrieve the force and torque and verify they are correct.
    ret = btInterface.getForceAndTorque(id_0)
    assert ret.ok
    assert np.array_equal(ret.data['force'], f0)
    assert np.array_equal(ret.data['torque'], t0)
    ret = btInterface.getForceAndTorque(id_1)
    assert ret.ok
    assert np.array_equal(ret.data['force'], f1)
    assert np.array_equal(ret.data['torque'], t1)

    # Update the force and torque of the second object only.
    f1 = np.ones(3, np.float64)
    t1 = 2 * np.ones(3, np.float64)
    assert btInterface.setForceAndTorque(id_1, f1, t1)

    # Only the force an torque of the second object must have changed.
    ret = btInterface.getForceAndTorque(id_0)
    assert ret.ok
    assert np.array_equal(ret.data['force'], f0)
    assert np.array_equal(ret.data['torque'], t0)
    ret = btInterface.getForceAndTorque(id_1)
    assert ret.ok
    assert np.array_equal(ret.data['force'], f1)
    assert np.array_equal(ret.data['torque'], t1)

    print('Test passed')


def test_StateVariable_tuple():
    """
    Test the BulletData class, most notably comparison and (de)serialisation.
    """
    # Compare two identical objects.
    sv1 = bullet_data.BulletData()
    sv2 = bullet_data.BulletData()
    assert sv1 == sv2

    # Compare two different objects.
    sv1 = bullet_data.BulletData()
    sv2 = bullet_data.BulletData(position=[1, 2, 3])
    assert not (sv1 == sv2)
    assert sv1 != sv2

    # Ensure (de)serialisation works.
    assert sv1 == bullet_data.fromJsonDict(sv1.toJsonDict())

    print('Test passed')


def test_set_get_AABB():
    """
    Create a new object with an AABB and query it back again.
    """
    # Reset the SV database.
    btInterface.initSVDB(reset=True)

    # Create two object IDs and a BulletData instances for this test.
    id_0, id_1 = int2id(0), int2id(1)
    id_2, id_3 = int2id(2), int2id(3)
    data = bullet_data.BulletData()

    # Attempt to add an object with a negative AABB value. This must fail.
    assert not btInterface.spawn(id_0, data, np.int64(1).tostring(), -1.5).ok

    # Add two new objects to the DB.
    assert btInterface.spawn(id_0, data, np.int64(1).tostring(), 1.5)
    assert btInterface.spawn(id_1, data, np.int64(1).tostring(), 2.5)

    # Query the AABB of the first.
    ret = btInterface.getAABB([id_0])
    assert np.array_equal(ret.data, [1.5])

    # Query the AABB of the second.
    ret = btInterface.getAABB([id_1])
    assert np.array_equal(ret.data, [2.5])

    # Query the AABB of both simultaneously.
    ret = btInterface.getAABB([id_0, id_1])
    assert np.array_equal(ret.data, [1.5, 2.5])

    # Query the AABB of a non-existing ID.
    ret = btInterface.getAABB([id_0, id_3])
    assert ret.ok
    assert np.array_equal(ret.data, [1.5, None])


if __name__ == '__main__':
    test_BulletDataOverride()
    test_set_get_AABB()
    test_StateVariable_tuple()
    test_get_set_forceandtorque()
    test_create_work_package_with_objects()
    test_create_work_package_without_objects()
    test_overrideAttributes()
    test_update_statevar()
    test_get_set_force()
    test_add_same()
    test_add_get_multiple()
    test_add_get_remove_single()
