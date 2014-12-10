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
    ok, data = btInterface.getStateVariables([id_0])
    assert not ok

    # Query an object. Since none exists yet this must return with an error.
    ok, data = btInterface.getStateVariables([id_0])
    assert not ok

    # Create an object and serialise it.
    data = bullet_data.BulletData()

    # Add the object to the DB with ID=0.
    assert btInterface.spawn(id_0, data, np.int64(1).tostring(), 0)

    # Query the object. This must return the SV data directly.
    assert btInterface.getStateVariables([id_0]) == (True, [data])

    # Query the same object but supply it as a list. This must return a list
    # with one element which is the exact same object as before.
    assert btInterface.getStateVariables([id_0]) == (True, [data])

    # Attempt to remove non-existing ID --> must fail.
    ok, msg = btInterface.deleteObject(id_1)
    assert not ok
    assert btInterface.getStateVariables([id_0]) == (True, [data])
    ok, out = btInterface.getAllStateVariables()
    assert (ok, len(out)) == (True, 1)

    # Remove existing ID --> must succeed.
    ok, msg = btInterface.deleteObject(id_0)
    assert ok
    assert btInterface.getStateVariables([id_0]) == (False, [])
    ok, out = btInterface.getAllStateVariables()
    assert (ok, len(out)) == (True, 0)

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
    ok, data = btInterface.getStateVariables([id_0])
    assert not ok

    # Create an object and serialise it.
    data_0 = bullet_data.BulletData()
    data_0.position[:] = 0

    data_1 = bullet_data.BulletData()
    data_1.position[:] = 10 * np.ones(3)

    # Add the objects to the DB.
    assert btInterface.spawn(id_0, data_0, np.int64(1).tostring(), 0)
    assert btInterface.spawn(id_1, data_1, np.int64(1).tostring(), 0)

    # Query the objects individually.
    ok, out = btInterface.getStateVariables([id_0])
    assert (ok, out) == (True, [data_0])
    ok, out = btInterface.getStateVariables([id_1])
    assert (ok, out) == (True, [data_1])

    # Manually query multiple objects.
    ok, out = btInterface.getStateVariables([id_0, id_1])
    assert (ok, len(out)) == (True, 2)
    assert out[0] == data_0
    assert out[1] == data_1

    # Repeat, but change the order of the objects.
    ok, out = btInterface.getStateVariables([id_1, id_0])
    assert (ok, len(out)) == (True, 2)
    assert out[1] == data_0
    assert out[0] == data_1

    # Query all objects at once.
    ok, out = btInterface.getAllStateVariables()
    assert (ok, len(out)) == (True, 2)
    assert out[id_0] == data_0
    assert out[id_1] == data_1

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
    ok, data = btInterface.getStateVariables([id_0])
    assert not ok

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
    assert not btInterface.spawn(id_0, data_1, np.int64(1).tostring(), 0)

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
    ok, force, torque = btInterface.getForceAndTorque(id_0)
    assert ok
    assert np.array_equal(force, f0)
    assert np.array_equal(torque, p0)
    ok, force, torque = btInterface.getForceAndTorque(id_1)
    assert ok
    assert np.array_equal(force, f1)
    assert np.array_equal(torque, p1)

    # Update the force vector of only the second object.
    f1 = np.ones(3, np.float64)
    p1 = 2 * np.ones(3, np.float64)
    assert btInterface.setForce(id_1, f1, p1)

    # Check again. The force of only the second object must have changed.
    ok, force, torque = btInterface.getForceAndTorque(id_0)
    assert ok
    assert np.array_equal(force, f0)
    assert np.array_equal(torque, p0)
    ok, force, torque = btInterface.getForceAndTorque(id_1)
    assert ok
    assert np.array_equal(force, f1)
    assert np.array_equal(torque, np.cross(p1, f1))

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
    ok, out = btInterface.getStateVariables([id_0])
    assert (ok, out) == (True, [data_0])

    # Create another SV object and serialise it as well.
    data_1 = bullet_data.BulletData()
    data_1.position[:] += 10

    # Change the SV data and check it was updated correctly.
    assert btInterface.update(id_0, data_1)
    ok, out = btInterface.getStateVariables([id_0])
    assert (ok, out) == (True, [data_1])

    # Updating an invalid object must fail.
    assert not btInterface.update(int2id(10), data_1)

    print('Test passed')


