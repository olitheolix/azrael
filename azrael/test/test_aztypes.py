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

from IPython import embed as ipshell
from azrael.aztypes import Template, FragMeta, RigidBodyData, Booster, Factory
from azrael.aztypes import CollShapeMeta, CollShapeEmpty, CollShapeSphere
from azrael.aztypes import CollShapeBox, CollShapePlane, ConstraintMeta
from azrael.test.test import getP2P, get6DofSpring2, getRigidBody
from azrael.test.test import getCSEmpty, getCSBox, getCSSphere, getCSPlane
from azrael.test.test import getFragRaw, getFragDae, getFragObj, getFragNone, getTemplate


class TestAZTypes:
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

    def isJsonCompatible(self, data, DataType):
        """
        Verify that `data` serialises to JSON and can compile
        itself into ``DataType`` from positional- and keyword arguments.
        """
        assert data == DataType(*json.loads(json.dumps(data)))
        assert data == DataType(**json.loads(json.dumps(data._asdict())))
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
        # Verify that all geometry types serialise correctly.
        for Getter in (getFragRaw, getFragDae, getFragObj, getFragNone):
            # Get a proper FragMeta instance. Then get a stunted one where
            # 'fragdata' is None. The stunted case often happens internally in
            # Azrael because the meta data is stored in a separate database
            # that may not yet have synced.
            frag_a = Getter()
            frag_b = frag_a._replace(fragdata=None)
            assert self.isJsonCompatible(frag_a, FragMeta)
            assert self.isJsonCompatible(frag_b, FragMeta)

        # Verify that 'FragMeta._asdict' also converts the 'fragdata' field
        # to dictionaries. To do this we first convert the entire structure,
        # then only the 'fragdata' field, and finally verify that the entire
        # structure contains the correct dictionary for 'fragdata'.
        frag_t = getFragRaw()
        frag_d = frag_t._asdict()
        assert isinstance(frag_d, dict)

        tmp = frag_t.fragdata._asdict()
        assert isinstance(tmp, dict)
        assert tmp == frag_d['fragdata']

    def test_RigidBodyData(self):
        body_a = getRigidBody()
        body_b = getRigidBody()
        assert body_a == body_b

        assert self.isJsonCompatible(body_a, RigidBodyData)

    def test_Template(self):
        # Define boosters and factories.
        boosters = {
            '0': Booster(pos=(0, 1, 2), direction=(1, 0, 0),
                         minval=0, maxval=1, force=0),
            '1': Booster(pos=(3, 4, 5), direction=(0, 1, 0),
                         minval=0, maxval=2, force=0)
        }
        factories = {
            '0': Factory(pos=(0, 1, 2), direction=(0, 0, 1),
                         templateID='_templateBox', exit_speed=(0, 1)),
            '1': Factory(pos=(3, 4, 5), direction=(0, 1, 0),
                         templateID='_templateBox', exit_speed=(0, 1))
        }

        rbs = getRigidBody(position=(1, 2, 3))

        # Define a new template with two boosters and add it to Azrael.
        frags = {'1': getFragRaw(), '2': getFragDae(), '3': getFragObj()}
        temp_t = getTemplate('t1',
                             rbs=rbs,
                             fragments=frags,
                             boosters=boosters,
                             factories=factories)

        # Verify that it is JSON compatible.
        assert self.isJsonCompatible(temp_t, Template)

        # Verify that Template._asdict() method calls the _asdict() methods
        # for all collision shapes, fragments, boosters, and factories.
        temp_d = temp_t._asdict()
        fragments_d = {k: v._asdict() for (k, v) in temp_t.fragments.items()}
        boosters_d = {k: v._asdict() for (k, v) in temp_t.boosters.items()}
        factories_d = {k: v._asdict() for (k, v)in temp_t.factories.items()}
        rbs_d = rbs._asdict()
        assert temp_d['fragments'] == fragments_d
        assert temp_d['boosters'] == boosters_d
        assert temp_d['factories'] == factories_d
        assert temp_d['rbs'] == rbs_d
