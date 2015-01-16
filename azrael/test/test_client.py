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
Test the client base class.

The client class is merely a convenience class to wrap the Clerk
commands. As such the tests here merely test these wrappers. See `test_clerk`
if you want to see thorough tests for the Clerk functionality.
"""

import sys
import time
import pytest
import IPython
import subprocess
import numpy as np

import azrael.clerk
import azrael.clacks
import azrael.client
import azrael.wsclient
import azrael.parts as parts
import azrael.config as config
import azrael.leonard as leonard
import azrael.database as database
import azrael.protocol as protocol
import azrael.physics_interface as physAPI
import azrael.bullet.bullet_data as bullet_data

from azrael.test.test_clerk import getLeonard, killAzrael
from azrael.test.test_clerk import startAzrael, stopAzrael

ipshell = IPython.embed
WSClient = azrael.wsclient.WSClient
Client = azrael.client.Client

def test_ping():
    """
    Send a ping to the Clerk and check the response is correct.
    """
    killAzrael()

    # Start the necessary services.
    clerk, client, clacks = startAzrael('ZeroMQ')

    ret = client.ping()
    print(ret)
    assert ret == (True, None, 'pong clerk')

    # Shutdown the services.
    stopAzrael(clerk, clacks)
    print('Test passed')


@pytest.mark.parametrize('client_type', ['Websocket', 'ZeroMQ'])
def test_spawn_and_delete_one_client(client_type):
    """
    Ask Clerk to spawn one object.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    id_1 = 1

    # Constants and parameters for this test.
    templateID = '_templateNone'.encode('utf8')

    # Start the necessary services.
    clerk, client, clacks = startAzrael(client_type)

    # Instruct Clerk to spawn a new template. The new object must have
    # objID=1.
    ok, _, objID = client.spawn(templateID, np.zeros(3))
    assert (ok, objID) == (True, id_1)
    leo.step(0, 1)

    # Attempt to spawn a non-existing template.
    templateID += 'blah'.encode('utf8')
    assert not client.spawn(templateID, np.zeros(3)).ok

    # Exactly one object must exist at this point.
    ok, _, ret = client.getAllObjectIDs()
    assert (ok, ret) == (True, [id_1])

    # Attempt to delete a non-existing object. This must silently fail.
    ok, _, ret = client.removeObject(100)
    assert ok
    leo.step(0, 1)
    ok, _, ret = client.getAllObjectIDs()
    assert (ok, ret) == (True, [id_1])

    # Delete an existing object.
    assert client.removeObject(id_1).ok
    leo.step(0, 1)
    ok, _, ret = client.getAllObjectIDs()
    assert (ok, ret) == (True, [])

    # Shutdown the services.
    stopAzrael(clerk, clacks)
    print('Test passed')


@pytest.mark.parametrize('client_type', ['Websocket', 'ZeroMQ'])
def test_spawn_and_get_state_variables(client_type):
    """
    Spawn a new object and query its state variables.
    """
    killAzrael()

    # Constants and parameters for this test.
    templateID = '_templateNone'.encode('utf8')

    # Start the necessary services.
    clerk, client, clacks = startAzrael(client_type)

    # Query state variables for non existing object.
    id_tmp = 100
    ok, _, sv = client.getStateVariables(id_tmp)
    assert (ok, sv) == (True, {id_tmp: None})
    del id_tmp

    # Instruct Clerk to spawn a new object. Its objID must be '1'.
    ok, _, id0 = client.spawn(templateID, pos=np.ones(3), vel=-np.ones(3))
    assert (ok, id0) == (True, 1)

    ok, _, sv = client.getStateVariables(id0)
    assert (ok, len(sv)) == (True, 1)
    assert id0 in sv

    # Shutdown the services.
    stopAzrael(clerk, clacks)
    print('Test passed')


