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
import json
import pytest
import urllib.request

import numpy as np

import azrael.igor
import azrael.util
import azrael.clerk
import azrael.clacks
import azrael.client
import azrael.dibbler
import azrael.wsclient
import azrael.types as types
import azrael.config as config
import azrael.database as database

from IPython import embed as ipshell
from azrael.types import RetVal, Template
from azrael.types import FragDae, FragRaw
from azrael.test.test import getFragRaw, getFragDae, getFragNone, getTemplate
from azrael.test.test import getLeonard, killAzrael, getP2P, get6DofSpring2
from azrael.test.test import getCSEmpty, getCSBox, getCSSphere, getRigidBody


class TestClient:
    @classmethod
    def setup_class(cls):
        # Kill all lingering Azrael processes.
        killAzrael()

        # Start a Clerk and Clacks instance.
        cls.clerk = azrael.clerk.Clerk()
        cls.clacks = azrael.clacks.ClacksServer()
        cls.clerk.start()
        cls.clacks.start()

        # Dibbler.
        cls.dibbler = azrael.dibbler.Dibbler()

        # Create a ZMQ- and Websocket client.
        client_zmq = azrael.client.Client()
        client_ws = azrael.wsclient.WSClient(
            ip=config.addr_clacks, port=config.port_clacks, timeout=1)
        assert client_ws.ping()
        cls.clients = {'ZeroMQ': client_zmq, 'Websocket': client_ws}

    @classmethod
    def teardown_class(cls):
        # Terminate the processes.
        cls.clerk.terminate()
        cls.clacks.terminate()

        cls.clerk.join(5)
        cls.clacks.join(5)
        del cls.clients, cls.clerk, cls.clacks

        # Kill all lingering Azrael processes.
        killAzrael()

    def setup_method(self, method):
        # Reset the database.
        azrael.database.init()

        # Flush the model database.
        self.dibbler.reset()

        # Insert default objects. None of them has an actual geometry but
        # their collision shapes are: none, sphere, box.
        clerk = azrael.clerk.Clerk()

        frag = {'NoName': getFragRaw()}
        rbs_empty = getRigidBody(cshapes={'csempty': getCSEmpty()})
        rbs_sphere = getRigidBody(cshapes={'cssphere': getCSSphere()})
        rbs_box = getRigidBody(cshapes={'csbox': getCSBox()})
        t1 = getTemplate('_templateEmpty', rbs=rbs_empty, fragments=frag)
        t2 = getTemplate('_templateSphere', rbs=rbs_sphere, fragments=frag)
        t3 = getTemplate('_templateBox', rbs=rbs_box, fragments=frag)
        ret = clerk.addTemplates([t1, t2, t3])
        assert ret.ok

    def teardown_method(self, method):
        # Clean up.
        azrael.database.init()
        self.dibbler.reset()

    def test_ping(self):
        """
        Send a ping to the Clerk and check the response is correct.
        """
        client = self.clients['ZeroMQ']
        assert client.ping() == (True, None, 'pong clerk')

    @pytest.mark.parametrize('client_type', ['Websocket', 'ZeroMQ'])
    def test_get_template(self, client_type):
        """
        Spawn some default templates and query their template IDs.
        """
        # Get the client for this test.
        client = self.clients[client_type]

        # Parameters and constants for this test.
        objID_1, objID_2 = 1, 2
        templateID_0 = '_templateEmpty'
        templateID_1 = '_templateBox'

        # Spawn a new object. Its ID must be 1.
        new_objs = [
            {'templateID': templateID_0, 'rbs': {'position': [0, 0, 0]}},
            {'templateID': templateID_1, 'rbs': {'position': [0, 0, 0]}},
        ]
        ret = client.spawn(new_objs)
        assert ret.ok and ret.data == [objID_1, objID_2]

        # Retrieve template of first object.
        ret = client.getTemplateID(objID_1)
        assert ret.ok and (ret.data == templateID_0)

        # Retrieve template of second object.
        ret = client.getTemplateID(objID_2)
        assert ret.ok and (ret.data == templateID_1)

        # Attempt to retrieve a non-existing object.
        assert not client.getTemplateID(100).ok

    @pytest.mark.parametrize('client_type', ['Websocket', 'ZeroMQ'])
    def test_create_fetch_template(self, client_type):
        """
        Add a new object to the templateID DB and query it again.
        """
        # Get the client for this test.
        client = self.clients[client_type]

        # Request an invalid ID.
        assert not client.getTemplates(['blah']).ok

        # Clerk has default objects. This one has an empty collision shape...
        name_1 = '_templateEmpty'
        ret = client.getTemplates([name_1])
        assert ret.ok and (len(ret.data) == 1)
        assert ret.data[name_1]['template'].rbs.cshapes == {'csempty': getCSEmpty()}

        # ... this one is a sphere...
        name_2 = '_templateSphere'
        ret = client.getTemplates([name_2])
        assert ret.ok and (len(ret.data) == 1)
        assert ret.data[name_2]['template'].rbs.cshapes == {'cssphere': getCSSphere()}

        # ... and this one is a box.
        name_3 = '_templateBox'
        ret = client.getTemplates([name_3])
        assert ret.ok and (len(ret.data) == 1)
        assert ret.data[name_3]['template'].rbs.cshapes == {'csbox': getCSBox()}

        # Retrieve all three again but with a single call.
        ret = client.getTemplates([name_1, name_2, name_3])
        assert ret.ok
        assert set(ret.data.keys()) == set((name_1, name_2, name_3))
        assert ret.data[name_2]['template'].rbs.cshapes == {'cssphere': getCSSphere()}
        assert ret.data[name_3]['template'].rbs.cshapes == {'csbox': getCSBox()}
        assert ret.data[name_1]['template'].rbs.cshapes == {'csempty': getCSEmpty()}

        # Add a new object template.
        frag = {'bar': getFragRaw()}
        body = getRigidBody()
        temp_name = 't1'
        temp_orig = getTemplate(temp_name, rbs=body, fragments=frag)
        assert client.addTemplates([temp_orig]).ok

        # Fetch the just added template again and verify its content (skip the
        # geometry because it contains only meta information and will be
        # checked afterwards).
        ret = client.getTemplates([temp_name])
        assert ret.ok and (len(ret.data) == 1)
        temp_out = ret.data[temp_name]['template']
        assert temp_out.boosters == temp_orig.boosters
        assert temp_out.factories == temp_orig.factories
        assert temp_out.rbs == temp_orig.rbs

        # Fetch the geometry from the web server and verify it.
        ret = client.getTemplateGeometry(ret.data[temp_name])
        assert ret.ok
        assert ret.data['bar'] == frag['bar'].fragdata
        del ret, temp_out, temp_orig

        # Define a new object with two boosters and one factory unit.
        # The 'boosters' and 'factories' arguments are a list of named
        # tuples. Their first argument is the unit ID (Azrael does not
        # automatically assign any).
        boosters = {
            '0': types.Booster(pos=(0, 0, 0), direction=(0, 0, 1),
                               minval=0, maxval=0.5, force=0),
            '1': types.Booster(pos=(0, 0, 0), direction=(0, 0, 1),
                               minval=0, maxval=0.5, force=0),
        }
        factories = {
            '0': types.Factory(pos=(0, 0, 0), direction=(0, 0, 1),
                               templateID='_templateBox',
                               exit_speed=(0.1, 0.5))
        }

        # Attempt to query the geometry of a non-existing object.
        assert client.getFragments([1]) == (True, None, {1: None})

        # Define a new template, add it to Azrael, spawn it, and record its
        # object ID.
        body = getRigidBody(cshapes={'csbox': getCSBox()})
        temp = getTemplate('t2',
                           rbs=body,
                           fragments=frag,
                           boosters=boosters,
                           factories=factories)
        assert client.addTemplates([temp]).ok
        init = {'templateID': temp.aid,
                'rbs': {'position': (0, 0, 0)}}
        ret = client.spawn([init])
        assert ret.ok and len(ret.data) == 1
        objID = ret.data[0]

        # Retrieve- and verify the geometry of the just spawned object.
        ret = client.getFragments([objID])
        assert ret.ok
        assert ret.data[objID]['bar']['fragtype'] == 'RAW'

        # Retrieve the entire template and verify the CS and geometry, and
        # number of boosters/factories.
        ret = client.getTemplates([temp.aid])
        assert ret.ok and (len(ret.data) == 1)
        t_data = ret.data[temp.aid]['template']
        assert t_data.rbs == body
        assert t_data.boosters == temp.boosters
        assert t_data.factories == temp.factories

        # Fetch the geometry from the Web server and verify it is correct.
        ret = client.getTemplateGeometry(ret.data[temp.aid])
        assert ret.ok
        assert ret.data['bar'] == frag['bar'].fragdata

    @pytest.mark.parametrize('client_type', ['ZeroMQ', 'Websocket'])
    def test_spawn_and_delete_one_object(self, client_type):
        """
        Ask Clerk to spawn one object.
        """
        # Get the client for this test.
        client = self.clients[client_type]

        # Constants and parameters for this test.
        objID, templateID = 1, '_templateEmpty'

        # Spawn a new object from templateID. The new object must have objID=1.
        init = {'templateID': templateID,
                'rbs': {'position': (0, 0, 0)}}
        ret = client.spawn([init])
        assert ret.ok and ret.data == [objID]

        # Attempt to spawn a non-existing template.
        assert not client.spawn([{'templateID': 'blah'}]).ok

        # Send invalid data to 'spawn'.
        assert not client.spawn([{'blah': 'blah'}]).ok

        # Exactly one object must exist at this point.
        ret = client.getAllObjectIDs()
        assert (ret.ok, ret.data) == (True, [objID])

        # Attempt to delete a non-existing object. This must silently fail.
        assert client.removeObject(100).ok
        ret = client.getAllObjectIDs()
        assert (ret.ok, ret.data) == (True, [objID])

        # Delete an existing object.
        assert client.removeObject(objID).ok
        ret = client.getAllObjectIDs()
        assert (ret.ok, ret.data) == (True, [])

    @pytest.mark.parametrize('client_type', ['Websocket', 'ZeroMQ'])
    def test_spawn_and_get_state_variables(self, client_type):
        """
        Spawn a new object and query its state variables.
        """
        # Get the client for this test.
        client = self.clients[client_type]

        # Constants and parameters for this test.
        templateID, objID_1 = '_templateEmpty', 1

        # Query the state variables for a non existing object.
        objID = 100
        assert client.getRigidBodies(objID) == (True, None, {objID: None})
        del objID

        # Instruct Clerk to spawn a new object. Its objID must be '1'.
        pos, vlin = (0, 1, 2), (-3, 4, -5)
        body = getRigidBody(position=pos, velocityLin=vlin)
        init = {
            'templateID': templateID,
            'rbs': {'position': body.position,
                    'velocityLin': body.velocityLin},
        }
        ret = client.spawn([init])
        assert ret.ok and ret.data == [objID_1]

        # The body parameters of the new object must match the inital state
        # (plus the tweaks provided to the spawn command).
        ret = client.getRigidBodies(objID_1)
        assert ret.ok and (set(ret.data.keys()) == {1})
        assert ret.data[objID_1]['rbs'].position == pos
        assert ret.data[objID_1]['rbs'].velocityLin == vlin

        # Same test but this time get all of them.
        assert client.getRigidBodies(None) == ret

        # Query just the state variables instead of the entire rigid body.
        assert client.getObjectStates(None) == client.getObjectStates([objID_1])
        ret = client.getObjectStates([objID_1])
        assert ret.ok
        r = ret.data[objID_1]
        assert set(r.keys()) == set(['rbs', 'frag'])
        r = ret.data[objID_1]['rbs']
        assert r['position'] == list(pos)
        assert r['velocityLin'] == list(vlin)

    @pytest.mark.parametrize('client_type', ['Websocket', 'ZeroMQ'])
    def test_getAllObjectIDs(self, client_type):
        """
        Ensure the getAllObjectIDs command reaches Clerk.
        """
        # Get the client for this test.
        client = self.clients[client_type]

        # Constants and parameters for this test.
        templateID, objID_1 = '_templateEmpty', 1

        # So far no objects have been spawned.
        ret = client.getAllObjectIDs()
        assert (ret.ok, ret.data) == (True, [])

        # Spawn a new object.
        init = {'templateID': templateID, 'rbs': {'position': (0, 0, 0)}}
        ret = client.spawn([init])
        assert ret.ok and ret.data == [objID_1]

        # The object list must now contain the ID of the just spawned object.
        ret = client.getAllObjectIDs()
        assert (ret.ok, ret.data) == (True, [objID_1])

    @pytest.mark.parametrize('client_type', ['Websocket', 'ZeroMQ'])
    def test_controlParts(self, client_type):
        """
        Create a template with boosters and factories. Then send control
        commands to them and ensure the applied forces, torques, and
        spawned objects are correct.

        In this test the parent object moves and is oriented away from its
        default.
        """
        # Get the client for this test.
        client = self.clients[client_type]

        # Reset the SV database and instantiate a Leonard.
        leo = getLeonard()

        # Parameters and constants for this test.
        objID_1 = 1
        pos_parent = [1, 2, 3]
        vel_parent = [4, 5, 6]

        # Part positions relative to parent.
        dir_0 = [0, 0, +2]
        dir_1 = [0, 0, -1]
        pos_0 = [0, 0, +3]
        pos_1 = [0, 0, -4]

        # Describes a rotation of 180 degrees around x-axis.
        orient_parent = [1, 0, 0, 0]

        # Part position in world coordinates if the parent is rotated by 180
        # degrees around the x-axis. The normalisation of the direction is
        # necessary because the parts will automatically normalise all
        # direction vectors, including dir_0 and dir_1 which are not unit
        # vectors.
        dir_0_out = -np.array(dir_0) / np.sum(abs(np.array(dir_0)))
        dir_1_out = -np.array(dir_1) / np.sum(abs(np.array(dir_1)))
        pos_0_out = -np.array(pos_0)
        pos_1_out = -np.array(pos_1)

        # State variable for parent. It has a position, speed, and is rotated
        # 180 degrees around the x-axis. This means the x-values of all forces
        # (boosters) and exit speeds of factory spawned objects must be
        # inverted.
        sv = getRigidBody(
            position=pos_parent,
            velocityLin=vel_parent,
            orientation=orient_parent)

        # ---------------------------------------------------------------------
        # Create a template with two factories and spawn it.
        # ---------------------------------------------------------------------

        # Define the parts.
        boosters = {
            '0': types.Booster(pos=pos_0, direction=dir_0,
                               minval=0, maxval=0.5, force=0),
            '1': types.Booster(pos=pos_1, direction=dir_1,
                               minval=0, maxval=1.0, force=0)
        }
        factories = {
            '0': types.Factory(pos=pos_0, direction=dir_0,
                               templateID='_templateBox',
                               exit_speed=[0.1, 0.5]),
            '1': types.Factory(pos=pos_1, direction=dir_1,
                               templateID='_templateSphere',
                               exit_speed=[1, 5])
        }

        # Define the template, add it to Azrael, and spawn an instance.
        temp = getTemplate('t1',
                           rbs=getRigidBody(),
                           boosters=boosters,
                           factories=factories)
        assert client.addTemplates([temp]).ok
        new_obj = {'templateID': temp.aid,
                   'rbs': {
                       'position': pos_parent,
                       'velocityLin': vel_parent,
                       'orientation': orient_parent}}
        ret = client.spawn([new_obj])
        assert ret.ok and (ret.data == [objID_1])
        del boosters, factories, temp, new_obj

        # ---------------------------------------------------------------------
        # Activate booster and factories and verify that the applied force and
        # torque is correct, as well as that the spawned objects have the
        # correct state variables attached to them.
        # ---------------------------------------------------------------------

        # Create the commands to let each factory spawn an object.
        exit_speed_0, exit_speed_1 = 0.2, 2
        forcemag_0, forcemag_1 = 0.2, 0.4
        cmd_b = {
            '0': types.CmdBooster(force_mag=forcemag_0),
            '1': types.CmdBooster(force_mag=forcemag_1),
        }
        cmd_f = {
            '0': types.CmdFactory(exit_speed=exit_speed_0),
            '1': types.CmdFactory(exit_speed=exit_speed_1),
        }

        # Send the commands and ascertain that the returned object IDs now
        # exist in the simulation. These IDs must be '2' and '3'.
        ret = client.controlParts(objID_1, cmd_b, cmd_f)
        id_2, id_3 = 2, 3
        assert (ret.ok, ret.data) == (True, [id_2, id_3])

        # Query the state variables of the objects spawned by the factories.
        ok, _, ret_SVs = client.getRigidBodies([id_2, id_3])
        assert (ok, len(ret_SVs)) == (True, 2)

        # Determine which body was spawned by which factory based on their
        # position. We do this by looking at their initial position which
        # *must* match one of the parents.
        body_2, body_3 = ret_SVs[id_2]['rbs'], ret_SVs[id_3]['rbs']
        if np.allclose(body_2.position, pos_1_out + pos_parent):
            body_2, body_3 = body_3, body_2

        # Verify the position and velocity of the spawned objects is correct.
        ac = np.allclose
        assert ac(body_2.velocityLin, exit_speed_0 * dir_0_out + vel_parent)
        assert ac(body_2.position, pos_0_out + pos_parent)
        assert ac(body_3.velocityLin, exit_speed_1 * dir_1_out + vel_parent)
        assert ac(body_3.position, pos_1_out + pos_parent)

        # Let Leonard sync its data and then verify it received the correct
        # total force and torque exerted by the boosters.
        leo.processCommandsAndSync()
        forcevec_0, forcevec_1 = forcemag_0 * dir_0_out, forcemag_1 * dir_1_out
        tot_force = forcevec_0 + forcevec_1
        tot_torque = (np.cross(pos_0_out, forcevec_0) +
                      np.cross(pos_1_out, forcevec_1))

        # Query the torque and force from Azrael and verify they are correct.
        leo_force, leo_torque = leo.totalForceAndTorque(objID_1)
        assert np.array_equal(leo_force, tot_force)
        assert np.array_equal(leo_torque, tot_torque)

    @pytest.mark.parametrize('client_type', ['Websocket', 'ZeroMQ'])
    def test_setFragments_raw(self, client_type):
        """
        Spawn a new object and modify its geometry at runtime.
        """
        # Get the client for this test.
        client = self.clients[client_type]

        # Convenience.
        objID = 1

        # Add a new template and spawn it.
        frag = {'bar': getFragRaw()}
        temp = getTemplate('t1', fragments=frag)
        assert client.addTemplates([temp]).ok

        new_obj = {'templateID': temp.aid,
                   'rbs': {'position': (1, 1, 1),
                           'velocityLin': (-1, -1, -1)}}
        ret = client.spawn([new_obj])
        assert ret.ok and ret.data == [objID]
        del temp, new_obj, ret

        # Query the SV to obtain the 'version' value.
        ret = client.getRigidBodies(objID)
        assert ret.ok
        version = ret.data[objID]['rbs'].version

        # Fetch-, modify-, update- and verify the geometry.
        ret = client.getFragments([objID])
        assert ret.ok
        assert ret.data[objID]['bar']['fragtype'] == 'RAW'

        # Download the fragment.
        base_url = 'http://{ip}:{port}'.format(
            ip=config.addr_clacks, port=config.port_clacks)
        url = base_url + ret.data[objID]['bar']['url_frag'] + '/model.json'
        for ii in range(10):
            assert ii < 8
            try:
                tmp = urllib.request.urlopen(url).readall()
                break
            except urllib.request.URLError:
                time.sleep(0.2)
        tmp = json.loads(tmp.decode('utf8'))
        assert FragRaw(**tmp) == frag['bar'].fragdata

        # Change the fragment geometries.
        cmd = {objID: {k: v._asdict() for (k, v) in frag.items()}}
        assert client.setFragments(cmd).ok

        ret = client.getFragments([objID])
        assert ret.ok
        assert ret.data[objID]['bar']['fragtype'] == 'RAW'

        # Download the fragment.
        url = base_url + ret.data[objID]['bar']['url_frag'] + '/model.json'
        tmp = urllib.request.urlopen(url).readall()
        tmp = json.loads(tmp.decode('utf8'))
        assert FragRaw(**tmp) == frag['bar'].fragdata

        # Ensure 'version' is different as well.
        ret = client.getRigidBodies(objID)
        assert ret.ok and (ret.data[objID]['rbs'].version != version)

    @pytest.mark.parametrize('client_type', ['Websocket', 'ZeroMQ'])
    def test_setFragments_dae(self, client_type):
        """
        Spawn a new object and modify its geometry at runtime.
        """
        # Get the client for this test.
        client = self.clients[client_type]

        # Get a Collada fragment.
        f_dae = {'f_dae': getFragDae()}

        # Add a new template and spawn it.
        temp = getTemplate('t1', fragments=f_dae)
        assert client.addTemplates([temp]).ok

        new_obj = {'templateID': temp.aid,
                   'rbs': {'position': (1, 1, 1), 'velocityLin': (-1, -1, -1)}}
        ret = client.spawn([new_obj])
        objID = ret.data[0]
        assert ret.ok and ret.data == [objID]
        del temp, new_obj, ret

        # Query the body states to obtain the 'version' value.
        ret = client.getRigidBodies(objID)
        assert ret.ok
        version = ret.data[objID]['rbs'].version

        # Fetch-, modify-, update- and verify the geometry.
        ret = client.getFragments([objID])
        assert ret.ok
        assert ret.data[objID]['f_dae']['fragtype'] == 'DAE'

        # Change the geometry for fragment 'f_dae' to a RAW type.
        assert client.setFragments({objID: {'f_dae': getFragRaw()._asdict()}}).ok

        # Ensure the fragment is now indeed of type 'RAW'.
        ret = client.getFragments([objID])
        assert ret.ok
        assert ret.data[objID]['f_dae']['fragtype'] == 'RAW'

        # Ensure 'version' is different as well.
        ret = client.getRigidBodies(objID)
        assert ret.ok and (ret.data[objID]['rbs'].version != version)

        # Change the fragment geometry once more.
        version = ret.data[objID]['rbs'].version
        assert client.setFragments({objID: {'f_dae': getFragDae()._asdict()}}).ok

        # Ensure it now has type 'DAE' again.
        ret = client.getFragments([objID])
        assert ret.ok
        assert ret.data[objID]['f_dae']['fragtype'] == 'DAE'

        # Ensure 'version' is different as well.
        ret = client.getRigidBodies(objID)
        assert ret.ok and (ret.data[objID]['rbs'].version != version)

    @pytest.mark.parametrize('client_type', ['Websocket', 'ZeroMQ'])
    def test_update_FragmentStates(self, client_type):
        """
        Query and modify fragment states.
        Note that fragment states are updated via 'setFragments'.
        """
        # Get the client for this test.
        client = self.clients[client_type]

        # Convenience.
        objID = 1

        # Add a new template and spawn it.
        temp = getTemplate('t1', fragments={'bar': getFragRaw()})
        assert client.addTemplates([temp]).ok

        new_obj = {'templateID': temp.aid,
                   'rbs': {'position': (1, 1, 1), 'velocityLin': (-1, -1, -1)}}
        ret = client.spawn([new_obj])
        assert ret.ok and ret.data == [objID]
        del temp, new_obj, ret

        # Query the Body State to get the Fragment States. Then verify the
        # Fragment State named 'bar'.
        ret = client.getRigidBodies(objID)
        ref = {'bar': {'scale': 1, 'position': [0, 0, 0], 'orientation': [0, 0, 0, 1]}}
        assert ret.ok
        assert ret.data[objID]['frag'] == ref

        # Modify and update the fragment states in Azrael, then query and
        # verify it worked.
        newStates = {objID: {'bar': {'scale': 2.2, 'position': [1, 2, 3],
                                     'orientation': [1, 0, 0, 0]}}}
        assert client.setFragments(newStates).ok
        ret = client.getRigidBodies(objID)
        assert ret.ok
        ret = ret.data[objID]['frag']['bar']
        assert ret == newStates[objID]['bar']

    @pytest.mark.parametrize('client_type', ['Websocket', 'ZeroMQ'])
    def test_remove_fragments(self, client_type):
        """
        Remove a fragment. This test is basically the integration test for
        'test_dibbler.test_updateFragments_partial'.
        """
        # Get the client for this test.
        client = self.clients[client_type]

        # Convenience.
        objID = 1

        # The original template has the following three fragments:
        frags_orig = {
            'fname_1': getFragRaw(),
            'fname_2': getFragDae(),
            'fname_3': getFragRaw(),
        }
        t1 = getTemplate('t1', fragments=frags_orig)

        # Add a new template and spawn it.
        assert client.addTemplates([t1]).ok
        new_obj = {'templateID': t1.aid,
                   'rbs': {'position': (1, 1, 1), 'velocityLin': (-1, -1, -1)}}
        assert client.spawn([new_obj]) == (True, None, [objID])

        # Query the fragment geometries and Body State to verify that both
        # report three fragments.
        ret = client.getFragments([objID])
        assert ret.ok and len(ret.data[objID]) == 3
        ret = client.getRigidBodies(objID)
        assert ret.ok and len(ret.data[objID]['frag']) == 3

        # Update the fragments as follows: keep the first intact, remove the
        # second, and modify the third one.
        frags_new = {'fname_2': getFragNone()._asdict(), 'fname_3': getFragDae()._asdict()}
        assert client.setFragments({objID: frags_new}).ok

        # After the last update there must now only be two fragments.
        ret = client.getFragments([objID])
        assert ret.ok and len(ret.data[objID]) == 2
        ret = client.getRigidBodies(objID)
        assert ret.ok and len(ret.data[objID]['frag']) == 2

    @pytest.mark.parametrize('client_type', ['Websocket', 'ZeroMQ'])
    def test_collada_model(self, client_type):
        """
        Add a template based on a Collada model, spawn it, and query its
        geometry.
        """
        # Get the client for this test.
        client = self.clients[client_type]

        # Add a valid template with Collada data and verify the upload worked.
        temp = getTemplate('foo', fragments={'f_dae': getFragDae()})
        assert client.addTemplates([temp]).ok

        # Spawn the template.
        ret = client.spawn([{'templateID': temp.aid}])
        assert ret.ok
        objID = ret.data[0]

        # Query and the geometry.
        ret = client.getFragments([objID])
        assert ret.ok

        # Verify it has the correct type ('DAE') and address.
        ret = ret.data[objID]
        assert ret['f_dae']['fragtype'] == 'DAE'
        assert ret['f_dae']['url_frag'] == (
            config.url_instances + '/' + str(objID) + '/f_dae')

    @pytest.mark.parametrize('client_type', ['Websocket', 'ZeroMQ'])
    def test_add_get_remove_constraints(self, client_type):
        """
        Create some bodies. Then add/query/remove constraints.

        This test only verifies that the Igor interface works. It does *not*
        verify that the objects are really linked in the actual simulation.
        """
        # Reset the constraint database.
        igor = azrael.igor.Igor()
        assert igor.reset().ok

        # Get the client for this test.
        client = self.clients[client_type]

        # Spawn the two bodies.
        pos_1, pos_2, pos_3 = [-2, 0, 0], [2, 0, 0], [6, 0, 0]
        new_objs = [
            {'templateID': '_templateSphere', 'rbs': {'position': pos_1}},
            {'templateID': '_templateSphere', 'rbs': {'position': pos_2}},
            {'templateID': '_templateSphere', 'rbs': {'position': pos_3}}
        ]
        id_1, id_2, id_3 = 1, 2, 3
        assert client.spawn(new_objs) == (True, None, [id_1, id_2, id_3])

        # Define the constraints.
        con_1 = getP2P(rb_a=id_1, rb_b=id_2, pivot_a=pos_2, pivot_b=pos_1)
        con_2 = get6DofSpring2(rb_a=id_2, rb_b=id_3)

        # Verify that no constraints are currently active.
        assert client.getAllConstraints() == (True, None, [])
        assert client.getConstraints([id_1]) == (True, None, [])

        # Add both constraints and verify they are returned correctly.
        assert client.addConstraints([con_1, con_2]) == (True, None, 2)
        ret = client.getAllConstraints()
        assert ret.ok and (sorted(ret.data) == sorted([con_1, con_2]))

        ret = client.getConstraints([id_2])
        assert ret.ok and (sorted(ret.data) == sorted([con_1, con_2]))

        assert client.getConstraints([id_1]) == (True, None, [con_1])
        assert client.getConstraints([id_3]) == (True, None, [con_2])

        # Remove the second constraint and verify the remaining constraint is
        # returned correctly.
        assert client.deleteConstraints([con_2]) == (True, None, 1)
        assert client.getAllConstraints() == (True, None, [con_1])
        assert client.getConstraints([id_1]) == (True, None, [con_1])
        assert client.getConstraints([id_2]) == (True, None, [con_1])
        assert client.getConstraints([id_3]) == (True, None, [])

    @pytest.mark.parametrize('client_type', ['Websocket', 'ZeroMQ'])
    def test_create_constraints_with_physics(self, client_type):
        """
        Spawn two rigid bodies and define a Point2Point constraint among them.
        Then apply a force onto one of them and verify the second one moves
        accordingly.
        """
        # Reset the constraint database.
        igor = azrael.igor.Igor()
        assert igor.reset().ok

        # Get the client for this test.
        client = self.clients[client_type]

        # Reset the SV database and instantiate a Leonard.
        leo = getLeonard(azrael.leonard.LeonardBullet)

        # Spawn the two bodies.
        pos_a, pos_b = [-2, 0, 0], [2, 0, 0]
        new_objs = [
            {'templateID': '_templateSphere',
             'rbs': {'position': pos_a}},
            {'templateID': '_templateSphere',
             'rbs': {'position': pos_b}},
        ]
        id_1, id_2 = 1, 2
        assert client.spawn(new_objs) == (True, None, [id_1, id_2])

        # Define- and add the constraints.
        con = [getP2P(rb_a=id_1, rb_b=id_2, pivot_a=pos_b, pivot_b=pos_a)]
        assert client.addConstraints(con) == (True, None, 1)

        # Apply a force that will pull the left object further to the left.
        # However, both objects must move the same distance in the same
        # direction because they are now linked together.
        assert client.setForce(id_1, [-10, 0, 0]).ok
        leo.processCommandsAndSync()
        leo.step(1.0, 60)
        ret = client.getRigidBodies([id_1, id_2])
        assert ret.ok
        pos_a2 = ret.data[id_1]['rbs'].position
        pos_b2 = ret.data[id_2]['rbs'].position
        delta_a = np.array(pos_a2) - np.array(pos_a)
        delta_b = np.array(pos_b2) - np.array(pos_b)
        assert delta_a[0] < pos_a[0]
        assert np.allclose(delta_a, delta_b)
