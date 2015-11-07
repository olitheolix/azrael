# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""
Test the client base class.

The client class is merely a convenience class to wrap the Clerk
commands. As such the tests here merely test these wrappers. See `test_clerk`
if you want to see thorough tests for the Clerk functionality.
"""
import os
import sys
import time
import json
import base64
import pytest
import requests

import numpy as np

import pyazrael
import pyazrael.aztypes as aztypes

# Import the necessary Azrael modules.
# fixme: use pytest path variable
p = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(p, '../'))

import azrael.web
import azrael.igor
import azrael.clerk
import azrael.dibbler
import azrael.config as config

from IPython import embed as ipshell
from azrael.test.test import getFragRaw, getFragDae, getFragNone, getTemplate
from azrael.test.test import getLeonard, killAzrael, getP2P, get6DofSpring2
from azrael.test.test import getCSEmpty, getCSBox, getCSSphere, getRigidBody


class TestClient:
    @classmethod
    def setup_class(cls):
        # Kill all lingering Azrael processes.
        killAzrael()

        # Start a Clerk and WebServer instance.
        cls.clerk = azrael.clerk.Clerk()
        cls.web = azrael.web.WebServer()
        cls.clerk.start()
        cls.web.start()

        # Reset the constraint database.
        cls.igor = azrael.igor.Igor()

        # Dibbler.
        cls.dibbler = azrael.dibbler.Dibbler()

        # Create a ZMQ- and Websocket client.
        client_zmq = pyazrael.AzraelClient(
            config.addr_clerk, config.port_clerk, config.port_webapi)
        client_ws = pyazrael.AzraelWSClient(
            config.addr_webapi, config.port_webapi, timeout=1)
        assert client_ws.ping()
        cls.clients = {'ZeroMQ': client_zmq, 'Websocket': client_ws}

    @classmethod
    def teardown_class(cls):
        # Terminate the processes.
        cls.clerk.terminate()
        cls.web.terminate()

        cls.clerk.join(5)
        cls.web.join(5)
        del cls.clients, cls.clerk, cls.web

        # Kill all lingering Azrael processes.
        killAzrael()

    def setup_method(self, method):
        # Reset the database.
        azrael.database.init()

        # Flush the model database.
        self.dibbler.reset()

        # Flush the constraints.
        assert self.igor.reset().ok

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

    def test_shared_files(self):
        """
        The client library uses a very few of Azrael's utility modules, most
        notably the type definitions. This test ensures the files stay in sync.
        """
        # Verify these files.
        fnames = ['util.py', 'aztypes.py']

        cur_path = os.path.dirname(os.path.abspath(__file__))
        pjoin = os.path.join
        dir_1 = pjoin(cur_path, '..')
        dir_2 = pjoin(cur_path, '..', '..', 'azrael')
        for fname in fnames:
            tmp_1 = open(pjoin(dir_1, fname), 'rb').read() 
            tmp_2 = open(pjoin(dir_2, fname), 'rb').read() 
            assert tmp_1 == tmp_2

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
        ret = ret.data['bar']['model.json'].encode('utf8')
        ret = base64.b64encode(ret).decode('utf8')
        assert ret == frag['bar'].files['model.json']
        del ret, temp_out, temp_orig

        # Define a new object with two boosters and one factory unit.
        # The 'boosters' and 'factories' arguments are a list of named
        # tuples. Their first argument is the unit ID (Azrael does not
        # automatically assign any).
        boosters = {
            '0': aztypes.Booster(pos=(0, 0, 0), direction=(0, 0, 1),
                               minval=0, maxval=0.5, force=0),
            '1': aztypes.Booster(pos=(0, 0, 0), direction=(0, 0, 1),
                               minval=0, maxval=0.5, force=0),
        }
        factories = {
            '0': aztypes.Factory(pos=(0, 0, 0), direction=(0, 0, 1),
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
        ret = ret.data['bar']['model.json'].encode('utf8')
        ret = base64.b64encode(ret).decode('utf8')
        assert ret == frag['bar'].files['model.json']

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

        # ---------------------------------------------------------------------
        # Create a template with two factories and spawn it.
        # ---------------------------------------------------------------------

        # Define the parts.
        boosters = {
            '0': aztypes.Booster(pos=pos_0, direction=dir_0,
                               minval=0, maxval=0.5, force=0),
            '1': aztypes.Booster(pos=pos_1, direction=dir_1,
                               minval=0, maxval=1.0, force=0)
        }
        factories = {
            '0': aztypes.Factory(pos=pos_0, direction=dir_0,
                               templateID='_templateBox',
                               exit_speed=[0.1, 0.5]),
            '1': aztypes.Factory(pos=pos_1, direction=dir_1,
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
                       'rotation': orient_parent}}
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
            '0': aztypes.CmdBooster(force=forcemag_0),
            '1': aztypes.CmdBooster(force=forcemag_1),
        }
        cmd_f = {
            '0': aztypes.CmdFactory(exit_speed=exit_speed_0),
            '1': aztypes.CmdFactory(exit_speed=exit_speed_1),
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
        Spawn a new object with a raw fragment. Then modify that fragment.
        """
        # Get the client for this test.
        client = self.clients[client_type]

        # Convenience.
        objID = 1

        # Add a new template and spawn it.
        fraw = getFragRaw()
        temp = getTemplate('t1', fragments={'fraw': fraw})
        assert client.addTemplates([temp]).ok

        new_obj = {'templateID': temp.aid,
                   'rbs': {'position': (1, 1, 1),
                           'velocityLin': (-1, -1, -1)}}
        ret = client.spawn([new_obj])
        assert ret.ok and ret.data == [objID]
        del temp, new_obj, ret

        # Query the rigid body to obtain the 'version' value.
        ret = client.getRigidBodies(objID)
        assert ret.ok
        version = ret.data[objID]['rbs'].version

        # Verify the fragment type.
        ret = client.getFragments([objID])
        assert ret.ok
        assert ret.data[objID]['fraw']['scale'] == fraw.scale
        assert ret.data[objID]['fraw']['position'] == list(fraw.position)
        assert ret.data[objID]['fraw']['rotation'] == list(fraw.rotation)
        assert ret.data[objID]['fraw']['fragtype'] == fraw.fragtype

        # Download the fragment.
        base_url = 'http://{ip}:{port}'.format(
            ip=config.addr_webapi, port=config.port_webapi)
        url = base_url + ret.data[objID]['fraw']['url_frag'] + '/model.json'
        for ii in range(10):
            assert ii < 8
            try:
                tmp = requests.get(url).content
                break
            except requests.exceptions.HTTPError:
                time.sleep(0.2)
        model = base64.b64encode(tmp).decode('utf8')
        assert model == fraw.files['model.json']

        # Change the geometries of fragment 'fraw'.
        b64enc = base64.b64encode
        cmd = {
            objID: {
                'fraw': {
                    'op': 'mod',
                    'state': {
                        'scale': 2,
                        'position': [3, 4, 5],
                        'rotation': [1, 0, 0, 0],
                        },
                    'fragtype': 'BLAH',
                    'put': {'myfile.txt': b64enc(b'aaa').decode('utf8')},
                    }
                }
            }
        assert client.setFragments(cmd) == (True, None, {'updated': 1})

        # The object must have received a new 'version'.
        ret = client.getRigidBodies(objID)
        assert ret.ok and (ret.data[objID]['rbs'].version != version)

        # ---------------------------------------------------------------------
        # Query the object state and the fragment. Both must return the same
        # data for the fragment state (scale, position, rotation).
        # ---------------------------------------------------------------------
        # Query the object state.
        ref = cmd[objID]['fraw']['state']
        ret1 = client.getObjectStates(objID)
        assert ret1.ok
        ret1 = ret1.data[objID]['frag']['fraw']

        # Query the fragment.
        ret2 = client.getFragments([objID])
        assert ret2.ok
        ret2 = ret2.data[objID]['fraw']

        # Compare that all values match.
        assert ref['scale'] == ret1['scale'] == ret2['scale']
        assert ref['position'] == ret1['position'] == ret1['position']
        assert ref['rotation'] == ret1['rotation'] == ret1['rotation']

        # ---------------------------------------------------------------------
        # Download the actual geometry files and verify their content.
        # ---------------------------------------------------------------------
        ret = client.getFragments([objID])

        # fraw: model.json (must not have changed).
        url = base_url + ret.data[objID]['fraw']['url_frag'] + '/model.json'
        tmp = requests.get(url).content
        model = base64.b64encode(tmp).decode('utf8')
        assert model == fraw.files['model.json']

        # fraw: myfile.txt (this one is new)
        url = base_url + ret.data[objID]['fraw']['url_frag'] + '/myfile.txt'
        assert requests.get(url).content == b'aaa'

        assert False

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
        assert client.getConstraints(None) == (True, None, [])
        assert client.getConstraints([id_1]) == (True, None, [])

        # Add both constraints and verify they are returned correctly.
        assert client.addConstraints([con_1, con_2]) == (True, None, 2)
        ret = client.getConstraints(None)
        assert ret.ok and (sorted(ret.data) == sorted([con_1, con_2]))

        ret = client.getConstraints([id_2])
        assert ret.ok and (sorted(ret.data) == sorted([con_1, con_2]))

        assert client.getConstraints([id_1]) == (True, None, [con_1])
        assert client.getConstraints([id_3]) == (True, None, [con_2])

        # Remove the second constraint and verify the remaining constraint is
        # returned correctly.
        assert client.deleteConstraints([con_2]) == (True, None, 1)
        assert client.getConstraints(None) == (True, None, [con_1])
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
        # Get the client for this test.
        client = self.clients[client_type]

        # Reset the database and instantiate a Leonard.
        leo = getLeonard(azrael.leonard.LeonardBullet)

        # Spawn two bodies.
        pos_a, pos_b = [-2, 0, 0], [2, 0, 0]
        new_objs = [
            {'templateID': '_templateSphere',
             'rbs': {'position': pos_a}},
            {'templateID': '_templateSphere',
             'rbs': {'position': pos_b}},
        ]
        id_1, id_2 = 1, 2
        assert client.spawn(new_objs) == (True, None, [id_1, id_2])

        # Verify the position of the bodies.
        ret = client.getObjectStates([id_1, id_2])
        assert ret.ok
        assert ret.data[id_1]['rbs']['position'] == pos_a
        assert ret.data[id_2]['rbs']['position'] == pos_b

        # Define- and add the constraints.
        con = [getP2P(rb_a=id_1, rb_b=id_2, pivot_a=pos_b, pivot_b=pos_a)]
        assert client.addConstraints(con) == (True, None, 1)

        # Apply a force that will pull the left object further to the left.
        # However, both objects must move the same distance in the same
        # direction because they are now linked together.
        assert client.setForce(id_1, [-10, 0, 0]).ok
        leo.processCommandsAndSync()
        leo.step(1.0, 60)

        # Query the object positions. Due to some database timings is sometimes
        # happen that the objects appear to not have moved. In that case retry
        # the query a few times before moving to the comparison.
        for ii in range(10):
            assert ii < 9

            # Query the objects and put their positions into convenience
            # variables.
            ret = client.getRigidBodies([id_1, id_2])
            pos_a2 = ret.data[id_1]['rbs'].position
            pos_b2 = ret.data[id_2]['rbs'].position

            # Exit this loop if both objects have moved.
            if (pos_a != pos_a2) and (pos_b != pos_b2):
                break
            time.sleep(0.1)

        # Verify that the objects have moved to the left and maintained their
        # distance.
        delta_a = np.array(pos_a2) - np.array(pos_a)
        delta_b = np.array(pos_b2) - np.array(pos_b)
        assert delta_a[0] < pos_a[0]
        assert np.allclose(delta_a, delta_b)

    @pytest.mark.parametrize('client_type', ['Websocket', 'ZeroMQ'])
    def test_set_get_custom(self, client_type):
        """
        Spawn two objects and modify their custom fields, as well as set/query
        the custom field of a non-existing object.
        """
        # Get the client for this test.
        client = self.clients[client_type]

        # Spawn two objects.
        id_1, id_2 = 1, 2
        init = {'templateID': '_templateSphere'}
        assert client.spawn([init, init]) == (True, None, [id_1, id_2])

        # Update the custom data for an existing- and a non-existing object.
        assert client.setCustomData({id_1: 'foo', 10: 'bar'}) == (True, None, [10])

        # Query two existing- and one non-existing object.
        ret = client.getCustomData([id_1, id_2, 10])
        assert ret.ok
        assert ret.data == ({id_1: 'foo', id_2: '', 10: None})

        # Query all at once.
        assert client.getCustomData(None) == client.getCustomData([id_1, id_2])
