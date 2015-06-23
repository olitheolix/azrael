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
import logging
import inspect
import functools
import numpy as np
from collections import namedtuple, OrderedDict

# Create module logger.
logit = logging.getLogger('azrael.' + __name__)

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
_ConstraintMeta = namedtuple('_ConstraintMeta', 'aid contype rb_a rb_b condata')
_ConstraintP2P = namedtuple('_ConstraintP2P', 'pivot_a pivot_b')
_Constraint6DofSpring2 = namedtuple(
    '_Constraint6DofSpring2', 'frameInA frameInB stiffness damping equilibrium '
                             'linLimitLo linLimitHi rotLimitLo rotLimitHi '
                             'bounce enableSpring')

def toVec(num_el, v):
    """
    Verify that ``v`` is a vector with ``num_el`` entries.

    :param int num_el: positive integer
    :param v: an iterable (eg tuple, list, NumPy array).
    :return: v as tuple
    """
    assert num_el > 0
    try:
        v = np.array(v, np.float64)
        assert v.ndim == 1
        assert len(v) == num_el
    except (TypeError, AssertionError):
        assert False
    return tuple(v)
    

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
            msg = 'Cannot construct <{}>'.format(cls.__name__)
            logit.warning(msg)
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
            msg = 'Cannot construct <{}>'.format(cls.__name__)
            logit.warning(msg)
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
            assert isAIDStringValid(aid)
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
            msg = 'Cannot construct <{}>'.format(cls.__name__)
            logit.warning(msg)
            raise TypeError

        return super().__new__(cls, aid, ftype, frag)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))


def isAIDStringValid(aid):
    """
    Return *True* if ``aid`` is a valid ID name in Azrael.

    The ``aid`` must be a string with at most 32 characters drawn from
    [a-zA-Z0-9] and '_'.

    :param str aid: the AID string to validate.
    :return: *True* if ``aid`` is valid, *False* otherwise.
    """
    # Aid must be a string.
    if not isinstance(aid, str):
        return False

    # Must contain at least one character and no more than 32.
    if not (0 <= len(aid) <= 32):
        return False

    # Compile the set of admissible characters.
    ref = 'abcdefghijklmnopqrstuvwxyz'
    ref += ref.upper()
    ref += '0123456789_'
    ref = set(ref)

    # Return true if ``aid`` only consists of characters from the just
    # defined reference set.
    return set(aid).issubset(ref)


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
            assert isAIDStringValid(aid)

            # Compile- and sanity check all collision shapes.
            cshapes = [CollShapeMeta(*_) for _ in cshapes]

            # Compile- and sanity check all geometry fragments.
            frags = [MetaFragment(*_) for _ in fragments]
        except (TypeError, AssertionError):
            msg = 'Cannot construct <{}>'.format(cls.__name__)
            logit.warning(msg)
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
            # Verify the inputs.
            assert isAIDStringValid(aid)
            assert scale >= 0
            position = toVec(3, position)
            orientation = toVec(4, orientation)

        except (TypeError, AssertionError):
            msg = 'Cannot construct <{}>'.format(cls.__name__)
            logit.warning(msg)
            raise TypeError

        return super().__new__(cls, aid, scale, position, orientation)

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
            # Verify the inputs.
            assert isAIDStringValid(aid)
            position = toVec(3, position)
            rotation = toVec(4, rotation)

            cstype = cstype.upper()
            if cstype == 'SPHERE':
                csdata = CollShapeSphere(*csdata)
            elif cstype == 'BOX':
                csdata = CollShapeBox(*csdata)
            elif cstype == 'EMPTY':
                csdata = CollShapeEmpty(*csdata)
            elif cstype == 'PLANE':
                csdata = CollShapePlane(*csdata)
            else:
                assert False
        except (TypeError, AssertionError):
            msg = 'Cannot construct <{}>'.format(cls.__name__)
            logit.warning(msg)
            raise TypeError

        return super().__new__(cls, aid, cstype, position, rotation, csdata)

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
            msg = 'Cannot construct <{}>'.format(cls.__name__)
            logit.warning(msg)
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
            msg = 'Cannot construct <{}>'.format(cls.__name__)
            logit.warning(msg)
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
            # Verify the inputs.
            normal = toVec(3, normal)
        except (TypeError, AssertionError):
            msg = 'Cannot construct <{}>'.format(cls.__name__)
            logit.warning(msg)
            raise TypeError
        return super().__new__(cls, normal, ofs)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))


