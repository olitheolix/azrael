#include <iostream>
#include <vector>
#include "btBulletDynamicsCommon.h"

/* Define the pair cache. The narrow phase callback will populate it. */
struct AzraelCollisionData {
  const int aid_a;
  const int aid_b;
  const btVector3 point_a;
  const btVector3 point_b;
  const btVector3 normal_on_b;
};
std::vector<AzraelCollisionData> narrowphasePairCache;


/*
  Bullet will call this function for every pair that has a collision.

  We are adding some minor logic here to compile collision contacts
  into the global `narrowphasePairCache` variable.

  This function is a modified version of the demo provided at
  http://www.bulletphysics.org/mediawiki-1.5.8/index.php/Simulation_Tick_Callbacks
  as explained at
  http://www.bulletphysics.org/mediawiki-1.5.8/index.php?title=Collision_Callbacks_and_Triggers
 */
void azNarrowphaseCallback(btDynamicsWorld *world, btScalar timeStep) {
  // Handle to all contacts.
  int numManifolds = world->getDispatcher()->getNumManifolds();

  // Loop over all contacts and compile the collision pairs and their
  // contact points.
  for (int i=0;i<numManifolds;i++) {
    // Query the collision pair.
    btPersistentManifold* contactManifold =  world->getDispatcher()->getManifoldByIndexInternal(i);
    btCollisionObject* obA = const_cast<btCollisionObject*>(contactManifold->getBody0());
    btCollisionObject* obB = const_cast<btCollisionObject*>(contactManifold->getBody1());

    // Get the AIDs of the two objects in question. Azrael stores
    // the AID of the objects in the 'userPointer' (provided by
    // Bullet for the user to store arbitrary information alongside
    // the object).
    void *upa = obA->getUserPointer();
    void *upb = obB->getUserPointer();

    // If there is no data then this is a bug; continue to the next
    // collision pair.
    if ((upa == NULL) || (upa == NULL)) continue;

    // Each collision pair may have multiple contacts. Loop over them
    // all and add them to the global 'narrowphasePairCache' vector.
    int numContacts = contactManifold->getNumContacts();
    for (int j=0;j<numContacts;j++) {
      // Get the next contact point.
      btManifoldPoint& pt = contactManifold->getContactPoint(j);

      // Skip to the next contact point if the collision points for
      // this object are merely close but not touching or
      // interpenetrating.
      if (pt.getDistance() > 0.f) continue;

      // Compile the collision data and add it to the global buffer.
      narrowphasePairCache.push_back(
        AzraelCollisionData {
          *reinterpret_cast<int*>(upa),
          *reinterpret_cast<int*>(upb),
          pt.getPositionWorldOnA(),
          pt.getPositionWorldOnB(),
          pt.m_normalWorldOnB
        }
      );
    }
  }
}

/* Reset the global collision pair buffer */
void resetNarrowphasePairCache() {
  narrowphasePairCache.clear();
  narrowphasePairCache.reserve(1000000);
}

/* Register the callback handler with the narrowphase dispatcher */
void installNarrowphaseCallback(btDiscreteDynamicsWorld *world) {
  world->setInternalTickCallback(azNarrowphaseCallback);
}
