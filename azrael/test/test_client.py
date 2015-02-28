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

import azrael.util
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
Template = azrael.util.Template


def test_ping():
    """
    Send a ping to the Clerk and check the response is correct.
    """
    killAzrael()

    # Start the necessary services.
    clerk, client, clacks = startAzrael('ZeroMQ')

    ret = client.ping()
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
    templateID = '_templateNone'

    # Start the necessary services.
    clerk, client, clacks = startAzrael(client_type)

    # Spawn a new object from templateID. The new object must have objID=1.
    new_obj = {'template': templateID,
               'position': np.zeros(3)}
    ret = client.spawn([new_obj])
    assert ret.ok and ret.data == (id_1, )
    leo.processCommandsAndSync()

    # Attempt to spawn a non-existing template.
    new_obj = {'template': 'blah',
               'position': np.zeros(3)}
    assert not client.spawn([new_obj]).ok

    # Exactly one object must exist at this point.
    ret = client.getAllObjectIDs()
    assert (ret.ok, ret.data) == (True, [id_1])

    # Attempt to delete a non-existing object. This must silently fail.
    assert client.removeObject(100).ok
    leo.processCommandsAndSync()
    ret = client.getAllObjectIDs()
    assert (ret.ok, ret.data) == (True, [id_1])

    # Delete an existing object.
    assert client.removeObject(id_1).ok
    leo.processCommandsAndSync()
    ret = client.getAllObjectIDs()
    assert (ret.ok, ret.data) == (True, [])

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
    templateID = '_templateNone'
    id_1 = 1

    # Start the necessary services.
    clerk, client, clacks = startAzrael(client_type)

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Query the state variable for a non existing object.
    id_tmp = 100
    ok, _, sv = client.getAllStateVariables()
    assert (ok, sv) == (True, {})

    ok, _, sv = client.getStateVariables(id_tmp)
    assert (ok, sv) == (True, {id_tmp: None})
    del id_tmp

    # Instruct Clerk to spawn a new object. Its objID must be '1'.
    new_obj = {'template': templateID,
               'position': np.zeros(3),
               'velocityLin': -np.ones(3)}
    ret = client.spawn([new_obj])
    assert ret.ok and ret.data == (id_1, )

    # The new object has not yet been picked up by Leonard --> its state
    # vector must thus be None.
    ret = client.getStateVariables(id_1)
    assert ret.ok and (len(ret.data) == 1) and (ret.data == {id_1: None})

    # getAllStateVarialbes must return an empty dictionary.
    ret = client.getAllStateVariables()
    assert ret.ok and (ret.data == {})

    # Run one Leonard step. This will pick up the newly spawned object and SV
    # queries must now return valid data.
    leo.processCommandsAndSync()
    ret = client.getStateVariables(id_1)
    assert ret.ok and (len(ret.data) == 1) and (id_1 in ret.data)
    assert ret.data[id_1] is not None

    ret = client.getAllStateVariables()
    assert ret.ok and (len(ret.data) == 1) and (id_1 in ret.data)
    assert ret.data[id_1] is not None

    # Shutdown the services.
    stopAzrael(clerk, clacks)
    print('Test passed')


