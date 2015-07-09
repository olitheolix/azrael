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

# Return value signature for (almost) all functions in Azrael.
RetVal = namedtuple('RetVal', 'ok msg data')

# Object Template.
_Template = namedtuple('_Template', 'aid rbs fragments boosters factories')

# Fragments.
_FragMeta = namedtuple('_FragMeta',
                       'fragtype scale position orientation fragdata')
_FragRaw = namedtuple('_FragRaw', 'vert uv rgb')
_FragDae = namedtuple('_FragDae', 'dae rgb')
FragNone = namedtuple('FragNone', '')
_FragState = namedtuple('_FragState', 'scale position orientation')

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
_ConstraintMeta = namedtuple('_ConstraintMeta',
                             'aid contype rb_a rb_b condata')
_ConstraintP2P = namedtuple('_ConstraintP2P', 'pivot_a pivot_b')
_Constraint6DofSpring2 = namedtuple(
    '_Constraint6DofSpring2', 'frameInA frameInB stiffness damping '
                              'equilibrium linLimitLo linLimitHi '
                              'rotLimitLo rotLimitHi bounce enableSpring')

# Boosters, Factories, and commands they can receive.
_Booster = namedtuple('Booster', 'pos direction minval maxval force ')
_Factory = namedtuple('Factory', 'pos direction templateID exit_speed')
_CmdBooster = namedtuple('CmdBooster', 'force_mag')
_CmdFactory = namedtuple('CmdFactory', 'exit_speed')


