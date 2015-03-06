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
import json
import pytest
import IPython
import urllib.request

import numpy as np

import azrael.util
import azrael.clerk
import azrael.client
import azrael.parts as parts
import azrael.physics_interface as physAPI
import azrael.bullet.bullet_data as bullet_data

from azrael.test.test_clacks import startAzrael, stopAzrael
from azrael.test.test_leonard import getLeonard, killAzrael
from azrael.bullet.test_boost_bullet import isEqualBD


ipshell = IPython.embed
Template = azrael.util.Template
Fragment = azrael.util.Fragment


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
    sv_1 = bullet_data.BulletData(imass=1)
    sv_2 = bullet_data.BulletData(imass=2)
    sv_3 = bullet_data.BulletData(imass=3)

    # Invalid templateID.
    templateID = 'blah'
    ret = clerk.spawn([(templateID, sv_1)])
    assert not ret.ok
    assert ret.msg.startswith('Not all template IDs were valid')

    # All parameters are now valid. This must spawn an object with ID=1
    # because this is the first ID in an otherwise pristine system.
    templateID = '_templateNone'
    ret = clerk.spawn([(templateID, sv_1)])
    assert (ret.ok, ret.data) == (True, (1, ))

    # Geometry for this object must now exist.
    assert clerk.getGeometry(1).ok

    # Spawn two more objects with a single call.
    name_2 = '_templateSphere'
    name_3 = '_templateCube'
    ret = clerk.spawn([(name_2, sv_2), (name_3, sv_3)])
    assert (ret.ok, ret.data) == (True, (2, 3))

    # Geometry for last two object must now exist as well.
    assert clerk.getGeometry(2).ok
    assert clerk.getGeometry(3).ok

    # Spawn two identical objects with a single call.
    ret = clerk.spawn([(name_2, sv_2), (name_2, sv_2)])
    assert (ret.ok, ret.data) == (True, (4, 5))

    # Geometry for last two object must now exist as well.
    assert clerk.getGeometry(4).ok
    assert clerk.getGeometry(5).ok

    # Invalid: list of objects must not be empty.
    assert not clerk.spawn([]).ok

    # Invalid: List elements do not contain the correct data types.
    assert not clerk.spawn([name_2]).ok

    # Invalid: one template does not exist.
    assert not clerk.spawn([(name_2, sv_2), (b'blah', sv_3)]).ok

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
    templateID = '_templateNone'
    ret = clerk.spawn([(templateID, sv), (templateID, sv)])
    assert (ret.ok, ret.data) == (True, (objID_1, objID_2))

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
    templateID = '_templateNone'

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk()

    # Retrieve the SV for a non-existing ID.
    ret = clerk.getStateVariables([10])
    assert (ret.ok, ret.data) == (True, {10: None})

    # Spawn a new object. It must have ID=1.
    ret = clerk.spawn([(templateID, sv_1)])
    assert (ret.ok, ret.data) == (True, (objID_1, ))

    # Retrieve the SV for a non-existing ID --> must fail.
    leo.processCommandsAndSync()
    ret = clerk.getStateVariables([10])
    assert (ret.ok, ret.data) == (True, {10: None})

    # Retrieve the SV for the existing ID=1.
    ret = clerk.getStateVariables([objID_1])
    assert (ret.ok, len(ret.data)) == (True, 1)
    assert isEqualBD(ret.data[objID_1]['sv'], sv_1)

    # Spawn a second object.
    ret = clerk.spawn([(templateID, sv_2)])
    assert (ret.ok, ret.data) == (True, (objID_2, ))

    # Retrieve the state variables for both objects individually.
    leo.processCommandsAndSync()
    for objID, ref_sv in zip([objID_1, objID_2], [sv_1, sv_2]):
        ret = clerk.getStateVariables([objID])
        assert (ret.ok, len(ret.data)) == (True, 1)
        assert isEqualBD(ret.data[objID]['sv'], ref_sv)

    # Retrieve the state variables for both objects at once.
    ret = clerk.getStateVariables([objID_1, objID_2])
    assert (ret.ok, len(ret.data)) == (True, 2)
    assert isEqualBD(ret.data[objID_1]['sv'], sv_1)
    assert isEqualBD(ret.data[objID_2]['sv'], sv_2)

    print('Test passed')


