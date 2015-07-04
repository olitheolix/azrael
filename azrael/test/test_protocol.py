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
import os
import sys
import json
import base64
import pytest
import numpy as np

import azrael.test.test
import azrael.types as types
import azrael.config as config
import azrael.leo_api as leoAPI
import azrael.protocol as protocol

from IPython import embed as ipshell
from azrael.test.test import getP2P, get6DofSpring2
from azrael.test.test import getFragRaw, getFragDae, getFragNone, getRigidBody
from azrael.types import FragState, FragDae, FragRaw, FragMeta, Template


class TestClerk:
    @classmethod
    def setup_class(cls):
        pass

    @classmethod
    def teardown_class(cls):
        pass

    def setup_method(self, method):
        pass

    def teardown_method(self, method):
        pass

    def verifyToClerk(self, encode, decode, *payload):
        """
        Verify the ``encoder``/``decoder`` pair with ``payload``.

        This method encodes the payload with ``encoder``, converts the result
        to- and from JSON to simulate the wire transmission, passes the result
        to the ``decoder`` and verifies that the result matches the original
        ``payload``.

        This method is for the Client --> Clerk direction.
        """
        # Encode source data.
        ok, msg, enc = encode(*payload)
        assert ok

        # Convert output to JSON and back (simulates the wire transmission).
        enc = json.loads(json.dumps(enc))

        # Decode the data.
        ok, dec = decode(enc)
        assert ok is True
        assert dec == payload

    def verifyFromClerk(self, encoder, decoder, payload):
        """
        Verify the ``encoder``/``decoder`` pair with ``payload``.

        This method encodes the payload with ``encoder``, converts the result
        to- and from JSON to simulate the wire transmission, passes the result
        to the ``decoder`` and verifies that the result matches the original
        ``payload``.

        This method is for the Clerk --> Client direction. The only difference
        to ``verifyToClerk`` is the return value signature of the
        encoder/decoder.
        """
        # Encode source data.
        ok, enc = encoder(payload)
        assert ok

        # Convert to JSON and back (simulates the wire transmission).
        enc = json.loads(json.dumps(enc))

        # Decode the data.
        ok, msg, dec = decoder(enc)
        assert ok is ok
        assert dec == payload

    def getTestTemplate(self, templateID='templateID'):
        """
        Return a valid template with non-trivial data. The template contains
        multiple fragments (Raw and Collada), boosters, factories, and a rigid
        body.

        This is a convenience method only.
        """
        # Define a new object with two boosters and one factory unit.
        # The 'boosters' and 'factories' arguments are a list of named
        # tuples. Their first argument is the unit ID (Azrael does not
        # automatically assign any IDs).
        b0 = types.Booster(partID='0', pos=(0, 1, 2), direction=(0, 0, 1),
                           minval=0, maxval=0.5, force=0)
        b1 = types.Booster(partID='1', pos=(6, 7, 8), direction=(0, 1, 0),
                           minval=1, maxval=1.5, force=0)
        f0 = types.Factory(
            partID='0', pos=(0, 0, 0), direction=(0, 0, 1),
            templateID='_templateBox', exit_speed=(0.1, 0.5))

        # Create some fragments...
        frags = {'f1': getFragRaw(), 'f2': getFragDae(), 'f3': getFragNone()}

        # ... and a body...
        body = getRigidBody(position=(1, 2, 3))

        # ... then compile and return the template.
        return azrael.test.test.getTemplate(
            templateID,
            rbs=body,
            fragments=frags,
            boosters=[b0, b1],
            factories=[f0])

    def test_GetTemplate(self):
        """
        Test codec for {add,get}Template functions.
        """
        # Get a valid template.
        template = self.getTestTemplate()

        # Client --> Clerk.
        payload = [template.aid]
        enc = protocol.ToClerk_GetTemplates_Encode
        dec = protocol.ToClerk_GetTemplates_Decode
        self.verifyToClerk(enc, dec, payload)

        # Clerk --> Client.
        payload = {template.aid: {
            'url_frag': 'http://somewhere',
            'template': template}
        }
        enc = protocol.FromClerk_GetTemplates_Encode
        dec = protocol.FromClerk_GetTemplates_Decode
        self.verifyFromClerk(enc, dec, payload)

    def test_ControlCommand(self):
        """
        Test controlParts codec.
        """
        # Define the commands.
        cmd_0 = types.CmdBooster(partID='0', force_mag=0.2)
        cmd_1 = types.CmdBooster(partID='1', force_mag=0.4)
        cmd_2 = types.CmdFactory(partID='0', exit_speed=0)
        cmd_3 = types.CmdFactory(partID='2', exit_speed=0.4)
        cmd_4 = types.CmdFactory(partID='3', exit_speed=4)
        objID = 1

        # ----------------------------------------------------------------------
        # Client --> Clerk.
        # ----------------------------------------------------------------------

        # Convenience.
        enc_fun = protocol.ToClerk_ControlParts_Encode
        dec_fun = protocol.ToClerk_ControlParts_Decode

        # Encode the booster- and factory commands.
        boosters, factories = [cmd_0, cmd_1], [cmd_2, cmd_3, cmd_4]
        ret = enc_fun(objID, boosters, factories)
        assert ret.ok

        # Convert to JSON and back (simulates the wire transmission).
        enc = json.loads(json.dumps(ret.data))

        # Decode- and verify the data.
        ok, (dec_objID, dec_boosters, dec_factories) = dec_fun(enc)
        assert (ok, dec_objID) == (True, objID)
        assert dec_boosters == boosters
        assert dec_factories == factories

        # ----------------------------------------------------------------------
        # Clerk --> Client
        # ----------------------------------------------------------------------

        # Convenience.
        enc_fun = protocol.FromClerk_ControlParts_Encode
        dec_fun = protocol.FromClerk_ControlParts_Decode
        objIDs = [1, 2]

        # Encode source data.
        ok, enc = enc_fun(objIDs)
        assert ok

        # Convert output to JSON and back (simulates the wire transmission).
        enc = json.loads(json.dumps(enc))

        # Decode the data.
        ret = dec_fun(enc)
        assert (ret.ok, ret.data) == (True, objIDs)

    def test_GetBodyState(self):
        """
        Test codec for GetBodyState.
        """
        # Client --> Clerk.
        # The payload are object IDs.
        payload = [1, 2, 5]
        enc = protocol.ToClerk_GetBodyState_Encode
        dec = protocol.ToClerk_GetBodyState_Decode
        self.verifyToClerk(enc, dec, payload)

        # Clerk --> Client.
        frag_states = {
            '1': FragState(1, (0, 1, 2), (0, 0, 0, 1)),
            '2': FragState(2, (3, 4, 5), (1, 0, 0, 0)),
        }

        # The payload contains fragment- and body state data for each object.
        # The payload used here covers all cases where both, only one of the
        # two, or neither are defined.
        payload = {
            1: {'frag': frag_states, 'rbs': getRigidBody()},
            2: {'frag': {}, 'rbs': getRigidBody()},
            3: {'frag': frag_states, 'rbs': None},
            4: {'frag': {}, 'rbs': None},
            5: None,
        }
        del frag_states

        enc = protocol.FromClerk_GetBodyState_Encode
        dec = protocol.FromClerk_GetBodyState_Decode
        self.verifyFromClerk(enc, dec, payload)

    def test_add_get_constraint(self):
        """
        Add- and get constraints.
        """
        # Define the constraints.
        p2p = getP2P(rb_a=1, rb_b=2, pivot_a=(0, 1, 2), pivot_b=(3, 4, 5))
        dof = get6DofSpring2(rb_a=1, rb_b=2)

        # ----------------------------------------------------------------------
        # Client --> Clerk.
        # ----------------------------------------------------------------------
        for con in (p2p, dof):
            # Encode source data.
            ret = protocol.ToClerk_AddConstraints_Encode([con])
            assert ret.ok

            # Convert to JSON and back (simulates the wire transmission).
            enc = json.loads(json.dumps(ret.data))

            # Decode the data.
            ok, (dec_con, ) = protocol.ToClerk_AddConstraints_Decode(enc)
            assert (ok, len(dec_con)) == (True, 1)

            # Verify.
            assert dec_con[0] == con

        # ----------------------------------------------------------------------
        # Clerk --> Client
        # ----------------------------------------------------------------------
        for con in (p2p, dof):
            # Encode source data.
            ok, enc = protocol.FromClerk_GetConstraints_Encode([con])
            assert ok

            # Convert to JSON and back (simulates the wire transmission).
            enc = json.loads(json.dumps(enc))

            # Decode the data.
            dec_con = protocol.FromClerk_GetConstraints_Decode(enc)
            assert (dec_con.ok, len(dec_con.data)) == (True, 1)

            # Verify.
            assert dec_con.data[0] == con

    def test_addTemplate(self):
        """
        Test addTemplate codec a complex Template.
        """
        # Compile a valid Template structure.
        payload = [self.getTestTemplate('t1'), self.getTestTemplate('t2')]

        # Client --> Clerk
        enc = protocol.ToClerk_AddTemplates_Encode
        dec = protocol.ToClerk_AddTemplates_Decode
        self.verifyToClerk(enc, dec, payload)

    def test_spawn(self):
        """
        Spawn objects.
        """
        # Compile a valid Template structure.
        payload = [
            {'templateID': 'tid_1', 'rbs': {'position': [0, 1, 2]}},
            {'templateID': 'tid_2', 'rbs': {'orientation': [0, 1, 0, 0]}},
        ]

        # Client --> Clerk
        enc = protocol.ToClerk_Spawn_Encode
        dec = protocol.ToClerk_Spawn_Decode
        self.verifyToClerk(enc, dec, payload)

        # Clerk --> Client
        payload = [1, 20, 300]
        enc = protocol.FromClerk_Spawn_Encode
        dec = protocol.FromClerk_Spawn_Decode
        self.verifyFromClerk(enc, dec, payload)

    def test_getFragmentGeometries(self):
        """
        Test getFragmentGeometries.
        """
        # Client --> Clerk
        payload = [1, 2, 3]
        enc = protocol.ToClerk_GetFragmentGeometries_Encode
        dec = protocol.ToClerk_GetFragmentGeometries_Decode
        self.verifyToClerk(enc, dec, payload)

        # Clerk --> Client
        payload = {
            1: {'foo1': {'fragtype': 'raw', 'url_frag': 'http://foo1'},
                'bar1': {'fragtype': 'dae', 'url_frag': 'http://bar1'}},
            5: {'foo2': {'fragtype': 'raw', 'url_frag': 'http://foo2'},
                'bar2': {'fragtype': 'dae', 'url_frag': 'http://bar2'}}
        }
        enc = protocol.FromClerk_GetFragmentGeometries_Encode
        dec = protocol.FromClerk_GetFragmentGeometries_Decode
        self.verifyFromClerk(enc, dec, payload)

    def test_setFragmentGeometry(self):
        """
        Test setFragmentGeometry.
        """
        # Client --> Clerk
        objID = 1
        frags = {'f1': getFragRaw(), 'f2': getFragDae(), 'f3': getFragNone()}
        payload = (objID, frags)
        enc = protocol.ToClerk_SetFragmentGeometry_Encode
        dec = protocol.ToClerk_SetFragmentGeometry_Decode
        self.verifyToClerk(enc, dec, *payload)

    def test_setFragmentStates(self):
        """
        Test setFragmentStates.
        """
        # Client --> Clerk
        objID_1, objID_2 = 2, 5
        fs_1 = FragState(scale=1, position=(0, 1, 2), orientation=(1, 0, 0, 0))
        fs_2 = FragState(scale=2, position=(3, 3, 3), orientation=(0, 1, 0, 0))
        fs_3 = FragState(scale=3, position=(4, 5, 6), orientation=(0, 0, 1, 0))

        # Client is responsible for sending dictionaries, but on the Clerk side
        # the protocol will automatically convert all fragment states to proper
        # FragState instances.
        payload_in = {
            objID_1: {'foo': fs_1._asdict()},
            objID_2: {'bar': fs_2._asdict(), 'foobar': fs_3._asdict()}
        }
        payload_out = {
            objID_1: {'foo': fs_1},
            objID_2: {'bar': fs_2, 'foobar': fs_3}
        }
        enc = protocol.ToClerk_SetFragmentStates_Encode
        dec = protocol.ToClerk_SetFragmentStates_Decode

        # Send from Client to Clerk via JSON link.
        aux = enc(payload_in)
        ok, _, aux = json.loads(json.dumps(aux))
        assert ok

        # Decode on Clerk's side.
        ok, out = dec(aux)
        assert ok

        # Verify that the the payload is correct.
        assert out[0] == payload_out
