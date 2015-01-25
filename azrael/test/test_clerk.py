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
Test the Clerk only. Use a modified Client to this end which allows to send
raw bytestrings to bypass all convenience wrappers that the Client class
offers and test purely the Clerk.
"""

import sys
import pytest
import IPython
import numpy as np

import azrael.util
import azrael.clerk
import azrael.client
import azrael.parts as parts
import azrael.protocol_json as json
import azrael.physics_interface as physAPI
import azrael.bullet.bullet_data as bullet_data

from azrael.test.test_clacks import startAzrael, stopAzrael
from azrael.test.test_leonard import getLeonard, killAzrael
from azrael.bullet.test_boost_bullet import isEqualBD


ipshell = IPython.embed
Template = azrael.util.Template


class ClientTest(azrael.client.Client):
    def testSend(self, data):
        """
        Pass data verbatim to Clerk.

        For testing only.

        This method allows to test Clerk's ability to handle corrupt and
        invalid commands. Otherwise the codecs would probably pick up many
        errors and never pass on the request to Clerk.
        """
        self.sock_cmd.send(data)
        data = self.sock_cmd.recv()
        data = json.loads(data.decode('utf8'))
        return data['ok'], data['payload']


def test_invalid():
    """
    Send an invalid command to Clerk.
    """
    killAzrael()

    # Start Clerk and instantiate a Client.
    clerk = azrael.clerk.Clerk()
    clerk.start()
    client = ClientTest()

    # Send a corrupt JSON to Clerk.
    msg = 'invalid_cmd'
    ret = client.testSend(msg.encode('utf8'))
    assert ret == (False, 'JSON decoding error in Clerk')

    # Send a malformatted JSON (it misses the 'payload' field).
    msg = json.dumps({'cmd': 'blah'})
    ok, ret = client.testSend(msg.encode('utf8'))
    assert (ok, ret) == (False, 'Invalid command format')

    # Send an invalid command.
    msg = json.dumps({'cmd': 'blah', 'payload': ''})
    ok, ret = client.testSend(msg.encode('utf8'))
    assert (ok, ret) == (False, 'Invalid command <blah>')

    # Terminate the Clerk.
    clerk.terminate()
    clerk.join()

    killAzrael()
    print('Test passed')


def test_ping():
    """
    Send a ping to the Clerk and check the response is correct.
    """
    # Start the necessary services and instantiate a Client.
    clerk, client, clacks = startAzrael('ZeroMQ')

    # Send the Ping command.
    ret = client.ping()
    assert (ret.ok, ret.data) == (True, 'pong clerk')

    # Shutdown the services.
    stopAzrael(clerk, clacks)
    print('Test passed')


def test_spawn():
    """
    Test the 'spawn' command in the Clerk.
    """
    killAzrael()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk()

    # Default object.
    sv = bullet_data.BulletData()

    # Invalid templateID.
    templateID = np.int64(100).tostring()
    ret = clerk.spawn(templateID, sv)
    assert not ret.ok
    assert ret.msg.startswith('Not all template IDs were valid')

    # All parameters are now valid. This must spawn an object with ID=1
    # because this is the first ID in an otherwise pristine system.
    templateID = '_templateNone'.encode('utf8')
    ret = clerk.spawn(templateID, sv)
    assert (ret.ok, ret.data) == (True, 1)

    print('Test passed')


def test_delete():
    """
    Test the 'removeObject' command in the Clerk.

    Spawn an object and ensure it exists, then delete it and ensure it does not
    exist anymore.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Test constants and parameters.
    objID_1, objID_2 = 1, 2

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk()

    # No objects must exist at this point.
    ret = clerk.getAllObjectIDs()
    assert (ret.ok, ret.data) == (True, [])

    # Spawn two default objects.
    sv = bullet_data.BulletData()
    templateID = '_templateNone'.encode('utf8')
    ret = clerk.spawn(templateID, sv)
    assert (ret.ok, ret.data) == (True, objID_1)
    ret = clerk.spawn(templateID, sv)
    assert (ret.ok, ret.data) == (True, objID_2)

    # Two objects must now exist.
    leo.processCommandsAndSync()
    ret = clerk.getAllObjectIDs()
    assert ret.ok and (set(ret.data) == set([objID_1, objID_2]))

    # Delete the first object.
    assert clerk.removeObject(objID_1).ok

    # Only the second object must still exist.
    leo.processCommandsAndSync()
    ret = clerk.getAllObjectIDs()
    assert (ret.ok, ret.data) == (True, [objID_2])

    # Deleting the same object again must silently fail.
    assert clerk.removeObject(objID_1).ok

    # Delete the second object.
    assert clerk.removeObject(objID_2).ok
    leo.processCommandsAndSync()
    ret = clerk.getAllObjectIDs()
    assert (ret.ok, ret.data) == (True, [])

    print('Test passed')


