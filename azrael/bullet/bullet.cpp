/*
 Copyright 2014, Oliver Nagy <olitheolix@gmail.com>

 This file is part of Azrael (https://github.com/olitheolix/azrael)

 Azrael is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as
 published by the Free Software Foundation, either version 3 of the
 License, or (at your option) any later version.
 
 Azrael is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 GNU Affero General Public License for more details.
 
 You should have received a copy of the GNU Affero General Public License
 along with Azrael. If not, see <http://www.gnu.org/licenses/>.
*/

#include <iostream>
#include <vector>

#include "types.hpp"
#include "bullet.hpp"

using std::cout;
using std::endl;

void printvec(const btVector3 &vec) {
  const uint numel = 2;
  cout << "<";
  for(uint ii=0; ii<numel; ++ii) {
    cout << vec[ii] << ", ";
  }
  cout << vec[numel] << ">" << endl;
}

struct myAdminStructure {
  long object_id;
  double radius;
  double scale;
};

// The pair cache for this Bullet instance. This has to be a global
// variable because the prototype of btOverlapFilterCallback declares
// the object as const which implies we cannot change any of its class
// variables.
std::vector<long> myPairCache {};


struct BroadphaseCallback : public btOverlapFilterCallback
{
  virtual bool needBroadphaseCollision (btBroadphaseProxy* proxy0,
                                        btBroadphaseProxy* proxy1)
                                        const {
    myAdminStructure *tmp0 = reinterpret_cast <myAdminStructure*>
      ((reinterpret_cast
        <btRigidBody*>(proxy0->m_clientObject))->getUserPointer());
    myAdminStructure *tmp1 = reinterpret_cast <myAdminStructure*>
      ((reinterpret_cast <btRigidBody*>
        (proxy1->m_clientObject))->getUserPointer());
  
    // Put the object pair into the cache.
    myPairCache.push_back(tmp0->object_id);
    myPairCache.push_back(tmp1->object_id);
  
    // Returning 'false' means Bullet will ignore it for collisions.
    return false;
  }
};


// ----------------------------------------------------------------------
// BulletPhys Class
// ----------------------------------------------------------------------

BulletPhys::BulletPhys(const int &id, const int &coll_filter) {
  // Assign an ID to the engine.
  assert (id >= 0);
  phys_id = id;

  // ----------------------------------------------------------------------
  // Initialise dynamic Bullet simulation.
  // ----------------------------------------------------------------------

  broadphase = new btDbvtBroadphase();
  collisionConfig = new btDefaultCollisionConfiguration();
  dispatcher = new btCollisionDispatcher(collisionConfig);
  solver = new btSequentialImpulseConstraintSolver;
  dynamicsWorld = new btDiscreteDynamicsWorld(dispatcher, broadphase,
                                              solver, collisionConfig);
  dynamicsWorld->setGravity(btVector3(0, 0, 0));

  // Not sure what this does but it was recommended at
  // http://bulletphysics.org/Bullet/phpBB3/viewtopic.php?t=9441
  dynamicsWorld->getSolverInfo().m_solverMode |= SOLVER_USE_2_FRICTION_DIRECTIONS;

  if (coll_filter != 0) {
    // Callback functions for broad- and narrowphase solver.
    cb_broadphase = new BroadphaseCallback();
    dynamicsWorld->getPairCache()->setOverlapFilterCallback(cb_broadphase);
  }
}


BulletPhys::~BulletPhys() {
  for (auto &v: object_cache) {
    if (object_cache.at(v.first) == nullptr) continue;
    dynamicsWorld->removeRigidBody(object_cache.at(v.first).get());
  }

  delete dynamicsWorld;
  delete solver;
  delete dispatcher;
  delete collisionConfig;
  delete broadphase;
}

/*
  Update an existing object or add a new one to the list.
 */