def toVec(num_el, v):
    """
    Verify that ``v`` is a ``num_el`` vector and return it as a tuple.

    The length check is skipped if if ``num_el`` is set to zero.

    :param int num_el: positive integer
    :param v: an iterable (eg tuple, list, NumPy array).
    :return: v as tuple
    :raises: TypeError if the input does not compile to the data type.
    """
    assert num_el >= 0
    try:
        v = np.array(v, np.float64)
        assert v.ndim == 1
        if num_el > 0:
            assert len(v) == num_el
    except (TypeError, AssertionError):
        assert False
    return tuple(v)


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

    Raises **TypeError** if at least one argument has an invalid type.
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
    A raw geometry fragment.

    Raw fragments are consists of a list of vertices, UV coordinates, and RGB
    values. They are useful for debugging since it is easy to specify
    triangles and build simple shapes like cubes.

    :param [float] vert: vertex data
    :param [float] uv: UV map coordinates
    :param [uint8]: RGB texture values.
    :return: compiled ``_FragRaw`` instance.
    :raises: TypeError if the input does not compile to the data type.
    """
    @typecheck
    def __new__(cls, vert, uv, rgb):
        try:
            # Sanity check.
            vert = toVec(0, vert)
            uv = toVec(0, uv)
            rgb = toVec(0, rgb)

            # RGB values must be integers in [0, 255]
            if len(rgb) > 0:
                assert (np.amin(rgb) >= 0) and (np.amax(rgb) < 256)
                rgb = tuple(np.array(rgb, np.uint8).tolist())

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

        # Return constructed data type.
        return super().__new__(cls, vert, uv, rgb)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))


class FragDae(_FragDae):
    """
    Return a valid description for a Collada file and its textures.

    The RGB dictionary denotes the texture images. The keys are file names (eg.
    'foo.png') whereas the associated values are the Base64 encoded images
    themselves.

    :param str dae: Collada file
    :param dict rgb: dictionary of texture files.
    :return: compiled ``_FragDae`` instance.
    :raises: TypeError if the input does not compile to the data type.
    """
    @typecheck
    def __new__(cls, dae: str, rgb: dict):
        try:
            # Verify the RGB dictionary.
            for k, v in rgb.items():
                assert isinstance(k, str)
                assert isinstance(v, str)
        except AssertionError:
            msg = 'Cannot construct <{}>'.format(cls.__name__)
            logit.warning(msg)
            raise TypeError

        # Return constructed data type.
        return super().__new__(cls, dae, rgb)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))


class FragMeta(_FragMeta):
    """
    Return a valid description for any of Azrael's supported data formats.

    Meta Fragments hold meta data about *one* geometry fragment, for instance
    its type and ID.

    The fragment data itself is available under the `fragdata` attribute. It
    must be either *None* or one of the other supported `Frag*` instances.

    A `fragtype` of *None* is unusual but sometimes necessary internally
    because the data about the fragment does not reside in the same database as
    the actual geometry. However, when `fragtype` is *None* then the `fragdata`
    argument is ignored altogether.

    :param str fragtype: fragment type (eg 'raw', or 'dae', or None)
    :param fragdata: one of the fragment types (eg. `FragRaw` or `FragDae`).
    :return: compiled  ``_FragMeta`` instance.
    :raises: TypeError if the input does not compile to the data type.
    """
    @typecheck
    def __new__(cls, fragtype: str, scale: (int, float),
                position: (tuple, list),
                orientation: (tuple, list),
                fragdata):
        try:
            # Sanity check position and orientation.
            position = toVec(3, position)
            orientation = toVec(4, orientation)

            # Verify that `fragtype` is valid and construct the respective data
            # type for the ``fragdata`` attribute.
            if fragdata is None:
                frag = None
            else:
                fragtype = fragtype.upper()
                if fragtype == 'RAW':
                    if isinstance(fragdata, dict):
                        frag = FragRaw(**fragdata)
                    else:
                        frag = FragRaw(*fragdata)
                elif fragtype == 'DAE':
                    if isinstance(fragdata, dict):
                        frag = FragDae(**fragdata)
                    else:
                        frag = FragDae(*fragdata)
                elif fragtype == '_DEL_':
                    frag = FragNone()
                else:
                    assert False
        except (TypeError, AssertionError):
            msg = 'Cannot construct <{}>'.format(cls.__name__)
            logit.warning(msg)
            raise TypeError

        # Return constructed data type.
        return super().__new__(cls, fragtype, scale, position, orientation, frag)

    def _asdict(self):
        if self.fragdata is None:
            tmp = self
        else:
            tmp = self._replace(fragdata=self.fragdata._asdict())
        return OrderedDict(zip(self._fields, tmp))


class FragState(_FragState):
    """
    Return a valid data set to describe the state of a particular fragment.

    Fragment states contain the scale, position, and orientation of a graphical
    object.

    ..note:: Fragment states and collision shapes are independent data sets.
             Changing parameters like position for one has no impact whatsoever
             on the other.

    :return: compiled ``_FragState`` instance.
    :raises: TypeError if the input does not compile to the data type.
    """
    @typecheck
    def __new__(cls,
                scale: (int, float),
                position: (tuple, list),
                orientation: (tuple, list)):
        try:
            # Verify the inputs.
            assert scale >= 0
            position = toVec(3, position)
            orientation = toVec(4, orientation)

        except (TypeError, AssertionError):
            msg = 'Cannot construct <{}>'.format(cls.__name__)
            logit.warning(msg)
            raise TypeError

        # Return constructed data type.
        return super().__new__(cls, scale, position, orientation)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))


class CollShapeMeta(_CollShapeMeta):
    """
    Return description of a collision shape and its meta data.

    :param str aid: Collision shape ID.
    :param vec3 position: position of collision shape in world coordinates.
    :param vec4 rotation: orientation of collision shape in world coordinates.
    :param csdate: instance of a collision shape (eg. ``CollShapeSphere``).
    :return: compiled  `_CollShapeMeta` instance.
    :raises: TypeError if the input does not compile to the data type.
    """
    @typecheck
    def __new__(cls, aid: str,
                cstype: str,
                position: (tuple, list, np.ndarray),
                rotation: (tuple, list, np.ndarray),
                csdata):
        try:
            # Verify the meta data for the collision shape.
            assert isAIDStringValid(aid)
            position = toVec(3, position)
            rotation = toVec(4, rotation)

            # Compile the collision shape data.
            cstype = cstype.upper()
            if cstype == 'SPHERE':
                if isinstance(csdata, dict):
                    csdata = CollShapeSphere(**csdata)
                else:
                    csdata = CollShapeSphere(*csdata)
            elif cstype == 'BOX':
                if isinstance(csdata, dict):
                    csdata = CollShapeBox(**csdata)
                else:
                    csdata = CollShapeBox(*csdata)
            elif cstype == 'EMPTY':
                if isinstance(csdata, dict):
                    csdata = CollShapeEmpty(**csdata)
                else:
                    csdata = CollShapeEmpty(*csdata)
            elif cstype == 'PLANE':
                if isinstance(csdata, dict):
                    csdata = CollShapePlane(**csdata)
                else:
                    csdata = CollShapePlane(*csdata)
            else:
                assert False
        except (TypeError, AssertionError):
            msg = 'Cannot construct <{}>'.format(cls.__name__)
            logit.warning(msg)
            raise TypeError

        # Return constructed data type.
        return super().__new__(cls, aid, cstype, position, rotation, csdata)

    def _asdict(self):
        csdata = self.csdata._asdict()
        tmp = self._replace(csdata=csdata)
        return OrderedDict(zip(self._fields, tmp))


class CollShapeEmpty(_CollShapeEmpty):
    """
    Return the description for an Empty collision shape.

    Empty collision shapes do not collide with anything - sometimes useful.

    :return: compiled `_CollShapeEmpty` instance.
    :raises: TypeError if the input does not compile to the data type.
    """
    @typecheck
    def __new__(cls):
        return super().__new__(cls)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))


class CollShapeBox(_CollShapeBox):
    """
    Return the description for a Box shape.

    The box size is specified in terms of half lengths. For instance, x=2 means
    the box extends from x=-2 to x=+2.

    :param float x: half length in x-direction.
    :param float y: half length in y-direction.
    :param float z: half length in z-direction.
    :return: compiled `_CollShapeBox`.
    :raises: TypeError if the input does not compile to the data type.
    """
    @typecheck
    def __new__(cls, x: (int, float), y: (int, float), z: (int, float)):
        try:
            assert (x >= 0) and (y >= 0) and (z >= 0)
        except (TypeError, AssertionError):
            msg = 'Cannot construct <{}>'.format(cls.__name__)
            logit.warning(msg)
            raise TypeError

        # Return constructed data type.
        return super().__new__(cls, x, y, z)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))


class CollShapeSphere(_CollShapeSphere):
    """
    Return the description for a Sphere shape.

    :param float radius: radius of sphere (must be non-negative).
    :return: compiled `_CollShapeSphere`.
    :raises: TypeError if the input does not compile to the data type.
    """
    @typecheck
    def __new__(cls, radius: (int, float)):
        try:
            assert radius >= 0
        except (TypeError, AssertionError):
            msg = 'Cannot construct <{}>'.format(cls.__name__)
            logit.warning(msg)
            raise TypeError

        # Return constructed data type.
        return super().__new__(cls, radius)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))


class CollShapePlane(_CollShapePlane):
    """
    Return the description for a Plane shape.

    Planes are an infinitely large flat surface. Its orientation is uniquely
    described by the normal vector on that sphere plus an offset along this
    normal.

    :param vec3 normal: plane normal.
    :param float ofs: plane offset in direction of normal.
    :return: compiled  `_CollShapePlane` instance.
    :raises: TypeError if the input does not compile to the data type.
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

        # Return constructed data type.
        return super().__new__(cls, normal, ofs)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))


