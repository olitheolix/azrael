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
A collection of named tuples and a typecheck decorator.

The decorator automatically verifies function arguments based on their
annotations in the signature.

Usage example::

    from azrael.types import typecheck

    @typecheck
    def foo(a, b:str, c:int =0, d:(int, str)=None):
        pass

"""
import inspect
import functools
import numpy as np
from collections import namedtuple, OrderedDict

# Uniform return value signature.
RetVal = namedtuple('RetVal', 'ok msg data')

# Template dataset.
_Template = namedtuple('_Template', 'aid cshapes fragments boosters factories')
_FragState = namedtuple('FragState', 'aid scale position orientation')

# Fragments.
_MetaFragment = namedtuple('_MetaFragment', 'aid fragtype fragdata')
_FragRaw = namedtuple('_FragRaw', 'vert uv rgb')
_FragDae = namedtuple('_FragDae', 'dae rgb')

# Work package related.
WPData = namedtuple('WPData', 'aid sv force torque')
WPMeta = namedtuple('WPAdmin', 'wpid dt maxsteps')
Forces = namedtuple('Forces',
                    'forceDirect forceBoost torqueDirect torqueBoost')

# Motion state of an object.
_RigidBodyState = namedtuple('_RigidBodyState',
                             'scale imass restitution orientation '
                             'position velocityLin velocityRot cshapes '
                             'axesLockLin axesLockRot version')

# Collision shapes.
_CollShapeMeta = namedtuple('_CollShapeMeta',
                            'aid cstype position rotation csdata')
_CollShapeBox = namedtuple('_CollShapeBox', 'x y z')
_CollShapeEmpty = namedtuple('_CollShapeEmpty', '')
_CollShapeSphere = namedtuple('_CollShapeSphere', 'radius')
_CollShapePlane = namedtuple('_CollShapePlane', 'normal ofs')

# Constraints.
ConstraintMeta = namedtuple('ConstraintMeta', 'aid contype rb_a rb_b condata')
ConstraintP2P = namedtuple('ConstraintP2P', 'pivot_a pivot_b')
Constraint6DofSpring2 = namedtuple(
    'Constraint6DofSpring2', 'frameInA frameInB stiffness damping equilibrium '
                             'linLimitLo linLimitHi rotLimitLo rotLimitHi '
                             'bounce enableSpring')


def typecheck(func_handle):
    """
    Ensure arguments have the type specified in the annotation signature.

    Example::

        def foo(a, b:str, c:int =0, d:(int, list)=None):
            pass

    This function accepts an arbitrary parameter for ``a``, a string
    for ``b``, an integer for ``c`` which defaults to 0, and either
    an integer or a list for ``d`` and defaults to ``None``.

    The decorator does not check return types and considers derived
    classes as valid (ie. the type check uses the Python native
    ``isinstance`` to do its job). For instance, if the function is
    defined as::

        @type_check
        def foo(a: QtGui.QWidget):
            pass

    then the following two calls will both succeed::

        foo(QtGui.QWidget())
        foo(QtGui.QTextEdit())

    because ``QTextEdit`` inherits ``QWidget``.

    .. note:: the check is skipped if the value (either passed or by
              default) is **None**.

    |Raises|

    * **TypeError** if at least one argument has an invalid type.
    """
    def checkType(var_name, var_val, annot):
        # Retrieve the annotation for this variable and determine
        # if the type of that variable matches with the annotation.
        # This annotation is stored in the dictionary ``annot``
        # but contains only variables for such an annotation exists,
        # hence the if/else branch.
        if var_name in annot:
            # Fetch the type-annotation of the variable.
            var_anno = annot[var_name]

            # Skip the type check if the variable is none, otherwise
            # check if it is a derived class. The only exception from
            # the latter rule are binary values, because in Python
            #
            # >> isinstance(False, int)
            # True
            #
            # and warrants a special check.
            if var_val is None:
                type_ok = True
            elif (type(var_val) is bool):
                type_ok = (type(var_val) in var_anno)
            else:
                type_ok = True in [isinstance(var_val, _) for _ in var_anno]
        else:
            # Variable without annotation are compatible by assumption.
            var_anno = 'Unspecified'
            type_ok = True

        # If the check failed then raise a TypeError.
        if not type_ok:
            args = (var_name, func_handle.__name__, var_anno, type(var_val))
            msg = ('Expected the variable <{}> in function <{}> to have\n'
                   'type {} but has {}\n')
            msg = msg.format(*args)
            print(msg)
            raise TypeError(*args)

    @functools.wraps(func_handle)
    def wrapper(*args, **kwds):
        # Retrieve information about all arguments passed to the function,
        # as well as their annotations in the function signature.
        argspec = inspect.getfullargspec(func_handle)

        # Convert all variable annotations that were not specified as a
        # tuple or list into one, eg. str --> will become (str,)
        annot = {}
        for key, val in argspec.annotations.items():
            if isinstance(val, tuple) or isinstance(val, list):
                annot[key] = val
            else:
                annot[key] = val,       # Note the trailing colon!

        # Prefix the argspec.defaults tuple with **None** elements to make
        # its length equal to the number of variables (for sanity in the
        # code below). Since **None** types are always ignored by this
        # decorator this change is neutral.
        if argspec.defaults is None:
            defaults = tuple([None] * len(argspec.args))
        else:
            num_none = len(argspec.args) - len(argspec.defaults)
            defaults = tuple([None] * num_none) + argspec.defaults

        # Shorthand for the number of unnamed arguments.
        ofs = len(args)

        # Process the unnamed arguments. These are always the first ``ofs``
        # elements in argspec.args.
        for idx, var_name in enumerate(argspec.args[:ofs]):
            # Look up the value in the ``args`` variable.
            var_val = args[idx]
            checkType(var_name, var_val, annot)

        # Process the named- and default arguments.
        for idx, var_name in enumerate(argspec.args[ofs:]):
            # Extract the argument value. If it was passed to the
            # function as a named (ie. keyword) argument then extract
            # it from ``kwds``, otherwise look it up in the tuple with
            # the default values.
            if var_name in kwds:
                var_val = kwds[var_name]
            else:
                var_val = defaults[idx + ofs]
            checkType(var_name, var_val, annot)
        return func_handle(*args, **kwds)
    return wrapper


class FragRaw(_FragRaw):
    """
    :param [float] vert: vertex data
    :param [float] uv: UV map coordinates
    :param [uint8]: RGB texture values.
    :return _FragRaw: compiled Raw fragment.
    """
    @typecheck
    def __new__(cls, vert, uv, rgb):
        try:
            assert isinstance(vert, (tuple, list, np.ndarray))
            assert isinstance(uv, (tuple, list, np.ndarray))
            assert isinstance(rgb, (tuple, list, np.ndarray))

            vert = np.array(vert, np.float64)
            uv = np.array(uv, np.float64)
            rgb = np.array(rgb, np.uint8)
            assert vert.ndim == 1
            assert uv.ndim == 1
            assert rgb.ndim == 1
            vert = tuple(vert.tolist())
            uv = tuple(uv.tolist())
            rgb = tuple(rgb.tolist())
            # The number of vertices must be an integer multiple of 9 to
            # constitute a valid triangle mesh (every triangle has three
            # edges and every edge requires an (x, y, z) triplet to
            # describe its position).
            assert len(vert) % 9 == 0
            assert len(uv) % 2 == 0
            assert len(rgb) % 3 == 0
            assert len(vert) % 3 == len(uv) % 2
        except (TypeError, AssertionError):
            raise TypeError

        return super().__new__(cls, vert, uv, rgb)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))


class FragDae(_FragDae):
    """
    :param str dae: Collada file
    :param dict rgb: dictionary of texture files.
    :return _FragDae: compiled Collada fragment description.
    """
    @typecheck
    def __new__(cls, dae: str, rgb: dict):
        try:
            assert isinstance(dae, str)
            for k, v in rgb.items():
                assert isinstance(k, str)
                assert isinstance(v, str)
        except AssertionError:
            raise TypeError

        return super().__new__(cls, dae, rgb)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))


class MetaFragment(_MetaFragment):
    """
    :param str type: fragment type (eg 'raw', or 'dae')
    :param dict aid: fragment name
    :param data: one of the fragment types (eg. `FragRaw` or `FragDae`).
    :return _MetaFragment: a valid meta fragment instance.
    """
    @typecheck
    def __new__(cls, aid: str, ftype: str, data):
        try:
            assert isinstance(aid, str)
            assert isinstance(ftype, str)
            if data is None:
                frag = None
            else:
                assert ftype.lower() in ('dae', 'raw')
                ftype = ftype.upper()
                if ftype == 'RAW':
                    frag = FragRaw(*data)
                elif ftype == 'DAE':
                    frag = FragDae(*data)
                else:
                    assert False
        except (TypeError, AssertionError):
            raise TypeError

        return super().__new__(cls, aid, ftype, frag)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))


class Template(_Template):
    """
    fixme: docu
    fixme: parameters

    :param dict aid: template name
    :return _Template: a valid meta fragment instance.
    """
    @typecheck
    def __new__(cls, aid: str,
                cshapes: (tuple, list),
                fragments: (tuple, list),
                boosters: (tuple, list),
                factories: (tuple, list)):
        try:
            frags = [MetaFragment(*_) for _ in fragments]
        except (TypeError, AssertionError):
            raise TypeError

        return super().__new__(cls, aid, cshapes, frags, boosters, factories)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))


class FragState(_FragState):
    """
    fixme: docu
    fixme: parameters

    :param dict aid: fragment name
    :return _FragState: a valid meta fragment instance.
    """
    @typecheck
    def __new__(cls, aid: str,
                scale: (int, float),
                position: (tuple, list),
                orientation: (tuple, list)):
        try:
            p = np.array(position, np.float64)
            o = np.array(orientation, np.float64)
            assert p.ndim == o.ndim == 1
            assert len(p) == 3
            assert len(o) == 4
            assert scale >= 0
            p = p.tolist()
            o = o.tolist()
        except (TypeError, AssertionError):
            raise TypeError

        return super().__new__(cls, aid, scale, p, o)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))


class CollShapeMeta(_CollShapeMeta):
    """
    fixme: docu
    fixme: parameters

    :param dict aid: fragment name
    :return _CollShapeMeta: a valid meta fragment instance.
    """
    @typecheck
    def __new__(cls, aid: str,
                cstype: str,
                position: (tuple, list, np.ndarray),
                rotation: (tuple, list, np.ndarray),
                csdata):
        try:
            p = np.array(position, np.float64)
            r = np.array(rotation, np.float64)
            assert p.ndim == r.ndim == 1
            assert len(p) == 3
            assert len(r) == 4
            p = p.tolist()
            r = r.tolist()
        except (TypeError, AssertionError):
            raise TypeError

        return super().__new__(cls, aid, cstype, p, r, csdata)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))


class CollShapeEmpty(_CollShapeEmpty):
    """
    fixme: docu
    fixme: parameters

    :param dict aid: fragment name
    :return _CollShapeEmpty: a valid 'Empty' collision shape.
    """
    @typecheck
    def __new__(cls):
        return super().__new__(cls)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))


class CollShapeBox(_CollShapeBox):
    """
    fixme: docu
    fixme: parameters

    :param dict aid: fragment name
    :return _CollShapeBox: a valid 'Box' collision shape.
    """
    @typecheck
    def __new__(cls, x: (int, float), y: (int, float), z: (int, float)):
        try:
            assert (x >= 0) and (y >= 0) and (z >= 0)
        except (TypeError, AssertionError):
            raise TypeError
        return super().__new__(cls, x, y, z)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))


class CollShapeSphere(_CollShapeSphere):
    """
    fixme: docu
    fixme: parameters

    :param dict aid: fragment name
    :return _CollShapeSphere: a valid 'Sphere' collision shape.
    """
    @typecheck
    def __new__(cls, radius: (int, float)):
        try:
            assert radius >= 0
        except (TypeError, AssertionError):
            raise TypeError
        return super().__new__(cls, radius)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))


class CollShapePlane(_CollShapePlane):
    """
    fixme: docu
    fixme: parameters

    :param dict aid: fragment name
    :return _CollShapePlane: a valid 'Plane' collision shape.
    """
    @typecheck
    def __new__(cls, normal: (tuple, list), ofs: (int, float)):
        try:
            normal = np.array(normal, np.float64)
            assert normal.ndim == 1
            assert len(normal) == 3
            normal = normal.tolist()
        except (TypeError, AssertionError):
            raise TypeError
        return super().__new__(cls, normal, ofs)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))