@pytest.mark.parametrize('client_type', ['Websocket', 'ZeroMQ'])
def test_setStateVariable(client_type):
    """
    Spawn an object and specify its state variables directly.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Constants and parameters for this test.
    templateID = '_templateNone'
    objID = 1

    # Start the necessary services.
    clerk, client, clacks = startAzrael(client_type)

    # Spawn one of the default templates.
    new_obj = {'template': templateID,
               'position': np.ones(3),
               'velocityLin': -np.ones(3)}
    ret = client.spawn([new_obj])
    assert ret.ok and (ret.data == (objID, ))

    # Verify that the State Vector is correct.
    leo.processCommandsAndSync()
    ok, _, ret_sv = client.getStateVariables(objID)
    ret_sv = ret_sv[objID]
    assert isinstance(ret_sv, bullet_data._BulletData)
    assert np.array_equal(ret_sv.position, new_obj['position'])
    assert np.array_equal(ret_sv.velocityLin, new_obj['velocityLin'])

    # Create and apply a new State Vector.
    new_sv = bullet_data.BulletDataOverride(
        position=[1, -1, 1], imass=2, scale=3, cshape=[4, 1, 1, 1])
    assert client.setStateVariable(objID, new_sv).ok

    # Verify that the new attributes came into effect.
    leo.processCommandsAndSync()
    ok, _, ret_sv = client.getStateVariables(objID)
    ret_sv = ret_sv[objID]
    assert isinstance(ret_sv, bullet_data._BulletData)
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
    templateID = '_templateNone'

    # Parameters and constants for this test.
    id_1 = 1

    # So far no objects have been spawned.
    ret = client.getAllObjectIDs()
    assert (ret.ok, ret.data) == (True, [])

    # Spawn a new object.
    new_obj = {'template': templateID,
               'position': np.zeros(3)}
    ret = client.spawn([new_obj])
    assert ret.ok and ret.data == (id_1, )

    # The object list must now contain the ID of the just spawned object.
    leo.processCommandsAndSync()
    ret = client.getAllObjectIDs()
    assert (ret.ok, ret.data) == (True, [id_1])

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
    templateID_0 = '_templateNone'
    templateID_1 = '_templateCube'

    # Spawn a new object. Its ID must be 1.
    new_objs = [{'template': templateID_0, 'position': np.zeros(3)},
                {'template': templateID_1, 'position': np.zeros(3)}]
    ret = client.spawn(new_objs)
    assert ret.ok and ret.data == (id_1, id_2)

    # Retrieve template of first object.
    ret = client.getTemplateID(id_1)
    assert ret.ok and (ret.data == templateID_0)

    # Retrieve template of second object.
    ret = client.getTemplateID(id_2)
    assert ret.ok and (ret.data == templateID_1)

    # Attempt to retrieve a non-existing object.
    assert not client.getTemplateID(100).ok

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
    assert not client.getTemplates(['blah']).ok

    # Clerk has a few default objects. This one has no collision shape...
    name_1 = '_templateNone'
    ret = client.getTemplates([name_1])
    assert ret.ok and (len(ret.data) == 1) and (name_1 in ret.data)
    assert np.array_equal(ret.data[name_1].cs, np.array([0, 1, 1, 1]))

    # ... this one is a sphere...
    name_2 = '_templateSphere'
    ret = client.getTemplates([name_2])
    assert ret.ok and (len(ret.data) == 1) and (name_2 in ret.data)
    assert np.array_equal(ret.data[name_2].cs, np.array([3, 1, 1, 1]))

    # ... and this one is a cube.
    name_3 = '_templateCube'
    ret = client.getTemplates([name_3])
    assert ret.ok and (len(ret.data) == 1) and (name_3 in ret.data)
    assert np.array_equal(ret.data[name_3].cs, np.array([4, 1, 1, 1]))

    # Retrieve all three again but with a single call.
    ret = client.getTemplates([name_1, name_2, name_3])
    assert ret.ok
    assert set(ret.data.keys()) == set((name_1, name_2, name_3))
    assert np.array_equal(ret.data[name_1].cs, np.array([0, 1, 1, 1]))
    assert np.array_equal(ret.data[name_2].cs, np.array([3, 1, 1, 1]))
    assert np.array_equal(ret.data[name_3].cs, np.array([4, 1, 1, 1]))

    # Add a new object template.
    cs = np.array([1, 2, 3, 4], np.float64)
    vert = np.arange(9).astype(np.float64)
    uv = np.array([9, 10], np.float64)
    rgb = np.array([1, 2, 250], np.uint8)
    t1 = Template('t1', cs, vert, uv, rgb, [], [])
    assert client.addTemplates([t1]).ok

    # Fetch the just added template again.
    ret = client.getTemplates([t1.name])
    assert ret.ok and (len(ret.data) == 1)
    ret = ret.data[t1.name]
    assert np.array_equal(ret.cs, cs)
    assert np.array_equal(ret.vert, vert)
    assert np.array_equal(ret.uv, uv)
    assert np.array_equal(ret.rgb, rgb)
    assert len(ret.boosters) == len(ret.factories) == 0

    # Define a new object with two boosters and one factory unit.
    # The 'boosters' and 'factories' arguments are a list of named
    # tuples. Their first argument is the unit ID (Azrael does not
    # automatically assign any).
    b0 = parts.Booster(partID=0, pos=[0, 0, 0], direction=[0, 0, 1],
                       minval=0, maxval=0.5, force=0)
    b1 = parts.Booster(partID=1, pos=[0, 0, 0], direction=[0, 0, 1],
                       minval=0, maxval=0.5, force=0)
    f0 = parts.Factory(
        partID=0, pos=[0, 0, 0], direction=[0, 0, 1],
        templateID='_templateCube', exit_speed=[0.1, 0.5])

    # Attempt to query the geometry of a non-existing object.
    assert not client.getGeometry(1).ok

    # Add the new template.
    t1 = Template('t2', cs, vert, uv, rgb, [b0, b1], [f0])
    assert client.addTemplates([t1]).ok

    # ... and spawn an instance thereof.
    new_obj = {'template': t1.name,
               'position': np.zeros(3)}
    ret = client.spawn([new_obj])
    assert ret.ok and len(ret.data) == 1
    objID = ret.data[0]

    # Retrieve the geometry of the new object and verify it is correct.
    ok, _, (out_vert, out_uv, out_rgb) = client.getGeometry(objID)
    assert np.array_equal(vert, out_vert)
    assert np.array_equal(uv, out_uv)
    assert np.array_equal(rgb, out_rgb)
    assert out_rgb.dtype == np.uint8

    # Retrieve the entire template and verify the CS and geometry.
    ret = client.getTemplates([t1.name])
    assert ret.ok and (len(ret.data) == 1)
    ret = ret.data[t1.name]
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
    out_boosters = [parts.Booster(*_) for _ in ret.boosters]
    out_factories = [parts.Factory(*_) for _ in ret.factories]
    assert b0 in out_boosters
    assert b1 in out_boosters
    assert f0 in out_factories

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
    id_1 = 1
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
    # named tuples passed to addTemplates. The user must assign the partIDs
    # manually.
    b0 = parts.Booster(partID=0, pos=pos_0, direction=dir_0,
                       minval=0, maxval=0.5, force=0)
    b1 = parts.Booster(partID=1, pos=pos_1, direction=dir_1,
                       minval=0, maxval=1.0, force=0)
    f0 = parts.Factory(
        partID=0, pos=pos_0, direction=dir_0,
        templateID='_templateCube', exit_speed=[0.1, 0.5])
    f1 = parts.Factory(
        partID=1, pos=pos_1, direction=dir_1,
        templateID='_templateSphere', exit_speed=[1, 5])

    # Add the template to Azrael...
    t2 = Template('t1', cs, vert, uv, rgb, [b0, b1], [f0, f1])
    assert client.addTemplates([t2]).ok

    # ... and spawn an instance thereof.
    new_obj = {'template': t2.name,
               'position': pos_parent,
               'velocityLin': vel_parent,
               'orientation': orient_parent}
    ret = client.spawn([new_obj])
    assert ret.ok and (ret.data == (id_1, ))
    leo.processCommandsAndSync()

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
    ret = client.controlParts(id_1, [cmd_0, cmd_1], [cmd_2, cmd_3])
    spawnIDs = ret.data
    assert (ret.ok, len(spawnIDs)) == (True, 2)
    assert spawnIDs == [2, 3]
    leo.processCommandsAndSync()

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
    leo_force, leo_torque = leo.totalForceAndTorque(id_1)
    assert np.array_equal(leo_force, tot_force)
    assert np.array_equal(leo_torque, tot_torque)

    # Shutdown the services.
    stopAzrael(clerk, clacks)
    print('Test passed')


@pytest.mark.parametrize('client_type', ['Websocket', 'ZeroMQ'])
def test_setGeometry(client_type):
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
    objID = 1

    # Start the necessary services.
    clerk, client, clacks = startAzrael(client_type)

    # Add a new template and spawn it.
    t1 = Template('t1', cs, vert, uv, rgb, [], [])
    assert client.addTemplates([t1]).ok

    new_obj = {'template': t1.name,
               'position': np.ones(3),
               'velocityLin': -np.ones(3)}
    ret = client.spawn([new_obj])
    assert ret.ok and ret.data == (objID, )

    # Query the SV to obtain the 'lastChanged' value.
    leo.processCommandsAndSync()
    ret = client.getStateVariables(objID)
    assert ret.ok
    lastChanged = ret.data[objID].lastChanged

    # Fetch-, modify-, update- and verify the geometry.
    ok, _, (ret_vert, ret_uv, ret_rgb) = client.getGeometry(objID)
    assert ok
    assert np.allclose(uv, ret_uv)
    assert np.allclose(vert, ret_vert)

    ret = client.setGeometry(objID, 2 * ret_vert, 2 * ret_uv, 2 * ret_rgb)
    assert ret.ok

    ok, _, (ret_vert, ret_uv, ret_rgb) = client.getGeometry(objID)
    assert ok
    assert np.allclose(2 * vert, ret_vert) and np.allclose(2 * uv, ret_uv)

    # Ensure 'lastChanged' is different as well.
    ret = client.getStateVariables(objID)
    assert ret.ok and (ret.data[objID].lastChanged != lastChanged)

    # Shutdown the services.
    stopAzrael(clerk, clacks)
    print('Test passed')


if __name__ == '__main__':
    for _transport_type in ('ZeroMQ', 'Websocket'):
        test_setStateVariable(_transport_type)
        test_setGeometry(_transport_type)
        test_spawn_and_delete_one_client(_transport_type)
        test_spawn_and_get_state_variables(_transport_type)
        test_ping()
        test_get_template(_transport_type)
        test_controlParts(_transport_type)
        test_getAllObjectIDs(_transport_type)
        test_create_fetch_template(_transport_type)