def test_override_attributes():
    """
    Set and retrieve a object attributes like position, velocity, acceleration,
    and orientation.
    """
    # Convenience.
    PosVelAccOrient = btInterface.PosVelAccOrient

    # Test constants.
    p = np.array([1, 2, 5])
    vl = np.array([8, 9, 10.5])
    vr = 1 + vl
    a = np.array([2.5, 3.5, 4.5])
    o = np.array([11, 12.5, 13, 13.5])
    data = PosVelAccOrient(p, vl, vr, a, o)
    del p, vl, vr, a, o

    # Reset the SV database.
    btInterface.initSVDB(reset=True)

    # Create an object ID for the test.
    id_0 = int2id(0)

    # Create an object and serialise it.
    btdata = bullet_data.BulletData()

    # Query attributes of non-existing object. This must fail.
    ok, ret = btInterface.getOverrideAttributes(id_0)
    assert not ok

    # Override attributes for a non-existing object. This must fail.
    assert not btInterface.overrideAttributes(int2id(10), data)

    # Add the object to the DB with ID=0.
    assert btInterface.spawn(id_0, btdata, np.int64(1).tostring(), 0)

    # Query the attributes for ID0. This must suceed. However, the
    # returned values must be None since no attribes have been forcefully set.
    ok, ret = btInterface.getOverrideAttributes(id_0)
    assert (ok, ret) == (True, PosVelAccOrient(None, None, None, None, None))

    # Request to overwrite attributes for the just inserted object.
    assert btInterface.overrideAttributes(id_0, data)

    # Retrieve the attributes and verify they are correct.
    ok, ret = btInterface.getOverrideAttributes(id_0)
    assert ok
    for a, b in zip(ret, data):
        assert np.array_equal(a, b)

    # Void the request to set attributes and verify that the attributes were
    # indeed reset.
    assert btInterface.overrideAttributes(id_0, None)
    ok, ret = btInterface.getOverrideAttributes(id_0)
    assert (ok, ret) == (True, PosVelAccOrient(None, None, None, None, None))

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
    ok, cnt = btInterface.countWorkPackages(token)
    assert (ok, cnt) == (True, 0)

    # This call is invalid because the IDs must be a non-empty list.
    ok, wpid_0 = btInterface.createWorkPackage([], token, 1, 2)
    assert not ok

    # There must still not be any work packages.
    ok, cnt = btInterface.countWorkPackages(token)
    assert (ok, cnt) == (True, 0)

    # Create a work package for two object IDs. The WPID must be 1.
    IDs = [int2id(_) for _ in range(3, 5)]
    ok, wpid_0 = btInterface.createWorkPackage(IDs, token, 1, 2)
    assert (ok, wpid_0) == (True, 1)

    # There must now be exactly one work package.
    ok, cnt = btInterface.countWorkPackages(token)
    assert (ok, cnt) == (True, 1)

    # Repeat. This WPID must be 2.
    IDs = [int2id(_) for _ in range(3, 5)]
    ok, wpid_1 = btInterface.createWorkPackage(IDs, token, 1, 2)
    assert (ok, wpid_1) == (True, 2)

    # There must now be exactly two work package.
    ok, cnt = btInterface.countWorkPackages(token)
    assert (ok, cnt) == (True, 2)

    # The attempt to retrie a non-existing ID must fail. The number of work
    # packages must remain unchanged.
    ok, data, _ = btInterface.getWorkPackage(0)
    assert not ok
    ok, cnt = btInterface.countWorkPackages(token)
    assert (ok, cnt) == (True, 2)

    # Retrieve an existing WPID. It must return an empty list because no
    # objects were added to the WP.
    ok, data, admin = btInterface.getWorkPackage(wpid_0)
    assert (ok, data) == (True, [])
    assert (admin.token, admin.dt, admin.maxsteps) == (token, 1, 2)

    # There must still be two work packages because retrieving one does not
    # remove it from the DB (only updating does).
    ok, cnt = btInterface.countWorkPackages(token)
    assert (ok, cnt) == (True, 2)

    # Update (and thus remove) a non-existing work package. The number of SV
    # data elements is irrelevant to this function.
    assert not btInterface.updateWorkPackage(0, token, {})
    ok, cnt = btInterface.countWorkPackages(token)
    assert (ok, cnt) == (True, 2)

    # For in invalid token the count must be zero.
    ok, cnt = btInterface.countWorkPackages(token + 1)
    assert (ok, cnt) == (True, 0)

    # Update (and thus remove) an existing work package. Once again, the number
    # of SV data elements is irrelevant to the function.
    assert btInterface.updateWorkPackage(wpid_0, token, {})
    ok, cnt = btInterface.countWorkPackages(token)
    assert (ok, cnt) == (True, 1)

    # Try to update it once more. This must fail since the WPID was
    # automatically removed by the previous updateWorkPackage command.
    assert not btInterface.updateWorkPackage(wpid_0, token, {})
    ok, cnt = btInterface.countWorkPackages(token)
    assert (ok, cnt) == (True, 1)

    # Update (and thus remove) the other work package.
    assert btInterface.updateWorkPackage(wpid_1, token, {})
    ok, cnt = btInterface.countWorkPackages(token)
    assert (ok, cnt) == (True, 0)

    print('Test passed')


