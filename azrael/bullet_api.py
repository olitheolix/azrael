# Copyright 2014, Oliver Nagy <olitheolix@gmail.com>
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
Provide classes to create-, modify- and query dynamic simulations. The classes
abstract away the particular physics engine (currently Bullet) used underneath.

This module is the *one and only* module that actually imports the Bullet
engine (ie the wrapper called `azBullet`). This will make it easier to swap out
Bullet for another engine at some point, should the need arise.
"""
import logging
import numpy as np

# Attempt to import the locally compiled version of azBullet first. If it does
# not exist (typically the case inside a Docker container) then import the
# system wide one.
try:
    import azrael.bullet.azBullet as azBullet
except ImportError:
    import azBullet

from IPython import embed as ipshell
from azrael.aztypes import typecheck, RetVal, _RigidBodyData, RbStateUpdate
from azrael.aztypes import ConstraintMeta, ConstraintP2P, Constraint6DofSpring2
from azrael.aztypes import CollShapeMeta, CollShapeSphere, CollShapeBox, CollShapePlane

# Convenience.
Vec3 = azBullet.Vec3
Quaternion = azBullet.Quaternion
Transform = azBullet.Transform


class PyRigidBody(azBullet.RigidBody):
    """
    Wrapper around RigidBody class.

    The original azBullet.RigidBody class cannot be extended since it is a
    compiled module. However, by subclassing it we get the convenience of
    a pure Python class (eg adding attributes at runtime). This is transparent
    to the end user.
    """
    def __init__(self, ci):
        super().__init__(ci)


def bullet2azrael(bt_pos: Vec3, bt_rot: Quaternion, com_ofs: list):
    """
    Return the Azrael object position for the compound shape.

    pos_new = bt_pos - bt_rot * com_ofs
    """
    # Use Bullet's Transform class to apply the Quaternion bt_rot.
    rot = Transform(bt_rot, Vec3(0, 0, 0))
    bt_pos = bt_pos - rot * Vec3(*com_ofs)
    return bt_pos.topy(), bt_rot.topy()


def azrael2bullet(az_pos: list, az_rot: list, com_ofs: list):
    """
    Return the compound shape transform for the Azrael object.

    pos_new = az_pos + az_rot * com_ofs
    """
    # Use Bullet's Transform class to apply the Quaternion bt_rot.
    az_rot = Quaternion(*az_rot)
    rot = Transform(az_rot, Vec3(0, 0, 0))
    az_pos = Vec3(*az_pos) + rot * Vec3(*com_ofs)
    return az_pos, az_rot


class PyBulletDynamicsWorld():
    """
    High level wrapper around the low level Bullet bindings.
    """
    def __init__(self, engineID: int):
        # Create a Class-specific logger.
        name = '.'.join([__name__, self.__class__.__name__])
        self.logit = logging.getLogger(name)

        # To distinguish engines.
        self.engineID = engineID

        # Create a standard Bullet Dynamics World.
        self.dynamicsWorld = azBullet.BulletBase()

        # Disable gravity.
        self.dynamicsWorld.setGravity(Vec3(0, 0, 0))

        # Dictionary of all bodies.
        self.rigidBodies = {}

    def setGravity(self, gravity: (tuple, list)):
        """
        Set the ``gravity`` in the simulation.
        """
        try:
            gravity = np.array(gravity, np.float64)
            assert gravity.ndim == 1
            assert len(gravity) == 3
        except (TypeError, ValueError, AssertionError):
            return RetVal(False, 'Invalid type', None)
        self.dynamicsWorld.setGravity(Vec3(*gravity))
        return RetVal(True, None, None)

    def removeRigidBody(self, bodyIDs: (list, tuple)):
        """
        Remove ``bodyIDs`` from Bullet and return the number of removed bodies.

        Non-existing bodies are not counted (and ignored).

        :param list bodyIDs: list of bodyIDs to remove.
        :return: number of actually removed bodies.
        :rtype: int
        """
        cnt = 0
        # Remove every body, skipping non-existing ones.
        for bodyID in bodyIDs:
            # Skip non-existing bodies.
            if bodyID not in self.rigidBodies:
                continue

            # Delete the body from all caches.
            del self.rigidBodies[bodyID]
            cnt += 1

        # Return the total number of removed bodies.
        return RetVal(True, None, cnt)

    def compute(self, bodyIDs: (tuple, list), dt: float, max_substeps: int):
        """
        Step the simulation for all ``bodyIDs`` by ``dt``.

        This method aborts immediately if one or more bodyIDs do not exist.

        The ``max_substeps`` parameter tells Bullet the maximum allowed
        granularity. Typiclal values for ``dt`` and ``max_substeps`` are
        (1, 60).

        :param list bodyIDs: list of bodyIDs for which to update the physics.
        :param float dt: time step in seconds
        :param int max_substeps: maximum number of sub-steps.
        :return: Success
        """
        # All specified bodies must exist. Abort otherwise.
        try:
            rigidBodies = [self.rigidBodies[_] for _ in bodyIDs]
        except KeyError as err:
            self.logit.warning('Body IDs {} do not exist'.format(err.args))
            return RetVal(False, None, None)

        # Add the body to the world and make sure it is activated, as
        # Bullet may otherwise decide to simply set its velocity to zero
        # and ignore the body.
        for body in rigidBodies:
            self.dynamicsWorld.addRigidBody(body)
            body.forceActivationState(4)

        # The max_substeps parameter instructs Bullet to subdivide the
        # specified timestep (dt) into at most max_substeps. For example, if
        # dt= 0.1 and max_substeps=10, then, internally, Bullet will simulate
        # no finer than dt / max_substeps = 0.01s.
        self.dynamicsWorld.stepSimulation(dt, max_substeps)

        # Remove all bodies from the simulation again.
        for body in rigidBodies:
            self.dynamicsWorld.removeRigidBody(body)
        return RetVal(True, None, None)

    def applyForceAndTorque(self, bodyID, force, torque):
        """
        Apply a ``force`` and ``torque`` to the center of mass of ``bodyID``.

        :param int bodyID: the ID of the body to update
        :param 3-array force: force applied directly to center of mass
        :param 3-array torque: torque around center of mass.
        :return: Success
        """
        # Sanity check.
        if bodyID not in self.rigidBodies:
            msg = 'Cannot set force of unknown body <{}>'.format(bodyID)
            self.logit.warning(msg)
            return RetVal(False, msg, None)

        # Convenience.
        body = self.rigidBodies[bodyID]

        # Convert the force and torque to Vec3.
        b_force = Vec3(*force)
        b_torque = Vec3(*torque)

        # Clear pending forces (should be cleared automatically by Bullet when
        # it steps the simulation) and apply the new ones.
        body.clearForces()
        body.applyCentralForce(b_force)
        body.applyTorque(b_torque)
        return RetVal(True, None, None)

    def applyForce(self, bodyID: str, force, rel_pos):
        """
        Apply a ``force`` at ``rel_pos`` to ``bodyID``.

        :param str bodyID: the ID of the body to update
        :param 3-array force: force applied directly to center of mass
        :param 3-array rel_pos: position of force relative to center of mass
        :return: Success
        """
        # Sanity check.
        if bodyID not in self.rigidBodies:
            msg = 'Cannot set force of unknown body <{}>'.format(bodyID)
            return RetVal(False, msg, None)

        # Convenience.
        body = self.rigidBodies[bodyID]

        # Convert the force and torque to Vec3.
        b_force = Vec3(*force)
        b_relpos = Vec3(*rel_pos)

        # Clear pending forces (should be cleared automatically by Bullet when
        # it steps the simulation) and apply the new ones.
        body.clearForces()
        body.applyForce(b_force, b_relpos)
        return RetVal(True, None, None)

    def setConstraints(self, constraints: (tuple, list)):
        """
        Apply the ``constraints`` to the specified bodies in the world.

        If one or more of the rigid bodies specified in any of the constraints
        do not exist then this method will abort. Similarly, it will also abort
        if one or more constraints could not be constructed for whatever
        reason (eg. unknown constraint name).

        In any case, this function will either apply all constraints or none.
        It is not possible that this function applies only some constraints.

        :param list constraints: list of `ConstraintMeta` instances.
        :return: Success
        """
        def _buildConstraint(c):
            """
            Compile the constraint `c` into the proper C-level Bullet body.
            """
            # Get handles to the two bodies. This will raise a KeyError unless
            # both bodies exist.
            rb_a = self.rigidBodies[c.rb_a]
            rb_b = self.rigidBodies[c.rb_b]

            # Construct the specified constraint type. Raise an error if the
            # constraint could not be constructed (eg the constraint name is
            # unknown).
            if c.contype.upper() == 'P2P':
                tmp = ConstraintP2P(*c.condata)
                out = azBullet.Point2PointConstraint(
                    rb_a, rb_b,
                    Vec3(*tmp.pivot_a),
                    Vec3(*tmp.pivot_b)
                )
            elif c.contype.upper() == '6DOFSPRING2':
                t = Constraint6DofSpring2(*c.condata)
                fa, fb = t.frameInA, t.frameInB
                frameInA = Transform(Quaternion(*fa[3:]), Vec3(*fa[:3]))
                frameInB = Transform(Quaternion(*fb[3:]), Vec3(*fb[:3]))
                out = azBullet.Generic6DofSpring2Constraint(
                    rb_a, rb_b, frameInA, frameInB
                )
                out.setLinearLowerLimit(Vec3(*t.linLimitLo))
                out.setLinearUpperLimit(Vec3(*t.linLimitHi))
                out.setAngularLowerLimit(Vec3(*t.rotLimitLo))
                out.setAngularUpperLimit(Vec3(*t.rotLimitHi))
                for ii in range(6):
                    if not t.enableSpring[ii]:
                        out.enableSpring(ii, False)
                        continue
                    out.enableSpring(ii, True)
                    out.setStiffness(ii, t.stiffness[ii])
                    out.setDamping(ii, t.damping[ii])
                    out.setEquilibriumPoint(ii, t.equilibrium[ii])

                for ii in range(3):
                    out.setBounce(ii, t.bounce[ii])
            else:
                assert False

            # Return the Bullet constraint body.
            return out

        # Compile a list of all Bullet constraints.
        try:
            constraints = [ConstraintMeta(*_) for _ in constraints]
            out = [_buildConstraint(_) for _ in constraints]
        except (TypeError, AttributeError, KeyError, AssertionError):
            return RetVal(False, 'Could not compile all Constraints.', None)

        # Apply the constraints.
        fun = self.dynamicsWorld.addConstraint
        for c in out:
            fun(c)

        # All went well.
        return RetVal(True, None, None)

    def clearAllConstraints(self):
        """
        Remove all constraints from the simulation.

        :return: success
        """
        # Convenience.
        world = self.dynamicsWorld

        # Return immediately if the world has no constraints to remove.
        if world.getNumConstraints() == 0:
            return RetVal(True, None, None)

        # Iterate over all constraints and remove them.
        for c in world.iterateConstraints():
            world.removeConstraint(c)

        # Verify that the number of constraints is now zero.
        if world.getNumConstraints() != 0:
            return RetVal(False, 'Bug: #constraints must now be zero', None)
        else:
            return RetVal(True, None, None)

    @typecheck
    def _compileCollisionShape(self, rbState: _RigidBodyData):
        """
        Return the correct Bullet collision shape based on ``rbState``.

        Bullet does *not* use inertia tensors. It also does not have (much of)
        a concept of centre of mass. Instead it *assumes* that the principal
        axis of inertia of the (unrotated) collision shape is *literally* the
        x/y/z axis of the world coordinate system. It *assumes* further that
        the centre of mass is at the center of that collision shape.

        This is fine for axis symmetric objects (eg spheres, boxes, capsules),
        but  not much else. We can get around this restriction with a compound
        shape. The basic idea is that with a compound shape bullet does not
        care about the child shapes, only the compound shape. We may thus apply
        a particular transform (translate/rotate) to all child shapes and the
        inverse transform to the compound shape. If we do this correctly we can
        make the position of the compound shape coincide with its centre of
        mass, and have its principal axis aligned with x/y/z in world
        coordinates. This is explained next.

        Before we start recall that the centre of mass and axis of inertia for
        the overall rigid body were specified by the user (available in the
        `rbState` argument). Azrael *never* computes or modifies inertia
        tensors or centre of masses - the user has to do that explicitly.

        Now, to get around the aforementioned problem: first we put the
        collision shape(s) into a compound shape. However, we do not put them
        at their absolute positions but at their respective position/rotation
        relative to the centre of mass and principal axis orientation.

        The compound shape's centre of mass thus coincides with the position of
        the compound shape. The compound's principal axis of inertia also
        coincides with the x/y/z axis of the world coordinates. Together this
        satisfies Bullet's assumption stated in the second paragraph of this
        doc string.

        The position/rotation of the child shapes in world coordinates is still
        *wrong*, however, because their position/rotation was relative to
        centre of mass and principal axis. To correct it we move and rotate the
        compound shape in the exact opposite way.

        The net effect is that the child shapes are now in the correct location
        (as we want it) *and* the centre of mass coincides with the position of
        the compound shape (as Bullet wants it) *and* the principal axis of the
        compound shape aligns with the x/y/z axis of the world coordinate
        system (as Bullet wants it as well).

        Remarks:
          * The mass and inertia of the child shapes is irrelevant; Bullet
            only looks at the mass/inertia of the compound.
          * Bullet does not compute the mass/inertia of the compound based on
            the children; it offers convenience methods for doing so, but the
            user must explicitly use them.
          * The one and only purpose of the child shapes inside a compound is
            to define where (and how) the rigid body can be "collided with".

        :param _RigidBodyData rbState: meta data to describe the body.
        :return: compound shape with all the individual shapes.
        :rtype: ``CompoundShape``
        """
        # Create the compound shape that will hold all other shapes.
        compound = azBullet.CompoundShape()

        # Compute the inverse paComT.
        # fixme: quaternion should normalise automatically
        paxis = Quaternion(*rbState.paxis)
        paxis.normalize()

        # Determine the transform with respect to the principal axis
        # orientation and the centre of mass.
        i_paComT = Transform(paxis, Vec3(*rbState.com)).inverse()

        # Create the collision shapes one by one.
        scale = rbState.scale
        for cs in rbState.cshapes.values():
            # Convert the input data (usually a list of values) to a
            # proper CollShapeMeta tuple (sanity checks included).
            cs = CollShapeMeta(*cs)

            # Instantiate the specified collision shape.
            cstype = cs.cstype.upper()
            if cstype == 'SPHERE':
                sphere = CollShapeSphere(*cs.csdata)
                child = azBullet.SphereShape(scale * sphere.radius)
            elif cstype == 'BOX':
                box = CollShapeBox(*cs.csdata)
                hl = Vec3(scale * box.x, scale * box.y, scale * box.z)
                child = azBullet.BoxShape(hl)
            elif cstype == 'EMPTY':
                child = azBullet.EmptyShape()
            elif cstype == 'PLANE':
                # Planes are always static.
                rbState_mass = 0
                plane = CollShapePlane(*cs.csdata)
                normal = Vec3(*plane.normal)
                child = azBullet.StaticPlaneShape(normal, plane.ofs)
            else:
                child = azBullet.EmptyShape()
                msg = 'Unrecognised collision shape <{}>'.format(cstype)
                self.logit.warning(msg)

            # Specify the position/rotation of the child shape. Then adjust
            # them to be relative to the principal axis orientation and centre
            # of mass location (setRigidBodyData will compensate for this with
            # the inverse transform on the compound shape).
            t = Transform(Quaternion(*cs.rotation), Vec3(*cs.position))
            t = i_paComT * t

            # Add the child with the correct transform.
            compound.addChildShape(t, child)

        return compound

    def getRigidBodyData(self, bodyID: str):
        """
        Return latest body state (pos, rot, vLin, vRot) of ``bodyID``.

        Return with an error if ``bodyID`` does not exist.

        :param str bodyID: the ID of body for which to return the state.
        :return: ``RbStateUpdate`` instances.
        """
        # Abort immediately if the ID is unknown.
        if bodyID not in self.rigidBodies:
            msg = 'Cannot find body with ID <{}>'.format(bodyID)
            return RetVal(False, msg, None)

        # Convenience.
        body = self.rigidBodies[bodyID]
        rbState = body.azrael['rbState']

        # Get the transform (ie. position and rotation) of the compound shape.
        t = body.getCenterOfMassTransform()
        rot, pos = t.getRotation(), t.getOrigin()

        # Undo the rotation that is purely due to the alignment with the ineria
        # axis so that Bullet can apply the moments of inertia directly.
        # fixme: Quaternions should automatically normalise
        paxis = Quaternion(*rbState.paxis)
        paxis.normalize()
        rot = paxis.inverse() * rot
        del t, paxis

        # The object position does not match the position of the rigid body
        # unless the center of mass is (0, 0, 0). Here we correct it.
        pos, rot = bullet2azrael(pos, rot, body.azrael['rbState'].com)

        # Determine linear and angular velocity.
        vLin = body.getLinearVelocity().topy()
        vRot = body.getAngularVelocity().topy()

        # Put the result into a named tuple and return it.
        out = RbStateUpdate(pos, rot, vLin, vRot)
        return RetVal(True, None, out)

    def needNewCollisionShape(self, objID, rbStateNew):
        """
        Return True if rbState warrants a new compound shape for objID.

        Specifically, create a new compound shape only if:
          * type of at least one collision shape changed,
          * size of at least one collision shape changed,
          * centre of mass position changed,
          * principal axs of inertia changed.

        :param str objID: ID of reference object.
        :param _RigidBodyData rbStateNew: the new body parameters
        :return: True if the new parameters require a modified compound shape.
        """
        try:
            ref = self.rigidBodies[objID].azrael['rbState']
        except KeyError:
            return True

        try:
            assert np.array_equal(ref.cshapes, rbStateNew.cshapes)
            assert ref.scale == rbStateNew.scale
            assert np.array_equal(ref.com, rbStateNew.com)
            assert np.array_equal(ref.paxis, rbStateNew.paxis)
        except AssertionError:
            return True
        return False

    @typecheck
    def setRigidBodyData(self, bodyID: str, rbState: _RigidBodyData):
        """
        Update State Variables of ``bodyID`` to ``rbState``.

        Create a new body with ``bodyID`` if it does not yet exist.

        :param str bodyID: the IDs of all bodies to retrieve.
        :param ``_RigidBodyData`` rbState: body description.
        :return: Success
        """
        paxis = Quaternion(*rbState.paxis)
        paxis.normalize()
        paComT = Transform(paxis, Vec3(*rbState.com))
        del paxis

        # Create the rigid body if it does not yet exist.
        if bodyID not in self.rigidBodies:
            # Get the collision shape (always a compund shape)
            compound = self._compileCollisionShape(rbState)

            # Create a rigid body for the collision shape. Use default values
            # for mass, inertia, position and orientation. We will overwrite
            # them later in this method.
            body = PyRigidBody(
                azBullet.RigidBodyConstructionInfo(
                    mass=1,
                    ms=azBullet.DefaultMotionState(),
                    cs=compound,
                    inert=Vec3(1, 1, 1)
                )
            )

            # Attach Azrael's info and add the body to our cache.
            body.azrael = {'rbState': rbState}
            self.rigidBodies[bodyID] = body

        # Convenience.
        body = self.rigidBodies[bodyID]

        # Build a new collision shape, if necessary, and replace the old one
        # with it.
        if self.needNewCollisionShape(bodyID, rbState):
            body.setCollisionShape(self._compileCollisionShape(rbState))

        # Convert rotation and position to Bullet types.
        pos, rot = Vec3(*rbState.position), Quaternion(*rbState.rotation)

        # Convert mass and inertia to Bullet types.
        if (rbState.imass < 1E-4) or (sum(rbState.inertia) < 1E-4):
            # Static body: mass and inertia are zero anyway.
            mass, inertia = 0, Vec3(0, 0, 0)
        else:
            # Dynamic body: convert mass/inertia to Bullet types.
            mass, inertia = 1 / rbState.imass, Vec3(*rbState.inertia)

        # pacomt
        # The shapes inside the compound have all been transformed with the
        # inverse COT. Here we undo this transformation by applying the COT
        # again. The net effect in terms of collision shape positions is zero.
        # However, by undoing the COT on every shape *inside* the compound it
        # has overall become aligned with the principal axis of all those
        # shapes. This, in turn, is what Bullet implicitly assumes when it
        # computes angular movement. This is also the reason why the inertia
        # Tensor has only 3 elements instead of being a 3x3 matrix. Yes, I know
        # this is confusing.
        t = Transform(rot, pos) * paComT

        # Assign body properties.
        body.setAngularFactor(Vec3(*rbState.axesLockRot))
        body.setAngularVelocity(Vec3(*rbState.velocityRot))
        body.setCenterOfMassTransform(t)
        body.setDamping(0.02, 0.02)
        body.setFriction(0.1)
        body.setLinearFactor(Vec3(*rbState.axesLockLin))
        body.setLinearVelocity(Vec3(*rbState.velocityLin))
        body.setMassProps(mass, inertia)
        body.setRestitution(rbState.restitution)
        body.setSleepingThresholds(0.1, 0.1)
        body.updateInertiaTensor()

        # Overwrite the rbState structure with the latest version.
        body.azrael = {'rbState': rbState}
        return RetVal(True, None, None)