def test_get_statevar():
    """
    Test the 'get_statevar' command in the Clerk.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Test parameters and constants.
    objID_1 = 1
    objID_2 = 2
    sv_1 = bullet_data.BulletData(position=np.arange(3), velocityLin=[2, 4, 6])
    sv_2 = bullet_data.BulletData(position=[2, 4, 6], velocityLin=[6, 8, 10])
    templateID = '_templateNone'.encode('utf8')

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk()

    # Retrieve the SV for a non-existing ID.
    ret = clerk.getStateVariables([10])
    assert (ret.ok, ret.data) == (True, {10: None})

    # Spawn a new object. It must have ID=1.
    ret = clerk.spawn(templateID, sv_1)
    assert (ret.ok, ret.data) == (True, objID_1)

    # Retrieve the SV for a non-existing ID --> must fail.
    leo.processCommandsAndSync()
    ret = clerk.getStateVariables([10])
    assert (ret.ok, ret.data) == (True, {10: None})

    # Retrieve the SV for the existing ID=1.
    ret = clerk.getStateVariables([objID_1])
    assert (ret.ok, len(ret.data)) == (True, 1)
    assert isEqualBD(ret.data[objID_1], sv_1)

    # Spawn a second object.
    ret = clerk.spawn(templateID, sv_2)
    assert (ret.ok, ret.data) == (True, objID_2)

    # Retrieve the state variables for both objects individually.
    leo.processCommandsAndSync()
    for objID, ref_sv in zip([objID_1, objID_2], [sv_1, sv_2]):
        ret = clerk.getStateVariables([objID])
        assert (ret.ok, len(ret.data)) == (True, 1)
        assert isEqualBD(ret.data[objID], ref_sv)

    # Retrieve the state variables for both objects at once.
    ret = clerk.getStateVariables([objID_1, objID_2])
    assert (ret.ok, len(ret.data)) == (True, 2)
    assert isEqualBD(ret.data[objID_1], sv_1)
    assert isEqualBD(ret.data[objID_2], sv_2)

    print('Test passed')


def test_set_force():
    """
    Set and retrieve force and torque values.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Parameters and constants for this test.
    id_1 = 1
    sv = bullet_data.BulletData()
    force = np.array([1, 2, 3], np.float64).tolist()
    relpos = np.array([4, 5, 6], np.float64).tolist()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk()

    # Spawn a new object. It must have ID=1.
    templateID = '_templateNone'.encode('utf8')
    ret = clerk.spawn(templateID, sv)
    assert (ret.ok, ret.data) == (True, id_1)

    # Apply the force.
    assert clerk.setForce(id_1, force, relpos).ok

    leo.processCommandsAndSync()
    assert np.array_equal(leo.allForces[id_1], force)
    assert np.array_equal(leo.allTorques[id_1], np.cross(relpos, force))

    print('Test passed')


