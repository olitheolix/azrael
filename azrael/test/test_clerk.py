# Copyright 2015, Oliver Nagy <olitheolix@gmail.com>
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
Test the Clerk module.
"""
import os
import sys
import json
import time
import base64
import pickle
import pytest
import urllib.request

import numpy as np
import unittest.mock as mock

import azrael.util
import azrael.clerk
import azrael.client
import azrael.dibbler
import azrael.parts as parts
import azrael.bullet_data as bullet_data

from IPython import embed as ipshell
from azrael.test.test_bullet_api import isEqualBD
from azrael.test.test import createFragRaw, createFragDae
from azrael.test.test_leonard import getLeonard, killAzrael
from azrael.types import Template, RetVal
from azrael.types import FragState, FragDae, FragRaw, MetaFragment


class TestClerk:
    @classmethod
    def setup_class(cls):
        killAzrael()
        cls.clerk = azrael.clerk.Clerk()

    @classmethod
    def teardown_class(cls):
        killAzrael()

    def setup_method(self, method):
        self.dibbler = azrael.dibbler.DibblerAPI()
        self.dibbler.reset()

    def teardown_method(self, method):
        self.dibbler.reset()

    def setup_method(self, method):
        azrael.database.init()

        # Insert default objects. None of them has an actual geometry but
        # their collision shapes are: none, sphere, cube.
        clerk = azrael.clerk.Clerk()
        frag = [MetaFragment('NoName', 'raw', createFragRaw())]
        t1 = Template('_templateNone', [0, 1, 1, 1], frag, [], [])
        t2 = Template('_templateSphere', [3, 1, 1, 1], frag, [], [])
        t3 = Template('_templateCube', [4, 1, 1, 1], frag, [], [])
        clerk.addTemplates([t1, t2, t3])

    def teardown_method(self, method):
        azrael.database.init()

    def test_spawn(self):
        """
        Test the 'spawn' command in the Clerk.
        """
        # Instantiate a Clerk.
        clerk = azrael.clerk.Clerk()

        # Default object.
        sv_1 = bullet_data.MotionState(imass=1)
        sv_2 = bullet_data.MotionState(imass=2)
        sv_3 = bullet_data.MotionState(imass=3)

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
        assert clerk.getGeometries([1]).data[1] is not None

        # Spawn two more objects with a single call.
        name_2 = '_templateSphere'
        name_3 = '_templateCube'
        ret = clerk.spawn([(name_2, sv_2), (name_3, sv_3)])
        assert (ret.ok, ret.data) == (True, (2, 3))

        # Geometry for last two object must now exist as well.
        ret = clerk.getGeometries([2, 3])
        assert ret.data[2] is not None
        assert ret.data[3] is not None

        # Spawn two identical objects with a single call.
        ret = clerk.spawn([(name_2, sv_2), (name_2, sv_2)])
        assert (ret.ok, ret.data) == (True, (4, 5))

        # Geometry for last two object must now exist as well.
        ret = clerk.getGeometries([4, 5])
        assert ret.data[4] is not None
        assert ret.data[5] is not None

        # Invalid: list of objects must not be empty.
        assert not clerk.spawn([]).ok

        # Invalid: List elements do not contain the correct data types.
        assert not clerk.spawn([name_2]).ok

        # Invalid: one template does not exist.
        assert not clerk.spawn([(name_2, sv_2), (b'blah', sv_3)]).ok

    def test_delete(self):
        """
        Test the 'removeObject' command in the Clerk.

        Spawn an object and ensure it exists, then delete it and ensure it does
        not exist anymore.
        """
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
        sv = bullet_data.MotionState()
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

    def test_get_statevar(self):
        """
        Test the 'get_statevar' command in the Clerk.
        """
        # Reset the SV database and instantiate a Leonard.
        leo = getLeonard()

        # Test parameters and constants.
        objID_1 = 1
        objID_2 = 2
        MS = bullet_data.MotionState
        sv_1 = MS(position=np.arange(3), velocityLin=[2, 4, 6])
        sv_2 = MS(position=[2, 4, 6], velocityLin=[6, 8, 10])
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

    def test_getAllStateVariables(self):
        """
        Test the 'getAllStateVariables' command in the Clerk.
        """
        # Reset the SV database and instantiate a Leonard.
        leo = getLeonard()

        # Test parameters and constants.
        objID_1, objID_2 = 1, 2
        MS = bullet_data.MotionState
        sv_1 = MS(position=np.arange(3), velocityLin=[2, 4, 6])
        sv_2 = MS(position=[2, 4, 6], velocityLin=[6, 8, 10])
        templateID = '_templateNone'

        # Instantiate a Clerk.
        clerk = azrael.clerk.Clerk()

        # Retrieve all SVs --> there must be none.
        ret = clerk.getAllStateVariables()
        assert (ret.ok, ret.data) == (True, {})

        # Spawn a new object and verify its ID.
        ret = clerk.spawn([(templateID, sv_1)])
        assert (ret.ok, ret.data) == (True, (objID_1, ))

        # Retrieve all SVs --> there must now be exactly one.
        leo.processCommandsAndSync()
        ret = clerk.getAllStateVariables()
        assert (ret.ok, len(ret.data)) == (True, 1)
        assert isEqualBD(ret.data[objID_1]['sv'], sv_1)

        # Spawn a second object and verify its ID.
        ret = clerk.spawn([(templateID, sv_2)])
        assert (ret.ok, ret.data) == (True, (objID_2, ))

        # Retrieve all SVs --> there must now be exactly two.
        leo.processCommandsAndSync()
        ret = clerk.getAllStateVariables()
        assert (ret.ok, len(ret.data)) == (True, 2)
        assert isEqualBD(ret.data[objID_1]['sv'], sv_1)
        assert isEqualBD(ret.data[objID_2]['sv'], sv_2)

    def test_set_force(self):
        """
        Set and retrieve force and torque values.
        """
        # Reset the SV database and instantiate a Leonard.
        leo = getLeonard()

        # Parameters and constants for this test.
        id_1 = 1
        sv = bullet_data.MotionState()
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

    def test_get_default_templates(self):
        """
        Query the defautl templates in Azrael.
        """
        # Instantiate a Clerk.
        clerk = azrael.clerk.Clerk()

        # Request an invalid ID.
        assert not clerk.getTemplates(['blah']).ok

        AE = np.array_equal

        # Clerk has a few default objects. This one has no collision shape...
        name_1 = '_templateNone'
        ret = clerk.getTemplates([name_1])
        assert ret.ok and (len(ret.data) == 1) and (name_1 in ret.data)
        assert AE(ret.data[name_1]['cshape'], np.array([0, 1, 1, 1]))

        # ... this one is a sphere...
        name_2 = '_templateSphere'
        ret = clerk.getTemplates([name_2])
        assert ret.ok and (len(ret.data) == 1) and (name_2 in ret.data)
        assert np.array_equal(ret.data[name_2]['cshape'],
                              np.array([3, 1, 1, 1]))

        # ... and this one is a cube.
        name_3 = '_templateCube'
        ret = clerk.getTemplates([name_3])
        assert ret.ok and (len(ret.data) == 1) and (name_3 in ret.data)
        assert AE(ret.data[name_3]['cshape'], np.array([4, 1, 1, 1]))

        # Retrieve all three again but with a single call.
        ret = clerk.getTemplates([name_1, name_2, name_3])
        assert ret.ok
        assert set(ret.data.keys()) == set((name_1, name_2, name_3))
        assert AE(ret.data[name_1]['cshape'], np.array([0, 1, 1, 1]))
        assert AE(ret.data[name_2]['cshape'], np.array([3, 1, 1, 1]))
        assert AE(ret.data[name_3]['cshape'], np.array([4, 1, 1, 1]))

    def test_add_get_template_single(self):
        """
        Add a new object to the templateID DB and query it again.
        """
        # Instantiate a Clerk.
        clerk = azrael.clerk.Clerk()

        # Install a mock for DibblerAPI with an 'addTemplate' function that
        # always succeeds.
        mock_dibbler = mock.create_autospec(azrael.dibbler.DibblerAPI)
        clerk.dibbler = mock_dibbler
        mock_dibbler.return_value = RetVal(True, None, {'aabb': 1.0})

        # The mock must not have been called so far.
        assert mock_dibbler.addTemplate.call_count == 0

        # Convenience.
        cs = [1, 2, 3, 4]

        # Reset the call_count of the mock.
        mock_dibbler.addTemplate.call_count = 0

        # Request an invalid ID.
        assert not clerk.getTemplates(['blah']).ok

        # Wrong argument .
        ret = clerk.addTemplates([1])
        assert (ret.ok, ret.msg) == (False, 'Invalid arguments')
        assert mock_dibbler.addTemplate.call_count == 0

        # Compile a template structure.
        frags = [MetaFragment('foo', 'raw', createFragRaw())]
        temp = Template('bar', cs, frags, [], [])

        # Add template when 'saveModel' fails.
        mock_dibbler.addTemplate.return_value = RetVal(False, 'test_error', None)
        ret = clerk.addTemplates([temp])
        assert (ret.ok, ret.msg) == (False, 'test_error')
        assert mock_dibbler.addTemplate.call_count == 1

        # Add template when 'saveModel' succeeds.
        mock_dibbler.addTemplate.return_value = RetVal(True, None, {'aabb': 1.0})
        assert clerk.addTemplates([temp]).ok
        assert mock_dibbler.addTemplate.call_count == 2

        # Adding the same template again must fail.
        assert not clerk.addTemplates([temp]).ok
        assert mock_dibbler.addTemplate.call_count == 3

        # Define a new object with two boosters and one factory unit.
        # The 'boosters' and 'factories' arguments are a list of named
        # tuples. Their first argument is the unit ID (Azrael does not assign
        # automatically assign any IDs).
        b0 = parts.Booster(partID='0', pos=[0, 0, 0], direction=[0, 0, 1],
                           minval=0, maxval=0.5, force=0)
        b1 = parts.Booster(partID='1', pos=[0, 0, 0], direction=[0, 0, 1],
                           minval=0, maxval=0.5, force=0)
        f0 = parts.Factory(
            partID='0', pos=[0, 0, 0], direction=[0, 0, 1],
            templateID='_templateCube', exit_speed=[0.1, 0.5])

        # Add the new template.
        temp = Template('t3', cs, frags, [b0, b1], [f0])
        assert clerk.addTemplates([temp]).ok
        assert mock_dibbler.addTemplate.call_count == 4

        # Retrieve the just created object and verify the collision shape.
        ret = clerk.getTemplates([temp.name])
        assert ret.ok
        assert np.array_equal(ret.data[temp.name]['cshape'], cs)

        # The template must also feature two boosters and one factory.
        assert len(ret.data[temp.name]['boosters']) == 2
        assert len(ret.data[temp.name]['factories']) == 1

        # Explicitly verify the booster- and factory units. The easisest
        # (albeit not most readable) way to do the comparison is to convert the
        # unit descriptions (which are named tuples) to byte strings and
        # compare those.
        Booster, Factory = parts.Booster, parts.Factory
        out_boosters = [Booster(*_) for _ in ret.data[temp.name]['boosters']]
        out_factories = [Factory(*_) for _ in ret.data[temp.name]['factories']]
        assert b0 in out_boosters
        assert b1 in out_boosters
        assert f0 in out_factories

        # Request the same templates multiple times in a single call. This must
        # return a dictionary with as many keys as there are unique template
        # IDs.
        ret = clerk.getTemplates([temp.name, temp.name, temp.name])
        assert ret.ok and (len(ret.data) == 1) and (temp.name in ret.data)

    def test_add_get_template_multi_url(self):
        """
        Add templates in bulk and verify that the models are availabe via the
        correct URL.
        """
        # Instantiate a Clerk.
        clerk = azrael.clerk.Clerk()

        # Install a mock for DibblerAPI with an 'addTemplate' function that
        # always succeeds.
        mock_dibbler = mock.create_autospec(azrael.dibbler.DibblerAPI)
        clerk.dibbler = mock_dibbler
        mock_dibbler.return_value = RetVal(True, None, {'aabb': 1.0})

        # The mock must not have been called so far.
        assert mock_dibbler.addTemplate.call_count == 0

        # Convenience.
        base_url = 'http://{}:{}'.format(
            azrael.config.addr_clacks,
            azrael.config.port_clacks)
        name_1, name_2 = 't1', 't2'

        # Define templates.
        frags_1 = [MetaFragment('foo', 'raw', createFragRaw())]
        frags_2 = [MetaFragment('foo', 'raw', createFragRaw())]
        t1 = Template(name_1, [1, 2], frags_1, [], [])
        t2 = Template(name_2, [3, 4], frags_2, [], [])

        # Add two valid templates. This must succeed.
        assert clerk.addTemplates([t1, t2]).ok
        assert mock_dibbler.addTemplate.call_count == 2

        # Attempt to add the same templates again. This must fail.
        assert not clerk.addTemplates([t1, t2]).ok
        assert mock_dibbler.addTemplate.call_count == 4

        # Fetch the just added template in order to get the URL where its
        # geometries are stored.
        ret = clerk.getTemplates([name_1])
        assert ret.ok
        assert MetaFragment(*(ret.data[name_1]['fragments'][0])).type == 'raw'
        assert ret.data[name_1]['url'] == '/templates/' + name_1

        # Fetch the second template.
        ret = clerk.getTemplates([name_2])
        assert ret.ok
        assert MetaFragment(*(ret.data[name_2]['fragments'][0])).type == 'raw'
        assert ret.data[name_2]['url'] == '/templates/' + name_2

        # Fetch both templates at once.
        ret = clerk.getTemplates([name_1, name_2])
        assert ret.ok and (len(ret.data) == 2)
        assert ret.data[name_1]['url'] == '/templates/' + name_1
        assert ret.data[name_2]['url'] == '/templates/' + name_2

    def test_add_get_template_AABB(self):
        """
        Similarly to test_add_get_template but focuses exclusively on the AABB.
        """
        # Instantiate a Clerk.
        clerk = azrael.clerk.Clerk()

        # Convenience.
        cs = [1, 2, 3, 4]
        uv = rgb = []

        # Manually specify the vertices and its spatial extent in the
        # 'max_sidelen' variable beneath.
        vert = [-4, 0, 0,
                1, 2, 3,
                4, 5, 6]
        max_sidelen = max(8, 5, 6)

        # Add- and fetch the template.
        frags = [MetaFragment('bar', 'raw', FragRaw(vert, uv, rgb))]
        t1 = Template('t1', cs, frags, [], [])
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
        frags = [MetaFragment('bar', 'raw', FragRaw(vert, uv, rgb))]
        t2 = Template('t2', cs, frags, [], [])
        assert clerk.addTemplates([t2]).ok
        ret = clerk.getTemplates([t2.name])
        assert ret.ok

        # The largest AABB side length must be roughly "sqrt(3) * max_sidelen".
        assert (ret.data[t2.name]['aabb'] - np.sqrt(3.1) * max_sidelen) < 1E-10

    def test_get_object_template_id(self):
        """
        Spawn two objects from different templates. Then query the template ID
        based on the object ID.
        """
        # Reset the SV database and instantiate a Leonard.
        leo = getLeonard()

        # Parameters and constants for this test.
        id_0, id_1 = 1, 2
        templateID_0 = '_templateNone'
        templateID_1 = '_templateCube'
        sv = bullet_data.MotionState()

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

    def test_controlParts_Boosters_bug_102(self):
        """
        ControlParts breaks when the objID does not exist. This
        typically happens when an object receives control commands
        _after_ it was spawned but _before_ Leonard has picked it up.
        """
        # Instantiate a Clerk.
        clerk = azrael.clerk.Clerk()

        # Define a boosters.
        v = np.array([1, 0, 0], np.float64)
        booster = parts.Booster(
            partID='0', pos=v, direction=v, minval=0, maxval=1, force=0)

        frags = [MetaFragment('bar', 'raw', createFragRaw())]

        # Define a new template with two boosters and add it to Azrael.
        template = Template('t1',
                            cs=[1, 2, 3, 4],
                            fragments=frags,
                            boosters=[booster],
                            factories=[])
        assert clerk.addTemplates([template]).ok

        # Spawn an instance of the template and get the object ID.
        ret = clerk.spawn([(template.name, bullet_data.MotionState())])
        assert ret.ok
        objID = ret.data[0]

        # Create a Booster command.
        cmd = parts.CmdBooster(partID='0', force=2)

        # Send the command to Clerk. With the bug present this triggered a
        # stack trace, whereas now it must simply return with cleared ok flag.
        assert not clerk.controlParts(objID, [cmd], []).ok

    def test_controlParts_invalid_commands(self):
        """
        Send invalid control commands to object.
        """
        # Reset the SV database and instantiate a Leonard.
        leo = getLeonard()

        # Parameters and constants for this test.
        objID_1, objID_2 = 1, 2
        templateID_1 = '_templateNone'
        sv = bullet_data.MotionState()

        # Instantiate a Clerk.
        clerk = azrael.clerk.Clerk()

        # Create a fake object. We will not need the actual object but other
        # commands used here depend on one to exist.
        ret = clerk.spawn([(templateID_1, sv)])
        assert (ret.ok, ret.data) == (True, (objID_1, ))

        # Create commands for a Booster and a Factory.
        cmd_b = parts.CmdBooster(partID='0', force=0.2)
        cmd_f = parts.CmdFactory(partID='0', exit_speed=0.5)

        # Call 'controlParts'. This must fail because the template for objID_1
        # has neither boosters nor factories.
        leo.processCommandsAndSync()
        assert not clerk.controlParts(objID_1, [cmd_b], []).ok

        # Must fail: objects has no factory.
        assert not clerk.controlParts(objID_1, [], [cmd_f]).ok

        # Must fail: objects still has neither a booster nor a factory.
        assert not clerk.controlParts(objID_1, [cmd_b], [cmd_f]).ok

        # Must fail: Factory where Booster is expected and vice versa.
        assert not clerk.controlParts(objID_1, [cmd_f], [cmd_b]).ok

        # Must fail: Booster command among Factory commands.
        assert not clerk.controlParts(objID_1, [], [cmd_f, cmd_b]).ok

        # ---------------------------------------------------------------------
        # Create a template with one booster and one factory. Then send
        # commands to them.
        # ---------------------------------------------------------------------

        # Define the Booster and Factory parts.
        b0 = parts.Booster(partID='0', pos=[0, 0, 0], direction=[0, 0, 1],
                           minval=0, maxval=0.5, force=0)
        f0 = parts.Factory(
            partID='0', pos=[0, 0, 0], direction=[0, 0, 1],
            templateID='_templateCube', exit_speed=[0, 1])

        # Define a new template, add it to Azrael, and spawn an instance.
        frags = [MetaFragment('bar', 'raw', createFragRaw())]
        temp = Template('t1', [1, 2], frags, [b0], [f0])
        assert clerk.addTemplates([temp]).ok
        sv = bullet_data.MotionState()
        ret = clerk.spawn([(temp.name, sv)])
        assert (ret.ok, ret.data) == (True, (objID_2, ))
        leo.processCommandsAndSync()

        # Tell each factory to spawn an object.
        cmd_b = parts.CmdBooster(partID='0', force=0.5)
        cmd_f = parts.CmdFactory(partID='0', exit_speed=0.5)

        # Valid: Clerk must accept these commands.
        assert clerk.controlParts(objID_2, [cmd_b], [cmd_f]).ok

        # Invalid: Booster where Factory is expected and vice versa.
        assert not clerk.controlParts(objID_2, [cmd_f], [cmd_b]).ok

        # Invalid: every part can only receive one command per call.
        assert not clerk.controlParts(objID_2, [cmd_b, cmd_b], []).ok
        assert not clerk.controlParts(objID_2, [], [cmd_f, cmd_f]).ok

    def test_controlParts_Boosters_notmoving(self):
        """
        Create a template with boosters and send control commands to it.

        The parent object does not move in the world coordinate system.
        """
        # Reset the SV database and instantiate a Leonard.
        leo = getLeonard()

        # Parameters and constants for this test.
        objID_1 = 1

        # Instantiate a Clerk.
        clerk = azrael.clerk.Clerk()

        # ---------------------------------------------------------------------
        # Define an object with a booster and spawn it.
        # ---------------------------------------------------------------------

        # Constants for the new template object.
        sv = bullet_data.MotionState()

        dir_0 = np.array([1, 0, 0], np.float64)
        dir_1 = np.array([0, 1, 0], np.float64)
        pos_0 = np.array([1, 1, -1], np.float64)
        pos_1 = np.array([-1, -1, 0], np.float64)

        # Define two boosters.
        b0 = parts.Booster(partID='0', pos=pos_0, direction=dir_0,
                           minval=0, maxval=0.5, force=0)
        b1 = parts.Booster(partID='1', pos=pos_1, direction=dir_1,
                           minval=0, maxval=0.5, force=0)

        # Define a new template with two boosters and add it to Azrael.
        frags = [MetaFragment('bar', 'raw', createFragRaw())]
        temp = Template('t1', [1, 2], frags, [b0, b1], [])
        assert clerk.addTemplates([temp]).ok

        # Spawn an instance of the template.
        ret = clerk.spawn([(temp.name, sv)])
        assert (ret.ok, ret.data) == (True, (objID_1, ))
        leo.processCommandsAndSync()
        del ret, temp

        # ---------------------------------------------------------------------
        # Engage the boosters and verify the total force exerted on the object.
        # ---------------------------------------------------------------------

        # Create the commands to activate both boosters with a different force.
        forcemag_0, forcemag_1 = 0.2, 0.4
        cmd_0 = parts.CmdBooster(partID='0', force=forcemag_0)
        cmd_1 = parts.CmdBooster(partID='1', force=forcemag_1)

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

        # Send an empty command. The total force and torque must not change.
        assert clerk.controlParts(objID_1, [], []).ok
        leo.processCommandsAndSync()
        tmp = leo.totalForceAndTorque(objID_1)
        assert np.array_equal(tmp[0], tot_force)
        assert np.array_equal(tmp[1], tot_torque)

    def test_controlParts_Factories_notmoving(self):
        """
        Create a template with factories and let them spawn objects.

        The parent object does not move in the world coordinate system.
        """
        # Reset the SV database and instantiate a Leonard.
        leo = getLeonard()

        # Instantiate a Clerk.
        clerk = azrael.clerk.Clerk()

        # ---------------------------------------------------------------------
        # Create a template with two factories and spawn it.
        # ---------------------------------------------------------------------

        # Constants for the new template object.
        objID_1 = 1
        sv = bullet_data.MotionState()
        dir_0 = np.array([1, 0, 0], np.float64)
        dir_1 = np.array([0, 1, 0], np.float64)
        pos_0 = np.array([1, 1, -1], np.float64)
        pos_1 = np.array([-1, -1, 0], np.float64)

        # Define a new object with two factory parts. The Factory parts are
        # named tuples passed to addTemplates. The user must assign the partIDs
        # manually.
        f0 = parts.Factory(
            partID='0', pos=pos_0, direction=dir_0,
            templateID='_templateCube', exit_speed=[0.1, 0.5])
        f1 = parts.Factory(
            partID='1', pos=pos_1, direction=dir_1,
            templateID='_templateSphere', exit_speed=[1, 5])

        # Add the template to Azrael and spawn one instance.
        frags = [MetaFragment('bar', 'raw', createFragRaw())]
        temp = Template('t1', [1, 2], frags, [], [f0, f1])
        assert clerk.addTemplates([temp]).ok
        ret = clerk.spawn([(temp.name, sv)])
        assert (ret.ok, ret.data) == (True, (objID_1, ))
        leo.processCommandsAndSync()
        del ret, temp, f0, f1, sv

        # ---------------------------------------------------------------------
        # Instruct factories to create an object with a specific exit velocity.
        # ---------------------------------------------------------------------

        # Create the commands to let each factory spawn an object.
        exit_speed_0, exit_speed_1 = 0.2, 2
        cmd_0 = parts.CmdFactory(partID='0', exit_speed=exit_speed_0)
        cmd_1 = parts.CmdFactory(partID='1', exit_speed=exit_speed_1)

        # Send the commands and ascertain that the returned object IDs now
        # exist in the simulation. These IDs must be '2' and '3'.
        ok, _, spawnedIDs = clerk.controlParts(objID_1, [], [cmd_0, cmd_1])
        assert (ok, spawnedIDs) == (True, [2, 3])
        leo.processCommandsAndSync()

        # Query the state variables of the objects spawned by the factories.
        ret = clerk.getStateVariables(spawnedIDs)
        assert (ret.ok, len(ret.data)) == (True, 2)

        # Ensure the position, velocity, and orientation of the spawned objects
        # are correct.
        sv_2, sv_3 = [ret.data[_]['sv'] for _ in spawnedIDs]
        assert np.allclose(sv_2.velocityLin, exit_speed_0 * dir_0)
        assert np.allclose(sv_2.position, pos_0)
        assert np.allclose(sv_2.orientation, [0, 0, 0, 1])
        assert np.allclose(sv_3.velocityLin, exit_speed_1 * dir_1)
        assert np.allclose(sv_3.position, pos_1)
        assert np.allclose(sv_3.orientation, [0, 0, 0, 1])

    def test_controlParts_Factories_moving(self):
        """
        Create a template with factories and send control commands to them.

        In this test the parent object moves at a non-zero velocity.
        """
        # Reset the SV database and instantiate a Leonard and Clerk.
        leo = getLeonard()
        clerk = azrael.clerk.Clerk()

        # Parameters and constants for this test.
        objID_1, objID_2, objID_3 = 1, 2, 3
        pos_parent = np.array([1, 2, 3], np.float64)
        vel_parent = np.array([4, 5, 6], np.float64)
        dir_0 = np.array([1, 0, 0], np.float64)
        dir_1 = np.array([0, 1, 0], np.float64)
        pos_0 = np.array([1, 1, -1], np.float64)
        pos_1 = np.array([-1, -1, 0], np.float64)

        # State variables for parent object.
        sv = bullet_data.MotionState(position=pos_parent,
                                     velocityLin=vel_parent)

        # ---------------------------------------------------------------------
        # Create a template with two factories and spawn it.
        # ---------------------------------------------------------------------

        # Define factory parts.
        f0 = parts.Factory(
            partID='0', pos=pos_0, direction=dir_0,
            templateID='_templateCube', exit_speed=[0.1, 0.5])
        f1 = parts.Factory(
            partID='1', pos=pos_1, direction=dir_1,
            templateID='_templateSphere', exit_speed=[1, 5])

        # Define a template with two factories, add it to Azrael, and spawn it.
        frags = [MetaFragment('bar', 'raw', createFragRaw())]
        temp = Template('t1', [1, 2], frags, [], [f0, f1])
        assert clerk.addTemplates([temp]).ok
        ret = clerk.spawn([(temp.name, sv)])
        assert (ret.ok, ret.data) == (True, (objID_1, ))
        leo.processCommandsAndSync()
        del temp, ret, f0, f1, sv

        # ---------------------------------------------------------------------
        # Instruct factories to create an object with a specific exit velocity.
        # ---------------------------------------------------------------------

        # Create the commands to let each factory spawn an object.
        exit_speed_0, exit_speed_1 = 0.2, 2
        cmd_0 = parts.CmdFactory(partID='0', exit_speed=exit_speed_0)
        cmd_1 = parts.CmdFactory(partID='1', exit_speed=exit_speed_1)

        # Send the commands and ascertain that the returned object IDs now
        # exist in the simulation.
        ret = clerk.controlParts(objID_1, [], [cmd_0, cmd_1])
        assert ret.ok and (len(ret.data) == 2)
        spawnedIDs = ret.data
        assert spawnedIDs == [objID_2, objID_3]
        leo.processCommandsAndSync()

        # Query the state variables of the objects spawned by the factories.
        ret = clerk.getStateVariables(spawnedIDs)
        assert (ret.ok, len(ret.data)) == (True, 2)

        # Ensure the position/velocity/orientation are correct.
        sv_2, sv_3 = ret.data[objID_2]['sv'], ret.data[objID_3]['sv']
        assert np.allclose(sv_2.velocityLin, exit_speed_0 * dir_0 + vel_parent)
        assert np.allclose(sv_2.position, pos_0 + pos_parent)
        assert np.allclose(sv_2.orientation, [0, 0, 0, 1])
        assert np.allclose(sv_3.velocityLin, exit_speed_1 * dir_1 + vel_parent)
        assert np.allclose(sv_3.position, pos_1 + pos_parent)
        assert np.allclose(sv_3.orientation, [0, 0, 0, 1])

    def test_controlParts_Boosters_and_Factories_move_and_rotated(self):
        """
        Create a template with boosters and factories. Then send control
        commands to them and ensure the applied forces, torques, and
        spawned objects are correct.

        In this test the parent object moves and is oriented away from its
        default.
        """
        # Reset the SV database and instantiate a Leonard.
        leo = getLeonard()

        # Parameters and constants for this test.
        objID_1, objID_2, objID_3 = 1, 2, 3
        pos_parent = np.array([1, 2, 3], np.float64)
        vel_parent = np.array([4, 5, 6], np.float64)

        # Part positions relative to parent.
        dir_0 = np.array([0, 0, +2], np.float64)
        dir_1 = np.array([0, 0, -1], np.float64)
        pos_0 = np.array([0, 0, +3], np.float64)
        pos_1 = np.array([0, 0, -4], np.float64)

        # Describes a rotation of 180 degrees around x-axis.
        orient_parent = [1, 0, 0, 0]

        # Part position in world coordinates if the parent is rotated by 180
        # degrees around the x-axis. The normalisation of the direction is
        # necessary because the parts will automatically normalise all
        # direction vectors, including dir_0 and dir_1 which are not unit
        # vectors.
        dir_0_out = np.array(-dir_0) / np.sum(abs(dir_0))
        dir_1_out = np.array(-dir_1) / np.sum(abs(dir_1))
        pos_0_out = np.array(-pos_0)
        pos_1_out = np.array(-pos_1)

        # State variables for parent object. This one has a position and speed,
        # and is rotate 180 degrees around the x-axis. This means the x-values
        # of all forces (boosters) and exit speeds (factory spawned objects)
        # must be inverted.
        sv = bullet_data.MotionState(position=pos_parent,
                                     velocityLin=vel_parent,
                                     orientation=orient_parent)
        # Instantiate a Clerk.
        clerk = azrael.clerk.Clerk()

        # ---------------------------------------------------------------------
        # Define and spawn a template with two boosters and two factories.
        # ---------------------------------------------------------------------

        # Define the Booster and Factory parts.
        b0 = parts.Booster(partID='0', pos=pos_0, direction=dir_0,
                           minval=0, maxval=0.5, force=0)
        b1 = parts.Booster(partID='1', pos=pos_1, direction=dir_1,
                           minval=0, maxval=1.0, force=0)
        f0 = parts.Factory(
            partID='0', pos=pos_0, direction=dir_0,
            templateID='_templateCube', exit_speed=[0.1, 0.5])
        f1 = parts.Factory(
            partID='1', pos=pos_1, direction=dir_1,
            templateID='_templateSphere', exit_speed=[1, 5])

        # Define the template, add it to Azrael, and spawn one instance.
        frags = [MetaFragment('bar', 'raw', createFragRaw())]
        temp = Template('t1', [1, 2], frags, [b0, b1], [f0, f1])
        assert clerk.addTemplates([temp]).ok
        ret = clerk.spawn([(temp.name, sv)])
        assert (ret.ok, ret.data) == (True, (objID_1, ))
        leo.processCommandsAndSync()
        del b0, b1, f0, f1, temp

        # ---------------------------------------------------------------------
        # Activate booster and factories. Then verify that boosters apply the
        # correct force and the spawned objects have the correct State Vector.
        # ---------------------------------------------------------------------

        # Create the commands to let each factory spawn an object.
        exit_speed_0, exit_speed_1 = 0.2, 2
        forcemag_0, forcemag_1 = 0.2, 0.4
        cmd_0 = parts.CmdBooster(partID='0', force=forcemag_0)
        cmd_1 = parts.CmdBooster(partID='1', force=forcemag_1)
        cmd_2 = parts.CmdFactory(partID='0', exit_speed=exit_speed_0)
        cmd_3 = parts.CmdFactory(partID='1', exit_speed=exit_speed_1)

        # Send the commands and ascertain that the returned object IDs now
        # exist in the simulation. These IDs must be '2' and '3'.
        ok, _, spawnIDs = clerk.controlParts(
            objID_1, [cmd_0, cmd_1], [cmd_2, cmd_3])
        assert (ok, spawnIDs) == (True, [objID_2, objID_3])
        leo.processCommandsAndSync()

        # Query the state variables of the objects spawned by the factories.
        ret = clerk.getStateVariables(spawnIDs)
        assert (ret.ok, len(ret.data)) == (True, 2)

        # Verify the positions and velocities are correct.
        sv_2, sv_3 = ret.data[objID_2]['sv'], ret.data[objID_3]['sv']
        AC = np.allclose
        assert AC(sv_2.velocityLin, exit_speed_0 * dir_0_out + vel_parent)
        assert AC(sv_2.position, pos_0_out + pos_parent)
        assert AC(sv_2.orientation, orient_parent)
        assert AC(sv_3.velocityLin, exit_speed_1 * dir_1_out + vel_parent)
        assert AC(sv_3.position, pos_1_out + pos_parent)
        assert AC(sv_3.orientation, orient_parent)

        # Manually compute the total force and torque exerted by the boosters.
        forcevec_0, forcevec_1 = forcemag_0 * dir_0_out, forcemag_1 * dir_1_out
        tot_force = forcevec_0 + forcevec_1
        tot_torque = (np.cross(pos_0_out, forcevec_0) +
                      np.cross(pos_1_out, forcevec_1))

        # Query the torque and force from Azrael and verify they are correct.
        tmp = leo.totalForceAndTorque(objID_1)
        assert np.array_equal(tmp[0], tot_force)
        assert np.array_equal(tmp[1], tot_torque)

    def test_get_all_objectids(self):
        """
        Test getAllObjects.
        """
        # Reset the SV database and instantiate a Leonard.
        leo = getLeonard()

        # Parameters and constants for this test.
        objID_1, objID_2 = 1, 2
        templateID = '_templateNone'
        sv = bullet_data.MotionState()

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

    def test_getGeometries(self):
        """
        Spawn two objects and query their geometries.
        """
        # Instantiate a Clerk.
        clerk = azrael.clerk.Clerk()

        # Raw object: specify vertices, UV, and texture (RGB) values directly.
        sv1 = bullet_data.MotionState(position=[1, 2, 3])
        sv2 = bullet_data.MotionState(position=[4, 5, 6])
        f_raw = createFragRaw()

        # Get Collada fragment.
        f_dae = createFragDae()

        # Put both fragments into a valid list of MetaFragments.
        frags = [MetaFragment('f_raw', 'raw', f_raw),
                 MetaFragment('f_dae', 'dae', f_dae)]

        # Add a valid template with the just specified fragments and verify the
        # upload worked.
        temp = Template('foo', [1, 2], frags, [], [])
        assert clerk.addTemplates([temp]).ok
        assert clerk.getTemplates([temp.name]).ok

        # Attempt to query the geometry of a non-existing object.
        assert clerk.getGeometries([123]) == (True, None, {123: None})

        # Spawn two objects from the previously added template.
        ret = clerk.spawn([(temp.name, sv1), (temp.name, sv2)])
        assert ret.ok
        objID_1, objID_2 = ret.data

        def _verify(_ret, _objID):
            _ret = _ret[_objID]
            _objID = str(_objID)

            # The object must have two fragments, an 'f_raw' with type 'raw'
            # and an 'f_dae' with type 'dae'.
            assert _ret['f_raw']['type'] == 'raw'
            assert _ret['f_raw']['url'] == '/instances/' + _objID + '/f_raw'
            assert _ret['f_dae']['type'] == 'dae'
            assert _ret['f_dae']['url'] == '/instances/' + _objID + '/f_dae'
            return True

        # Query and verify the geometry of the first instance.
        ret = clerk.getGeometries([objID_1])
        assert ret.ok and _verify(ret.data, objID_1)

        # Query and verify the geometry of the second instance.
        ret = clerk.getGeometries([objID_2])
        assert ret.ok and _verify(ret.data, objID_2)

        # Query both instances at once and verify them.
        ret = clerk.getGeometries([objID_1, objID_2])
        assert ret.ok and _verify(ret.data, objID_1)
        assert ret.ok and _verify(ret.data, objID_2)

        # Delete first and query again.
        assert clerk.removeObject(objID_1).ok
        ret = clerk.getGeometries([objID_1, objID_2])
        assert ret.ok
        assert ret.data[objID_1] is None
        assert _verify(ret.data, objID_2)

    def test_instanceDB_checksum(self):
        """
        Spawn two objects, modify their geometries, and verify that the
        'lastChanged' flag changes accordingly.
        """
        # Instantiate a Clerk.
        clerk = azrael.clerk.Clerk()

        # Reset the SV database and instantiate a Leonard.
        leo = getLeonard()

        # Convenience.
        sv = bullet_data.MotionState()

        # Add a valid template and verify it now exists in Azrael.
        frags = [MetaFragment('bar', 'raw', createFragRaw())]
        temp = Template('foo', [1, 2], frags, [], [])
        assert clerk.addTemplates([temp]).ok

        # Spawn two objects from the previously defined template.
        ret = clerk.spawn([(temp.name, sv), (temp.name, sv)])
        assert ret.ok and (len(ret.data) == 2)
        objID0, objID1 = ret.data

        # Let Leonard pick up the new objects so that we can query them.
        leo.processCommandsAndSync()

        # Query the State Vectors for both objects.
        ret = clerk.getStateVariables([objID0, objID1])
        assert ret.ok and (set((objID0, objID1)) == set(ret.data.keys()))
        ref_lastChanged = ret.data[objID0]['sv'].lastChanged

        # Modify the 'bar' fragment of objID0 and verify that exactly one
        # geometry was updated.
        frags = [MetaFragment('bar', 'raw', createFragRaw())]
        assert clerk.updateFragments(objID0, frags).ok

        # Verify that the new 'lastChanged' flag is now different.
        ret = clerk.getStateVariables([objID0])
        assert ret.ok
        assert ref_lastChanged != ret.data[objID0]['sv'].lastChanged

        # Verify further that the lastChanged attribute of objID1 is unchanged.
        ret = clerk.getStateVariables([objID1])
        assert ret.ok
        assert ref_lastChanged == ret.data[objID1]['sv'].lastChanged

    def test_updateBoosterValues(self):
        """
        Query and update the booster values in the instance data base.
        The query includes computing the correct force in object coordinates.
        """
        # Instantiate a Clerk.
        clerk = azrael.clerk.Clerk()

        # ---------------------------------------------------------------------
        # Create a template with two boosters and spawn it. The Boosters are
        # to the left/right of the object and point both in the positive
        # z-direction.
        # ---------------------------------------------------------------------
        # Convenience.
        sv = bullet_data.MotionState()

        b0 = parts.Booster(partID='0', pos=[-1, 0, 0], direction=[0, 0, 1],
                           minval=-1, maxval=1, force=0)
        b1 = parts.Booster(partID='1', pos=[+1, 0, 0], direction=[0, 0, 1],
                           minval=-1, maxval=1, force=0)

        # Define a template with one fragment.
        frags = [MetaFragment('foo', 'raw', createFragRaw())]
        t1 = Template('t1', [1, 2], frags, [b0, b1], [])

        # Add the template and spawn two instances.
        assert clerk.addTemplates([t1]).ok
        ret = clerk.spawn([(t1.name, sv), (t1.name, sv)])
        assert ret.ok
        objID_1, objID_2 = ret.data

        # ---------------------------------------------------------------------
        # Update the Booster forces on the first object: both accelerate the
        # object in z-direction, which means a force purely in z-direction and
        # no torque.
        # ---------------------------------------------------------------------
        cmd_0 = parts.CmdBooster(partID='0', force=1)
        cmd_1 = parts.CmdBooster(partID='1', force=1)
        ret = clerk.updateBoosterForces(objID_1, [cmd_0, cmd_1])
        assert ret.ok
        assert ret.data == ([0, 0, 2], [0, 0, 0])

        # ---------------------------------------------------------------------
        # Update the Booster forces on the first object: accelerate the left
        # one upwards and the right one downwards. This must result in a zero
        # net force but non-zero torque.
        # ---------------------------------------------------------------------
        cmd_0 = parts.CmdBooster(partID='0', force=1)
        cmd_1 = parts.CmdBooster(partID='1', force=-1)
        ret = clerk.updateBoosterForces(objID_1, [cmd_0, cmd_1])
        assert ret.ok
        assert ret.data == ([0, 0, 0], [0, 2, 0])

        # ---------------------------------------------------------------------
        # Update the Booster forces on the second object to ensure the function
        # correctly distinguishes between objects.
        # ---------------------------------------------------------------------
        # Turn off left Booster of first object (right booster remains active).
        cmd_0 = parts.CmdBooster(partID='0', force=0)
        ret = clerk.updateBoosterForces(objID_1, [cmd_0])
        assert ret.ok
        assert ret.data == ([0, 0, -1], [0, 1, 0])

        # Turn on left Booster of the second object.
        cmd_0 = parts.CmdBooster(partID='0', force=1)
        ret = clerk.updateBoosterForces(objID_2, [cmd_0])
        assert ret.ok
        assert ret.data == ([0, 0, +1], [0, 1, 0])

        # ---------------------------------------------------------------------
        # Attempt to update a non-existing Booster or a non-existing object.
        # ---------------------------------------------------------------------
        cmd_0 = parts.CmdBooster(partID='10', force=1)
        assert not clerk.updateBoosterForces(objID_2, [cmd_0]).ok

        cmd_0 = parts.CmdBooster(partID='0', force=1)
        assert not clerk.updateBoosterForces(1000, [cmd_0]).ok

    def test_updateFragmentState(self):
        """
        Create a new template with one fragment and create two instances. Then
        query and update the fragment states.
        """
        # Reset the SV database and instantiate a Leonard and Clerk.
        leo = getLeonard()
        clerk = azrael.clerk.Clerk()

        # Attempt to update the fragment state of non-existing objects.
        newStates = {2: [FragState('1', 2.2, [1, 2, 3], [1, 0, 0, 0])]}
        ret = clerk.updateFragmentStates(newStates)
        assert not ret.ok

        # Convenience.
        sv = bullet_data.MotionState()

        # Define a new template with one fragment.
        frags = [MetaFragment('foo', 'raw', createFragRaw())]
        t1 = Template('t1', [1, 2], fragments=frags, boosters=[], factories=[])

        # Add the template to Azrael, spawn two instances, and make sure
        # Leonard picks it up so that the object becomes available.
        assert clerk.addTemplates([t1]).ok
        _, _, (objID_1, objID_2) = clerk.spawn([(t1.name, sv), (t1.name, sv)])
        leo.processCommandsAndSync()

        def checkFragState(scale_1, pos_1, rot_1, scale_2, pos_2, rot_2):
            """
            Convenience function to verify the fragment states of
            objID_1 and objID_2 (defined in outer scope). This function
            assumes there are two objects and each has one fragment with
            name 'foo'.
            """
            # Query the SV for both objects.
            ret = clerk.getStateVariables([objID_1, objID_2])
            assert ret.ok and (len(ret.data) == 2)

            # Exract the one and only fragment of each object.
            _frag_1 = ret.data[objID_1]['frag'][0]
            _frag_2 = ret.data[objID_2]['frag'][0]

            # Verify the fragments have the expected values.
            assert _frag_1 == FragState('foo', scale_1, pos_1, rot_1)
            assert _frag_2 == FragState('foo', scale_2, pos_2, rot_2)

        # All fragments must initially be at the center.
        checkFragState(1, [0, 0, 0], [0, 0, 0, 1],
                       1, [0, 0, 0], [0, 0, 0, 1])

        # Update and verify the fragment states of the second object.
        newStates = {objID_2: [FragState('foo', 2.2, [1, 2, 3], [1, 0, 0, 0])]}
        assert clerk.updateFragmentStates(newStates).ok
        checkFragState(1, [0, 0, 0], [0, 0, 0, 1],
                       2.2, [1, 2, 3], [1, 0, 0, 0])

        # Modify the fragment states of two instances at once.
        newStates = {
            objID_1: [FragState('foo', 3.3, [1, 2, 4], [2, 0, 0, 0])],
            objID_2: [FragState('foo', 4.4, [1, 2, 5], [0, 3, 0, 0])]
        }
        assert clerk.updateFragmentStates(newStates).ok
        checkFragState(3.3, [1, 2, 4], [2, 0, 0, 0],
                       4.4, [1, 2, 5], [0, 3, 0, 0])

        # Attempt to update the fragment state of two objects. However, this
        # time only one of the objects actually exists. The expected behaviour
        # is that the command returns an error yet correctly updates the
        # fragment state of the existing object.
        newStates = {
            1000000: [FragState('foo', 5, [5, 5, 5], [5, 5, 5, 5])],
            objID_2: [FragState('foo', 5, [5, 5, 5], [5, 5, 5, 5])]
        }
        assert not clerk.updateFragmentStates(newStates).ok
        checkFragState(3.3, [1, 2, 4], [2, 0, 0, 0],
                       5.0, [5, 5, 5], [5, 5, 5, 5])

        # Attempt to update a non-existing fragment.
        newStates = {
            objID_2: [FragState('blah', 6, [6, 6, 6], [6, 6, 6, 6])]
        }
        assert not clerk.updateFragmentStates(newStates).ok
        checkFragState(3.3, [1, 2, 4], [2, 0, 0, 0],
                       5.0, [5, 5, 5], [5, 5, 5, 5])

        # Attempt to update several fragments in one object. However, not all
        # fragment IDs are valid. The expected behaviour is that none of the
        # fragments was updated.
        newStates = {
            objID_2: [FragState('foo', 7, [7, 7, 7], [7, 7, 7, 7]),
                      FragState('blah', 8, [8, 8, 8], [8, 8, 8, 8])]
        }
        assert not clerk.updateFragmentStates(newStates).ok
        checkFragState(3.3, [1, 2, 4], [2, 0, 0, 0],
                       5.0, [5, 5, 5], [5, 5, 5, 5])

        # Update the fragments twice with the exact same data. This trigger a
        # bug at one point but is fixed now.
        newStates = {objID_2: [FragState('foo', 9, [9, 9, 9], [9, 9, 9, 9])]}
        assert clerk.updateFragmentStates(newStates).ok
        assert clerk.updateFragmentStates(newStates).ok

    def test_isNameValid(self):
        """
        Test _isValid function.
        """
        # Create a Clerk instance and a shortcut to the test method.
        clerk = azrael.clerk.Clerk()
        inv = clerk._isNameValid

        # Thest valid names.
        assert inv('a')
        assert inv('a1')
        assert inv('a_')
        assert inv('_a')
        assert inv('1')
        assert inv('1a')
        assert inv('a' * 32)

        # Test invalid names.
        assert not inv('')
        assert not inv('.')
        assert not inv('a.b')
        assert not inv('a' * 33)

    def test_fragments_end2end(self):
        """
        Integration test: create a live system, add a template with two
        fragments, spawn it, query it, very its geometry, alter its
        geometry, and verify again.
        """
        clerk = azrael.clerk.Clerk()
        clacks = azrael.clacks.ClacksServer()
        clacks.start()

        # Reset the SV database and instantiate a Leonard and Clerk.
        leo = getLeonard()

        # Convenience.
        sv = bullet_data.MotionState()
        cs = [1, 2, 3, 4]
        vert_1 = list(range(0, 9))
        vert_2 = list(range(9, 18))

        def checkFragState(objID, name_1, scale_1, pos_1, rot_1,
                           name_2, scale_2, pos_2, rot_2):
            """
            Convenience function to verify the fragment states of ``objID``.
            This function assumes the object has exactly two fragments.
            """
            # Query the SV for both objects.
            ret = clerk.getStateVariables([objID])
            assert ret.ok and (len(ret.data) == 1)

            # Extract the fragments and verify there are the two.
            _frags = ret.data[objID]['frag']
            assert len(_frags) == 2

            # Convert the [FragState(), FragState()] list into a
            # {name_1: FragState, name_2: FragState, ...} dictionary. This is
            # purely for convenience below.
            _frags = {_.name: _ for _ in _frags}
            assert (name_1 in _frags) and (name_2 in _frags)

            # Verify the fragments have the expected values.
            assert _frags[name_1] == FragState(name_1, scale_1, pos_1, rot_1)
            assert _frags[name_2] == FragState(name_2, scale_2, pos_2, rot_2)
            del ret, _frags

        # Create a raw Fragment.
        f_raw = createFragRaw()
        f_dae = createFragDae()

        frags = [MetaFragment('10', 'raw', f_raw),
                 MetaFragment('test', 'dae', f_dae)]

        t1 = Template('t1', cs, frags, boosters=[], factories=[])
        assert clerk.addTemplates([t1]).ok
        ret = clerk.spawn([(t1.name, sv)])
        assert ret.ok
        objID = ret.data[0]
        leo.processCommandsAndSync()

        # Query the SV for the object and verify it has as many FragmentState
        # vectors as it has fragments.
        ret = clerk.getStateVariables([objID])
        assert ret.ok
        ret_frags = ret.data[objID]['frag']
        assert len(ret_frags) == len(frags)

        # Same as before, but this time use 'getAllStateVariables' instead of
        # 'getStateVariables'.
        ret = clerk.getAllStateVariables()
        assert ret.ok
        ret_frags = ret.data[objID]['frag']
        assert len(ret_frags) == len(frags)

        # Verify the fragment _states_ themselves.
        checkFragState(objID,
                       '10', 1, [0, 0, 0], [0, 0, 0, 1],
                       'test', 1, [0, 0, 0], [0, 0, 0, 1])

        # Modify the _state_ of both fragments and verify it worked.
        newStates = {
            objID: [
                FragState('10', 7, [7, 7, 7], [7, 7, 7, 7]),
                FragState('test', 8, [8, 8, 8], [8, 8, 8, 8])]
        }
        assert clerk.updateFragmentStates(newStates).ok
        checkFragState(objID,
                       '10', 7, [7, 7, 7], [7, 7, 7, 7],
                       'test', 8, [8, 8, 8], [8, 8, 8, 8])

        # Query the fragment _geometries_.
        ret = clerk.getGeometries([objID])
        assert ret.ok
        data = ret.data[objID]
        del ret

        def _download(url):
            for ii in range(10):
                try:
                    return urllib.request.urlopen(url).readall()
                except (urllib.request.HTTPError, urllib.request.URLError):
                    time.sleep(0.1)
            assert False

        # Download the 'raw' file and verify its content is correct.
        base_url = 'http://{}:{}'.format(
            azrael.config.addr_clacks, azrael.config.port_clacks)
        url = base_url + data['10']['url'] + '/model.json'
        tmp = _download(url)
        tmp = json.loads(tmp.decode('utf8'))
        assert FragRaw(**tmp) == f_raw

        # Download and verify the dae file. Note that the file name itself
        # matches the name of the fragment (ie. 'test'), *not* the name of the
        # original Collada file ('cube.dae').
        url = base_url + data['test']['url'] + '/test'
        tmp = _download(url)
        assert tmp == f_dae.dae

        # Download and verify the first texture.
        url = base_url + data['test']['url'] + '/rgb1.png'
        tmp = _download(url)
        assert tmp == f_dae.rgb['rgb1.png']

        # Download and verify the second texture.
        url = base_url + data['test']['url'] + '/rgb2.jpg'
        tmp = _download(url)
        assert tmp == f_dae.rgb['rgb2.jpg']

        # Change the fragment geometries.
        f_raw = createFragRaw()
        frags = [MetaFragment('10', 'raw', f_raw),
                 MetaFragment('test', 'dae', f_dae)]
        assert clerk.updateFragments(objID, frags).ok
        ret = clerk.getGeometries([objID])
        assert ret.ok
        data = ret.data[objID]
        del ret

        # Download the 'raw' file and verify its content is correct.
        url = base_url + data['10']['url'] + '/model.json'
        tmp = _download(url)
        tmp = json.loads(tmp.decode('utf8'))
        assert FragRaw(**tmp) == f_raw

        # Download and verify the dae file. Note that the file name itself
        # matches the name of the fragment (ie. 'test'), *not* the name of the
        # original Collada file ('cube.dae').
        url = base_url + data['test']['url'] + '/test'
        tmp = _download(url)
        assert tmp == f_dae.dae

        # Download and verify the first texture.
        url = base_url + data['test']['url'] + '/rgb1.png'
        tmp = _download(url)
        assert tmp == f_dae.rgb['rgb1.png']

        # Download and verify the second texture.
        url = base_url + data['test']['url'] + '/rgb2.jpg'
        tmp = _download(url)
        assert tmp == f_dae.rgb['rgb2.jpg']

        clacks.terminate()
        clacks.join()


def test_invalid():
    """
    Send an invalid command to Clerk.
    """
    class ClientTest(azrael.client.Client):
        def testSend(self, data):
            """
            Pass data verbatim to Clerk.

            This method is to test Clerk's ability to handle corrupt and
            invalid commands. If we used a normal Client then the protocol
            module would probably pick up most errors without them ever
            reaching Clerk.
            """
            self.sock_cmd.send(data)
            data = self.sock_cmd.recv()
            data = json.loads(data.decode('utf8'))
            return data['ok'], data['msg']

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

    print('Test passed')
