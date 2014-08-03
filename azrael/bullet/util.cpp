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

#include <cstring>
#include <iostream>
#include <sstream>

#include "types.hpp"
#include "util.hpp"

using std::cout;
using std::endl;

template <>
void printvec<btVector3>(const btVector3 &vec) {
  const uint numel = 2;
  cout << "<";
  for(uint ii=0; ii<numel; ++ii) {
    cout << vec[ii] << ", ";
  }
  cout << vec[numel] << ">" << endl;
}

template <>
void printvec<btQuaternion>(const btQuaternion &vec) {
  const uint numel = 3;
  cout << "<";
  for(uint ii=0; ii<numel; ++ii) {
    cout << vec[ii] << ", ";
  }
  cout << vec[numel] << ">" << endl;
}

btVector3 toBtVector3(const vecdouble &v) {
  assert (v.size() == 3);
  return btVector3(v[0], v[1], v[2]);
}

btQuaternion toBtQuaternion(const vecdouble &v) {
  assert (v.size() == 4);
  return btQuaternion(v[0], v[1], v[2], v[3]);
}

vecdouble toVecdouble (const btVector3 &v) {
  return vecdouble {v[0], v[1], v[2]};
}

vecdouble toVecdouble (const btQuaternion &v) {
  return vecdouble {v[0], v[1], v[2], v[3]};
}

void fccJoin (std::map<int, std::set<int>> &src, int key,
              std::set<int> &out) {
  // Add all elements at src[key].
  for (auto &u: src[key]) out.insert(u);

  // Make a copy of these elements and erase it from src.
  std::set<int> copy = src[key];
  src[key].clear();

  // Call join for every element in the copy.
  for (auto &u: copy) {
    std::set<int> tmp {};
    fccJoin (src, u, tmp);
    for (auto &v: tmp) out.insert(v);
  }
}

void findConnectedComponents (std::map<int, std::set<int>> &src,
                              std::vector<std::set<int>> &dst) {

  int tot = 0;
  for (auto &u: src) tot += src[u.first].size();

  for (auto &v: src) {
    std::set<int> tmp {};
    fccJoin(src, v.first, tmp);
    if (!tmp.empty()) dst.push_back(tmp);
  }  
}

btVector3 char2btVector3 (const char *buf) {
  std::string str;
  str.assign(buf, buf + strlen(buf));
  std::stringstream ss(str);

  btVector3 out;
  for (int ii=0; ii < 3; ii++) {
    ss >> out[ii];
  }
  return out;
}

btQuaternion char2btQuaternion (const char *buf) {
  std::string str;
  str.assign(buf, buf + strlen(buf));
  std::stringstream ss(str);

  btQuaternion out;
  for (int ii=0; ii < 4; ii++) {
    ss >> out[ii];
  }
  return out;
}

const char* vecdouble2char (const vecdouble &data) {
  std::string str = "";
  for (uint ii=0; ii < data.size(); ii++) {
    str = str + std::to_string(data.at(ii)) + " ";
  }
  if (!str.empty()) str.pop_back();
  str = "[" + str + "]";
  
  char *buf = new char[str.size() + 1];
  memcpy(buf, str.c_str(), str.size());
  buf[str.size()] = 0;
  return buf;
}

const char* vecint2char (const vecint &data) {
  vecdouble tmp (data.size());
  for (uint ii=0; ii < data.size(); ii++) tmp.at(ii) = data.at(ii);
  return vecdouble2char(tmp);
}

const char* vecvecdouble2char (const vecvecdouble &data) {
  std::string str = "[";
  for (uint ii=0; ii < data.size(); ii++) {
    str = str + vecdouble2char(data.at(ii));
  }
  str = str + "]";
  
  char *buf = new char[str.size() + 1];
  memcpy(buf, str.c_str(), str.size());
  buf[str.size()] = 0;
  return buf;
}

vecdouble char2vecdouble (const char *buf) {
  std::string str;
  size_t len = strlen(buf);

  assert (buf[0] == '[');
  assert (buf[len-1] == ']');

  str.assign(buf + 1, buf + len - 1);
  std::stringstream ss(str);

  vecdouble out(len);
  int ii = 0;
  while (ss >> out[ii++]);
  out.resize(ii-1);
  return out;
}

double char2double (const char *buf) {
  std::string str;
  size_t len = strlen(buf);

  str.assign(buf, buf + len);
  std::stringstream ss(str);

  double out;
  ss >> out;
  return out;
}

const char* double2char (const double &value) {
  std::string s = std::to_string(value);
  char *ptr = new char[s.size() + 1];
  memcpy(ptr, s.c_str(), s.size());
  ptr[s.size()] = 0;
  return ptr;
}

vecvecdouble char2vecvecdouble (const char *buf) {
  std::string str;
  size_t len = strlen(buf);

  assert (buf[0] == '[');
  assert (buf[len-1] == ']');

  str.assign(buf + 1, buf + len - 1);

  // todo: check for zero length strings.
  size_t start = 0, stop = 0;
  vecvecdouble out {};
  while (true) {
    stop = str.find("]", start);
    if (stop == std::string::npos) break;
    stop++;
    std::string tmp;
    tmp.assign(str.c_str() + start, str.c_str() + stop);
    out.push_back(char2vecdouble(tmp.c_str()));
    start = stop;
  }
  return out;
}

vecint char2vecint (const char *buf) {
  vecdouble tmp = char2vecdouble (buf);
  vecint out(tmp.size());
  for (uint ii=0; ii < tmp.size(); ii++) out.at(ii) = int(tmp.at(ii));
  return out;
}

vecvecchar char2vecvecchar (const char *buf) {
  vecvecdouble tmp = char2vecvecdouble (buf);
  vecvecchar out;
  vecchar aux;

  for (uint ii=0; ii < tmp.size(); ii++) {
    aux.clear();
    for (uint jj=0; jj < tmp.at(ii).size(); jj++)
      aux.push_back(char(tmp.at(ii).at(jj)));
    out.push_back(aux);
  }
  return out;
}