def test_add_get_template_single():
    """
    Add a new object to the templateID DB and query it again.
    """
    killAzrael()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk()

    # Request an invalid ID.
    assert not clerk.getTemplate('blah'.encode('utf8')).ok

    # Clerk has a few default objects. This one has no collision shape...
    ret = clerk.getTemplate('_templateNone'.encode('utf8'))
    assert ret.ok
    assert np.array_equal(ret.data['cshape'], np.array([0, 1, 1, 1]))

    # ... this one is a sphere...
    ret = clerk.getTemplate('_templateSphere'.encode('utf8'))
    assert ret.ok
    assert np.array_equal(ret.data['cshape'], np.array([3, 1, 1, 1]))

    # ... and this one is a cube.
    ret = clerk.getTemplate('_templateCube'.encode('utf8'))
    assert ret.ok
    assert np.array_equal(ret.data['cshape'], np.array([4, 1, 1, 1]))

    # Convenience.
    cs = np.array([1, 2, 3, 4], np.float64)
    vert = list(range(9))
    uv = [9, 10]
    rgb = [1, 2, 250]

    # Wrong argument .
    t1 = Template('t1'.encode('utf8'), cs, vert[:-1], uv, rgb, [], [])
    ret = clerk.addTemplates([1])
    assert not ret.ok
    assert ret.msg == 'Invalid arguments'

    # Attempt to add a template where the number of vertices is not a multiple
    # of 9. This must fail.
    ret = clerk.addTemplates([t1])
    assert not ret.ok
    assert ret.msg == 'Number of vertices must be a multiple of Nine'

    # Add a valid template. This must succeed.
    t1 = Template('t1'.encode('utf8'), cs, vert, uv, rgb, [], [])
    assert clerk.addTemplates([t1]).ok

    # Attempt to add another template with the same name. This must fail.
    t2 = Template('t1'.encode('utf8'), 2 * cs, 2 * vert, uv, rgb, [], [])
    assert not clerk.addTemplates([t2]).ok

    # Fetch the just added template and verify its parameters have not changed.
    ret = clerk.getTemplate(t2.name)
    assert ret.ok
    assert np.array_equal(ret.data['cshape'], cs)
    assert np.array_equal(ret.data['vert'], vert)
    assert np.array_equal(ret.data['uv'], uv)
    assert np.array_equal(ret.data['rgb'], rgb)

    # Define a new object with two boosters and one factory unit.
    # The 'boosters' and 'factories' arguments are a list of named
    # tuples. Their first argument is the unit ID (Azrael does not assign
    # automatically assign any IDs).
    z = np.zeros(3)
    b0 = parts.Booster(
        partID=0, pos=z, direction=[0, 0, 1], max_force=0.5)
    b1 = parts.Booster(
        partID=1, pos=z, direction=[0, 0, 1], max_force=0.5)
    f0 = parts.Factory(
        partID=0, pos=z, direction=[0, 0, 1],
        templateID='_templateCube'.encode('utf8'), exit_speed=[0.1, 0.5])
    del z

    # Add the new template.
    t3 = Template('t3'.encode('utf8'), cs, vert, uv, rgb, [b0, b1], [f0])
    assert clerk.addTemplates([t3]).ok

    # Retrieve the just created object and verify the CS and geometry.
    ret = clerk.getTemplate(t3.name)
    assert ret.ok
    assert np.array_equal(ret.data['cshape'], cs)
    assert np.array_equal(ret.data['vert'], vert)
    assert np.array_equal(ret.data['uv'], uv)
    assert np.array_equal(ret.data['rgb'], rgb)

    # The template must also feature two boosters and one factory.
    assert len(ret.data['boosters']) == 2
    assert len(ret.data['factories']) == 1

    # Explicitly verify the booster- and factory units. The easisest (albeit
    # not most readable) way to do the comparison is to convert the unit
    # descriptions (which are named tuples) to byte strings and compare those.
    out_boosters = [_.tostring() for _ in ret.data['boosters']]
    out_factories = [_.tostring() for _ in ret.data['factories']]
    assert b0.tostring() in out_boosters
    assert b1.tostring() in out_boosters
    assert f0.tostring() in out_factories

    print('Test passed')


def test_add_get_template_multi():
    """
    Add templates in bulk.
    """
    killAzrael()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk()

    # Convenience.
    cs = np.array([1, 2, 3, 4], np.float64)
    vert = list(range(9))
    uv = [9, 10]
    rgb = [1, 2, 250]
    name1 = 't1'.encode('utf8')
    name2 = 't2'.encode('utf8')

    # Add valid template. This must succeed.
    t1 = Template(name1, cs, vert, uv, rgb, [], [])
    t2 = Template(name2, 2 * cs, 2 * vert, uv, rgb, [], [])

    assert clerk.addTemplates([t1, t2]).ok

    # Attempt to add another template with the same name. This must fail.
    assert not clerk.addTemplates([t1, t2]).ok

    # Fetch the just added template again and verify CS, vertices, UV, and RGB.
    ret = clerk.getTemplate(name1)
    assert ret.ok
    assert np.array_equal(ret.data['cshape'], t1.cs)
    assert np.array_equal(ret.data['vert'], t1.vert)
    assert np.array_equal(ret.data['uv'], t1.uv)
    assert np.array_equal(ret.data['rgb'], t1.rgb)

    ret = clerk.getTemplate(name2)
    assert ret.ok
    assert np.array_equal(ret.data['cshape'], t2.cs)
    assert np.array_equal(ret.data['vert'], t2.vert)
    assert np.array_equal(ret.data['uv'], t2.uv)
    assert np.array_equal(ret.data['rgb'], t2.rgb)

    print('Test passed')


def test_add_get_template_AABB():
    """
    Similarly to test_add_get_template but focuses exclusively on the AABB.
    """
    killAzrael()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk()

    # Convenience.
    cs = np.array([1, 2, 3, 4], np.float64)
    uv = rgb = []

    # Manually specify the vertices.
    vert = [-4, 0, 0,
            1, 2, 3,
            4, 5, 6]
    max_sidelen = max(8, 5, 6)

    # Add template and retrieve it again.
    t1 = Template('t1'.encode('utf8'), cs, vert, uv, rgb, [], [])
    assert clerk.addTemplates([t1]).ok
    ret = clerk.getTemplate(t1.name)
    assert ret.ok

    # The largest AABB side length must be roughly "sqrt(3) * max_sidelen".
    assert (ret.data['aabb'] - np.sqrt(3.1) * max_sidelen) < 1E-10

    # Repeat the experiment with a larger mesh.
    vert = [0, 0, 0,
            1, 2, 3,
            4, 5, 6,
            8, 2, 7,
           -5, -9, 8,
            3, 2, 3]
    max_sidelen = max(8, 14, 8)

    # Add template and retrieve it again.
    t2 = Template('t2'.encode('utf8'), cs, vert, uv, rgb, [], [])
    assert clerk.addTemplates([t2]).ok
    ret = clerk.getTemplate(t2.name)
    assert ret.ok

    # The largest AABB side length must be roughly "sqrt(3) * max_sidelen".
    assert (ret.data['aabb'] - np.sqrt(3.1) * max_sidelen) < 1E-10

    print('Test passed')


