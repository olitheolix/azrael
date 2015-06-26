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

import azrael.types as types
import azrael.config as config
import azrael.leo_api as leoAPI
import azrael.protocol as protocol

from IPython import embed as ipshell
from azrael.test.test import getP2P, get6DofSpring2
from azrael.test.test import getFragRaw, getFragDae, getFragNone
from azrael.types import FragState, FragDae, FragRaw, FragmentMeta, Template


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

    def verifyToClerk(self, encode, decode, payload):
        """
        Verify the ``encoder``/``decoder`` pair with ``payload``.

        This method encodes the payload with ``encoder``, converts the result
        to- and from JSON to simulate the wire transmission, passes the result
        to the ``decoder`` and verifies that the result matches the original
        ``payload``.

        This method is for the Client --> Clerk direction.
        """
        # Encode source data.
        ok, msg, enc = encode(payload)
        assert ok

        # Convert output to JSON and back (simulates the wire transmission).
        enc = json.loads(json.dumps(enc))

        # Decode the data.
        ok, dec = decode(enc)
        assert ok is True
        assert dec == (payload, )

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

        # Convert output to JSON and back (simulates the wire transmission).
        enc = json.loads(json.dumps(enc))

        # Decode the data.
        ok, msg, dec = decoder(enc)
        assert ok is ok
        assert dec == payload

    def test_encoding_get_template(self):
        """
        Test codec for {add,get}Template functions.
        """
        # Collada format: a .dae file plus a list of textures in jpg or png format.
        dae_file = b'abc'
        dae_rgb1 = b'def'
        dae_rgb2 = b'ghj'

        # Encode the data as Base64.
        b64e = base64.b64encode
        b64_dae_file = b64e(dae_file).decode('utf8')
        b64_dae_rgb1 = b64e(dae_rgb1).decode('utf8')
        b64_dae_rgb2 = b64e(dae_rgb2).decode('utf8')

        # Compile the Collada fragment with the Base64 encoded data.
        f_dae = FragDae(dae=b64_dae_file,
                        rgb={'rgb1.png': b64_dae_rgb1,
                             'rgb2.jpg': b64_dae_rgb2})

        # Compile a valid Template structure.
        frags = [getFragRaw(), getFragDae(), getFragNone()]
        temp = Template('foo', [], frags, [], [])

        # ----------------------------------------------------------------------
        # Client --> Clerk.
        # ----------------------------------------------------------------------
        # Encode source data.
        ret = protocol.ToClerk_GetTemplates_Encode([temp.aid])

        # Convert output to JSON and back (simulates the wire transmission).
        enc = json.loads(json.dumps(ret.data))

        # Decode the data.
        ok, dec = protocol.ToClerk_GetTemplates_Decode(enc)
        assert dec[0] == [temp.aid]

        # ----------------------------------------------------------------------
        # Clerk --> Client.
        # ----------------------------------------------------------------------
        payload = {temp.aid: {'url': 'http://somewhere', 'template': temp}}
        ok, enc = protocol.FromClerk_GetTemplates_Encode(payload)

        # Convert output to JSON and back (simulates the wire transmission).
        enc = json.loads(json.dumps(enc))

        # Decode the data.
        dec = protocol.FromClerk_GetTemplates_Decode(enc)

        # Verify.
        assert dec.ok
        assert dec.data == payload

    def test_send_command(self):
        """
        Test controlParts codec.
        """
        # Define the commands.
        cmd_0 = types.CmdBooster(partID='0', force=0.2)
        cmd_1 = types.CmdBooster(partID='1', force=0.4)
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
        ret = enc_fun(objID, [cmd_0, cmd_1], [cmd_2, cmd_3, cmd_4])
        assert ret.ok

        # Convert output to JSON and back (simulates the wire transmission).
        enc = json.loads(json.dumps(ret.data))

        # Decode the data and verify the correct number of commands was returned.
        ok, (dec_objID, dec_booster, dec_factory) = dec_fun(enc)
        assert (ok, dec_objID) == (True, objID)
        assert len(dec_booster) == 2
        assert len(dec_factory) == 3

        # Use getattr to automatically test all attributes.
        assert dec_booster[0] == cmd_0
        assert dec_booster[1] == cmd_1
        assert dec_factory[0] == cmd_2
        assert dec_factory[1] == cmd_3
        assert dec_factory[2] == cmd_4

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
        Test codec for RigidBodyState tuple.
        """
        objs = [{'frag': {}, 'sv': types.RigidBodyState()},
                {'frag': {}, 'sv': types.RigidBodyState()}]
        objIDs = [1, 2]

        # ----------------------------------------------------------------------
        # Client --> Clerk.
        # ----------------------------------------------------------------------
        # Encode source data.
        ret = protocol.ToClerk_GetBodyState_Encode(objIDs)
        assert ret.ok

        # Convert output to JSON and back (simulates the wire transmission).
        enc = json.loads(json.dumps(ret.data))

        # Decode the data.
        ok, (dec_ids, ) = protocol.ToClerk_GetBodyState_Decode(enc)
        assert (ok, len(dec_ids)) == (True, 2)

        # Verify.
        assert dec_ids == objIDs

        # ----------------------------------------------------------------------
        # Clerk --> Client.
        # ----------------------------------------------------------------------
        # Encode source data.
        data = dict(zip(objIDs, objs))
        ok, enc = protocol.FromClerk_GetBodyState_Encode(data)

        # Convert output to JSON and back (simulates the wire transmission).
        enc = json.loads(json.dumps(enc))

        # Decode the data.
        dec_sv = protocol.FromClerk_GetBodyState_Decode(enc)
        assert (dec_sv.ok, len(dec_sv.data)) == (True, 2)

        # Verify.
        dec_sv = dec_sv.data
        dec_sv = {k: dec_sv[k]['sv'] for k in dec_sv}
        assert dec_sv[1] == objs[0]['sv']
        assert dec_sv[2] == objs[1]['sv']

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

            # Convert output to JSON and back (simulates the wire transmission).
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

            # Convert output to JSON and back (simulates the wire transmission).
            enc = json.loads(json.dumps(enc))

            # Decode the data.
            dec_con = protocol.FromClerk_GetConstraints_Decode(enc)
            assert (dec_con.ok, len(dec_con.data)) == (True, 1)

            # Verify.
            assert dec_con.data[0] == con

    def test_addTemplate(self):
        """
        Test addTemplate codec with Collada data.
        """
        # Collada format: a .dae file plus a list of textures in jpg or png format.
        dae_file = b'abc'
        dae_rgb1 = b'def'
        dae_rgb2 = b'ghj'

        # Encode the data as Base64.
        b64e = base64.b64encode
        b64_dae_file = b64e(dae_file).decode('utf8')
        b64_dae_rgb1 = b64e(dae_rgb1).decode('utf8')
        b64_dae_rgb2 = b64e(dae_rgb2).decode('utf8')

        # Compile the Collada fragment with the Base64 encoded data.
        f_dae = FragDae(dae=b64_dae_file,
                        rgb={'rgb1.png': b64_dae_rgb1,
                             'rgb2.jpg': b64_dae_rgb2})

        # Compile a valid Template structure.
        frags = [getFragRaw(), getFragDae(), getFragNone()]
        temp = Template('foo', [], frags, [], [])

        # ----------------------------------------------------------------------
        # Client --> Clerk.
        # ----------------------------------------------------------------------
        # Encode source data.
        ret = protocol.ToClerk_AddTemplates_Encode([temp])
        assert ret.ok

        # Convert output to JSON and back (simulates the wire transmission).
        enc = json.loads(json.dumps(ret.data))

        # Decode the data.
        ok, dec = protocol.ToClerk_AddTemplates_Decode(enc)

        # Extract the data from the first fragment of the first template.
        dec_mf = dec[0][0].fragments

        # Compare with the Fragment before it was Base64 encoded.
        assert dec_mf == frags

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
            1: {'foo1': {'type': 'raw', 'url': 'http://foo1'},
                'bar1': {'type': 'dae', 'url': 'http://bar1'}},
            5: {'foo2': {'type': 'raw', 'url': 'http://foo2'},
                'bar2': {'type': 'dae', 'url': 'http://bar2'}}
        }
        enc = protocol.FromClerk_GetFragmentGeometries_Encode
        dec = protocol.FromClerk_GetFragmentGeometries_Decode
        self.verifyFromClerk(enc, dec, payload)
