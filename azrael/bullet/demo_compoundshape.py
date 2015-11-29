"""
Test behaviour of compound shapes in terms of their masses and inertia.
"""
import azBullet
from azBullet import Vec3, Quaternion
from azBullet import StaticPlaneShape, SphereShape, CompoundShape
from azBullet import DefaultMotionState, Transform
from azBullet import RigidBody, RigidBodyConstructionInfo

from IPython import embed as ipshell

# Instantiate the Bullet simulation.
sim = azBullet.BulletBase()
sim.setGravity(Vec3(0, 0, 0))

# Create the spherical collision shape and a compound shape.
csSphere = SphereShape(radius=1)
cs = azBullet.CompoundShape()

# Specify the mass and let Bullet compute the Inertia.
total_mass = 1
print('Inertia sphere: ', csSphere.calculateLocalInertia(total_mass))

# Add collision shapes to the compound. Its constituents are two spheres
# at different positions.
t1 = Transform(Quaternion(0, 0, 0, 1), Vec3(0, -5, 0))
t2 = Transform(Quaternion(0, 0, 0, 1), Vec3(0, 5, 0))
cs.addChildShape(t1, csSphere)
cs.addChildShape(t2, csSphere)

# The local inertia is only a crude approximation based on the AABBs. Do not
# use it. Use calculatePrincipalAxisTransform instead (see below).
print('Local Inertia AABBs: ', cs.calculateLocalInertia(total_mass))

# Assign each child 1/N of the total mass.
N = cs.getNumChildShapes()
masses = [total_mass / N for _ in range(N)]
del total_mass, N

# Compute the inertia vector (ie diagonal entries of inertia Tensor) and the
# principal axis of the Inertia tensor.
inertia, principal = cs.calculatePrincipalAxisTransform(masses)
print('\nCenter of Mass: ', principal.getOrigin().topy())
print('Inertia Values: ', inertia)
print('Inertia Principal Axis: ', principal.getRotation().topy())
del t1, t2, csSphere

# Construct the rigid body for the compound shape based on the just computed
# inertia tensor.
print('\nTotal Mass: {}'.format(sum(masses)))
ci = azBullet.RigidBodyConstructionInfo(
    sum(masses),
    azBullet.DefaultMotionState(principal),
    cs,
    inertia,
)
body = RigidBody(ci)

# Add the body with its compound shape to the simulation.
sim.addRigidBody(body)
del masses, ci

# Apply an initial force and torque (only valid for the first simulation step
# because Bullet will clear all the forces afterwards).
body.clearForces()
body.applyCentralForce(Vec3(*(0, 1, 0)))
#body.applyTorque(Vec3(*(0, 1, 0)))

# Step the simulation and print the position of the Ball.
for ii in range(10):
    wt = body.getMotionState().getWorldTransform()
    pos = wt.getOrigin().topy()
    rot = wt.getRotation().topy()
    print('Pos: {:.2f}  {:.2f}  {:.2f}'.format(*pos))
    print('Rot: {:.2f}  {:.2f}  {:.2f}  {:.2f}'.format(*rot))
    print('---')
    sim.stepSimulation(0.5, 30)

# Remove the rigid body from the simulation.
sim.removeRigidBody(body)