@pytest.mark.parametrize('client_type', ['Websocket', 'ZeroMQ'])
def test_setStateVariables(client_type):
    """
    Spawn an object and specify its state variables directly.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Constants and parameters for this test.
    templateID = '_templateNone'.encode('utf8')

    # Start the necessary services.
    clerk, client, clacks = startAzrael(client_type)

    # Spawn one of the default templates.
    ok, _, objID = client.spawn(templateID, pos=np.ones(3), vel=-np.ones(3))
    assert ok

    # Create and apply a new State Vector.
    new_sv = bullet_data.BulletDataOverride(
        position=[1, -1, 1], imass=2, scale=3, cshape=[4, 1, 1, 1])
    assert client.setStateVariables(objID, new_sv).ok

    # Verify that the new attributes came into effect.
    leo.step(0, 1)
    ok, _, ret_sv = client.getStateVariables(objID)
    ret_sv = ret_sv[objID]
    assert isinstance(ret_sv, bullet_data.BulletData)
    assert ret_sv.imass == new_sv.imass
    assert ret_sv.scale == new_sv.scale
    assert np.array_equal(ret_sv.position, new_sv.position)
    assert np.array_equal(ret_sv.cshape, new_sv.cshape)

    # Shutdown the services.
    stopAzrael(clerk, clacks)
    print('Test passed')


@pytest.mark.parametrize('client_type', ['Websocket', 'ZeroMQ'])
def test_getAllObjectIDs(client_type):
    """
    Ensure the getAllObjectIDs command reaches Clerk.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Start the necessary services.
    clerk, client, clacks = startAzrael(client_type)

    # Constants and parameters for this test.
    templateID = '_templateNone'.encode('utf8')

    # Parameters and constants for this test.
    objID_1 = 1

    # So far no objects have been spawned.
    ret = client.getAllObjectIDs()
    assert (ret.ok, ret.data) == (True, [])

    # Spawn a new object.
    ret = client.spawn(templateID, np.zeros(3))
    assert (ret.ok, ret.data) == (True, objID_1)

    # The object list must now contain the ID of the just spawned object.
    leo.step(0, 1)
    ret = client.getAllObjectIDs()
    assert (ret.ok, ret.data) == (True, [objID_1])

    # Shutdown the services.
    stopAzrael(clerk, clacks)
    print('Test passed')


@pytest.mark.parametrize('client_type', ['Websocket', 'ZeroMQ'])
def test_get_template(client_type):
    """
    Spawn some objects from the default templates and query their template IDs.
    """
    killAzrael()

    # Start the necessary services.
    clerk, client, clacks = startAzrael(client_type)

    # Parameters and constants for this test.
    id_1, id_2 = 1, 2
    templateID_0 = '_templateNone'.encode('utf8')
    templateID_1 = '_templateCube'.encode('utf8')

    # Spawn a new object. Its ID must be 1.
    ok, _, objID = client.spawn(templateID_0, np.zeros(3))
    assert (ok, objID) == (True, id_1)

    # Spawn another object from a different template.
    ok, _, objID = client.spawn(templateID_1, np.zeros(3))
    assert (ok, objID) == (True, id_2)

    # Retrieve template of first object.
    ok, _, ret = client.getTemplateID(id_1)
    assert (ok, ret) == (True, templateID_0)

    # Retrieve template of second object.
    ok, _, ret = client.getTemplateID(id_2)
    assert (ok, ret) == (True, templateID_1)

    # Attempt to retrieve a non-existing object.
    ok, _, ret = client.getTemplateID(100)
    assert not ok

    # Shutdown the services.
    stopAzrael(clerk, clacks)
    print('Test passed')