def test_getAllStateVariables():
    """
    Test the 'getAllStateVariables' command in the Clerk.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard.
    leo = getLeonard()

    # Test parameters and constants.
    objID_1 = 1
    objID_2 = 2
    sv_1 = bullet_data.BulletData(position=np.arange(3), velocityLin=[2, 4, 6])
    sv_2 = bullet_data.BulletData(position=[2, 4, 6], velocityLin=[6, 8, 10])
    templateID = '_templateNone'

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk()

    # Retrieve all SV --> there must be none.
    ret = clerk.getAllStateVariables()
    assert (ret.ok, ret.data) == (True, {})

    # Spawn a new object. It must have ID=1.
    ret = clerk.spawn([(templateID, sv_1)])
    assert (ret.ok, ret.data) == (True, (objID_1, ))

    # Retrieve all SV --> there must be one.
    leo.processCommandsAndSync()
    ret = clerk.getAllStateVariables()
    assert (ret.ok, len(ret.data)) == (True, 1)
    assert isEqualBD(ret.data[objID_1]['sv'], sv_1)

    # Spawn a second object.
    ret = clerk.spawn([(templateID, sv_2)])
    assert (ret.ok, ret.data) == (True, (objID_2, ))

    # Retrieve all SV --> there must now be two.
    leo.processCommandsAndSync()
    ret = clerk.getAllStateVariables()
    assert (ret.ok, len(ret.data)) == (True, 2)
    assert isEqualBD(ret.data[objID_1]['sv'], sv_1)
    assert isEqualBD(ret.data[objID_2]['sv'], sv_2)

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
    templateID = '_templateNone'
    ret = clerk.spawn([(templateID, sv)])
    assert (ret.ok, ret.data) == (True, (id_1, ))

    # Apply the force.
    assert clerk.setForce(id_1, force, relpos).ok

    leo.processCommandsAndSync()
    tmp = leo.totalForceAndTorque(id_1)
    assert np.array_equal(tmp[0], force)
    assert np.array_equal(tmp[1], np.cross(relpos, force))

    print('Test passed')


def test_add_get_template_single():
    """
    Add a new object to the templateID DB and query it again.
    """
    killAzrael()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk()

    # Request an invalid ID.
    assert not clerk.getTemplates(['blah']).ok

    # Clerk has a few default objects. This one has no collision shape...
    name_1 = '_templateNone'
    ret = clerk.getTemplates([name_1])
    assert ret.ok and (len(ret.data) == 1) and (name_1 in ret.data)
    assert np.array_equal(ret.data[name_1]['cshape'], np.array([0, 1, 1, 1]))

    # ... this one is a sphere...
    name_2 = '_templateSphere'
    ret = clerk.getTemplates([name_2])
    assert ret.ok and (len(ret.data) == 1) and (name_2 in ret.data)
    assert np.array_equal(ret.data[name_2]['cshape'], np.array([3, 1, 1, 1]))

    # ... and this one is a cube.
    name_3 = '_templateCube'
    ret = clerk.getTemplates([name_3])
    assert ret.ok and (len(ret.data) == 1) and (name_3 in ret.data)
    assert np.array_equal(ret.data[name_3]['cshape'], np.array([4, 1, 1, 1]))

    # Retrieve all three again but with a single call.
    ret = clerk.getTemplates([name_1, name_2, name_3])
    assert ret.ok
    assert set(ret.data.keys()) == set((name_1, name_2, name_3))
    assert np.array_equal(ret.data[name_1]['cshape'], np.array([0, 1, 1, 1]))
    assert np.array_equal(ret.data[name_2]['cshape'], np.array([3, 1, 1, 1]))
    assert np.array_equal(ret.data[name_3]['cshape'], np.array([4, 1, 1, 1]))

    # Convenience.
    cs = [1, 2, 3, 4]
    vert = list(range(9))
    uv = [9, 10]
    rgb = [1, 2, 250]

    # Wrong argument .
    t1 = Template('t1', cs, vert[:-1], uv, rgb, [], [])
    ret = clerk.addTemplates([1])
    assert not ret.ok
    assert ret.msg == 'Invalid arguments'

    # Attempt to add a template where the number of vertices is not a multiple
    # of 9. This must fail.
    ret = clerk.addTemplates([t1])
    assert not ret.ok
    assert ret.msg.startswith('Invalid geometry for template')

    # Add a valid template. This must succeed.
    t1 = Template('t1', cs, vert, uv, rgb, [], [])
    assert clerk.addTemplates([t1]).ok

    # Attempt to add another template with the same name. This must fail.
    t2 = Template('t1', 2 * cs, 2 * vert, uv, rgb, [], [])
    assert not clerk.addTemplates([t2]).ok

    # Fetch the just added template and verify its parameters have not changed.
    ret = clerk.getTemplates([t2.name])
    assert ret.ok
    assert np.array_equal(ret.data[t2.name]['cshape'], cs)

    # Define a new object with two boosters and one factory unit.
    # The 'boosters' and 'factories' arguments are a list of named
    # tuples. Their first argument is the unit ID (Azrael does not assign
    # automatically assign any IDs).
    z = np.zeros(3)
    b0 = parts.Booster(partID=0, pos=z, direction=[0, 0, 1],
                       minval=0, maxval=0.5, force=0)
    b1 = parts.Booster(partID=1, pos=z, direction=[0, 0, 1],
                       minval=0, maxval=0.5, force=0)
    f0 = parts.Factory(
        partID=0, pos=z, direction=[0, 0, 1],
        templateID='_templateCube', exit_speed=[0.1, 0.5])
    del z

    # Add the new template.
    t3 = Template('t3', cs, vert, uv, rgb, [b0, b1], [f0])
    assert clerk.addTemplates([t3]).ok

    # Retrieve the just created object and verify the CS and geometry.
    ret = clerk.getTemplates([t3.name])
    assert ret.ok
    assert np.array_equal(ret.data[t3.name]['cshape'], cs)

    # The template must also feature two boosters and one factory.
    assert len(ret.data[t3.name]['boosters']) == 2
    assert len(ret.data[t3.name]['factories']) == 1

    # Explicitly verify the booster- and factory units. The easisest (albeit
    # not most readable) way to do the comparison is to convert the unit
    # descriptions (which are named tuples) to byte strings and compare those.
    out_boosters = [parts.Booster(*_) for _ in ret.data[t3.name]['boosters']]
    out_factories = [parts.Factory(*_) for _ in ret.data[t3.name]['factories']]
    assert b0 in out_boosters
    assert b1 in out_boosters
    assert f0 in out_factories

    # Request the same templates multiple times in a single call. This must
    # return a dictionary with as many keys as there are unique template IDs.
    ret = clerk.getTemplates([t3.name, t3.name, t3.name])
    assert ret.ok and (len(ret.data) == 1) and (t3.name in ret.data)

    print('Test passed')


def test_add_get_template_multi_url():
    """
    Add templates in bulk. Also verify that the geometries are availabe
    via an URL.
    """
    killAzrael()

    # Start the necessary services and instantiate a Client.
    clerk, client, clacks = startAzrael('Websocket')

    # Convenience.
    cs = [1, 2, 3, 4]
    vert = list(range(9))
    uv = [9, 10]
    rgb = [1, 2, 250]
    name1 = 't1'
    name2 = 't2'

    # Add valid template. This must succeed.
    t1 = Template(name1, cs, vert, uv, rgb, [], [])
    t2 = Template(name2, 2 * cs, 2 * vert, uv, rgb, [], [])

    assert clerk.addTemplates([t1, t2]).ok

    # Attempt to add another template with the same name. This must fail.
    assert not clerk.addTemplates([t1, t2]).ok

    # Fetch the just added template again and verify the CS.
    ret = clerk.getTemplates([name1])
    assert ret.ok and (len(ret.data) == 1)
    assert np.array_equal(ret.data[name1]['cshape'], t1.cs)

    # Fetch the geometry from the Web server and verify it is correct.
    base_url = 'http://localhost:8080'
    url = base_url + ret.data[name1]['url_geo']
    tmp = json.loads(urllib.request.urlopen(url).readall().decode('utf8'))
    assert np.array_equal(tmp['1']['vert'], t1.vert)
    assert np.array_equal(tmp['1']['uv'], t1.uv)
    assert np.array_equal(tmp['1']['rgb'], t1.rgb)

    # Fetch the second template.
    ret = clerk.getTemplates([name2])
    assert ret.ok and (len(ret.data) == 1)
    assert np.array_equal(ret.data[name2]['cshape'], t2.cs)

    # Fetch the geometry from the Web server and verify it is correct.
    base_url = 'http://localhost:8080'
    url = base_url + ret.data[name2]['url_geo']
    tmp = json.loads(urllib.request.urlopen(url).readall().decode('utf8'))
    assert np.array_equal(tmp['1']['vert'], t2.vert)
    assert np.array_equal(tmp['1']['uv'], t2.uv)
    assert np.array_equal(tmp['1']['rgb'], t2.rgb)

    # Fetch both templates at once.
    ret = clerk.getTemplates([name1, name2])
    assert ret.ok and (len(ret.data) == 2)
    assert np.array_equal(ret.data[name1]['cshape'], t1.cs)
    assert np.array_equal(ret.data[name2]['cshape'], t2.cs)

    # Shutdown the services.
    stopAzrael(clerk, clacks)

    print('Test passed')


def test_add_get_template_AABB():
    """
    Similarly to test_add_get_template but focuses exclusively on the AABB.
    """
    killAzrael()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk()

    # Convenience.
    cs = [1, 2, 3, 4]
    uv = rgb = []

    # Manually specify the vertices.
    vert = [-4, 0, 0,
            1, 2, 3,
            4, 5, 6]
    max_sidelen = max(8, 5, 6)

    # Add template and retrieve it again.
    t1 = Template('t1', cs, vert, uv, rgb, [], [])
    assert clerk.addTemplates([t1]).ok
    ret = clerk.getTemplates([t1.name])
    assert ret.ok

    # The largest AABB side length must be roughly "sqrt(3) * max_sidelen".
    assert (ret.data[t1.name]['aabb'] - np.sqrt(3.1) * max_sidelen) < 1E-10

    # Repeat the experiment with a larger mesh.
    vert = [0, 0, 0,
            1, 2, 3,
            4, 5, 6,
            8, 2, 7,
            -5, -9, 8,
            3, 2, 3]
    max_sidelen = max(8, 14, 8)

    # Add template and retrieve it again.
    t2 = Template('t2', cs, vert, uv, rgb, [], [])
    assert clerk.addTemplates([t2]).ok
    ret = clerk.getTemplates([t2.name])
    assert ret.ok

    # The largest AABB side length must be roughly "sqrt(3) * max_sidelen".
    assert (ret.data[t2.name]['aabb'] - np.sqrt(3.1) * max_sidelen) < 1E-10

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
    templateID_0 = '_templateNone'
    templateID_1 = '_templateCube'
    sv = bullet_data.BulletData()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk()

    # Spawn two object. They must have id_0 and id_1, respectively.
    ret = clerk.spawn([(templateID_0, sv), (templateID_1, sv)])
    assert (ret.ok, ret.data) == (True, (id_0, id_1))

    # Retrieve template of first object.
    leo.processCommandsAndSync()
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
    templateID_1 = '_templateNone'
    sv = bullet_data.BulletData()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk()

    # Create a fake object. We will not need the actual object but other
    # commands tested here depend on the existence of an object.
    ret = clerk.spawn([(templateID_1, sv)])
    assert (ret.ok, ret.data) == (True, (objID_1, ))

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
    # named tuples passed to addTemplates. The user must assign the partIDs
    # manually.
    b0 = parts.Booster(partID=0, pos=[0, 0, 0], direction=[0, 0, 1],
                       minval=0, maxval=0.5, force=0)
    f0 = parts.Factory(
        partID=0, pos=[0, 0, 0], direction=[0, 0, 1],
        templateID='_templateCube', exit_speed=[0, 1])

    # Add the template to Azrael...
    cs = [1, 2, 3, 4]
    vert = list(range(9))
    uv = [9, 10]
    rgb = [1, 2, 250]
    t2 = Template('t1', cs, vert, uv, rgb, [b0], [f0])
    assert clerk.addTemplates([t2]).ok

    # ... and spawn an instance thereof.
    sv = bullet_data.BulletData()
    ret = clerk.spawn([(t2.name, sv)])
    assert (ret.ok, ret.data) == (True, (objID_2, ))
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
    tNone = '_templateNone'
    sv = bullet_data.BulletData()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk()

    # ------------------------------------------------------------------------
    # Define an object with a booster and spawn it.
    # ------------------------------------------------------------------------

    # Constants for the new template object.
    cs = [1, 2, 3, 4]
    vert = list(range(9))
    uv = [9, 10]
    rgb = [1, 2, 250]

    dir_0 = np.array([1, 0, 0], np.float64)
    dir_1 = np.array([0, 1, 0], np.float64)
    pos_0 = np.array([1, 1, -1], np.float64)
    pos_1 = np.array([-1, -1, 0], np.float64)

    # Define two boosters.
    b0 = parts.Booster(partID=0, pos=pos_0, direction=dir_0,
                       minval=0, maxval=0.5, force=0)
    b1 = parts.Booster(partID=1, pos=pos_1, direction=dir_1,
                       minval=0, maxval=0.5, force=0)

    # Create a new template in Azrael of an object with two boosters.
    t2 = Template('t1', cs, vert, uv, rgb, [b0, b1], [])
    assert clerk.addTemplates([t2]).ok

    # Spawn the object.
    ret = clerk.spawn([(t2.name, sv)])
    assert (ret.ok, ret.data) == (True, (objID_1, ))
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
    tmp = leo.totalForceAndTorque(objID_1)
    assert np.array_equal(tmp[0], tot_force)
    assert np.array_equal(tmp[1], tot_torque)

    # ------------------------------------------------------------------------
    # Send an empty command. The total force and torque must not change, ie
    # nothing must happen at all.
    # ------------------------------------------------------------------------

    # Send booster commands to Clerk.
    assert clerk.controlParts(objID_1, [], []).ok
    leo.processCommandsAndSync()

    # Query the torque and force from Azrael and verify they are correct.
    tmp = leo.totalForceAndTorque(objID_1)
    assert np.array_equal(tmp[0], tot_force)
    assert np.array_equal(tmp[1], tot_torque)

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
    cs = [1, 2, 3, 4]
    vert = list(range(9))
    uv = [9, 10]
    rgb = [1, 2, 250]
    dir_0 = np.array([1, 0, 0], np.float64)
    dir_1 = np.array([0, 1, 0], np.float64)
    pos_0 = np.array([1, 1, -1], np.float64)
    pos_1 = np.array([-1, -1, 0], np.float64)

    # Define a new object with two factory parts. The Factory parts are
    # named tuples passed to addTemplates. The user must assign the partIDs
    # manually.
    f0 = parts.Factory(
        partID=0, pos=pos_0, direction=dir_0,
        templateID='_templateCube', exit_speed=[0.1, 0.5])
    f1 = parts.Factory(
        partID=1, pos=pos_1, direction=dir_1,
        templateID='_templateSphere', exit_speed=[1, 5])

    # Add the template to Azrael...
    t2 = Template('t1', cs, vert, uv, rgb, [], [f0, f1])
    assert clerk.addTemplates([t2]).ok

    # ... and spawn an instance thereof.
    ret = clerk.spawn([(t2.name, sv)])
    assert (ret.ok, ret.data) == (True, (objID_1, ))
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
    assert spawnedIDs == [2, 3]
    leo.processCommandsAndSync()

    # Query the state variables of the objects spawned by the factories.
    ret = clerk.getStateVariables(spawnedIDs)
    assert (ret.ok, len(ret.data)) == (True, 2)

    # Ensure the position, velocity, and orientation of the spawned objects are
    # correct.
    sv_2, sv_3 = [ret.data[_]['sv'] for _ in spawnedIDs]
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
    cs = [1, 2, 3, 4]
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
    # named tuples passed to addTemplates. The user must assign the partIDs
    # manually.
    f0 = parts.Factory(
        partID=0, pos=pos_0, direction=dir_0,
        templateID='_templateCube', exit_speed=[0.1, 0.5])
    f1 = parts.Factory(
        partID=1, pos=pos_1, direction=dir_1,
        templateID='_templateSphere', exit_speed=[1, 5])

    # Add the template to Azrael...
    t2 = Template('t1', cs, vert, uv, rgb, [], [f0, f1])
    assert clerk.addTemplates([t2]).ok

    # ... and spawn an instance thereof.
    ret = clerk.spawn([(t2.name, sv)])
    assert (ret.ok, ret.data) == (True, (objID_1, ))
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
    sv_2, sv_3 = ret.data[objID_2]['sv'], ret.data[objID_3]['sv']
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
    cs = [1, 2, 3, 4]
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
    assert clerk.addTemplates([t2]).ok

    # ... and spawn an instance thereof.
    ret = clerk.spawn([(t2.name, sv)])
    assert (ret.ok, ret.data) == (True, (objID_1, ))
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
    # the simulation. These IDs must be '2' and '3'.
    ret = clerk.controlParts(objID_1, [cmd_0, cmd_1], [cmd_2, cmd_3])
    assert ret.ok
    spawnIDs = ret.data
    assert spawnIDs == [objID_2, objID_3]
    leo.processCommandsAndSync()

    # Query the state variables of the objects spawned by the factories.
    ret = clerk.getStateVariables(spawnIDs)
    assert (ret.ok, len(ret.data)) == (True, 2)

    # Verify the positions and velocities of the spawned objects are correct.
    sv_2, sv_3 = ret.data[objID_2]['sv'], ret.data[objID_3]['sv']
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
    tmp = leo.totalForceAndTorque(objID_1)
    assert np.array_equal(tmp[0], tot_force)
    assert np.array_equal(tmp[1], tot_torque)

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
    templateID = '_templateNone'
    sv = bullet_data.BulletData()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk()

    # So far no objects have been spawned.
    ret = clerk.getAllObjectIDs()
    assert (ret.ok, ret.data) == (True, [])

    # Spawn a new object.
    ret = clerk.spawn([(templateID, sv)])
    assert (ret.ok, ret.data) == (True, (objID_1, ))

    # The object list must now contain the ID of the just spawned object.
    leo.processCommandsAndSync()
    ret = clerk.getAllObjectIDs()
    assert (ret.ok, ret.data) == (True, [objID_1])

    # Spawn another object.
    ret = clerk.spawn([(templateID, sv)])
    assert (ret.ok, ret.data) == (True, (objID_2, ))

    # The object list must now contain the ID of both spawned objects.
    leo.processCommandsAndSync()
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
    cs = [1, 2, 3, 4]
    vert = list(range(9))
    uv = [9, 10]
    rgb = [1, 2, 250]
    sv = bullet_data.BulletData()

    # Add a valid template and verify it now exists in Azrael.
    t1 = Template('t1', cs, vert, uv, rgb, [], [])
    assert clerk.addTemplates([t1]).ok
    assert clerk.getTemplates([t1.name]).ok

    # Attempt to query the geometry of a non-existing object.
    assert not clerk.getGeometry(1).ok

    # Spawn an object from the previously added template.
    ret = clerk.spawn([(t1.name, sv)])
    assert ret.ok and (len(ret.data) == 1)
    objID = ret.data[0]

    # Query the geometry of the object.
    ret = clerk.getGeometry(objID)
    assert ret.ok
    assert np.array_equal(vert, ret.data['1']['vert'])
    assert np.array_equal(uv, ret.data['1']['uv'])
    assert np.array_equal(rgb, ret.data['1']['rgb'])

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
    cs = [1, 2, 3, 4]
    vert = list(range(9))
    uv = [9, 10]
    rgb = [1, 2, 250]
    sv = bullet_data.BulletData()

    # Add a valid template and verify it now exists in Azrael.
    t1 = Template('t1', cs, vert, uv, rgb, [], [])
    assert clerk.addTemplates([t1]).ok

    # Spawn two objects from the previously defined template.
    ret = clerk.spawn([(t1.name, sv), (t1.name, sv)])
    assert ret.ok and (len(ret.data) == 2)
    objID0, objID1 = ret.data

    # Query the State Vectors for both objects.
    leo.processCommandsAndSync()
    ret_1 = clerk.getStateVariables([objID0, objID1])
    assert ret_1.ok and (set((objID0, objID1)) == set(ret_1.data.keys()))

    # Modify the geometry of the first object and verify that its 'lastChanged'
    # attribute has changed.
    assert clerk.setGeometry(objID0, 2 * vert, 2 * uv, 2 * rgb).ok

    ret = clerk.getStateVariables([objID0])
    assert ret.ok
    assert ret_1.data[objID0]['sv'].lastChanged != ret.data[objID0]['sv'].lastChanged

    ret = clerk.getStateVariables([objID1])
    assert ret.ok
    assert ret_1.data[objID1]['sv'].lastChanged == ret.data[objID1]['sv'].lastChanged

    # Query the geometry and verify it has the new values.
    ret = clerk.getGeometry(objID0)
    assert ret.ok
    assert np.array_equal(ret.data['1']['vert'], 2 * vert)
    assert np.array_equal(ret.data['1']['uv'], 2 * uv)
    assert np.array_equal(ret.data['1']['rgb'], 2 * rgb)

    # Kill all spawned Client processes.
    killAzrael()
    print('Test passed')


def test_updateBoosterValues():
    """
    Query and update the booster values in the instance data base.
    The query includes computing the correct force in object coordinates.
    """
    killAzrael()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk()

    # ------------------------------------------------------------------------
    # Create a template with two boosters and spawn it. The Boosters are
    # to the left/right of the object and point both in the positive
    # z-direction.
    # ------------------------------------------------------------------------
    # Convenience.
    sv = bullet_data.BulletData()
    cs = [1, 2, 3, 4]
    uv = rgb = []
    vert = [-4, 0, 0,
            1, 2, 3,
            4, 5, 6]

    b0 = parts.Booster(partID=0, pos=[-1, 0, 0], direction=[0, 0, 1],
                       minval=-1, maxval=1, force=0)
    b1 = parts.Booster(partID=1, pos=[+1, 0, 0], direction=[0, 0, 1],
                       minval=-1, maxval=1, force=0)

    # Add the template to Azrael...
    t1 = Template('t1', cs, vert, uv, rgb, [b0, b1], [])
    assert clerk.addTemplates([t1]).ok
    # ... and spawn two instances of it.
    ret = clerk.spawn([(t1.name, sv)])
    assert ret.ok
    objID_1 = ret.data[0]
    ret = clerk.spawn([(t1.name, sv)])
    assert ret.ok
    objID_2 = ret.data[0]

    # ------------------------------------------------------------------------
    # Update the Booster forces on the first object: both accelerate the object
    # in z-direction, which means a force purely in z-direction and no torque.
    # ------------------------------------------------------------------------
    cmd_0 = parts.CmdBooster(partID=0, force=1)
    cmd_1 = parts.CmdBooster(partID=1, force=1)
    ret = clerk.updateBoosterForces(objID_1, [cmd_0, cmd_1])
    assert ret.ok
    assert ret.data == ([0, 0, 2], [0, 0, 0])

    # ------------------------------------------------------------------------
    # Update the Booster forces on the first object: accelerate the left one
    # upwards and the right one downwards. This must result in a zero net force
    # but non-zero torque.
    # ------------------------------------------------------------------------
    cmd_0 = parts.CmdBooster(partID=0, force=1)
    cmd_1 = parts.CmdBooster(partID=1, force=-1)
    ret = clerk.updateBoosterForces(objID_1, [cmd_0, cmd_1])
    assert ret.ok
    assert ret.data == ([0, 0, 0], [0, 2, 0])

    # ------------------------------------------------------------------------
    # Update the Booster forces on the second object to ensure the function
    # correctly distinguishes between objects.
    # ------------------------------------------------------------------------
    # Turn off left Booster of first object (right booster is still active).
    cmd_0 = parts.CmdBooster(partID=0, force=0)
    ret = clerk.updateBoosterForces(objID_1, [cmd_0])
    assert ret.ok
    assert ret.data == ([0, 0, -1], [0, 1, 0])

    # Turn on left Booster of the second object.
    cmd_0 = parts.CmdBooster(partID=0, force=1)
    ret = clerk.updateBoosterForces(objID_2, [cmd_0])
    assert ret.ok
    assert ret.data == ([0, 0, +1], [0, 1, 0])

    # ------------------------------------------------------------------------
    # Attempt to update a non-existing Booster or a non-existing object.
    # ------------------------------------------------------------------------
    cmd_0 = parts.CmdBooster(partID=10, force=1)
    assert not clerk.updateBoosterForces(objID_2, [cmd_0]).ok

    cmd_0 = parts.CmdBooster(partID=0, force=1)
    assert not clerk.updateBoosterForces(1000, [cmd_0]).ok

    # Kill all spawned Client processes.
    killAzrael()
    print('Test passed')


def test_updateFragmentState():
    """
    Create a new template with one fragment and instantiate it.

    Then query the SV for the object and verify the states of the fragments are
    correct. Modify the fragment states and verify again.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard and Clerk.
    leo = getLeonard()
    clerk = azrael.clerk.Clerk()

    # Attempt to update the fragment state of non-existing objects.
    newStates = {2: {'1': [2.2, [1, 2, 3], [1, 0, 0, 0]]}}
    ret = clerk.updateFragmentStates(newStates)
    assert not ret.ok

    # Convenience.
    sv = bullet_data.BulletData()
    cs = [1, 2, 3, 4]
    vert = [-4, 0, 0, 1, 2, 3, 4, 5, 6]

    # Add the template to Azrael and spawn two instances.
    t1 = Template('t1', cs, vert, uv=[], rgb=[], boosters=[], factories=[])
    assert clerk.addTemplates([t1]).ok
    ret = clerk.spawn([(t1.name, sv), (t1.name, sv)])
    assert ret.ok
    objID_1, objID_2 = ret.data
    leo.processCommandsAndSync()

    def checkFragState(scale_1, pos_1, rot_1, scale_2, pos_2, rot_2):
        """
        Convenience function to verify the fragment states of two objects.
        This function assumes there are two objects and each has exactly one
        fragment.
        """
        # fixme: pass objID into this function as well
        # Query the SV and ensure the fragment positions are correct.
        ret = clerk.getStateVariables([objID_1, objID_2])
        assert ret.ok
        assert len(ret.data) == 2
        frag1 = ret.data[objID_1]['frag']
        frag2 = ret.data[objID_2]['frag']

        assert frag1['1'] == [scale_1, pos_1, rot_1]
        assert frag2['1'] == [scale_2, pos_2, rot_2]

    # All fragments must initially be at the center.
    checkFragState(1, [0, 0, 0], [0, 0, 0, 1],
                   1, [0, 0, 0], [0, 0, 0, 1])

    # Update the fragment states of the second object and verify.
    newStates = {objID_2: {'1': [2.2, [1, 2, 3], [1, 0, 0, 0]]}}
    ret = clerk.updateFragmentStates(newStates)
    assert ret.ok
    checkFragState(1, [0, 0, 0], [0, 0, 0, 1],
                   2.2, [1, 2, 3], [1, 0, 0, 0])

    # Modify two instances at once and verify again.
    newStates = {
        objID_1: {'1': [3.3, [1, 2, 4], [2, 0, 0, 0]]},
        objID_2: {'1': [4.4, [1, 2, 5], [0, 3, 0, 0]]}}
    ret = clerk.updateFragmentStates(newStates)
    assert ret.ok
    checkFragState(3.3, [1, 2, 4], [2, 0, 0, 0],
                   4.4, [1, 2, 5], [0, 3, 0, 0])

    # Attempt to update the fragment state of two objects of which only one
    # actually exists.
    newStates = {
        1000000: {'1': [5, [5, 5, 5], [5, 5, 5, 5]]},
        objID_2: {'1': [5, [5, 5, 5], [5, 5, 5, 5]]}}
    ret = clerk.updateFragmentStates(newStates)
    assert not ret.ok

    # The command must have updated only the existing fragment.
    checkFragState(3.3, [1, 2, 4], [2, 0, 0, 0],
                   5.0, [5, 5, 5], [5, 5, 5, 5])

    # Attempt to update a non-existing fragment.
    newStates = {
        objID_2: {'2': [6, [6, 6, 6], [6, 6, 6, 6]]}}
    ret = clerk.updateFragmentStates(newStates)
    assert not ret.ok

    checkFragState(3.3, [1, 2, 4], [2, 0, 0, 0],
                   5.0, [5, 5, 5], [5, 5, 5, 5])

    # Attempt to update several fragments in one object. However, not all
    # fragment IDs are valid. The expected behaviour is that none of the
    # fragments was updated.
    newStates = {
        objID_2: {
            '1': [7, [7, 7, 7], [7, 7, 7, 7]],
            '2': [8, [8, 8, 8], [8, 8, 8, 8]]}}
    ret = clerk.updateFragmentStates(newStates)
    assert not ret.ok

    checkFragState(3.3, [1, 2, 4], [2, 0, 0, 0],
                   5.0, [5, 5, 5], [5, 5, 5, 5])

    # Update the fragments twice with the exact same data. This will trigger a
    # bug I once had because I checked the wrong Mongo return code.
    newStates = {
        objID_2: {'1': [9, [9, 9, 9], [9, 9, 9, 9]]}}
    ret = clerk.updateFragmentStates(newStates)
    assert ret.ok
    ret = clerk.updateFragmentStates(newStates)
    assert ret.ok

    # Kill all spawned Client processes.
    killAzrael()
    print('Test passed')


