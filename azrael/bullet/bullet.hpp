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

#ifndef BULLET_H
#define BULLET_H

#include <map>
#include <vector>
#include <memory>

#include <btBulletDynamicsCommon.h>
#include <BulletCollision/CollisionDispatch/btCollisionDispatcher.h>

#include "types.hpp"

typedef std::shared_ptr<btRigidBody> spRigidBody;
typedef std::shared_ptr<btCollisionShape> spCShape;
typedef std::shared_ptr<btMotionState> spMotionState;


class BulletPhys {
public:
  int phys_id = 0;

  btOverlapFilterCallback *cb_broadphase = nullptr;
  std::map<long, spRigidBody> object_cache;
  std::map<long, spCShape> collision_shapes;
  std::map<long, spMotionState> motion_states;
  
  btBroadphaseInterface* broadphase {nullptr};
  btDefaultCollisionConfiguration* collisionConfig {nullptr};
  btCollisionDispatcher* dispatcher {nullptr};
  btSequentialImpulseConstraintSolver* solver {nullptr};
  btDiscreteDynamicsWorld* dynamicsWorld {nullptr};

  BulletPhys() = delete;
  BulletPhys(const int &, const int &coll_filter);
  virtual ~BulletPhys();

  void compileObject(const long &id,
                     const double &radius,
                     const double &scale,
                     const double &inv_mass,
                     const double &restitution,
                     const btQuaternion &rot,
                     const btVector3 &pos,
                     const btVector3 &vLin,
                     const btVector3 &vRot,
                     const int &cShapeLen,
                     const double *cShape);

  // Exposed to Python.
  virtual int compute(const long&, long*, const double&, const long&);
  int getObjectData(const long &numIDs, const long *IDs,
                    const long &bufLen, double* buf);
  int setObjectData(const long &numIDs, const long *IDs,
                    const long &bufLen, double *buf);
  int getPairCache(const long &N, long *buf);
  int applyForce(const long &ID, const double *force, const double *rel_pos);
  int getPairCacheSize();
  int removeObject(const long &numIDs, long *IDs);
};

#endif
