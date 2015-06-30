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
import json
import pytest

import azrael.config as config

from IPython import embed as ipshell
from azrael.types import Template, RetVal, FragDae, FragRaw, FragMeta
from azrael.types import Booster, Factory
from azrael.types import CollShapeMeta, CollShapeEmpty, CollShapeSphere
from azrael.types import CollShapeBox, CollShapePlane, FragState
from azrael.types import ConstraintMeta, ConstraintP2P, Constraint6DofSpring2
from azrael.types import RigidBodyState
from azrael.test.test import getFragRaw, getFragDae, getFragNone, getTemplate
from azrael.test.test import getCSEmpty, getCSBox, getCSSphere, getCSPlane
from azrael.test.test import getP2P, get6DofSpring2, getRigidBody


class TestDibbler:
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

    def isJsonCompatible(self, dt_a, DataType):
        """
        Verify that that the `instance` serialises to JSON and can compile
        itself from positional- and keyword arguments.
        """
        assert dt_a == DataType(*json.loads(json.dumps(dt_a)))
        assert dt_a == DataType(**json.loads(json.dumps(dt_a._asdict())))
        return True

    def test_CollShapeMeta(self):
        for Getter in (getCSEmpty, getCSSphere, getCSBox, getCSPlane):
            cs_a = Getter()
            cs_b = Getter()
            assert cs_a == cs_b
            assert self.isJsonCompatible(cs_a, CollShapeMeta)

    def test_CollShapeEmpty(self):
        cs_a = CollShapeEmpty()
        cs_b = CollShapeEmpty()
        assert cs_a == cs_b
        assert self.isJsonCompatible(cs_a, CollShapeEmpty)

    def test_CollShapeSphere(self):
        cs_a = CollShapeSphere(radius=1)
        cs_b = CollShapeSphere(radius=1)
        assert cs_a == cs_b
        assert self.isJsonCompatible(cs_a, CollShapeSphere)

    def test_CollShapeBox(self):
        cs_a = CollShapeBox(x=1, y=2, z=3.5)
        cs_b = CollShapeBox(x=1, y=2, z=3.5)
        assert cs_a == cs_b
        assert self.isJsonCompatible(cs_a, CollShapeBox)

    def test_CollShapePlane(self):
        cs_a = CollShapePlane(normal=(1, 2, 3), ofs=-1)
        cs_b = CollShapePlane(normal=(1, 2, 3), ofs=-1)
        assert cs_a == cs_b
        assert self.isJsonCompatible(cs_a, CollShapePlane)

    def test_ConstraintMeta(self):
        for Getter in (getP2P, get6DofSpring2):
            con_a = Getter()
            con_b = Getter()
            assert con_a == con_b
            assert self.isJsonCompatible(con_a, ConstraintMeta)

        # Verify that 'FragMeta._asdict' also converts the 'fragdata' field
        # to dictionaries.
        con_t = getP2P()
        con_d = con_t._asdict()
        assert isinstance(con_d, dict)
        tmp = con_t.condata._asdict()
        assert isinstance(tmp, dict)
        assert tmp == con_d['condata']

    def test_FragMeta(self):
        for Getter in (getFragRaw, getFragDae, getFragNone):
            # Get a proper FragMeta, and a stunted one where the 'fragdata'
            # field is None. This case often happens internally in Azrael
            # because the meta data is stored in a separate database.
            frag_a = Getter()
            frag_b = frag_a._replace(fragdata=None)
            assert self.isJsonCompatible(frag_a, FragMeta)
            assert self.isJsonCompatible(frag_b, FragMeta)

        # Verify that 'FragMeta._asdict' also converts the 'fragdata' field
        # to dictionaries.
        frag_t = getFragRaw()
        frag_d = frag_t._asdict()
        assert isinstance(frag_d, dict)
        tmp = frag_t.fragdata._asdict()
        assert isinstance(tmp, dict)
        assert tmp == frag_d['fragdata']

    def test_RigidBodyState(self):
        body_a = getRigidBody()
        body_b = getRigidBody()
        assert body_a == body_b

        assert self.isJsonCompatible(body_a, RigidBodyState)

    def test_FragState(self):
        body_a = FragState('blah', 2, (1, 2, 3), (0, 0, 0, 1))
        body_b = FragState('blah', 2, (1, 2, 3), (0, 0, 0, 1))
        assert body_a == body_b

        assert self.isJsonCompatible(body_a, FragState)

    def test_Template(self):
        # Define a boosters.
        b0 = Booster(partID='0', pos=(0, 1, 2), direction=(1, 0, 0),
                     minval=0, maxval=1, force=0)
        b1 = Booster(partID='1', pos=(3, 4, 5), direction=(0, 1, 0),
                     minval=0, maxval=2, force=0)
        f0 = Factory(partID='0', pos=(0, 1, 2), direction=(0, 0, 1),
                     templateID='_templateBox', exit_speed=(0, 1))
        f1 = Factory(partID='1', pos=(3, 4, 5), direction=(0, 1, 0),
                     templateID='_templateBox', exit_speed=(0, 1))

        rbs = getRigidBody(position=(1, 2, 3))

        # Define a new template with two boosters and add it to Azrael.
        temp_t = getTemplate('t1',
                             cshapes=[getCSSphere(), getCSEmpty()],
                             rbs=rbs,
                             fragments=[getFragRaw(), getFragDae()],
                             boosters=[b0, b1],
                             factories=[f0, f1])

        # Verify that it is JSON compatible.
        assert self.isJsonCompatible(temp_t, Template)

        # Verify that Templae._asdict() method calls the _asdict() methods for
        # all collision shapes, fragments, boosters, and factories.
        temp_d = temp_t._asdict()
        cshapes_d = [_._asdict() for _ in temp_t.cshapes]
        fragments_d = [_._asdict() for _ in temp_t.fragments]
        boosters_d = [_._asdict() for _ in temp_t.boosters]
        factories_d = [_._asdict() for _ in temp_t.factories]
        rbs_d = rbs._asdict()
        assert temp_d['cshapes'] == cshapes_d
        assert temp_d['fragments'] == fragments_d
        assert temp_d['boosters'] == boosters_d
        assert temp_d['factories'] == factories_d
        assert temp_d['rbs'] == rbs_d