class ConstraintMeta(_ConstraintMeta):
    """
    Return definition of a constraint plus its meta information.

    Every constraint connects two rigid body objects.

    :param str aid: Constraint ID.
    :param str contype: constraint type (eg. 'P2P').
    :param int rb_a: First rigid body this constraint is connected to.
    :param int rb_b: Second rigid body this constraint is connected to.
    :param condata: specific information about the constraint.
    :return: Compiled `_ConstraintMeta` instance.
    :raises: TypeError if the input does not compile to the data type.
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

        # Return constructed data type.
        return super().__new__(cls, aid, contype, rb_a, rb_b, condata)

    def _asdict(self):
        tmp = self._replace(condata=self.condata._asdict())
        return OrderedDict(zip(self._fields, tmp))


class ConstraintP2P(_ConstraintP2P):
    """
    Return the description of a Point2Point constraint.

    This type of constraint connects two bodies at a fixed (pivot) point
    relative to each others positions.

    :param vec3 pivot_a: Pivot position relative to the first body.
    :param vec3 pivot_b: Pivot position relative to the second body.
    :return: compiled `_ConstraintP2P` instance.
    :raises: TypeError if the input does not compile to the data type.
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

        # Return constructed data type.
        return super().__new__(cls, pivot_a, pivot_b)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))


