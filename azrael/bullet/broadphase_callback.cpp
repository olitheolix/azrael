#include <iostream>
#include <vector>
#include "btBulletDynamicsCommon.h"

/* Global pair cache variable. Should be inside the
   BroadphasePaircacheBuilder but the compiler does not like that for
   some reason. */
std::vector<int> myPairCache;

/*
Custom callback class for Broadphase solver.

This class collects all broadphase collision pairs and tells Bullet to
not resolve any of the collisions.

The main purpose of this class is thus to collect the collision pairs
which can then be sent to other physics engines for processing.
*/
struct BroadphasePaircacheBuilder : public btOverlapFilterCallback
{
  /*
    Record all collision pairs in the global myPairCache variable.

    Bullet will call this method for every broadphase collision pair.
    This particular implementation will return false to disable
    collision resolution for all objects.
  */
  bool needBroadphaseCollision(
               btBroadphaseProxy* proxy0,
               btBroadphaseProxy* proxy1) const {
  
    /* Get the two rigid bodies involved in the collision. */
    btRigidBody *a = (btRigidBody*)(proxy0->m_clientObject);
    btRigidBody *b = (btRigidBody*)(proxy1->m_clientObject);

    /* Convenience variables to store the user pointers.*/
    auto up_a = a->getUserPointer();
    auto up_b = b->getUserPointer();

    /* If both user pointers are valid we will _assume_ they contain
       an integer value, namely the body ID assigned by Azrael. */
    if ((up_a != NULL) && (up_b != NULL)) {
      // Get the body IDs.
      int bodyID_a = ((int*)up_a)[0];
      int bodyID_b = ((int*)up_b)[0];

      // Push them into the cache in a sorted manner.
      if (bodyID_a < bodyID_b) {
        myPairCache.push_back(bodyID_a);
        myPairCache.push_back(bodyID_b);
      } else {
        myPairCache.push_back(bodyID_b);
        myPairCache.push_back(bodyID_a);
      }
    }

    // Return 'false' to let Bullet know that we do not want it to
    // resolve collisions for these objects.
    return false;
  }

  /* Return the pair cache. */
  std::vector<int> *azGetPairCache() {
    return &myPairCache;
  }

  /* Reset the pair cache. */
  void azResetPairCache() {
    myPairCache.clear();
    myPairCache.reserve(1000000);
  }
};
