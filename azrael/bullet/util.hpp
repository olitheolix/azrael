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

#ifndef UTIL_H
#define UTIL_H

#include <set>
#include <vector>
#include <memory>
#include <sstream>
#include <iostream>

#include <btBulletDynamicsCommon.h>

#include "types.hpp"

template <typename T>
void printvec(const T &v) {
  if (v.empty()) {
    std::cout << "<>" << std::endl;
    return;
  }
  
  std::cout << "<";
  for (auto &u: v) std::cout << u << ", ";
  std::cout << "\b\b>" << std::endl;
}

template <>
void printvec(const btVector3 &vec);

template <>
void printvec(const btQuaternion &vec);

btVector3 toBtVector3(const vecdouble &v);
btQuaternion toBtQuaternion(const vecdouble &v);

vecdouble toVecdouble (const btVector3 &v);
vecdouble toVecdouble (const btQuaternion &v);

btVector3 char2btVector3 (const char *buf);
btQuaternion char2btQuaternion (const char *buf);

vecdouble char2vecdouble (const char *buf);
const char* vecdouble2char (const vecdouble &data);
vecvecdouble char2vecvecdouble (const char *buf);
const char* vecvecdouble2char (const vecvecdouble &data);
const char* vecint2char (const vecint &data);
const char* vecchar2char (const vecchar &data);
vecvecchar char2vecvecchar (const char *buf);
vecint char2vecint (const char *buf);
double char2double (const char *buf);
const char* double2char (const double &value);

void findConnectedComponents (std::map<int, std::set<int>> &,
                              std::vector<std::set<int>> &);
#endif