class ConstraintMeta(_ConstraintMeta):
    """
    fixme: docu
    fixme: parameters

    :param dict aid: fragment name
    :return _ConstraintMeta: a valid 'Plane' collision shape.
    """
    @typecheck
    def __new__(cls, aid: str, contype: str, rb_a: int, rb_b: int,
                condata: (tuple, list, dict)):
        try:
            # Verify the inputs.
            assert isAIDStringValid(aid)
            assert (rb_a >= 0) and (rb_b >= 0)

            if contype.upper() == 'P2P':
                if isinstance(condata, dict):
                    condata = ConstraintP2P(**condata)
                else:
                    condata = ConstraintP2P(*condata)
            elif contype.upper() == '6DOFSPRING2':
                if isinstance(condata, dict):
                    condata = Constraint6DofSpring2(**condata)
                else:
                    condata = Constraint6DofSpring2(*condata)
            else:
                assert False
        except (TypeError, AssertionError) as err:
            msg = 'Cannot construct <{}>'.format(cls.__name__)
            logit.warning(msg)
            raise TypeError
        return super().__new__(cls, aid, contype, rb_a, rb_b, condata)

    def _asdict(self):
        tmp = self._replace(condata=self.condata._asdict())
        return OrderedDict(zip(self._fields, tmp))


class ConstraintP2P(_ConstraintP2P):
    """
    fixme: docu
    fixme: parameters

    :param dict aid: fragment name
    :return _ConstraintP2P: a valid 'Plane' collision shape.
    """
    @typecheck
    def __new__(cls, pivot_a: (tuple, list), pivot_b: (tuple, list)):
        try:
            # Verify the inputs.
            pivot_a = toVec(3, pivot_a)
            pivot_b = toVec(3, pivot_b)
        except (TypeError, AssertionError):
            msg = 'Cannot construct <{}>'.format(cls.__name__)
            logit.warning(msg)
            raise TypeError
        return super().__new__(cls, pivot_a, pivot_b)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))


class Constraint6DofSpring2(_Constraint6DofSpring2):
    """
    fixme: docu
    fixme: parameters

    :param dict aid: fragment name
    :return _Constraint6DofSpring2: a valid 'Plane' collision shape.
    """
    @typecheck
    def __new__(cls,
                frameInA: (tuple, list),
                frameInB: (tuple, list),
                stiffness: (tuple, list),
                damping: (tuple, list),
                equilibrium: (tuple, list),
                linLimitLo: (tuple, list, np.ndarray),
                linLimitHi: (tuple, list, np.ndarray),
                rotLimitLo: (tuple, list, np.ndarray),
                rotLimitHi: (tuple, list, np.ndarray),
                bounce: (tuple, list, np.ndarray),
                enableSpring: (tuple, list)):

        try:
            # Verify the inputs.
            frameInA = toVec(7, frameInA)
            frameInB = toVec(7, frameInB)
            stiffness = toVec(6, stiffness)
            damping = toVec(6, damping)
            equilibrium = toVec(6, equilibrium)
            linLimitLo = toVec(3, linLimitLo)
            linLimitHi = toVec(3, linLimitHi)
            rotLimitLo = toVec(3, rotLimitLo)
            rotLimitHi = toVec(3, rotLimitHi)
            bounce = toVec(3, bounce)
            enableSpring = toVec(6, enableSpring)
        except (TypeError, AssertionError):
            msg = 'Cannot construct <{}>'.format(cls.__name__)
            logit.warning(msg)
            raise TypeError
        return super().__new__(cls, frameInA, frameInB, stiffness,
                               damping, equilibrium,
                               linLimitLo, linLimitHi,
                               rotLimitLo, rotLimitHi,
                               bounce, enableSpring)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))



