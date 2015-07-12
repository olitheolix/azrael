"""
Experiments with Bullet's Generic6DofSpring2 constraint.
"""
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import animation
from IPython import embed as ipshell

import azBullet
from azBullet import Vec3, Quaternion, Transform
from azBullet import SphereShape, DefaultMotionState
from azBullet import RigidBody, RigidBodyConstructionInfo
from azBullet import Generic6DofSpring2Constraint


def animateMotion(out_a, out_b):
    """
    Visualise the trajectories described by 'out_a' and 'out_b'.
    """
    # Create the figure.
    fig = plt.figure()
    ax = plt.axes(xlim=(-15, 15), ylim=(-0.02, 0.02))
    ax.grid()

    # Get the artists we want to anmiate.
    scat_a = ax.scatter(out_a[0, 0], out_a[0, 1], color='blue', animated=True)
    scat_b = ax.scatter(out_b[0, 0], out_b[0, 1], color='red', animated=True)

    # Initialisation function simply returns the artists.
    def animInit():
        return scat_a, scat_b

    # Update the artists to draw the points at the new location.
    def animate(ii):
        scat_a.set_offsets((out_a[ii, 0], out_a[ii, 1]))
        scat_b.set_offsets((out_b[ii, 0], out_b[ii, 1]))
        return scat_a, scat_b

    # Convenience.
    numFrames = out_a.shape[0]

    # Start the animation.
    animation.FuncAnimation(
        fig, animate, init_func=animInit,
        frames=numFrames, interval=50, blit=True)
    plt.show()


def getRB(pos=Vec3(0, 0, 0), cshape=SphereShape(1)):
    """
    Return a Rigid Body plus auxiliary information (do *not* delete; see
    note below).

    .. note:: Do not delete the tuple until the end of the test
    because it may lead to memory access violations. The reason is that a
    rigid body requires several indepenent structures that need to remain
    in memory.
    """
    t = Transform(Quaternion(0, 0, 0, 1), pos)
    ms = DefaultMotionState(t)
    mass = 1

    # Build construction info and instantiate the rigid body.
    ci = RigidBodyConstructionInfo(mass, ms, cshape)
    return RigidBody(ci)


def main():
    # Create two rigid bodies side by side (they *do* touch, but just).
    pos_a = Vec3(-10, 0, 0)
    pos_b = Vec3(10, 0, 0)
    r = 0.001
    rb_a = getRB(pos=pos_a, cshape=SphereShape(r))
    rb_b = getRB(pos=pos_b, cshape=SphereShape(r))
    del r

    # Create the constraint between the two bodies. The constraint applies
    # at (0, 0, 0) in world coordinates.
    frameInA = Transform(Quaternion(0, 1, 0, 0), Vec3(5, 0, 0))
    frameInB = Transform(Quaternion(0, -1, 0, 0), Vec3(-5, 0, 0))
    frameInA.setIdentity()
    frameInB.setIdentity()
    clsDof6 = Generic6DofSpring2Constraint
    dof = clsDof6(rb_a, rb_b, frameInA, frameInB)

    # We are now emulating a slider constraint with this 6DOF constraint.
    # For this purpose we need to specify the linear/angular limits.
    sliderLimitLo = -100
    sliderLimitHi = 100

    # Apply the linear/angular limits.
    dof.setLinearLowerLimit(Vec3(sliderLimitLo, sliderLimitLo, sliderLimitLo))
    dof.setLinearLowerLimit(Vec3(sliderLimitHi, sliderLimitHi, sliderLimitHi))
    tmp = 0 * np.pi / 12
    dof.setAngularLowerLimit(Vec3(-tmp, -tmp, -tmp))
    dof.setAngularUpperLimit(Vec3(tmp, tmp, tmp))

    # Activate the spring for all three translational axis and disable it
    # for the three angular axis.
    for ii in range(3):
        dof.enableSpring(ii, True)
        dof.enableSpring(3 + ii, False)
        dof.setStiffness(ii, 0.1)
        dof.setDamping(ii, 1)
        dof.setEquilibriumPoint(ii, 0)

    # Add both rigid bodies and the constraint to the Bullet simulation.
    bb = azBullet.BulletBase()
    bb.setGravity(Vec3(0, 0, 0))
    bb.addRigidBody(rb_a)
    bb.addRigidBody(rb_b)
    rb_a.forceActivationState(4)
    rb_b.forceActivationState(4)
    bb.addConstraint(dof)

    # Pull the right object to the right. Initially this must not affect
    # the object on the left until the slider is fully extended, at which
    # point the left object must begin to move as well.
#    rb_a.applyCentralForce(Vec3(0, -1, 0))
#    rb_b.applyCentralForce(Vec3(0, 1, 0))

    numIter = 1000
    out_a = np.zeros((numIter, 3))
    out_b = np.zeros_like(out_a)
    for ii in range(numIter):
        if ii == 1:
            rb_a.applyCentralForce(Vec3(0, 0, 0))
            rb_b.applyCentralForce(Vec3(0, 0, 0))

        # Step simulation.
        bb.stepSimulation(1 / 60, 60)

        # Query the position of the objects.
        p_a = rb_a.getCenterOfMassTransform().getOrigin().topy()
        p_b = rb_b.getCenterOfMassTransform().getOrigin().topy()

        out_a[ii, :] = p_a
        out_b[ii, :] = p_b
    animateMotion(out_a, out_b)


if __name__ == '__main__':
    main()