def test_get_object_template_id():
    """
    Spawn two objects from different templates. Then query the template ID
    based on the object ID.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Parameters and constants for this test.
    id_0, id_1 = 1, 2
    templateID_0 = '_templateNone'.encode('utf8')
    templateID_1 = '_templateCube'.encode('utf8')
    sv = bullet_data.BulletData()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk()

    # Spawn a new object. It must have ID=1.
    ret = clerk.spawn(templateID_0, sv)
    assert (ret.ok, ret.data) == (True, id_0)

    # Spawn another object from a different template.
    ret = clerk.spawn(templateID_1, sv)
    assert (ret.ok, ret.data) == (True, id_1)

    # Retrieve template of first object.
    leo.step(0, 10)
    ret = clerk.getTemplateID(id_0)
    assert (ret.ok, ret.data) == (True, templateID_0)

    # Retrieve template of second object.
    ret = clerk.getTemplateID(id_1)
    assert (ret.ok, ret.data) == (True, templateID_1)

    # Attempt to retrieve a non-existing object.
    assert not clerk.getTemplateID(100).ok

    # Shutdown.
    killAzrael()
    print('Test passed')


def test_controlParts_invalid_commands():
    """
    Send invalid control commands to object.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Parameters and constants for this test.
    objID_1, objID_2 = 1, 2
    templateID_1 = '_templateNone'.encode('utf8')
    sv = bullet_data.BulletData()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk()

    # Create a fake object. We will not need the actual object but other
    # commands tested here depend on the existence of an object.
    ret = clerk.spawn(templateID_1, sv)
    assert (ret.ok, ret.data) == (True, objID_1)

    # Create commands for a Booster and a Factory.
    cmd_b = parts.CmdBooster(partID=0, force=0.2)
    cmd_f = parts.CmdFactory(partID=0, exit_speed=0.5)

    # Call 'controlParts'. This must fail because the chosen template has no
    # boosters or factory units.
    leo.processCommandsAndSync()
    assert not clerk.controlParts(objID_1, [cmd_b], []).ok

    # Must fail: objects has no factory.
    assert not clerk.controlParts(objID_1, [], [cmd_f]).ok

    # Must fail: objects still has neither a booster nor a factory.
    assert not clerk.controlParts(objID_1, [cmd_b], [cmd_f]).ok

    # Must fail: Factory command where a Booster is expected and vice versa.
    assert not clerk.controlParts(objID_1, [cmd_f], [cmd_b]).ok

    # Must fail: Booster command among Factory commands.
    assert not clerk.controlParts(objID_1, [], [cmd_f, cmd_b]).ok

    # ------------------------------------------------------------------------
    # Create a template with a booster and a factory. Then send invalid
    # commands to them.
    # ------------------------------------------------------------------------

    # Define a new object with two factory parts. The Factory parts are
    # named tuples passed to addTemplate. The user must assign the partIDs
    # manually.
    b0 = parts.Booster(
        partID=0, pos=[0, 0, 0], direction=[0, 0, 1], max_force=0.5)
    f0 = parts.Factory(
        partID=0, pos=[0, 0, 0], direction=[0, 0, 1],
        templateID='_templateCube'.encode('utf8'), exit_speed=[0, 1])

    # Add the template to Azrael...
    cs = np.array([1, 2, 3, 4], np.float64)
    vert = list(range(9))
    uv = [9, 10]
    rgb = [1, 2, 250]
    t2 = Template('t1'.encode('utf8'), cs, vert, uv, rgb, [b0], [f0])
    assert clerk.addTemplates([t2]).ok

    # ... and spawn an instance thereof.
    sv = bullet_data.BulletData()
    ret = clerk.spawn(t2.name, sv)
    assert (ret.ok, ret.data) == (True, objID_2)
    leo.processCommandsAndSync()

    # Create the commands to let each factory spawn an object.
    cmd_b = parts.CmdBooster(partID=0, force=0.5)
    cmd_f = parts.CmdFactory(partID=0, exit_speed=0.5)

    # Valid commands: simply verify the new template works correctly.
    assert clerk.controlParts(objID_2, [cmd_b], [cmd_f]).ok

    # Must fail: Booster where Factory is expected and vice versa.
    assert not clerk.controlParts(objID_2, [cmd_f], [cmd_b]).ok

    # Must fail: every part can only receive one command per call.
    assert not clerk.controlParts(objID_2, [cmd_b, cmd_b], []).ok
    assert not clerk.controlParts(objID_2, [], [cmd_f, cmd_f]).ok

    # Clean up.
    killAzrael()
    print('Test passed')


