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
from azrael.types import Template, RetVal, FragDae, FragRaw, FragmentMeta
from azrael.types import CollShapeMeta, CollShapeEmpty, CollShapeSphere
from azrael.types import CollShapeBox, CollShapePlane, FragState
from azrael.types import ConstraintMeta, ConstraintP2P, Constraint6DofSpring2
from azrael.types import RigidBodyState
from azrael.test.test import getFragRaw, getFragDae, getFragNone
from azrael.test.test import getCSEmpty, getCSBox, getCSSphere, getCSPlane
from azrael.test.test import getP2P, get6DofSpring2


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

    def test_FragmentMeta(self):
        for Getter in (getFragRaw, getFragDae, getFragNone):
            frag_a = Getter()
            assert self.isJsonCompatible(frag_a, FragmentMeta)

    def test_RigidBodyState(self):
        body_a = RigidBodyState()
        body_b = RigidBodyState()
        assert body_a == body_b

        assert self.isJsonCompatible(body_a, RigidBodyState)
