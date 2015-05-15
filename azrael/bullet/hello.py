import sys
import azBullet as bt
from azBullet import vec3, BoxShape, StaticPlaneShape, SphereShape, Quaternion
from azBullet import Transform
from azBullet import DefaultMotionState
from azBullet import RigidBody

sim = bt.BulletBase()
sim.setGravity(0, -10, 0)

# Declare the two shapes.
groundShape = StaticPlaneShape(vec3(0, 1, 0), 1)
fallShape = SphereShape(1)

# Specify the ground shape.
groundMotionState = DefaultMotionState(
    Transform(Quaternion(0, 0, 0, 1), vec3(0, -1, 0)))
groundRigidBody = RigidBody(0, groundMotionState, groundShape, vec3(0, 0, 0))
groundRigidBody.setRestitution(1.0)
sim.addRigidBody(groundRigidBody)

# Specify the ball shape.
fallMotionState = DefaultMotionState(
    Transform(Quaternion(0, 0, 0, 1), vec3(0, 20, 0)))
mass = 1
fallInertia = vec3(0, 0, 0)
fallShape.calculateLocalInertia(mass, fallInertia)
fallRigidBody = RigidBody(mass, fallMotionState, fallShape, fallInertia)
fallRigidBody.setRestitution(0.5)
sim.addRigidBody(fallRigidBody)

# Step the simulation and print the position of the sphere.
for ii in range(10):
    sim.stepSimulation(0.5, 30)
    ms = fallRigidBody.getMotionState()
    wt = ms.getWorldTransform()
    print(wt.getOrigin())

sim.removeRigidBody(fallRigidBody)
sim.removeRigidBody(groundRigidBody)

del fallMotionState
del fallRigidBody

del groundMotionState
del groundRigidBody

del fallShape
del groundShape
del sim