def test_controlParts_Boosters_notmoving():
    """
    Create a template with boosters and send control commands to it.

    The parent object does not move in the world coordinate system.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Parameters and constants for this test.
    objID_1 = 1
    tNone = '_templateNone'.encode('utf8')
    sv = bullet_data.BulletData()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk()

    # ------------------------------------------------------------------------
    # Define an object with a booster and spawn it.
    # ------------------------------------------------------------------------

    # Constants for the new template object.
    cs = np.array([1, 2, 3, 4], np.float64)
    vert = list(range(9))
    uv = [9, 10]
    rgb = [1, 2, 250]

    dir_0 = np.array([1, 0, 0], np.float64)
    dir_1 = np.array([0, 1, 0], np.float64)
    pos_0 = np.array([1, 1, -1], np.float64)
    pos_1 = np.array([-1, -1, 0], np.float64)

    # Define two boosters.
    b0 = parts.Booster(partID=0, pos=pos_0, direction=dir_0, max_force=0.5)
    b1 = parts.Booster(partID=1, pos=pos_1, direction=dir_1, max_force=0.5)

    # Create a new template in Azrael of an object with two boosters.
    t2 = Template('t1'.encode('utf8'), cs, vert, uv, rgb, [b0, b1], [])
    assert clerk.addTemplates([t2]).ok

    # Spawn the object.
    ret = clerk.spawn(t2.name, sv)
    assert (ret.ok, ret.data) == (True, objID_1)
    leo.processCommandsAndSync()

    # ------------------------------------------------------------------------
    # Engage the boosters and verify the total force exerted on the object.
    # ------------------------------------------------------------------------

    # Create the commands to activate both boosters with a different force.
    forcemag_0, forcemag_1 = 0.2, 0.4
    cmd_0 = parts.CmdBooster(partID=0, force=forcemag_0)
    cmd_1 = parts.CmdBooster(partID=1, force=forcemag_1)

    # Send booster commands to Clerk.
    assert clerk.controlParts(objID_1, [cmd_0, cmd_1], []).ok
    leo.processCommandsAndSync()

    # Manually compute the total force and torque exerted by the boosters.
    forcevec_0, forcevec_1 = forcemag_0 * dir_0, forcemag_1 * dir_1
    tot_force = forcevec_0 + forcevec_1
    tot_torque = np.cross(pos_0, forcevec_0) + np.cross(pos_1, forcevec_1)

    # Query the torque and force from Azrael and verify they are correct.
    assert np.array_equal(leo.allForces[objID_1], tot_force)
    assert np.array_equal(leo.allTorques[objID_1], tot_torque)

    # ------------------------------------------------------------------------
    # Send an empty command. The total force and torque must not change, ie
    # nothing must happen at all.
    # ------------------------------------------------------------------------

    # Send booster commands to Clerk.
    assert clerk.controlParts(objID_1, [], []).ok
    leo.processCommandsAndSync()

    # Query the torque and force from Azrael and verify they are correct.
    assert np.array_equal(leo.allForces[objID_1], tot_force)
    assert np.array_equal(leo.allTorques[objID_1], tot_torque)

    # Clean up.
    killAzrael()
    print('Test passed')


def test_controlParts_Factories_notmoving():
    """
    Create a template with factories and send control commands to them.

    The parent object does not move in the world coordinate system.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Parameters and constants for this test.
    objID_1 = 1
    sv = bullet_data.BulletData()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk()

    # ------------------------------------------------------------------------
    # Create a template with two factories and spawn it.
    # ------------------------------------------------------------------------

    # Constants for the new template object.
    cs = np.array([1, 2, 3, 4], np.float64)
    vert = list(range(9))
    uv = [9, 10]
    rgb = [1, 2, 250]
    dir_0 = np.array([1, 0, 0], np.float64)
    dir_1 = np.array([0, 1, 0], np.float64)
    pos_0 = np.array([1, 1, -1], np.float64)
    pos_1 = np.array([-1, -1, 0], np.float64)

    # Define a new object with two factory parts. The Factory parts are
    # named tuples passed to addTemplate. The user must assign the partIDs
    # manually.
    f0 = parts.Factory(
        partID=0, pos=pos_0, direction=dir_0,
        templateID='_templateCube'.encode('utf8'), exit_speed=[0.1, 0.5])
    f1 = parts.Factory(
        partID=1, pos=pos_1, direction=dir_1,
        templateID='_templateSphere'.encode('utf8'), exit_speed=[1, 5])

    # Add the template to Azrael...
    t2 = Template('t1'.encode('utf8'), cs, vert, uv, rgb, [], [f0, f1])
    assert clerk.addTemplates([t2]).ok

    # ... and spawn an instance thereof.
    ret = clerk.spawn(t2.name, sv)
    assert (ret.ok, ret.data) == (True, objID_1)
    leo.processCommandsAndSync()

    # ------------------------------------------------------------------------
    # Send commands to the factories. Tell them to spawn their object with
    # the specified velocity.
    # ------------------------------------------------------------------------

    # Create the commands to let each factory spawn an object.
    exit_speed_0, exit_speed_1 = 0.2, 2
    cmd_0 = parts.CmdFactory(partID=0, exit_speed=exit_speed_0)
    cmd_1 = parts.CmdFactory(partID=1, exit_speed=exit_speed_1)

    # Send the commands and ascertain that the returned object IDs now exist in
    # the simulation. These IDs must be '2' and '3', since ID 1 was already
    # given to the client object.
    ok, _, spawnedIDs = clerk.controlParts(objID_1, [], [cmd_0, cmd_1])
    assert ok
    assert len(spawnedIDs) == 2
    assert spawnedIDs == [2, 3]
    leo.processCommandsAndSync()

    # Query the state variables of the objects spawned by the factories.
    ret = clerk.getStateVariables(spawnedIDs)
    assert (ret.ok, len(ret.data)) == (True, 2)

    # Ensure the position, velocity, and orientation of the spawned objects are
    # correct.
    sv_2, sv_3 = [ret.data[_] for _ in spawnedIDs]
    assert np.allclose(sv_2.velocityLin, exit_speed_0 * dir_0)
    assert np.allclose(sv_2.position, pos_0)
    assert np.allclose(sv_2.orientation, [0, 0, 0, 1])
    assert np.allclose(sv_3.velocityLin, exit_speed_1 * dir_1)
    assert np.allclose(sv_3.position, pos_1)
    assert np.allclose(sv_3.orientation, [0, 0, 0, 1])

    # Clean up.
    killAzrael()
    print('Test passed')