def test_addTemplate_multiple_fragments():
    """
    Create a new template with multiple fragments and instantiate it. Then
    query the fragment geometries.
    """
    killAzrael()

    # Reset the SV database and instantiate a Leonard and Clerk.
    leo = getLeonard()
    clerk = azrael.clerk.Clerk()

    # Convenience.
    sv = bullet_data.BulletData()
    cs = [1, 2, 3, 4]
    vert = [-4, 0, 0, 1, 2, 3, 4, 5, 6]

    def checkFragState(name_1, scale_1, pos_1, rot_1,
                       name_2, scale_2, pos_2, rot_2):
        """
        Convenience function to verify the fragment states of on object.
        This function assumes there is exactly one object with two fragments.
        """
        # Query the SV and ensure the fragment positions are correct.
        ret = clerk.getAllStateVariables()
        assert ret.ok
        assert len(ret.data) == 1
        frags = list(ret.data.values())[0]['frag']
        assert len(frags) == 2
        assert (name_1 in frags) and (name_2 in frags)

        assert frags[name_1] == [scale_1, pos_1, rot_1]
        assert frags[name_2] == [scale_2, pos_2, rot_2]

    # Add the template to Azrael and spawn two instances.
    frags = [Fragment(name='1', vert=vert, uv=[], rgb=[]),
             Fragment(name='test', vert=vert, uv=[], rgb=[])]
    t1 = Template('t1', cs, frags, boosters=[], factories=[])
    assert clerk.addTemplates([t1]).ok
    ret = clerk.spawn([(t1.name, sv)])
    assert ret.ok
    objID_1 = ret.data[0]
    leo.processCommandsAndSync()

    ret = clerk.getStateVariables([objID_1])
    assert ret.ok
    ret_frags = ret.data[objID_1]['frag']
    assert len(ret_frags) == len(frags)

    ret = clerk.getAllStateVariables()
    assert ret.ok
    ret_frags = ret.data[objID_1]['frag']
    assert len(ret_frags) == len(frags)

    checkFragState('1', 1, [0, 0, 0], [0, 0, 0, 1],
                   'test', 1, [0, 0, 0], [0, 0, 0, 1])

    newStates = {
        objID_1: {
            '1': [7, [7, 7, 7], [7, 7, 7, 7]],
            'test': [8, [8, 8, 8], [8, 8, 8, 8]]}}
    ret = clerk.updateFragmentStates(newStates)
    assert ret.ok

    checkFragState('1', 7, [7, 7, 7], [7, 7, 7, 7],
                   'test', 8, [8, 8, 8], [8, 8, 8, 8])


    # Kill all spawned Client processes.
    killAzrael()
    print('Test passed')


if __name__ == '__main__':
    test_addTemplate_multiple_fragments()
    print('all good')
    assert False
    test_updateFragmentState()
    test_updateBoosterValues()
    test_getAllStateVariables()
    test_add_get_template_single()
    test_add_get_template_multi_url()
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