# -----------------------------------------------------------------------------
# Booster
#
# Boosters exert a force on an object. Boosters have an ID (user can specify
# it), a position relative to the object's centre of mass, a force direction
# relative to the object's overall orientation, and a maximum force. Note that
# the force is a scalar not a vector.
# -----------------------------------------------------------------------------

# Define named tuples to describe a Booster and the commands it can receive.
_Booster = namedtuple('Booster', 'partID pos direction maxval minval force ')
_CmdBooster = namedtuple('CmdBooster', 'partID force_mag')


class Booster(_Booster):
    """
    Return a ``Booster`` instance.

    The unit is located at ``pos`` relative to the parent's centre of mass. The
    Booster points into ``direction``.

    .. note::
       ``direction`` is *not* a Quaternion but merely a unit vector that points
       in the direction of the force.

    :param str partID: Booster ID (arbitrary)
    :param vec3 pos: position vector (3-elements)
    :param vec3 direction: force direction (3-elements)
    :param float minval: minimum force this Booster can generate.
    :param float maxval: maximum force this Booster can generate.
    :param float force: force value this booster currently exerts on object.
    :return Booster: compiled booster description.
    """
    @typecheck
    def __new__(cls, partID: str, pos: (list, np.ndarray),
                direction: (list, np.ndarray), minval: (int, float),
                maxval: (int, float), force: (int, float)):
        try:
            # Verify the inputs.
            assert isAIDStringValid(partID)
            pos = toVec(3, pos)
            direction = toVec(3, direction)

            # Normalise the direction vector. Raise an error if it is invalid.
            assert np.dot(direction, direction) > 1E-5
            direction = direction / np.sqrt(np.dot(direction, direction))
            direction = tuple(direction)
        except (TypeError, AssertionError):
            msg = 'Cannot construct <{}>'.format(cls.__name__)
            logit.warning(msg)
            raise TypeError

        return super().__new__(cls, partID, pos, direction,
                               minval, maxval, force)

    def __eq__(self, ref):
        # Sanity check.
        if not isinstance(ref, type(self)):
            return False

        # Test if all fields are essentially identical. All fields except
        # partID must be numeric arrays (Python lists or NumPy arrays).
        for f in self._fields:
            a, b = getattr(self, f), getattr(ref, f)
            if isinstance(a, (tuple, list, np.ndarray)):
                if not np.allclose(a, b, atol=1E-9):
                    return False
            else:
                if a != b:
                    return False
        return True

    def __ne__(self, ref):
        return not self.__eq__(ref)


class CmdBooster(_CmdBooster):
    """
    Return Booster command wrapped into a ``CmdBooster`` instance.

    This wrapper only ensures the provided data is sane.

    :param str partID: Booster ID (arbitrary)
    :param float force: magnitude of force (a scalar!)
    :return Booster: compiled description of booster command.
    """
    @typecheck
    def __new__(cls, partID: str, force: (int, float, np.float64)):
        # Verify the inputs.
        assert isAIDStringValid(partID)

        return super().__new__(cls, partID, float(force))

    def __eq__(self, ref):
        # Sanity check.
        if not isinstance(ref, type(self)):
            return False

        # Test if all fields are essentially identical. All fields except
        # partID must be numeric arrays (Python lists or NumPy arrays).
        for f in self._fields:
            a, b = getattr(self, f), getattr(ref, f)
            if isinstance(a, (tuple, list, np.ndarray)):
                if not np.allclose(a, b, atol=1E-9):
                    return False
            else:
                if a != b:
                    return False
        return True

    def __ne__(self, ref):
        return not self.__eq__(ref)


