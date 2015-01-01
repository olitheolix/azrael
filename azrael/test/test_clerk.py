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
Test the Clerk only. Use a modified Controller to this end which allows to send
raw bytestrings to bypass all convenience wrappers that the Controller class
offers and test purely the Clerk.
"""

import sys
import time
import pytest
import IPython
import websocket
import subprocess
import numpy as np

import azrael.clerk
import azrael.parts as parts
import azrael.config as config
import azrael.clacks as clacks
import azrael.leonard as leonard
import azrael.protocol as protocol
import azrael.protocol_json as json
import azrael.controller as controller
import azrael.wscontroller as wscontroller
import azrael.bullet.btInterface as btInterface
import azrael.bullet.bullet_data as bullet_data

from azrael.util import int2id, id2int
from azrael.test.test_leonard import startAzrael, stopAzrael, killAzrael

ipshell = IPython.embed


class ControllerTest(controller.ControllerBase):
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


def test_connect():
    """
    Connect to Clerk and make sure we get correct ID.
    """
    # Start the necessary services and instantiate a Controller.
    clerk, ctrl, clacks = startAzrael('ZeroMQ')

    # Since only one Controller was instantiated it must have objID=1.
    assert ctrl.objID == int2id(1)

    # Shutdown the services.
    stopAzrael(clerk, clacks)
    print('Test passed')


def test_invalid():
    """
    Send an invalid command to the Clerk.
    """
    killAzrael()

    # Start Clerk and instantiate a Controller.
    clerk = azrael.clerk.Clerk(reset=True)
    clerk.start()
    ctrl = ControllerTest()
    ctrl.setupZMQ()
    ctrl.connectToClerk()

    # Send a corrupt JSON to Clerk.
    msg = 'invalid_cmd'
    ok, ret = ctrl.testSend(msg.encode('utf8'))
    assert (ok, ret) == (False, 'JSON decoding error in Clerk')

    # Send a malformatted JSON (it misses the 'payload' field).
    msg = json.dumps({'cmd': 'blah'})
    ok, ret = ctrl.testSend(msg.encode('utf8'))
    assert (ok, ret) == (False, 'Invalid command format')

    # Send an invalid command.
    msg = json.dumps({'cmd': 'blah', 'payload': ''})
    ok, ret = ctrl.testSend(msg.encode('utf8'))
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
    # Start the necessary services and instantiate a Controller.
    clerk, ctrl, clacks = startAzrael('ZeroMQ')

    # Send the Ping command.
    ok, ret = ctrl.ping()
    assert (ok, ret) == (True, 'pong clerk')

    # Shutdown the services.
    stopAzrael(clerk, clacks)
    print('Test passed')


def test_get_id():
    """
    Request a new ID for this controller.
    """
    # Start the necessary services and instantiate a Controller.
    clerk, ctrl, clacks = startAzrael('ZeroMQ')

    # Request new IDs. It must increase with every request, starting at 1.
    for ii in range(3):
        objID = ctrl.connectToClerk()
        assert objID == int2id(ii + 1)

        # Clear the objID as the `connectToClerk` method will otherwise not
        # request a new one.
        ctrl.objID = None

    # Shutdown the services.
    stopAzrael(clerk, clacks)
    print('Test passed')


def test_send_receive_message():
    """
    Try to send a message to a random controller ID. The ID itself does not
    matter because the Clerk silently drops messages for non-existing
    controllers.
    """
    killAzrael()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)

    # Test parameters.
    src, dst, data = int2id(5), int2id(10), 'blah'.encode('utf8')

    # Retrieve a non-existing message.
    ok, (_, msg) = clerk.recvMessage(src)
    assert (ok, msg) == (True, b'')

    # Dispatch a message.
    ok, msg = clerk.sendMessage(src, dst, data)
    assert ok

    # Attempt to retrieve it with the wrong 'dst' -- we must get nothing.
    ok, (_, msg) = clerk.recvMessage(src)
    assert (ok, msg) == (True, b'')

    # Now retrieve it with the correct ID, and the retrieve it once more to
    # ensure that the same message is not delivered twice.
    ok, (_, msg) = clerk.recvMessage(dst)
    assert (ok, (_, msg)) == (True, (src, data))
    ok, (_, msg) = clerk.recvMessage(dst)
    assert (ok, msg) == (True, b'')

    print('Test passed')


def test_spawn():
    """
    Test the 'spawn' command in the Clerk.
    """
    killAzrael()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)

    # Default object.
    sv = bullet_data.BulletData()

    # Unknown controller name.
    templateID = '_templateNone'.encode('utf8')
    ok, ret = clerk.spawn('aaaa'.encode('utf8'), templateID, sv)
    assert (ok, ret) == (False, 'Unknown Controller Name')

    # Invalid templateID.
    templateID = np.int64(100).tostring()
    ok, ret = clerk.spawn(None, templateID, sv)
    assert (ok, ret) == (False, 'Invalid Template ID')

    # All parameters are now valid. This must spawn an object with ID=1
    # because this is the first ID in an otherwise pristine system.
    templateID = '_templateNone'.encode('utf8')
    ok, (ret,) = clerk.spawn(None, templateID, sv)
    assert (ok, ret) == (True, int2id(1))

    print('Test passed')


def test_delete():
    """
    Test the 'deleteObject' command in the Clerk.

    Spawn an object and ensure it exists, then delete it and ensure it does not
    exist anymore.
    """
    killAzrael()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)

    # No objects must exist at this point.
    ok, (out,) = clerk.getAllObjectIDs()
    assert (ok, out) == (True, [])

    # Spawn two default objects.
    sv = bullet_data.BulletData()
    templateID = '_templateNone'.encode('utf8')
    ok, (objID_0,) = clerk.spawn(None, templateID, sv)
    assert (ok, objID_0) == (True, int2id(1))
    ok, (objID_1,) = clerk.spawn(None, templateID, sv)
    assert (ok, objID_1) == (True, int2id(2))

    # Two objects must now exist.
    ok, (out,) = clerk.getAllObjectIDs()
    assert ok and (len(out) == 2)
    assert (objID_0 in out) and (objID_1 in out)

    # Delete the first object.
    ok, (out, ) = clerk.deleteObject(objID_0)
    assert ok

    # Only the second object must still exist.
    ok, (out,) = clerk.getAllObjectIDs()
    assert (ok, out) == (True, [objID_1])

    # Deleting the same object again must result in an error.
    ok, _ = clerk.deleteObject(objID_0)
    assert not ok

    # Delete the second object.
    ok, _ = clerk.deleteObject(objID_1)
    assert ok
    assert clerk.getAllObjectIDs() == (True, ([],))

    print('Test passed')


def test_get_statevar():
    """
    Test the 'get_statevar' command in the Clerk.
    """
    killAzrael()

    # Test parameters and constants.
    objID_1 = int2id(1)
    objID_2 = int2id(2)
    sv_1 = bullet_data.BulletData(position=np.arange(3), velocityLin=[2, 4, 6])
    sv_2 = bullet_data.BulletData(position=[2, 4, 6], velocityLin=[6, 8, 10])
    templateID = '_templateNone'.encode('utf8')

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)

    # Retrieve the SV for a non-existing ID.
    ok, ret = clerk.getStateVariables([int2id(10)])
    assert (ok, ret) == (True, ([int2id(10)], [None]))

    # Spawn a new object. It must have ID=1.
    ok, (ret,) = clerk.spawn(None, templateID, sv_1)
    assert (ok, ret) == (True, objID_1)

    # Retrieve the SV for a non-existing ID --> must fail.
    ok, ret = clerk.getStateVariables([int2id(10)])
    assert (ok, ret) == (True, ([int2id(10)], [None]))

    # Retrieve the SV for the existing ID=1.
    ok, (ret_objIDs, ret_SVs) = clerk.getStateVariables([objID_1])
    assert (ok, len(ret_objIDs), len(ret_SVs)) == (True, 1, 1)
    assert ret_objIDs == [objID_1]
    assert ret_SVs[0] == sv_1

    # Spawn a second object.
    ok, (ret,) = clerk.spawn(None, templateID, sv_2)
    assert (ok, ret) == (True, objID_2)

    # Retrieve the state variables for both objects individually.
    for objID, ref_sv in zip([objID_1, objID_2], [sv_1, sv_2]):
        ok, (ret_objIDs, ret_SVs) = clerk.getStateVariables([objID])
        assert (ok, len(ret_objIDs), len(ret_SVs)) == (True, 1, 1)
        assert ret_objIDs == [objID]
        assert ret_SVs[0] == ref_sv

    # Retrieve the state variables for both objects at once.
    ok, (ret_objIDs, ret_SVs) = clerk.getStateVariables([objID_1, objID_2])
    assert (ok, len(ret_objIDs), len(ret_SVs)) == (True, 2, 2)
    assert ret_objIDs == [objID_1, objID_2]
    assert ret_SVs[0] == sv_1
    assert ret_SVs[1] == sv_2

    print('Test passed')


def test_set_force():
    """
    Set and retrieve force and torque values.
    """
    killAzrael()

    # Parameters and constants for this test.
    id_1 = int2id(1)
    sv = bullet_data.BulletData()
    force = np.array([1, 2, 3], np.float64)
    relpos = np.array([4, 5, 6], np.float64)

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)

    # Invalid/non-existing ID.
    ok, ret = clerk.setForce(int2id(0), force, relpos)
    assert (ok, ret) == (False, 'ID does not exist')

    # Spawn a new object. It must have ID=1.
    templateID = '_templateNone'.encode('utf8')
    ok, (ret,) = clerk.spawn(None, templateID, sv)
    assert (ok, ret) == (True, id_1)

    # Apply the force.
    ok, (ret, ) = clerk.setForce(id_1, force, relpos)
    assert (ok, ret) == (True, '')

    ok, ret_force, ret_torque = btInterface.getForceAndTorque(id_1)
    assert ok
    assert np.array_equal(ret_force, force)
    assert np.array_equal(ret_torque, np.cross(relpos, force))

    print('Test passed')


def test_add_get_template():
    """
    Add a new object to the templateID DB and query it again.
    """
    killAzrael()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)

    # Request and invalid ID.
    ok, out = clerk.getTemplate('blah'.encode('utf8'))
    assert not ok

    # Clerk has a few default objects. This one has no collision shape...
    ok, out = clerk.getTemplate('_templateNone'.encode('utf8'))
    assert ok
    assert np.array_equal(out[0], np.array([0, 1, 1, 1]))

    # ... this one is a sphere...
    ok, out = clerk.getTemplate('_templateSphere'.encode('utf8'))
    assert ok
    assert np.array_equal(out[0], np.array([3, 1, 1, 1]))

    # ... and this one is a cube.
    ok, out = clerk.getTemplate('_templateCube'.encode('utf8'))
    assert ok
    assert np.array_equal(out[0], np.array([4, 1, 1, 1]))

    # Convenience.
    cs = np.array([1, 2, 3, 4], np.float64)
    vert = np.arange(9).astype(np.float64)
    uv = np.array([9, 10], np.float64)
    rgb = np.array([1, 2, 250], np.uint8)
    templateID = 't1'.encode('utf8')

    # Attempt to add a template where the number of vertices is not a multiple
    # of 9. This must fail.
    ok, _ = clerk.addTemplate(templateID, cs, vert[:-1], uv, rgb, [], [])
    assert (ok, _) == (False, 'Number of vertices must be a multiple of Nine')

    # Add valid template. This must succeed.
    ok, _ = clerk.addTemplate(templateID, cs, vert, uv, rgb, [], [])
    assert ok

    # Attempt to add another template with the same name. This must fail.
    ok, _ = clerk.addTemplate(templateID, 2 * cs, 2 * vert, uv, rgb, [], [])
    assert not ok

    # Fetch the just added template again and verify CS, vertices, UV, and RGB.
    ok, out = clerk.getTemplate(templateID)
    assert ok
    assert np.array_equal(out[0], cs)
    assert np.array_equal(out[1], vert)
    assert np.array_equal(out[2], uv)
    assert np.array_equal(out[3], rgb)

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
    templateID = 't2'.encode('utf8')
    ok, _ = clerk.addTemplate(templateID, cs, vert, uv, rgb, [b0, b1], [f0])

    # Retrieve the just created object and verify the CS and geometry.
    ok, out = clerk.getTemplate(templateID)
    assert ok
    assert np.array_equal(out[0], cs)
    assert np.array_equal(out[1], vert)
    assert np.array_equal(out[2], uv)
    assert np.array_equal(out[3], rgb)

    # The template must also feature two boosters and one factory.
    assert len(out[4]) == 2
    assert len(out[5]) == 1

    # Explicitly verify the booster- and factory units. The easisest (albeit
    # not most readable) way to do the comparison is to convert the unit
    # descriptions (which are named tuples) to byte strings and compare those.
    out_boosters = [_.tostring() for _ in out[4]]
    out_factories = [_.tostring() for _ in out[5]]
    assert b0.tostring() in out_boosters
    assert b1.tostring() in out_boosters
    assert f0.tostring() in out_factories

    print('Test passed')


def test_add_get_template_AABB():
    """
    Similarly to test_add_get_template but focuses exclusively on the AABB.
    """
    killAzrael()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)

    # Convenience.
    cs = np.array([1, 2, 3, 4], np.float64)
    uv = rgb = np.zeros([])
    tID1, tID2 = 't1'.encode('utf8'), 't2'.encode('utf8')

    # Manually specify the vertices.
    vert = np.array([-4, 0, 0,
                     1, 2, 3,
                     4, 5, 6], np.float64)
    max_sidelen = max(8, 5, 6)

    # Add template and retrieve it again.
    ok, _ = clerk.addTemplate(tID1, cs, vert, uv, rgb, [], [])
    assert ok
    ok, out = clerk.getTemplate(tID1)
    assert ok

    # The largest AABB side length must be roughly "sqrt(3) * max_sidelen".
    assert (out[6] - np.sqrt(3.1) * max_sidelen) < 1E-10

    # Repeat the experiment with a larger mesh.
    vert = np.array([0, 0, 0,
                     1, 2, 3,
                     4, 5, 6,
                     8, 2, 7,
                    -5, -9, 8,
                     3, 2, 3], np.float64)
    max_sidelen = max(8, 14, 8)

    # Add template and retrieve it again.
    ok, _ = clerk.addTemplate(tID2, cs, vert, uv, rgb, [], [])
    assert ok
    ok, out = clerk.getTemplate(tID2)
    assert ok

    # The largest AABB side length must be roughly "sqrt(3) * max_sidelen".
    assert (out[6] - np.sqrt(3.1) * max_sidelen) < 1E-10

    print('Test passed')


def test_get_object_template_id():
    """
    Spawn two objects from different templates. Then query the template ID
    based on the object ID.
    """
    killAzrael()

    # Parameters and constants for this test.
    id_0, id_1 = int2id(1), int2id(2)
    templateID_0 = '_templateNone'.encode('utf8')
    templateID_1 = '_templateCube'.encode('utf8')
    sv = bullet_data.BulletData()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)

    # Spawn a new object. It must have ID=1.
    ok, (ctrl_id,) = clerk.spawn(None, templateID_0, sv)
    assert (ok, ctrl_id) == (True, id_0)

    # Spawn another object from a different template.
    ok, (ctrl_id,) = clerk.spawn(None, templateID_1, sv)
    assert (ok, ctrl_id) == (True, id_1)

    # Retrieve template of first object.
    ok, (ret,) = clerk.getTemplateID(id_0)
    assert (ok, ret) == (True, templateID_0)

    # Retrieve template of second object.
    ok, (ret,) = clerk.getTemplateID(id_1)
    assert (ok, ret) == (True, templateID_1)

    # Attempt to retrieve a non-existing object.
    ok, ret = clerk.getTemplateID(int2id(100))
    assert not ok

    # Shutdown.
    killAzrael()
    print('Test passed')


def test_controlParts_invalid_commands():
    """
    Send invalid control commands to object.
    """
    killAzrael()

    # Parameters and constants for this test.
    objID_1, objID_2 = int2id(1), int2id(2)
    templateID_1 = '_templateNone'.encode('utf8')
    sv = bullet_data.BulletData()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)

    # Create a fake object. We will not need it but for this test one must
    # exist as other commands would otherwise fail.
    ok, (ctrl_id,) = clerk.spawn(None, templateID_1, sv)
    assert (ok, ctrl_id) == (True, objID_1)
    del ok, ctrl_id

    # Create commands for a Booster and a Factory.
    cmd_b = parts.CmdBooster(partID=0, force=0.2)
    cmd_f = parts.CmdFactory(partID=0, exit_speed=0.5)

    # Call 'controlParts'. This must fail because the chosen template has no
    # boosters or factory units.
    ok, msg = clerk.controlParts(objID_1, [cmd_b], [])
    assert not ok

    # Must fail: objects has no factory.
    ok, msg = clerk.controlParts(objID_1, [], [cmd_f])
    assert not ok

    # Must fail: objects still has neither a booster nor a factory.
    ok, msg = clerk.controlParts(objID_1, [cmd_b], [cmd_f])
    assert not ok

    # Must fail: Factory command where a Booster is expected and vice versa.
    ok, msg = clerk.controlParts(objID_1, [cmd_f], [cmd_b])
    assert not ok

    # Must fail: Booster command among Factory commands.
    ok, msg = clerk.controlParts(objID_1, [], [cmd_f, cmd_b])
    assert not ok

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
    vert = np.arange(9).astype(np.float64)
    uv = np.array([9, 10], np.float64)
    rgb = np.array([1, 2, 250], np.uint8)
    templateID_2 = 't1'.encode('utf8')
    ok, _ = clerk.addTemplate(templateID_2, cs, vert, uv, rgb, [b0], [f0])
    assert ok

    # ... and spawn an instance thereof.
    sv = bullet_data.BulletData()
    ok, (ctrl_id,) = clerk.spawn(None, templateID_2, sv)
    assert (ok, ctrl_id) == (True, objID_2)
    del ok, ctrl_id

    # Create the commands to let each factory spawn an object.
    cmd_b = parts.CmdBooster(partID=0, force=0.5)
    cmd_f = parts.CmdFactory(partID=0, exit_speed=0.5)

    # Valid commands: simply verify the new template works correctly.
    ok, spawnedIDs = clerk.controlParts(objID_2, [cmd_b], [cmd_f])
    assert ok

    # Must fail: Booster where Factory is expected and vice versa.
    ok, msg = clerk.controlParts(objID_2, [cmd_f], [cmd_b])
    assert not ok

    # Must fail: every part can only receive one command per call.
    ok, spawnedIDs = clerk.controlParts(objID_2, [cmd_b, cmd_b], [])
    assert not ok
    ok, spawnedIDs = clerk.controlParts(objID_2, [], [cmd_f, cmd_f])
    assert not ok

    # Clean up.
    killAzrael()
    print('Test passed')


def test_controlParts_Boosters_notmoving():
    """
    Create a template with boosters and send control commands to it.

    The parent object does not move in the world coordinate system.
    """
    killAzrael()

    # Parameters and constants for this test.
    objID_1 = int2id(1)
    tNone = '_templateNone'.encode('utf8')
    sv = bullet_data.BulletData()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)

    # ------------------------------------------------------------------------
    # Define an object with a booster and spawn it.
    # ------------------------------------------------------------------------

    # Constants for the new template object.
    cs = np.array([1, 2, 3, 4], np.float64)
    vert = np.arange(9).astype(np.float64)
    uv = np.array([9, 10], np.float64)
    rgb = np.array([1, 2, 250], np.uint8)

    dir_0 = np.array([1, 0, 0], np.float64)
    dir_1 = np.array([0, 1, 0], np.float64)
    pos_0 = np.array([1, 1, -1], np.float64)
    pos_1 = np.array([-1, -1, 0], np.float64)

    # Define two boosters.
    b0 = parts.Booster(partID=0, pos=pos_0, direction=dir_0, max_force=0.5)
    b1 = parts.Booster(partID=1, pos=pos_1, direction=dir_1, max_force=0.5)

    # Create a new template in Azrael of an object with two boosters.
    templateID_2 = 't1'.encode('utf8')
    ok, _ = clerk.addTemplate(templateID_2, cs, vert, uv, rgb, [b0, b1], [])

    # Spawn the object.
    ok, (ctrl_id,) = clerk.spawn(None, templateID_2, sv)
    assert (ok, ctrl_id) == (True, objID_1)
    del ok, ctrl_id

    # ------------------------------------------------------------------------
    # Engage the boosters and verify the total force exerted on the object.
    # ------------------------------------------------------------------------

    # Create the commands to activate both boosters with a different force.
    forcemag_0, forcemag_1 = 0.2, 0.4
    cmd_0 = parts.CmdBooster(partID=0, force=forcemag_0)
    cmd_1 = parts.CmdBooster(partID=1, force=forcemag_1)

    # Send booster commands to Clerk.
    ok, msg = clerk.controlParts(objID_1, [cmd_0, cmd_1], [])
    assert ok

    # Manually compute the total force and torque exerted by the boosters.
    forcevec_0, forcevec_1 = forcemag_0 * dir_0, forcemag_1 * dir_1
    tot_force = forcevec_0 + forcevec_1
    tot_torque = np.cross(pos_0, forcevec_0) + np.cross(pos_1, forcevec_1)

    # Query the torque and force from Azrael and verify they are correct.
    ok, ret_force, ret_torque = btInterface.getForceAndTorque(objID_1)
    assert ok
    assert np.array_equal(ret_force, tot_force)
    assert np.array_equal(ret_torque, tot_torque)

    # ------------------------------------------------------------------------
    # Send an empty command. The total force and torque must not change, ie
    # nothing must happen at all.
    # ------------------------------------------------------------------------

    # Send booster commands to Clerk.
    ok, msg = clerk.controlParts(objID_1, [], [])
    assert ok

    # Query the torque and force from Azrael and verify they are correct.
    ok, ret_force, ret_torque = btInterface.getForceAndTorque(objID_1)
    assert ok
    assert np.array_equal(ret_force, tot_force)
    assert np.array_equal(ret_torque, tot_torque)

    # Clean up.
    killAzrael()
    print('Test passed')


def test_controlParts_Factories_notmoving():
    """
    Create a template with factories and send control commands to them.

    The parent object does not move in the world coordinate system.
    """
    killAzrael()

    # Parameters and constants for this test.
    objID_1 = int2id(1)
    sv = bullet_data.BulletData()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)

    # ------------------------------------------------------------------------
    # Create a template with two factories and spawn it.
    # ------------------------------------------------------------------------

    # Constants for the new template object.
    cs = np.array([1, 2, 3, 4], np.float64)
    vert = np.arange(9).astype(np.float64)
    uv = np.array([9, 10], np.float64)
    rgb = np.array([1, 2, 250], np.uint8)
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
    templateID_2 = 't1'.encode('utf8')
    ok, _ = clerk.addTemplate(templateID_2, cs, vert, uv, rgb, [], [f0, f1])
    assert ok

    # ... and spawn an instance thereof.
    ok, (ctrl_id,) = clerk.spawn(None, templateID_2, sv)
    assert (ok, ctrl_id) == (True, objID_1)
    del ok, ctrl_id

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
    # given to the controller object.
    ok, spawnedIDs = clerk.controlParts(objID_1, [], [cmd_0, cmd_1])
    assert ok
    spawnedIDs = spawnedIDs[0]
    assert len(spawnedIDs) == 2
    assert spawnedIDs == [int2id(2), int2id(3)]

    # Query the state variables of the objects spawned by the factories.
    ok, (ret_objIDs, ret_SVs) = clerk.getStateVariables(spawnedIDs)
    assert (ok, len(ret_objIDs)) == (True, 2)
    ret_SVs = dict(zip(ret_objIDs, ret_SVs))

    # Ensure the position, velocity, and orientation of the spawned objects are
    # correct.
    sv_2, sv_3 = [ret_SVs[_] for _ in spawnedIDs]
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

    # Parameters and constants for this test.
    objID_1 = int2id(1)
    pos_parent = np.array([1, 2, 3], np.float64)
    vel_parent = np.array([4, 5, 6], np.float64)
    cs = np.array([1, 2, 3, 4], np.float64)
    vert = np.arange(9).astype(np.float64)
    uv = np.array([9, 10], np.float64)
    rgb = np.array([1, 2, 250], np.uint8)
    dir_0 = np.array([1, 0, 0], np.float64)
    dir_1 = np.array([0, 1, 0], np.float64)
    pos_0 = np.array([1, 1, -1], np.float64)
    pos_1 = np.array([-1, -1, 0], np.float64)

    # State variables for parent object.
    sv = bullet_data.BulletData(position=pos_parent, velocityLin=vel_parent)

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)

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
    templateID_2 = 't1'.encode('utf8')
    ok, _ = clerk.addTemplate(templateID_2, cs, vert, uv, rgb, [], [f0, f1])
    assert ok

    # ... and spawn an instance thereof.
    ok, (ctrl_id,) = clerk.spawn(None, templateID_2, sv)
    assert (ok, ctrl_id) == (True, objID_1)
    del ok, ctrl_id

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
    # given to the controller object.
    ok, spawnedIDs = clerk.controlParts(objID_1, [], [cmd_0, cmd_1])
    assert ok
    spawnedIDs = spawnedIDs[0]
    assert len(spawnedIDs) == 2
    assert spawnedIDs == [int2id(2), int2id(3)]

    # Query the state variables of the objects spawned by the factories.
    ok, (ret_objIDs, ret_SVs) = clerk.getStateVariables(spawnedIDs)
    assert (ok, len(ret_objIDs)) == (True, 2)
    ret_SVs = dict(zip(ret_objIDs, ret_SVs))

    # Ensure the position, velocity, and orientation of the spawned objects are
    # correct.
    sv_2, sv_3 = [ret_SVs[_] for _ in spawnedIDs]
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

    # Parameters and constants for this test.
    objID_1 = int2id(1)
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

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)

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
    ok, _ = clerk.addTemplate(
        templateID_2, cs, vert, uv, rgb, [b0, b1], [f0, f1])
    assert ok

    # ... and spawn an instance thereof.
    ok, (ctrl_id,) = clerk.spawn(None, templateID_2, sv)
    assert (ok, ctrl_id) == (True, objID_1)
    del ok, ctrl_id

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
    # the simulation. These IDS must be '3' and '4', since ID 1 was already
    # given to the controller object.
    ok, spawnIDs = clerk.controlParts(objID_1, [cmd_0, cmd_1], [cmd_2, cmd_3])
    assert ok
    spawnIDs = spawnIDs[0]
    assert len(spawnIDs) == 2
    assert spawnIDs == [int2id(2), int2id(3)]

    # Query the state variables of the objects spawned by the factories.
    ok, (ret_objIDs, ret_SVs) = clerk.getStateVariables(spawnIDs)
    assert (ok, len(ret_objIDs)) == (True, 2)
    ret_SVs = dict(zip(ret_objIDs, ret_SVs))

    # Verify the position and velocity of the spawned objects is correct.
    sv_2, sv_3 = [ret_SVs[_] for _ in spawnIDs]
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
    ok, ret_force, ret_torque = btInterface.getForceAndTorque(objID_1)
    assert ok
    assert np.array_equal(ret_force, tot_force)
    assert np.array_equal(ret_torque, tot_torque)

    # Clean up.
    killAzrael()
    print('Test passed')


def test_get_all_objectids():
    """
    Test getAllObjects.
    """
    killAzrael()

    # Parameters and constants for this test.
    objID_1, objID_2 = int2id(1), int2id(2)
    templateID = '_templateNone'.encode('utf8')
    sv = bullet_data.BulletData()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)

    # So far no objects have been spawned.
    ok, (out,) = clerk.getAllObjectIDs()
    assert (ok, out) == (True, [])

    # Spawn a new object.
    ok, (ret,) = clerk.spawn(None, templateID, sv)
    assert (ok, ret) == (True, objID_1)

    # The object list must now contain the ID of the just spawned object.
    ok, (out,) = clerk.getAllObjectIDs()
    assert (ok, out) == (True, [objID_1])

    # Spawn another object.
    ok, (ret,) = clerk.spawn(None, templateID, sv)
    assert (ok, ret) == (True, objID_2)

    # The object list must now contain the ID of both spawned objects.
    ok, (out,) = clerk.getAllObjectIDs()
    assert (ok, out) == (True, [objID_1, objID_2])

    # Kill all spawned Controller processes.
    killAzrael()
    print('Test passed')


def test_getGeometry():
    """
    Spawn an object and query its geometry.
    """
    killAzrael()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)

    # Convenience.
    cs = np.array([1, 2, 3, 4], np.float64)
    vert = np.arange(9).astype(np.float64)
    uv = np.array([9, 10], np.float64)
    rgb = np.array([1, 2, 250], np.uint8)
    templateID = 't1'.encode('utf8')
    sv = bullet_data.BulletData()

    # Add a valid template and verify it now exists in Azrael.
    ok, _ = clerk.addTemplate(templateID, cs, vert, uv, rgb, [], [])
    assert ok
    ok, _ = clerk.getTemplate(templateID)
    assert ok

    # Attempt to query the geometry of a non-existing object.
    ok, _ = clerk.getGeometry(int2id(1))
    assert not ok

    # Spawn an object from the previously added template.
    ok, (objID,) = clerk.spawn(None, templateID, sv)
    assert ok

    # Query the geometry of the object.
    ok, (ret_vert, ret_uv, ret_rgb) = clerk.getGeometry(objID)
    assert ok
    assert np.array_equal(vert, ret_vert)
    assert np.array_equal(uv, ret_uv)
    assert np.array_equal(rgb, ret_rgb)

    # Delete the object.
    ok, _ = clerk.deleteObject(objID)
    assert ok

    # Attempt to query the geometry of the now deleted object.
    ok, _ = clerk.getGeometry(objID)
    assert not ok

    # Kill all spawned Controller processes.
    killAzrael()
    print('Test passed')


def test_instanceDB_checksum():
    """
    Spawn and object and verify that the checksum changes whenever the geometry
    is modified.
    """
    killAzrael()

    # Instantiate a Clerk.
    clerk = azrael.clerk.Clerk(reset=True)

    # Convenience.
    cs = np.array([1, 2, 3, 4], np.float64)
    vert = np.arange(9).astype(np.float64)
    uv = np.array([9, 10], np.float64)
    rgb = np.array([1, 2, 250], np.uint8)
    templateID = 't1'.encode('utf8')
    sv = bullet_data.BulletData()

    # Add a valid template and verify it now exists in Azrael.
    ok, _ = clerk.addTemplate(templateID, cs, vert, uv, rgb, [], [])
    assert ok

    # Spawn two objects from the previously defined template.
    ok, (objID0,) = clerk.spawn(None, templateID, sv)
    assert ok
    ok, (objID1,) = clerk.spawn(None, templateID, sv)
    assert ok

    # Query the checksum of the objects.
    ok, (ret_objIDs, ret_SVs) = clerk.getStateVariables([objID0, objID1])
    assert ok
    assert (objID0 in ret_objIDs) and (objID1 in ret_objIDs)
    checksums = {ret_objIDs[0]: ret_SVs[0].checksumGeometry,
                 ret_objIDs[1]: ret_SVs[1].checksumGeometry}

    # Modify the geometry of the first object.
    ok, _ = clerk.setGeometry(objID0, 2 * vert, 2 * uv, 2 * rgb)
    assert ok

    # Verify that the checksum of the first object has changed and that of the
    # second object has not.
    ok, (ret_objIDs, ret_SVs) = clerk.getStateVariables([objID0])
    assert (ok, ret_objIDs) == (True, [objID0])
    assert checksums[objID0] != ret_SVs[0].checksumGeometry
    ok, (ret_objIDs, ret_SVs) = clerk.getStateVariables([objID1])
    assert (ok, ret_objIDs) == (True, [objID1])
    assert checksums[objID1] == ret_SVs[0].checksumGeometry

    # Kill all spawned Controller processes.
    killAzrael()
    print('Test passed')


if __name__ == '__main__':
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
    test_add_get_template()
    test_set_force()
    test_send_receive_message()
    test_connect()
    test_ping()
    test_invalid()
    test_get_id()
