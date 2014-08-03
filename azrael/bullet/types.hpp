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

#ifndef TYPES_H
#define TYPES_H

#include <map>
#include <vector>
#include <memory>

enum CollisionShapeName {
  colShape_None,                // collision detection disabled
  colShape_Auto,                // engine chooses the shape
  colShape_StaticPlane,         // a static plane.
  colShape_Sphere,
  colShape_Box};

typedef std::vector<std::string> strlist;
typedef std::vector<int> vecint;
typedef std::vector<char> vecchar;
typedef std::vector<float> vecfloat;
typedef std::vector<double> vecdouble;
typedef std::vector<vecdouble> vecvecdouble;
typedef std::vector<vecint> vecvecint;
typedef std::vector<vecchar> vecvecchar;

#endif