# -----------------------------------------------------------------------------
# Factory
#
# Factories can spawn objects. Like Boosters, they have a custom ID, position,
# direction (both relative to the object). Furthermore, they can only spawn a
# particular template. The newly spawned object can exit with the specified
# speed along the factory direction.
# -----------------------------------------------------------------------------

# Define named tuples to describe a Factory and the commands it can receive.
_Factory = namedtuple('Factory', 'partID pos direction templateID exit_speed')
_CmdFactory = namedtuple('CmdFactory', 'partID exit_speed')


class Factory(_Factory):
    @typecheck
    def __new__(cls, partID: str, pos: (list, np.ndarray),
                direction: (list, np.ndarray), templateID: str,
                exit_speed: (list, np.ndarray)):
        """
        Return a ``Factory`` instance.

        The unit is located at ``pos`` relative to the parent's centre of
        mass. The initial velocity of the spawned objects is constrained by the
        ``exit_speed`` variable.

        .. note::
           ``direction`` is *not* a Quaternion but merely a unit vector that
           points in the nozzle direction of the factory (it the direction in
           which new objects will be spawned).

        :param str partID: factory ID (arbitrary).
        :param vec3 pos: position vector (3-elements).
        :param vec3 direction: exit direction of new objects (3-elements).
        :param str templateID: name of template spawned by this factory.
        :param vec2 exit_speed: [min, max] exit speed of spawned object.
        :return Factory: compiled factory description.
        """
        try:
            # Verify the inputs.
            assert isAIDStringValid(partID)
            pos = toVec(3, pos)
            direction = toVec(3, direction)
            exit_speed = toVec(2, exit_speed)

            # Normalise the direction vector. Raise an error if it is invalid.
            assert np.dot(direction, direction) > 1E-5
            direction = direction / np.sqrt(np.dot(direction, direction))
            direction = tuple(direction)
        except (TypeError, AssertionError):
            msg = 'Cannot construct <{}>'.format(cls.__name__)
            logit.warning(msg)
            raise TypeError

        # Return a valid Factory instance based on the arguments.
        return super().__new__(
            cls, partID, pos, direction, templateID, exit_speed)

    def __eq__(self, ref):
        if not isinstance(ref, type(self)):
            return False

        for f in self._fields:
            a, b = getattr(self, f), getattr(ref, f)
            if isinstance(a, (tuple, list, np.ndarray)):
                if not np.allclose(a, b, 1E-9):
                    return False
            else:
                if a != b:
                    return False
        return True


class CmdFactory(_CmdFactory):
    """
    Return Factory command wrapped into a ``CmdFactory`` instance.

    This wrapper only ensures the provided data is sane.

    :param str partID: Factory ID (arbitrary)
    :param float force: magnitude of force (a scalar!)
    :return Factory: compiled description of factory command.
    """
    @typecheck
    def __new__(cls, partID: str, exit_speed: (int, float, np.float64)):
        assert isAIDStringValid(partID)
        exit_speed = float(exit_speed)
        return super().__new__(cls, partID, exit_speed)

    def __eq__(self, ref):
        # Sanity check.
        if not isinstance(ref, type(self)):
            return False

        # Test if all fields are essentially identical.
        for f in self._fields:
            a, b = getattr(self, f), getattr(ref, f)
            if isinstance(a, (tuple, list, np.ndarray)):
                if not np.allclose(a, b, 1E-9):
                    return False
            else:
                if a != b:
                    return False
        return True

    def __ne__(self, ref):
        return not self.__eq__(ref)


# Default argument for RigidBodyState below (purely for visual appeal, not
# because anyone would/should use it).
_CSDefault = CollShapeMeta(aid='',
                           cstype='Empty',
                           position=(0, 0, 0),
                           rotation=(0, 0, 0, 1),
                           csdata=CollShapeEmpty())