class Constraint6DofSpring2(_Constraint6DofSpring2):
    """
    Return the description of a Point2Point constraint.

    This type of constraint connects two bodies at a fixed (pivot) point
    relative to each others positions.

    The parameters below suffice to constructe Bullet's
    `Generic6DofSpring2Constraint`. I do not understand all of the parameters
    myself.

    :param vec7 frameInA: Rotation- and position relative to first body.
    :param vec7 frameInB: Rotation- and position relative to second body.
    :param vec6 stiffness: linear- and angular stiffness.
    :param vec6 damping: linear- and angular damping.
    :param vec6 equilibrium: equilibrium position at which the constraint does
                             not produce any forces.
    :param vec3 linLimitLo: lower limit for translation.
    :param vec3 linLimitHi: upper limit for translation.
    :param vec3 rotLimitLo: lower limit for rotation.
    :param vec3 rotLimitHi: upper limit for rotation.
    :param vec3 bounce: bouncing factor.
    :param list[bool] enableSpring: six Booleans to specify whether the
                                    linear/angular spring is active.
    :return: compiled `_Constraint6DofSpring2`.
    :raises: TypeError if the input does not compile to the data type.
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

        # Return constructed data type.
        return super().__new__(cls, frameInA, frameInB, stiffness,
                               damping, equilibrium,
                               linLimitLo, linLimitHi,
                               rotLimitLo, rotLimitHi,
                               bounce, enableSpring)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))


class Booster(_Booster):
    """
    Return a ``Booster`` instance.

    Boosters exert a force on an object. Boosters have an ID (user can
    specify it), a position relative to the object's centre of mass, a
    force direction relative to the object's overall orientation, and a
    maximum force. Note that the force is a scalar not a vector.

    The unit is located at ``pos`` relative to the parent's centre of mass. The
    Booster points into ``direction``.

    .. note::
       ``direction`` is *not* a Quaternion but merely a unit vector that points
       in the direction of the force.

    :param vec3 pos: position vector (3-elements)
    :param vec3 direction: force direction (3-elements)
    :param float minval: minimum force this Booster can generate.
    :param float maxval: maximum force this Booster can generate.
    :param float force: force value this booster currently exerts on object.
    :return Booster: compiled booster description.
    """
    @typecheck
    def __new__(cls, pos: (tuple, list, np.ndarray),
                direction: (tuple, list, np.ndarray), minval: (int, float),
                maxval: (int, float), force: (int, float)):
        try:
            # Verify the inputs.
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

        # Return constructed data type.
        return super().__new__(cls, pos, direction, minval, maxval, force)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))


class CmdBooster(_CmdBooster):
    """
    Return Booster command wrapped into a ``CmdBooster`` instance.

    This wrapper only ensures the provided data is sane.

    :param float force: magnitude of force (a scalar!)
    :return Booster: compiled description of booster command.
    """
    @typecheck
    def __new__(cls, force_mag: (int, float, np.float64)):
        # Return constructed data type.
        return super().__new__(cls, float(force_mag))

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))


class Factory(_Factory):
    """
    Return a ``Factory`` instance.

    Factories can spawn objects. Like Boosters, they have a custom ID,
    position, direction (both relative to the object). Furthermore, they
    can only spawn a particular template. The newly spawned object can
    exit with the specified speed along the factory direction.

    The unit is located at ``pos`` relative to the parent's centre of
    mass. The initial velocity of the spawned objects is constrained by the
    ``exit_speed`` variable.

    .. note::
       ``direction`` is *not* a Quaternion but merely a unit vector that
       points in the nozzle direction of the factory (it the direction in
       which new objects will be spawned).

    :param vec3 pos: position vector (3-elements).
    :param vec3 direction: exit direction of new objects (3-elements).
    :param str templateID: name of template spawned by this factory.
    :param vec2 exit_speed: [min, max] exit speed of spawned object.
    :return Factory: compiled factory description.
    """
    @typecheck
    def __new__(cls, pos: (tuple, list, np.ndarray),
                direction: (tuple, list, np.ndarray), templateID: str,
                exit_speed: (tuple, list, np.ndarray)):
        try:
            # Verify the inputs.
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
            cls, pos, direction, templateID, exit_speed)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))


class CmdFactory(_CmdFactory):
    """
    Return Factory command wrapped into a ``CmdFactory`` instance.

    This wrapper only ensures the provided data is sane.

    :param float force: magnitude of force (a scalar!)
    :return Factory: compiled description of factory command.
    """
    @typecheck
    def __new__(cls, exit_speed: (int, float, np.float64)):
        exit_speed = float(exit_speed)

        # Return constructed data type.
        return super().__new__(cls, exit_speed)

    def _asdict(self):
        return OrderedDict(zip(self._fields, self))


class RigidBodyState(_RigidBodyState):
    # fixme: docu
    @typecheck
    def __new__(cls, scale: (int, float),
                   imass: (int, float),
                   restitution: (int, float),
                   orientation: (tuple, list),
                   position: (tuple, list, np.ndarray),
                   velocityLin: (tuple, list, np.ndarray),
                   velocityRot: (tuple, list, np.ndarray),
                   cshapes: dict,
                   axesLockLin: (tuple, list, np.ndarray),
                   axesLockRot: (tuple, list, np.ndarray),
                   version: int):
        """
        Return a ``_RigidBodyState`` object.
        """
        try:
            # Sanity checks inputs.
            axesLockLin = toVec(3, axesLockLin)
            axesLockRot = toVec(3, axesLockRot)
            orientation = toVec(4, orientation)
            position = toVec(3, position)
            velocityLin = toVec(3, velocityLin)
            velocityRot = toVec(3, velocityRot)
            assert version >= 0

            # fixme: sanity check the name of the collision shape.
            # Compile- and sanity check all collision shapes.
            cshapes = {
                k: CollShapeMeta(**v) if isinstance(v, dict) else CollShapeMeta(*v)
                for (k, v) in cshapes.items()
            }
        except (AssertionError, TypeError) as err:
            return None

        # Build- and return the compiled RigidBodyState tuple.
        return super().__new__(cls,
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

    def _asdict(self):
        tmp = self._replace(cshapes={k: v._asdict() for (k, v) in self.cshapes.items()})
        return OrderedDict(zip(tmp._fields, tmp))


def DefaultRigidBody(scale=1,
                     imass=1,
                     restitution=0.9,
                     orientation=(0, 0, 0, 1),
                     position=(0, 0, 0),
                     velocityLin=(0, 0, 0),
                     velocityRot=(0, 0, 0),
                     cshapes=None,
                     axesLockLin=(1, 1, 1),
                     axesLockRot=(1, 1, 1),
                     version=0):

    # If cshape was explicitly 'None' then we create a default collision shape.
    # Note that cshape={} means the object has no collision shape, whereas
    # cshape=None means we should create a default.
    if cshapes is None:
        cshapes = CollShapeMeta(aid='',
                                cstype='Sphere',
                                position=(0, 0, 0),
                                rotation=(0, 0, 0, 1),
                                csdata=CollShapeSphere(radius=1))
        cshapes = {'': cshapes}
    else:
        cshapes = {
            k: CollShapeMeta(**v) if isinstance(v, dict) else CollShapeMeta(*v)
            for (k, v) in cshapes.items()
        }

    return RigidBodyState(scale, imass, restitution, orientation, position,
                          velocityLin, velocityRot, cshapes, axesLockLin,
                          axesLockRot, version)


class Template(_Template):
    """
    Return a valid object template.

    Object templates encapsulate all the information known about the object.
    Azrael uses this information to spawn the object and make it available to
    the various other components like physics.

    Almost all of the inital template values can be modified at run time.

    :param str aid: template name
    :param list[FragMeta] fragments: geometry fragments.
    :param list[Booster] boosters: booster data
    :param list[Factory] factories: factory data
    :return: compiled ``_Template`` instance.
    :raises: TypeError if the input does not compile to the data type.
    """
    @typecheck
    def __new__(cls, aid: str,
                rbs: (tuple, list, dict),
                fragments: dict,
                boosters: dict,
                factories: dict):
        try:
            # Sanity check the AID of the template, boosters, and factories.
            assert isAIDStringValid(aid)
            for bb in boosters:
                assert isAIDStringValid(bb)
            for ff in factories:
                assert isAIDStringValid(ff)

            # AID must be valid.
            for tmp_aid in fragments:
                assert isAIDStringValid(tmp_aid)

            # Compile- and sanity check all geometry fragments.
            fragments = {k: FragMeta(**v) if isinstance(v, dict) else FragMeta(*v)
                         for (k, v) in fragments.items()}

            # Compile- and sanity check all boosters.
            boosters = {k: Booster(**v)
                        if isinstance(v, dict) else Booster(*v)
                        for (k, v) in boosters.items()}

            # Compile- and sanity check all factories.
            factories = {k: Factory(**v)
                         if isinstance(v, dict) else Factory(*v)
                         for (k, v) in factories.items()}

            # Compile the RBS data.
            if isinstance(rbs, dict):
                rbs = RigidBodyState(**rbs)
            else:
                rbs = RigidBodyState(*rbs)
        except (TypeError, AssertionError) as err:
            raise err
            msg = 'Cannot construct <{}>'.format(cls.__name__)
            logit.warning(msg)
            raise TypeError

        # Return constructed data type.
        return super().__new__(
            cls, aid, rbs, fragments, boosters, factories)

    def _asdict(self):
        fragments = {k: v._asdict() for (k, v) in self.fragments.items()}
        boosters = {k: v._asdict() for (k, v) in self.boosters.items()}
        factories = {k: v._asdict() for (k, v) in self.factories.items()}
        rbs = self.rbs._asdict()
        tmp = _Template(aid=self.aid,
                        rbs=rbs,
                        fragments=fragments,
                        boosters=boosters,
                        factories=factories)
        return OrderedDict(zip(tmp._fields, tmp))