void BulletPhys::compileObject(const long &id,
                               const double &radius,
                               const double &scale,
                               const double &inv_mass,
                               const double &restitution,
                               const btQuaternion &rot,
                               const btVector3 &pos,
                               const btVector3 &velocityLin,
                               const btVector3 &velocityRot,
                               const int &cShapeLen,
                               const double *cShape) {

  // Assign the inverse mass.
  btScalar new_inv_mass = btScalar(inv_mass);

  if (object_cache.find(id) != object_cache.end()) {
    // Object already downloaded --> just update.

    object_cache.at(id)->setCenterOfMassTransform(btTransform(rot, pos));
    object_cache.at(id)->setLinearVelocity(velocityLin);
    object_cache.at(id)->setAngularVelocity(velocityRot);
    return;
  }

  // Ensure the key is defined. The nullptr object will be replaced
  // if a rigid body can be successfully constructed.
  object_cache[id] = nullptr;

  vecdouble tmp_cs;
  for (int ii=0; ii < cShapeLen; ii++) tmp_cs.push_back(cShape[ii]);
  if (tmp_cs.empty())
    tmp_cs.push_back(colShape_None);

  // Instantiate collision shape.
  spCShape cshape {nullptr};
  if (tmp_cs.at(0) == colShape_None) {
    cshape = spCShape (new btEmptyShape());

    // Ensure the object cannot collide (strange things will happen otherwise
    // once Bullet tries to estimate the inertia for an empty shape).
    new_inv_mass = 0;
  }
  else if (tmp_cs.at(0) == colShape_Sphere) {
    cshape = spCShape(new btSphereShape(scale * radius));
  }
  else if (tmp_cs.at(0) == colShape_Box) {
    auto width = scale * tmp_cs.at(1) / 2;
    auto height = scale * tmp_cs.at(2) / 2;
    auto length = scale * tmp_cs.at(3) / 2;
    cshape = spCShape(new btBoxShape(btVector3(width, height, length)));
  }
  else if (tmp_cs.at(0) == colShape_StaticPlane) {
    btVector3 normal {btScalar(tmp_cs.at(1)),
        btScalar(tmp_cs.at(2)), btScalar(tmp_cs.at(3))};
    btScalar thickness = 0.01;
    cshape = spCShape(new btStaticPlaneShape(normal, thickness));
  }

  // Use an empty shape if the requested one is unknown.
  if (!cshape) {
    cout << "Unrecognised collision shape <"
         << tmp_cs.at(0) << ">" << endl;        
    cshape = spCShape (new btEmptyShape());

    // Ensure the object cannot collide (strange things will happen
    // if Bullet tries to estimate the inertia for an empty shape).
    new_inv_mass = 0;
  }


  // Create the initial orientation and position and store it
  // in a motion state.
  btTransform start {rot, pos};
  spMotionState ms {new btDefaultMotionState(start)};

  // Add the collision shape and motion state to the local
  // cache. Neither is explicitly used anymore but the pointers are
  // were passed to Bullet calls and Bullet did not make a copy of
  // it. Therefore, we have to keep a reference to them alive as the
  // smart pointer logic would otherwise remove it.
  collision_shapes[id] = cshape;
  motion_states[id] = ms;

  // Ask Bullet to compute the mass and inertia for us.
  btScalar mass;
  btVector3 inertia;
  if (new_inv_mass < 1E-4) {
    mass = 0;
    inertia = btVector3(0, 0, 0);
  }
  else {
    mass = 1.0f / new_inv_mass;
    cshape->calculateLocalInertia(mass, inertia);
  }

  // Compute inertia magnitude and warn about unreasonable values.
  if ((inertia.length() > 20) || (inertia.length() < 1E-5)) {
    cout << "Bullet " << phys_id << ": Warning: Inertia="
         << inertia.length() << endl;
  }

  // Instantiate the admin structure for the rigid object.
  btRigidBody::btRigidBodyConstructionInfo
    body_CI(mass, ms.get(), cshape.get(), inertia);
  body_CI.m_restitution = restitution;

  // Based on the admin structure, instantiate the actual object.
  spRigidBody body {new btRigidBody(body_CI)};
  body->setLinearVelocity(velocityLin);
  body->setAngularVelocity(velocityRot);
  body->setDamping(0.02f, 0.02f);
  body->setSleepingThresholds(0.1f, 0.1f);
  body->setFriction(1);

  // Attach my own admin structure to the object.
  myAdminStructure *ptr = new myAdminStructure;
  ptr->object_id = id;
  ptr->radius = radius;
  ptr->scale = scale;
  body->setUserPointer((void*)ptr);

  // Add the rigid body to the object cache.
  object_cache[id] = body;
}

