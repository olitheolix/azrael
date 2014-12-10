#!/bin/bash

# (K)Ubuntu repos.
apt-get install -y \
  IPython3 \
  libassimp-dev \
  libassimp3 \
  libboost-python-dev \
  mongodb \
  python3-matplotlib \
  python3-netifaces \
  python3-numpy \
  python3-pandas \
  python3-pil \
  python3-pip \
  python3-pymongo \
  python3-tornado \
  python3-zmq

# PIP repos.
pip3 install cytoolz setproctitle websocket-client==0.15 pytest pytest-cov

# PIP install boost-python-wrapper directory from GitHub.
pip3 install --install-option="-j" \
 -e git+https://github.com/Klumhru/boost-python-bullet.git#egg=boost-python-bullet