def test_create_work_package_with_objects():
    """
    Create, fetch, and update Bullet work packages.

    Similar to test_create_work_package_without_objects but now the there are
    actual objects in the simulation.
    """
    # Reset the SV database.
    btInterface.initSVDB(reset=True)

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
    ok, wpid_1 = btInterface.createWorkPackage([id_1], token, 1, 2)
    assert (ok, wpid_1) == (True, 1)

    # Add ID1 and ID2 to the second WP. The WPID must be 2.
    ok, wpid_2 = btInterface.createWorkPackage([id_1, id_2], token, 3, 4)
    assert (ok, wpid_2) == (True, 2)

    # Retrieve the first work package.
    ok, ret, admin = btInterface.getWorkPackage(wpid_1)
    assert (ok, len(ret)) == (True, 1)
    assert (admin.token, admin.dt, admin.maxsteps) == (token, 1, 2)
    assert ret[0].id == id_1
    assert ret[0].sv == data_1
    assert np.array_equal(np.fromstring(ret[0].central_force), [0, 0, 0])

    # Retrieve the second work package.
    ok, ret, admin = btInterface.getWorkPackage(wpid_2)
    assert (admin.token, admin.dt, admin.maxsteps) == (token, 3, 4)
    assert (ok, len(ret)) == (True, 2)
    assert (ret[0].id, ret[1].id) == (id_1, id_2)
    assert (ret[0].sv, ret[1].sv) == (data_1, data_2)
    assert np.array_equal(np.fromstring(ret[0].central_force), [0, 0, 0])

    # Create a new SV data to replace the old one.
    data_3 = bullet_data.BulletData(imass=3)

    # Manually retrieve the original data for id_1.
    assert btInterface.getStateVariables([id_1]) == (True, [data_1])

    # Update the first work package with the wrong token. The call must fail
    # and the data must remain intact.
    assert not btInterface.updateWorkPackage(wpid_1, token + 1, {id_1: data_3})
    assert btInterface.getStateVariables([id_1]) == (True, [data_1])

    # Update the first work package with the correct token. This must succeed.
    assert btInterface.updateWorkPackage(wpid_1, token, {id_1: data_3})
    assert btInterface.getStateVariables([id_1]) == (True, [data_3])

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
    ok, force, torque = btInterface.getForceAndTorque(id_0)
    assert ok
    assert np.array_equal(force, f0)
    assert np.array_equal(torque, t0)
    ok, force, torque = btInterface.getForceAndTorque(id_1)
    assert ok
    assert np.array_equal(force, f1)
    assert np.array_equal(torque, t1)

    # Update the force and torque of the second object only.
    f1 = np.ones(3, np.float64)
    t1 = 2 * np.ones(3, np.float64)
    assert btInterface.setForceAndTorque(id_1, f1, t1)

    # Only the force an torque of the second object must have changed.
    ok, force, torque = btInterface.getForceAndTorque(id_0)
    assert ok
    assert np.array_equal(force, f0)
    assert np.array_equal(torque, t0)
    ok, force, torque = btInterface.getForceAndTorque(id_1)
    assert ok
    assert np.array_equal(force, f1)
    assert np.array_equal(torque, t1)

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

    # Ensure (de)serialisation works.
    assert sv1 == bullet_data.fromNumPyString(sv1.toNumPyString())
    print('Test passed')


def test_set_get_AABB():
    """
    Create a new object with an AABB and query it back again.
    """
    # Reset the SV database.
    btInterface.initSVDB(reset=True)

    # Create two object IDs and a BulletData instances for this test.
    id_0, id_1 = int2id(0), int2id(1)
    data = bullet_data.BulletData()

    # Attempt to add an object with a negative AABB value. This must fail.
    assert not btInterface.spawn(id_0, data, np.int64(1).tostring(), -1.5)

    # Add two new objects to the DB.
    assert btInterface.spawn(id_0, data, np.int64(1).tostring(), 1.5)
    assert btInterface.spawn(id_1, data, np.int64(1).tostring(), 2.5)

    # Query the AABB of the first.
    ok, aabb = btInterface.getAABB([id_0])
    assert np.array_equal(aabb, [1.5])

    # Query the AABB of the second.
    ok, aabb = btInterface.getAABB([id_1])
    assert np.array_equal(aabb, [2.5])

    # Query the AABB of both simultaneously.
    ok, aabb = btInterface.getAABB([id_0, id_1])
    assert np.array_equal(aabb, [1.5, 2.5])


if __name__ == '__main__':
    test_set_get_AABB()
    test_StateVariable_tuple()
    test_get_set_forceandtorque()
    test_create_work_package_with_objects()
    test_create_work_package_without_objects()
    test_override_attributes()
    test_update_statevar()
    test_get_set_force()
    test_add_same()
    test_add_get_multiple()
    test_add_get_remove_single()