def test_controlParts_Factories_moving():
    """
    Create a template with factories and send control commands to them.

    In this test the parent object moves at a non-zero velocity.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Parameters and constants for this test.
    objID_1 = 1
    pos_parent = np.array([1, 2, 3], np.float64)
    vel_parent = np.array([4, 5, 6], np.float64)
    cs = np.array([1, 2, 3, 4], np.float64)
    vert = list(range(9))
    uv = [9, 10]
    rgb = [1, 2, 250]
    dir_0 = np.array([1, 0, 0], np.float64)
    dir_1 = np.array([0, 1, 0], np.float64)
    pos_0 = np.array([1, 1, -1], np.float64)
    pos_1 = np.array([-1, -1, 0], np.float64)
    objID_2, objID_3 = 2, 3

    # State variables for parent object.
    sv = bullet_data.BulletData(position=pos_parent, velocityLin=vel_parent)

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk()

    # ------------------------------------------------------------------------
    # Create a template with two factories and spawn it.
    # ------------------------------------------------------------------------

    # Define a new object with two factory parts. The Factory parts are
    # named tuples passed to addTemplate. The user must assign the partIDs
    # manually.
    f0 = parts.Factory(
        partID=0, pos=pos_0, direction=dir_0,
        templateID='_templateCube'.encode('utf8'), exit_speed=[0.1, 0.5])
    f1 = parts.Factory(
        partID=1, pos=pos_1, direction=dir_1,
        templateID='_templateSphere'.encode('utf8'), exit_speed=[1, 5])

    # Add the template to Azrael...
    t2 = Template('t1'.encode('utf8'), cs, vert, uv, rgb, [], [f0, f1])
    assert clerk.addTemplates([t2]).ok

    # ... and spawn an instance thereof.
    ret = clerk.spawn(t2.name, sv)
    assert (ret.ok, ret.data) == (True, objID_1)
    leo.processCommandsAndSync()

    # ------------------------------------------------------------------------
    # Send commands to the factories. Tell them to spawn their object with
    # the specified velocity.
    # ------------------------------------------------------------------------

    # Create the commands to let each factory spawn an object.
    exit_speed_0, exit_speed_1 = 0.2, 2
    cmd_0 = parts.CmdFactory(partID=0, exit_speed=exit_speed_0)
    cmd_1 = parts.CmdFactory(partID=1, exit_speed=exit_speed_1)

    # Send the commands and ascertain that the returned object IDs now exist in
    # the simulation. These IDS must be '3' and '4', since ID 1 was already
    # given to the client object.
    ret = clerk.controlParts(objID_1, [], [cmd_0, cmd_1])
    assert ret.ok and (len(ret.data) == 2)
    spawnedIDs = ret.data
    assert spawnedIDs == [objID_2, objID_3]
    leo.processCommandsAndSync()

    # Query the state variables of the objects spawned by the factories.
    ret = clerk.getStateVariables(spawnedIDs)
    assert (ret.ok, len(ret.data)) == (True, 2)

    # Ensure the position, velocity, and orientation of the spawned objects are
    # correct.
    sv_2, sv_3 = ret.data[objID_2], ret.data[objID_3]
    assert np.allclose(sv_2.velocityLin, exit_speed_0 * dir_0 + vel_parent)
    assert np.allclose(sv_2.position, pos_0 + pos_parent)
    assert np.allclose(sv_2.orientation, [0, 0, 0, 1])
    assert np.allclose(sv_3.velocityLin, exit_speed_1 * dir_1 + vel_parent)
    assert np.allclose(sv_3.position, pos_1 + pos_parent)
    assert np.allclose(sv_3.orientation, [0, 0, 0, 1])

    # Clean up.
    killAzrael()
    print('Test passed')


def test_controlParts_Boosters_and_Factories_move_and_rotated():
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

    # Parameters and constants for this test.
    objID_1, objID_2, objID_3 = 1, 2, 3
    pos_parent = np.array([1, 2, 3], np.float64)
    vel_parent = np.array([4, 5, 6], np.float64)
    cs = np.array([1, 2, 3, 4], np.float64)
    vert = list(range(9))
    uv = [9, 10]
    rgb = [1, 2, 250]

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

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk()

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
    t2 = Template('t1'.encode('utf8'), cs, vert, uv, rgb, [b0, b1], [f0, f1])
    assert clerk.addTemplates([t2]).ok

    # ... and spawn an instance thereof.
    ret = clerk.spawn(t2.name, sv)
    assert (ret.ok, ret.data) == (True, objID_1)
    leo.processCommandsAndSync()

    # ------------------------------------------------------------------------
    # Activate booster and factories. Then verify that boosters apply the
    # correct force and the newly spawned objcts have the correct State
    # Vector.
    # ------------------------------------------------------------------------

    # Create the commands to let each factory spawn an object.
    exit_speed_0, exit_speed_1 = 0.2, 2
    forcemag_0, forcemag_1 = 0.2, 0.4
    cmd_0 = parts.CmdBooster(partID=0, force=forcemag_0)
    cmd_1 = parts.CmdBooster(partID=1, force=forcemag_1)
    cmd_2 = parts.CmdFactory(partID=0, exit_speed=exit_speed_0)
    cmd_3 = parts.CmdFactory(partID=1, exit_speed=exit_speed_1)

    # Send the commands and ascertain that the returned object IDs now exist in
    # the simulation. These IDS must be '3' and '4', since ID 1 was already
    # given to the client object.
    ret = clerk.controlParts(objID_1, [cmd_0, cmd_1], [cmd_2, cmd_3])
    assert ret.ok
    spawnIDs = ret.data
    assert spawnIDs == [objID_2, objID_3]
    leo.processCommandsAndSync()

    # Query the state variables of the objects spawned by the factories.
    ret = clerk.getStateVariables(spawnIDs)
    assert (ret.ok, len(ret.data)) == (True, 2)

    # Verify the positions and velocities of the spawned objects are correct.
    sv_2, sv_3 = ret.data[objID_2], ret.data[objID_3]
    assert np.allclose(sv_2.velocityLin, exit_speed_0 * dir_0_out + vel_parent)
    assert np.allclose(sv_2.position, pos_0_out + pos_parent)
    assert np.allclose(sv_2.orientation, orient_parent)
    assert np.allclose(sv_3.velocityLin, exit_speed_1 * dir_1_out + vel_parent)
    assert np.allclose(sv_3.position, pos_1_out + pos_parent)
    assert np.allclose(sv_3.orientation, orient_parent)

    # Manually compute the total force and torque exerted by the boosters.
    forcevec_0, forcevec_1 = forcemag_0 * dir_0_out, forcemag_1 * dir_1_out
    tot_force = forcevec_0 + forcevec_1
    tot_torque = (np.cross(pos_0_out, forcevec_0) +
                  np.cross(pos_1_out, forcevec_1))

    # Query the torque and force from Azrael and verify they are correct.
    assert np.array_equal(leo.allForces[objID_1], tot_force)
    assert np.array_equal(leo.allTorques[objID_1], tot_torque)

    # Clean up.
    killAzrael()
    print('Test passed')


def test_get_all_objectids():
    """
    Test getAllObjects.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Parameters and constants for this test.
    objID_1, objID_2 = 1, 2
    templateID = '_templateNone'.encode('utf8')
    sv = bullet_data.BulletData()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk()

    # So far no objects have been spawned.
    ret = clerk.getAllObjectIDs()
    assert (ret.ok, ret.data) == (True, [])

    # Spawn a new object.
    ret = clerk.spawn(templateID, sv)
    assert (ret.ok, ret.data) == (True, objID_1)

    # The object list must now contain the ID of the just spawned object.
    leo.step(0, 10)
    ret = clerk.getAllObjectIDs()
    assert (ret.ok, ret.data) == (True, [objID_1])

    # Spawn another object.
    ret = clerk.spawn(templateID, sv)
    assert (ret.ok, ret.data) == (True, objID_2)

    # The object list must now contain the ID of both spawned objects.
    leo.step(0, 10)
    ret = clerk.getAllObjectIDs()
    assert (ret.ok, ret.data) == (True, [objID_1, objID_2])

    # Kill all spawned Client processes.
    killAzrael()
    print('Test passed')