@typecheck
def RigidBodyState(scale: (int, float)=1,
                   imass: (int, float)=1,
                   restitution: (int, float)=0.9,
                   orientation: (tuple, list, np.ndarray)=[0, 0, 0, 1],
                   position: (tuple, list, np.ndarray)=[0, 0, 0],
                   velocityLin: (tuple, list, np.ndarray)=[0, 0, 0],
                   velocityRot: (tuple, list, np.ndarray)=[0, 0, 0],
                   cshapes: (tuple, list)=[_CSDefault],
                   axesLockLin: (tuple, list, np.ndarray)=[1, 1, 1],
                   axesLockRot: (tuple, list, np.ndarray)=[1, 1, 1],
                   version: int=0):
    """
    Return a ``_RigidBodyState`` object.

    Without any arguments this function will return a valid ``RigidBodyState``
    specimen with sensible defaults.
    """
    # Convert arguments to NumPy types where necessary.
    position = np.array(position, np.float64).tolist()
    orientation = np.array(orientation, np.float64).tolist()
    velocityLin = np.array(velocityLin, np.float64).tolist()
    velocityRot = np.array(velocityRot, np.float64).tolist()
    axesLockLin = np.array(axesLockLin, np.float64).tolist()
    axesLockRot = np.array(axesLockRot, np.float64).tolist()

    # Sanity checks.
    try:
        assert len(axesLockLin) == len(axesLockRot) == 3
        assert len(orientation) == 4
        assert len(position) == len(velocityLin) == len(velocityRot) == 3
        assert version >= 0

        # Create- and sanity check the collision shapes.
        cshapes = [CollShapeMeta(*_) for _ in cshapes]
    except (AssertionError, TypeError) as err:
        return None

    # Build- and return the actual named tuple.
    return _RigidBodyState(
        scale=scale,
        imass=imass,
        restitution=restitution,
        orientation=orientation,
        position=position,
        velocityLin=velocityLin,
        velocityRot=velocityRot,
        cshapes=cshapes,
        axesLockLin=axesLockLin,
        axesLockRot=axesLockRot,
        version=version)


class RigidBodyStateOverride(_RigidBodyState):
    """
    Create a ``_RigidBodyState`` tuple.

    The only difference between this class and ``RigidBodyState`` is
    that this one permits *None* values for any of its arguments, whereas the
    other one does not.
    """
    @typecheck
    def __new__(cls, *args, **kwargs):
        """
        Same as ``RigidBodyState` except that every unspecified value is *None*
        instead of a numeric default.
        """
        # Convert all positional- and keyword arguments that are not None to a
        # dictionary of keyword arguments. Step 1: convert the positional
        # arguments to a dictionary...
        kwargs_tmp = dict(zip(_RigidBodyState._fields, args))

        # ... Step 2: Remove all keys where the value is None...
        kwargs_tmp = {k: v for (k, v) in kwargs_tmp.items() if v is not None}

        # ... Step 3: add the original keyword arguments that are not None.
        for key, value in kwargs.items():
            if value is not None:
                kwargs_tmp[key] = value
        kwargs = kwargs_tmp
        del args, kwargs_tmp

        # Create a RigidBodyState instance. Return an error if this fails.
        try:
            sv = RigidBodyState(**kwargs)
        except TypeError:
            sv = None
        if sv is None:
            return None

        # Create keyword arguments for all fields and set them to *None*.
        kwargs_all = {f: None for f in _RigidBodyState._fields}

        # Overwrite those keys for which we actually have a value. Note that we
        # will not use the values supplied to this function directly but use
        # the ones from the temporary RigidBodyState object because this
        # one already sanitised the inputs.
        for key in kwargs:
            kwargs_all[key] = getattr(sv, key)

        # Create the ``_RigidBodyState`` named tuple.
        return super().__new__(cls, **kwargs_all)