@pytest.mark.parametrize('client_type', ['Websocket', 'ZeroMQ'])
def test_create_fetch_template(client_type):
    """
    Add a new object to the templateID DB and query it again.
    """
    killAzrael()

    # Start the necessary services.
    clerk, client, clacks = startAzrael(client_type)

    # Request an invalid ID.
    assert not client.getTemplate('blah'.encode('utf8')).ok

    # Clerk has a few default objects. This one has no collision shape...
    ok, _, ret = client.getTemplate('_templateNone'.encode('utf8'))
    assert ok
    assert np.array_equal(ret.cs, [0, 1, 1, 1])
    assert len(ret.vert) == len(ret.boosters) == len(ret.factories) == 0

    # ... this one is a sphere...
    ok, _, ret = client.getTemplate('_templateSphere'.encode('utf8'))
    assert ok
    assert np.array_equal(ret.cs, [3, 1, 1, 1])
    assert len(ret.vert) == len(ret.boosters) == len(ret.factories) == 0

    # ... and this one is a cube.
    ok, _, ret = client.getTemplate('_templateCube'.encode('utf8'))
    assert ok
    assert np.array_equal(ret.cs, [4, 1, 1, 1])
    assert len(ret.vert) == len(ret.boosters) == len(ret.factories) == 0

    # Add a new object template.
    cs = np.array([1, 2, 3, 4], np.float64)
    vert = np.arange(9).astype(np.float64)
    uv = np.array([9, 10], np.float64)
    rgb = np.array([1, 2, 250], np.uint8)
    templateID = 't1'.encode('utf8')
    ok, _, templateID = client.addTemplate(templateID, cs, vert, uv, rgb, [], [])

    # Fetch the just added template again.
    ok, _, ret = client.getTemplate(templateID)
    assert np.array_equal(ret.cs, cs)
    assert np.array_equal(ret.vert, vert)
    assert np.array_equal(ret.uv, uv)
    assert np.array_equal(ret.rgb, rgb)
    assert len(ret.boosters) == len(ret.factories) == 0

    # Define a new object with two boosters and one factory unit.
    # The 'boosters' and 'factories' arguments are a list of named
    # tuples. Their first argument is the unit ID (Azrael does not
    # automatically assign any).
    b0 = parts.Booster(
        partID=0, pos=[0, 0, 0], direction=[0, 0, 1], max_force=0.5)
    b1 = parts.Booster(
        partID=1, pos=[0, 0, 0], direction=[0, 0, 1], max_force=0.5)
    f0 = parts.Factory(
        partID=0, pos=[0, 0, 0], direction=[0, 0, 1],
        templateID='_templateCube'.encode('utf8'), exit_speed=[0.1, 0.5])

    # Attempt to query the geometry of a non-existing object.
    assert not client.getGeometry(1).ok

    # Add the new template.
    templateID = 't2'.encode('utf8')
    ok, _, templateID = client.addTemplate(
        templateID, cs, vert, uv, rgb, [b0, b1], [f0])

    # ... and spawn an instance thereof.
    ok, _, objID = client.spawn(templateID)
    assert ok

    # Retrieve the geometry of the new object and verify it is correct.
    ok, _, (out_vert, out_uv, out_rgb) = client.getGeometry(objID)
    assert np.array_equal(vert, out_vert)
    assert np.array_equal(uv, out_uv)
    assert np.array_equal(rgb, out_rgb)
    assert out_rgb.dtype == np.uint8

    # Retrieve the entire template and verify the CS and geometry.
    ok, _, ret = client.getTemplate(templateID)
    assert np.array_equal(ret.cs, cs)
    assert np.array_equal(ret.vert, vert)
    assert np.array_equal(ret.uv, uv)
    assert np.array_equal(ret.rgb, rgb)

    # The template must also feature two boosters and one factory.
    assert len(ret.boosters) == 2
    assert len(ret.factories) == 1

    # Explicitly verify the booster- and factory units. The easiest (albeit
    # not most readable) way to do the comparison is to convert the unit
    # descriptions (which are named tuples) to byte strings and compare those.
    out_boosters = [_.tostring() for _ in ret.boosters]
    out_factories = [_.tostring() for _ in ret.factories]
    assert b0.tostring() in out_boosters
    assert b1.tostring() in out_boosters
    assert f0.tostring() in out_factories

    # Shutdown the services.
    stopAzrael(clerk, clacks)
    print('Test passed')


