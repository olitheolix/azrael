"""
Python version of Bullet's own 'Hello World' demo using 'azBullet' wrapper.
"""
import azBullet
from azBullet import Vec3, Quaternion
from azBullet import StaticPlaneShape, SphereShape
from azBullet import DefaultMotionState, Transform
from azBullet import RigidBody, RigidBodyConstructionInfo

sim = azBullet.BulletBase()
sim.setGravity(Vec3(0, -10, 0))

# Create a collision shape for the Ball and for the Ground.
ballShape = SphereShape(1)
groundShape = StaticPlaneShape(Vec3(0, 1, 0), 1)

# Create a Rigid Body for the Ground based on the collision shape.
mass = 0
groundRigidBodyState = DefaultMotionState(
    Transform(Quaternion(0, 0, 0, 1), Vec3(0, -1, 0)))
ci = RigidBodyConstructionInfo(mass, groundRigidBodyState, groundShape)
groundRigidBody = RigidBody(ci)
groundRigidBody.setRestitution(1.0)
sim.addRigidBody(groundRigidBody)
del mass, ci

# Create a Rigid body for the Ball based on its collision shape. Let Bullet do
# the heavy lifting and compute the mass and inertia for us.
fallRigidBodyState = DefaultMotionState(
    Transform(Quaternion(0, 0, 0, 1), Vec3(0, 20, 0)))
mass = 1
fallInertia = ballShape.calculateLocalInertia(mass)
ci = RigidBodyConstructionInfo(
    mass, fallRigidBodyState, ballShape, fallInertia)
fallRigidBody = RigidBody(ci)
fallRigidBody.setRestitution(0.5)
sim.addRigidBody(fallRigidBody)
del mass, fallInertia, ci

# Step the simulation and print the position of the ball.
for ii in range(10):
    sim.stepSimulation(0.5, 30)
    ms = fallRigidBody.getMotionState()
    wt = ms.getWorldTransform()
    print(wt.getOrigin())

# Remove the rigid bodies from the simulation.
sim.removeRigidBody(fallRigidBody)
sim.removeRigidBody(groundRigidBody)