def test_getGeometry():
    """
    Spawn an object and query its geometry.
    """
    killAzrael()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk()

    # Convenience.
    cs = np.array([1, 2, 3, 4], np.float64)
    vert = list(range(9))
    uv = [9, 10]
    rgb = [1, 2, 250]
    sv = bullet_data.BulletData()

    # Add a valid template and verify it now exists in Azrael.
    t1 = Template('t1'.encode('utf8'), cs, vert, uv, rgb, [], [])
    assert clerk.addTemplates([t1]).ok
    assert clerk.getTemplate(t1.name).ok

    # Attempt to query the geometry of a non-existing object.
    assert not clerk.getGeometry(1).ok

    # Spawn an object from the previously added template.
    ret = clerk.spawn(t1.name, sv)
    assert ret.ok
    objID = ret.data

    # Query the geometry of the object.
    ret = clerk.getGeometry(objID)
    assert ret.ok
    assert np.array_equal(vert, ret.data['vert'])
    assert np.array_equal(uv, ret.data['uv'])
    assert np.array_equal(rgb, ret.data['rgb'])

    # Delete the object.
    assert clerk.removeObject(objID).ok

    # Attempt to query the geometry of the now deleted object.
    assert not clerk.getGeometry(objID).ok

    # Kill all spawned Client processes.
    killAzrael()
    print('Test passed')