@pytest.mark.parametrize('client_type', ['Websocket', 'ZeroMQ'])
def test_controlParts(client_type):
    """
    Create a template with boosters and factories. Then send control commands
    to them and ensure the applied forces, torques, and spawned objects are
    correct.

    In this test the parent object moves and is oriented away from its
    default.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Start the necessary services.
    clerk, client, clacks = startAzrael(client_type)

    # Parameters and constants for this test.
    objID_1 = 1
    pos_parent = np.array([1, 2, 3], np.float64)
    vel_parent = np.array([4, 5, 6], np.float64)
    cs = np.array([1, 2, 3, 4], np.float64)
    vert = np.arange(9).astype(np.float64)
    uv = np.array([9, 10], np.float64)
    rgb = np.array([1, 2, 250], np.uint8)

    # Part positions relative to parent.
    dir_0 = np.array([0, 0, +2], np.float64)
    dir_1 = np.array([0, 0, -1], np.float64)
    pos_0 = np.array([0, 0, +3], np.float64)
    pos_1 = np.array([0, 0, -4], np.float64)

    # Describes a rotation of 180 degrees around x-axis.
    orient_parent = [1, 0, 0, 0]

    # Part position in world coordinates if the parent is rotated by 180
    # degrees around the x-axis. The normalisation of the direction is
    # necessary because the parts will automatically normalise all direction
    # vectors, including dir_0 and dir_1 which are not unit vectors.
    dir_0_out = np.array(-dir_0) / np.sum(abs(dir_0))
    dir_1_out = np.array(-dir_1) / np.sum(abs(dir_1))
    pos_0_out = np.array(-pos_0)
    pos_1_out = np.array(-pos_1)

    # State variables for parent object. This one has a position and speed, and
    # is rotate 180 degrees around the x-axis. This means the x-values of all
    # forces (boosters) and exit speeds (factory spawned objects) must be
    # inverted.
    sv = bullet_data.BulletData(
        position=pos_parent, velocityLin=vel_parent, orientation=orient_parent)

    # ------------------------------------------------------------------------
    # Create a template with two factories and spawn it.
    # ------------------------------------------------------------------------

    # Define a new object with two factory parts. The Factory parts are
    # named tuples passed to addTemplate. The user must assign the partIDs
    # manually.
    b0 = parts.Booster(
        partID=0, pos=pos_0, direction=dir_0, max_force=0.5)
    b1 = parts.Booster(
        partID=1, pos=pos_1, direction=dir_1, max_force=1.0)
    f0 = parts.Factory(
        partID=0, pos=pos_0, direction=dir_0,
        templateID='_templateCube'.encode('utf8'), exit_speed=[0.1, 0.5])
    f1 = parts.Factory(
        partID=1, pos=pos_1, direction=dir_1,
        templateID='_templateSphere'.encode('utf8'), exit_speed=[1, 5])

    # Add the template to Azrael...
    templateID_2 = 't1'.encode('utf8')
    ret = client.addTemplate(templateID_2, cs, vert, uv, rgb, [b0, b1], [f0, f1])
    assert ret.ok

    # ... and spawn an instance thereof.
    ok, _, objID = client.spawn(templateID_2, pos=pos_parent,
                           vel=vel_parent, orient=orient_parent)
    assert (ok, objID) == (True, objID_1)
    del ok, objID
    leo.step(0, 1)

    # ------------------------------------------------------------------------
    # Activate booster and factories and verify that the applied force and
    # torque is correct, as well as that the spawned objects have the correct
    # state variables attached to them.
    # ------------------------------------------------------------------------

    # Create the commands to let each factory spawn an object.
    exit_speed_0, exit_speed_1 = 0.2, 2
    forcemag_0, forcemag_1 = 0.2, 0.4
    cmd_0 = parts.CmdBooster(partID=0, force=forcemag_0)
    cmd_1 = parts.CmdBooster(partID=1, force=forcemag_1)
    cmd_2 = parts.CmdFactory(partID=0, exit_speed=exit_speed_0)
    cmd_3 = parts.CmdFactory(partID=1, exit_speed=exit_speed_1)

    # Send the commands and ascertain that the returned object IDs now exist in
    # the simulation. These IDs must be '2' and '3'.
    ok, _, spawnIDs = client.controlParts(objID_1, [cmd_0, cmd_1], [cmd_2, cmd_3])
    assert (ok, len(spawnIDs)) == (True, 2)
    assert spawnIDs == [2, 3]
    leo.step(0, 1)

    # Query the state variables of the objects spawned by the factories.
    ok, _, ret_SVs = client.getStateVariables(spawnIDs)
    assert (ok, len(ret_SVs)) == (True, 2)

    # Verify the position and velocity of the spawned objects is correct.
    sv_2, sv_3 = [ret_SVs[_] for _ in spawnIDs]
    assert np.allclose(sv_2.velocityLin, exit_speed_0 * dir_0_out + vel_parent)
    assert np.allclose(sv_2.position, pos_0_out + pos_parent)
    assert np.allclose(sv_3.velocityLin, exit_speed_1 * dir_1_out + vel_parent)
    assert np.allclose(sv_3.position, pos_1_out + pos_parent)

    # Manually compute the total force and torque exerted by the boosters.
    forcevec_0, forcevec_1 = forcemag_0 * dir_0_out, forcemag_1 * dir_1_out
    tot_force = forcevec_0 + forcevec_1
    tot_torque = (np.cross(pos_0_out, forcevec_0) +
                  np.cross(pos_1_out, forcevec_1))

    # Query the torque and force from Azrael and verify they are correct.
    ret = physAPI.getForceAndTorque(objID_1)
    assert ret.ok
    assert np.array_equal(ret.data['force'], tot_force)
    assert np.array_equal(ret.data['torque'], tot_torque)

    # Shutdown the services.
    stopAzrael(clerk, clacks)
    print('Test passed')


@pytest.mark.parametrize('client_type', ['Websocket', 'ZeroMQ'])
def test_updateGeometry(client_type):
    """
    Spawn a new object and modify its geometry at runtime.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Convenience.
    cs = np.array([1, 2, 3, 4], np.float64)
    vert = np.arange(9).astype(np.float64)
    uv = np.array([9, 10], np.float64)
    rgb = np.array([1, 2, 250], np.uint8)
    templateID = 't1'.encode('utf8')

    # Start the necessary services.
    clerk, client, clacks = startAzrael(client_type)

    # Add a new template and spawn it.
    ok, _, templateID = client.addTemplate(templateID, cs, vert, uv, rgb, [], [])
    assert ok
    ok, _, objID = client.spawn(templateID, pos=np.ones(3), vel=-np.ones(3))
    assert ok

    # Query the SV to obtain the geometry checksum value.
    leo.step(0, 1)
    ok, _, sv = client.getStateVariables(objID)
    assert ok
    checksumGeometry = sv[objID].checksumGeometry

    # Fetch-, modify-, update- and verify the geometry.
    ok, _, (ret_vert, ret_uv, ret_rgb) = client.getGeometry(objID)
    assert ok
    assert np.allclose(uv, ret_uv)
    assert np.allclose(vert, ret_vert)

    assert client.updateGeometry(objID, 2 * ret_vert, 2 * ret_uv, 2 * ret_rgb).ok

    ok, _, (ret_vert, ret_uv, ret_rgb) = client.getGeometry(objID)
    assert ok
    assert np.allclose(2 * vert, ret_vert) and np.allclose(2 * uv, ret_uv)

    # Ensure the geometry checksum is different as well.
    ok, _, sv = client.getStateVariables(objID)
    assert ok
    assert sv[objID].checksumGeometry != checksumGeometry

    # Shutdown the services.
    stopAzrael(clerk, clacks)
    print('Test passed')


if __name__ == '__main__':
    _transport_type = 'Websocket'
#    _transport_type = 'ZeroMQ'

    test_setStateVariables(_transport_type)
    test_updateGeometry(_transport_type)
    test_spawn_and_delete_one_client(_transport_type)
    test_spawn_and_get_state_variables(_transport_type)
    test_ping()
    test_get_template(_transport_type)
    test_controlParts(_transport_type)
    test_getAllObjectIDs(_transport_type)
    test_create_fetch_template(_transport_type)