int BulletPhys::applyForce(
    const long &ID, const double *force_raw, const double *rel_pos_raw) {

  if (object_cache.find(ID) == object_cache.end()) {
    // There is no such object.
    return 1;
  }

  // Unpack the force and rel_pos into a btVector3.
  btVector3 force, rel_pos;
  for (int ii=0; ii < 3; ii++) {
    force[ii] = btScalar(force_raw[ii]);
    rel_pos[ii] = btScalar(rel_pos_raw[ii]);
  }
  
  object_cache.at(ID)->applyForce(force, rel_pos);
  return 0;
}


/*
  Serialise the objects with ``IDs`` and write the result into ``buf``.
 */
int BulletPhys::getObjectData(const long &numIDs, const long *IDs,
                               const long &bufLen, double *buf) {
  // Sanity check.
  if (bufLen < numIDs * 21) {
    cout << "Output buffer too short" << endl;
    assert (bufLen >= numIDs * 21);
  }

  // Auxiliary variable to keep track of the position in the buffer
  // where the next value should be written.
  double *idx = buf;

  // Serialise each object in turn and fill the provided buffer.
  for (int ii=0; ii < numIDs; ii++) {
    int id = IDs[ii];

    // Return immediately with an error if the object does not exist.
    if (object_cache.find(id) == object_cache.end()) {
      cout << "C++ getObjectData: Object with ID <" << id
           << "> does not exist in local cache." << endl;
      return 1;
    }

    // Radius and scale are in my own admin structure (every Bullet
    // object has one).
    myAdminStructure *tmp = (myAdminStructure*)(
                             object_cache.at(id)->getUserPointer());
    *idx++ = tmp->radius;
    *idx++ = tmp->scale;

    // inv_mass: skip, because I have no idea how to extract that one
    // from Bullet again.
    *idx++ = object_cache.at(id)->getInvMass();

    // Restitution.
    *idx++ = object_cache.at(id)->getRestitution();

    // Serialise the orientation.
    auto quat = object_cache.at(id)->getOrientation();
    for (int jj=0; jj < 4; jj++)
      *idx++ = quat[jj];

    // Serialise the position.
    auto pos = object_cache.at(id)->getCenterOfMassPosition();
    for (int jj=0; jj < 3; jj++)
      *idx++ = pos[jj];

    // Serialise linear- and angular velocities.
    auto vLin = object_cache.at(id)->getLinearVelocity();
    for (int jj=0; jj < 3; jj++)
      *idx++ = vLin[jj];
    auto vRot = object_cache.at(id)->getAngularVelocity();
    for (int jj=0; jj < 3; jj++)
      *idx++ = vRot[jj];

    // Skip the cShape.
    idx += 4;
  }
  if (idx > buf + bufLen) {
    cout << "Read too much from buffer" << endl;
  }

  assert (idx <= buf + bufLen);
  return 0;
}

/*
  De-serialise the objects with ``IDs`` and update the values in the
  local object cache. If the object does not yet exist in the cache,
  then create a new one.
 */
