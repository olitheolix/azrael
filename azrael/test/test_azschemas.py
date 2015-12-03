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
Validate the JSON schemas.
"""
import jsonschema

from IPython import embed as ipshell
import azrael.azschemas as azschemas


class TestAZSchema:
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

    def getRigidBodyState(self):
        return {
            'scale': 1,
            'imass': 1,
            'restitution': 0.9,
            'rotation': [0.0, 0.0, 0.0, 1.0],
            'position': [0.0, 0.0, 0.0],
            'velocityLin': [0.0, 0.0, 0.0],
            'velocityRot': [0.0, 0.0, 0.0],
            'cshapes': {
                'Sphere': {
                    'cstype': 'SPHERE',
                    'position': [0.0, 0.0, 0.0],
                    'rotation': [0.0, 0.0, 0.0, 1.0],
                    'csdata': {'radius': 1},
                }
            },
            'linFactor': [1.0, 1.0, 1.0],
            'rotFactor': [1.0, 1.0, 1.0],
            'version': 0
        }

    def getFragments(self):
        return {
            'b_left': {
                'fragtype': 'RAW',
                'scale': 1,
                'position': [0.0, 0.0, 0.0],
                'rotation': [0.0, 0.0, 0.0, 1.0],
                'files': {'model.json': 'aa'}
            },
            'b_right': {
                'fragtype': 'RAW',
                'scale': 1,
                'position': [0.0, 0.0, 0.0],
                'rotation': [0.0, 0.0, 0.0, 1.0],
                'files': {'model.json': 'aa'}
            },
            'frag_1': {
                'fragtype': 'RAW',
                'scale': 1,
                'position': [0.0, 0.0, 0.0],
                'rotation': [0.0, 0.0, 0.0, 1.0],
                'files': {'model.json': 'aa'}
            }
        }

    def getBoosters(self):
        return {
            '0': {'position': [-1.5, 0.0, 0.0],
                  'direction': [0.0, -1.0, 0.0],
                  'force': 0},
            '1': {'position': [0.0, 0.0, 0.0],
                  'direction': [0.0, 0.0, -1.0],
                  'force': 0},
            '2': {'position': [1.5, -0.0, -0.0],
                  'direction': [0.0, 1.0, 0.0],
                  'force': 0},
            '3': {'position': [0.0, 0.0, 0.0],
                  'direction': [0.0, 0.0, 1.0],
                  'force': 0}
        }

    def getFactories(self):
        return {
            '0': {
                'position': [1.5, 0.0, 0.0],
                'direction': [1.0, 0.0, 0.0],
                'templateID': 'Product1',
                'exit_speed': [0.1, 1.0],
            },
            '1': {
                'position': [-1.5, 0.0, 0.0],
                'direction': [-1.0, 0.0, 0.0],
                'templateID': 'Product2',
                'exit_speed': [0.1, 1.0],
            }
        }

    def getTemplate(self):
        return {
            'aid': 'ground',
            'custom': '',
            'rbs': self.getRigidBodyState(),
            'fragments': self.getFragments(),
            'boosters': self.getBoosters(),
            'factories': self.getFactories(),
        }

    def test_Fragment(self):
        d = self.getFragments()
        for fragname, fragdata in d.items():
            jsonschema.validate(fragdata, azschemas.FragMeta)

    def test_Booster(self):
        d = self.getBoosters()
        for fragname, fragdata in d.items():
            jsonschema.validate(fragdata, azschemas.Booster)

    def test_Factory(self):
        d = self.getFactories()
        for fragname, fragdata in d.items():
            jsonschema.validate(fragdata, azschemas.Factory)

    def test_RigidBodyState(self):
        d = self.getRigidBodyState()
        jsonschema.validate(d, azschemas.RigidBodyState)

    def test_Template(self):
        d = self.getTemplate()
        jsonschema.validate(d, azschemas.Template)
