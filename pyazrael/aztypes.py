# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""
A collection of named tuples and a typecheck decorator.

The decorator automatically verifies function arguments based on their
annotations in the signature.

Usage example::

    from azrael.aztypes import typecheck

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
_Template = namedtuple('_Template', 'aid rbs fragments boosters factories custom')

# Fragments.
_FragMeta = namedtuple('_FragMeta',
                       'fragtype scale position rotation fragdata')
_FragDae = namedtuple('_FragDae', 'files')
FragNone = namedtuple('FragNone', '')

# Work package related.
WPData = namedtuple('WPData', 'aid sv force torque')
WPMeta = namedtuple('WPAdmin', 'wpid dt maxsteps')
Forces = namedtuple('Forces',
                    'forceDirect forceBoost torqueDirect torqueBoost')

# Motion state of an object.
_RigidBodyData = namedtuple('_RigidBodyData',
                            'scale imass restitution rotation '
                            'position velocityLin velocityRot cshapes '
                            'axesLockLin axesLockRot version')

# Collision shapes.
_CollShapeMeta = namedtuple('_CollShapeMeta', 'cstype position rotation csdata')
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
_CmdBooster = namedtuple('CmdBooster', 'force')
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


class FragDae(_FragDae):
    """
    fixme: docu update
    Return a valid description for a Collada file and its textures.

    The RGB dictionary denotes the texture images. The keys are file names (eg.
    'foo.png') whereas the associated values are the Base64 encoded images
    themselves.

    :param dict files: dictionary of files.
    :return: compiled ``_FragDae`` instance.
    :raises: TypeError if the input does not compile to the data type.
    """
    @typecheck
    def __new__(cls, files: dict):
        try:
            # Verify the RGB dictionary.
            for k, v in files.items():
                assert isinstance(k, str)
                assert isinstance(v, str)
        except AssertionError:
            msg = 'Cannot construct <{}>'.format(cls.__name__)
            logit.warning(msg)
            raise TypeError

        # Return constructed data type.
        return super().__new__(cls, files)

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
    :param dict fragdata: fragment files (eg {'model.json': base64 string})
    :return: compiled  ``_FragMeta`` instance.
    :raises: TypeError if the input does not compile to the data type.
    """
    @typecheck
    def __new__(cls, fragtype: str, scale: (int, float),
                position: (tuple, list),
                rotation: (tuple, list),
                fragdata):
        try:
            # Sanity check position and rotation.
            position = toVec(3, position)
            rotation = toVec(4, rotation)

            # Verify that `fragtype` is valid and construct the respective data
            # type for the ``fragdata`` attribute.
            if fragdata is None:
                frag = None
            else:
                # fixme: this if condition should become redundant once the
                # formats have been eliminated.
                fragtype = fragtype.upper()
                if fragtype in ['DAE', 'OBJ', 'RAW']:
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
        return super().__new__(cls, fragtype, scale, position, rotation, frag)

    def _asdict(self):
        if self.fragdata is None:
            tmp = self
        else:
            tmp = self._replace(fragdata=self.fragdata._asdict())
        return OrderedDict(zip(self._fields, tmp))


class CollShapeMeta(_CollShapeMeta):
    """
    Return description of a collision shape and its meta data.

    :param vec3 position: position of collision shape in world coordinates.
    :param vec4 rotation: rotation of collision shape in world coordinates.
    :param csdate: instance of a collision shape (eg. ``CollShapeSphere``).
    :return: compiled  `_CollShapeMeta` instance.
    :raises: TypeError if the input does not compile to the data type.
    """
    @typecheck
    def __new__(cls,
                cstype: str,
                position: (tuple, list, np.ndarray),
                rotation: (tuple, list, np.ndarray),
                csdata):
        try:
            # Verify the meta data for the collision shape.
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
        return super().__new__(cls, cstype, position, rotation, csdata)

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

    Planes are an infinitely large flat surface. Its rotation is uniquely
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
        except (TypeError, AssertionError):
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
    force direction relative to the object's overall rotation, and a
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
    def __new__(cls, force: (int, float, np.float64)):
        # Return constructed data type.
        return super().__new__(cls, float(force))

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


class RigidBodyData(_RigidBodyData):
    """
    Return a valid Rigid Body object.

    A ``RigidBodyData`` instance comprises all the information required for a
    Newtonian rigid body simulation. Each object in Azrael has exactly one
    Rigid Body attached to which denotes the position and orientation of that
    object. The rigid body may have zero, one, or more collision shapes.

    :param float scale: non-negative scale of rigid body (should almost
        certainly be always 1).
    :param float restitution: restitution coefficient (non-negative).
    :param vec4 rotation: orientation Quaternion.
    :param vec3 position: position of body in world coordinates.
    :param vec3 velocityLin: linear velocity of body.
    :param vec3 velocityRot: angular velocity of body.
    :param dict cshapes: Collision shapes (the names is the key).
    :param vec3 axisLockLin: linear damping of body movements.
    :param vec3 axisLockRot: angular damping of body movements.
    :param int version: version number of body (will be updated by Azrael).
    :return: compiled ``RigidBodyData`` instance.
    :raises: TypeError if the input does not compile to the data type.
    """
    @typecheck
    def __new__(cls,
                scale: (int, float),
                imass: (int, float),
                restitution: (int, float),
                rotation: (tuple, list),
                position: (tuple, list, np.ndarray),
                velocityLin: (tuple, list, np.ndarray),
                velocityRot: (tuple, list, np.ndarray),
                cshapes: dict,
                axesLockLin: (tuple, list, np.ndarray),
                axesLockRot: (tuple, list, np.ndarray),
                version: int):
        try:
            # Sanity checks inputs.
            assert scale >= 0
            assert restitution >= 0
            assert version >= 0
            rotation = toVec(4, rotation)
            position = toVec(3, position)
            axesLockLin = toVec(3, axesLockLin)
            axesLockRot = toVec(3, axesLockRot)
            velocityLin = toVec(3, velocityLin)
            velocityRot = toVec(3, velocityRot)

            # Compile- and sanity check all collision shapes.
            cshapes = {
                k: CollShapeMeta(**v) if isinstance(v, dict) else CollShapeMeta(*v)
                for (k, v) in cshapes.items()
            }

            # Verify that the collision shapes have valid names.
            for csname in cshapes:
                assert isinstance(csname, str)
                assert isAIDStringValid(csname)
        except (AssertionError, TypeError):
            raise TypeError

        # Build- and return the compiled RigidBodyData tuple.
        return super().__new__(
            cls,
            scale=scale,
            imass=imass,
            restitution=restitution,
            rotation=rotation,
            position=position,
            velocityLin=velocityLin,
            velocityRot=velocityRot,
            cshapes=cshapes,
            axesLockLin=axesLockLin,
            axesLockRot=axesLockRot,
            version=version)

    def _asdict(self):
        # Only the collision shapes requires special treatment and need to be
        # converted to dictionaries.
        tmp = self._replace(cshapes={k: v._asdict() for (k, v) in self.cshapes.items()})
        return OrderedDict(zip(tmp._fields, tmp))


def DefaultRigidBody(scale=1,
                     imass=1,
                     restitution=0.9,
                     rotation=(0, 0, 0, 1),
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
        cshapes = CollShapeMeta(cstype='Sphere',
                                position=(0, 0, 0),
                                rotation=(0, 0, 0, 1),
                                csdata=CollShapeSphere(radius=1))
        cshapes = {'': cshapes}
    else:
        cshapes = {
            k: CollShapeMeta(**v) if isinstance(v, dict) else CollShapeMeta(*v)
            for (k, v) in cshapes.items()
        }

    return RigidBodyData(scale, imass, restitution, rotation, position,
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
    def __new__(cls,
                aid: str,
                rbs: (tuple, list, dict),
                fragments: dict,
                boosters: dict,
                factories: dict,
                custom: str=''):
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
                rbs = RigidBodyData(**rbs)
            else:
                rbs = RigidBodyData(*rbs)
        except (TypeError, AssertionError) as err:
            raise err
            msg = 'Cannot construct <{}>'.format(cls.__name__)
            logit.warning(msg)
            raise TypeError

        # Return constructed data type.
        custom = ''
        return super().__new__(
            cls, aid, rbs, fragments, boosters, factories, custom)

    def _asdict(self):
        fragments = {k: v._asdict() for (k, v) in self.fragments.items()}
        boosters = {k: v._asdict() for (k, v) in self.boosters.items()}
        factories = {k: v._asdict() for (k, v) in self.factories.items()}
        rbs = self.rbs._asdict()
        tmp = _Template(aid=self.aid,
                        rbs=rbs,
                        fragments=fragments,
                        boosters=boosters,
                        factories=factories,
                        custom=self.custom)
        return OrderedDict(zip(tmp._fields, tmp))