int BulletPhys::setObjectData(const long &numIDs, const long *IDs,
                              const long &bufLen, double *buf) {
  // Auxiliary variable to keep track of where we are in the buffer.
  double *idx = buf;

  // Sanity check.
  if (bufLen < numIDs * 21) {
    cout << "C++ setObjectData: input buffer too short" << endl;
    return 1;
  }

  // Extract the object data one by one and call compileObject on them.
  for (int ii=0; ii < numIDs; ii++) {
    int id = IDs[ii];
    double radius, scale, inv_mass, restitution;
    btQuaternion orientation;
    btVector3 position, vLin, vRot;
    double cShape[4];

    // The first four buffer values correspond to radius, scale,
    // inv_mass and restitution.
    radius = *idx++;
    scale = *idx++;
    inv_mass = *idx++;
    restitution = *idx++;

    // Copy the orientation values into a Quaternion.
    for (int ii=0; ii < 4; ii++) orientation[ii] = btScalar(*idx++);

    // Copy the position and velocities into btVector3 arrays.
    for (int ii=0; ii < 3; ii++)
      position[ii] = btScalar(*idx++);
    for (int ii=0; ii < 3; ii++)
      vLin[ii] = btScalar(*idx++);
    for (int ii=0; ii < 3; ii++)
      vRot[ii] = btScalar(*idx++);

    // Copy the cShape. The length of the cShape is currently hard coded
    // to be 4 bytes.
    for (int ii=0; ii < 4; ii++)
      cShape[ii] = btScalar(*idx++);

    // Update the object data and add it to the simulation.
    compileObject(id, radius, scale, inv_mass, restitution, orientation,
                  position, vLin, vRot, 4, cShape);
  }
  return 0;
}

/*
  Remove specified object IDs. Ignore non-existing IDs. Return the
  total number of removed objects.
 */
int BulletPhys::removeObject(const long &numIDs, long *IDs) {
  int cnt = 0;
  for (int ii=0; ii < numIDs; ii++) {
    object_cache.erase(IDs[ii]);
    cnt++;
  }
  return cnt;
}

int BulletPhys::compute(const long &numIDs, long *IDs,
                        const double &delta_t, const long &max_substeps) {
  
  myPairCache.clear();
  myPairCache.reserve(1024);

  // Add the objects from the cache to the Bullet simulation.
  for (int ii=0; ii < numIDs; ii++) {
    // Abort immediately if the object does not exist in the local
    // cache.
    if (object_cache.find(IDs[ii]) == object_cache.end()) {
      cout << "C++ compute: Object with ID <" << IDs[ii]
           << "> does not exist in local cache - Abort." << endl;
      return 1;
    } 

    // Sanity check.
    assert (object_cache.at(IDs[ii]).get() != nullptr);

    // Add the body to the world and make sure it is activated, as
    // Bullet may otherwise decide to simply set its velocity to zero
    // and ignore the body.
    dynamicsWorld->addRigidBody(object_cache.at(IDs[ii]).get());
    object_cache.at(IDs[ii])->activate();
  }

  // The max_substeps parameter instructs Bullet to subdivide the specified
  // timestep (delta_t) into at most max_substeps. For example, if
  // delta_t = 0.1 and max_substeps=10, then, internally, Bullet will
  // simulate no finer than delta_t / max_substeps = 0.01s.
  dynamicsWorld->stepSimulation(delta_t, max_substeps);

  // Remove the object from the simulation again.
  for (int ii=0; ii < numIDs; ii++) {
    dynamicsWorld->removeRigidBody(object_cache.at(IDs[ii]).get());
  }
  return 0;
}

int BulletPhys::getPairCacheSize() {
  return (long)myPairCache.size();
}

int BulletPhys::getPairCache(const long &N, long *buf) {
  long num_bytes = myPairCache.size() * sizeof(myPairCache.at(0));
  if (num_bytes > N) num_bytes = N;

  memcpy((void*) buf, (void*)myPairCache.data(), num_bytes);
  return num_bytes;
}