def test_instanceDB_checksum():
    """
    Spawn and object and verify that the geometry tag changes whenever the
    geometry is modified.
    """
    killAzrael()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Convenience.
    cs = np.array([1, 2, 3, 4], np.float64)
    vert = list(range(9))
    uv = [9, 10]
    rgb = [1, 2, 250]
    sv = bullet_data.BulletData()

    # Add a valid template and verify it now exists in Azrael.
    t1 = Template('t1'.encode('utf8'), cs, vert, uv, rgb, [], [])
    assert clerk.addTemplates([t1]).ok

    # Spawn two objects from the previously defined template.
    (ok, msg, objID0) = clerk.spawn(t1.name, sv)
    assert ok
    (ok, msg, objID1) = clerk.spawn(t1.name, sv)
    assert ok

    # Query the 'lastChanged' value for the objects.
    leo.step(0, 10)
    ret = clerk.getStateVariables([objID0, objID1])
    assert ret.ok
    ret_1 = ret.data
    assert set((objID0, objID1)) == set(ret_1.keys())

    # Modify the geometry of the first object and verify that its 'lastChanged'
    # attribute has changed.
    assert clerk.setGeometry(objID0, 2 * vert, 2 * uv, 2 * rgb).ok
    ret = clerk.getStateVariables([objID0])
    assert ret.ok
    assert ret_1[objID0].lastChanged != ret.data[objID0].lastChanged
    ret = clerk.getStateVariables([objID1])
    assert ret.ok
    assert ret_1[objID1].lastChanged == ret.data[objID1].lastChanged

    # Query the geometry and verify it has the new values.
    ret = clerk.getGeometry(objID0)
    assert ret.ok
    assert np.array_equal(ret.data['vert'], 2 * vert)
    assert np.array_equal(ret.data['uv'], 2 * uv)
    assert np.array_equal(ret.data['rgb'], 2 * rgb)

    # Kill all spawned Client processes.
    killAzrael()
    print('Test passed')


if __name__ == '__main__':
    test_add_get_template_single()
    test_add_get_template_multi()

    test_getGeometry()
    test_instanceDB_checksum()
    test_add_get_template_AABB()
    test_controlParts_invalid_commands()
    test_controlParts_Boosters_notmoving()
    test_controlParts_Factories_notmoving()
    test_controlParts_Factories_moving()
    test_controlParts_Boosters_and_Factories_move_and_rotated()
    test_get_all_objectids()
    test_get_object_template_id()
    test_get_statevar()
    test_spawn()
    test_delete()
    test_set_force()
    test_ping()
    test_invalid()
