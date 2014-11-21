#!/bin/bash

# (K)Ubuntu repos.
apt-get install -y libassimp3 libassimp-dev python3-pymongo \
python3-zmq mongodb rabbitmq-server libboost-python-dev \
python3-pip python3-numpy python3-pytest IPython3 python3-matplotlib \
python3-tornado python3-pil python3-netifaces

# PIP repos.
pip3 install cytoolz setproctitle websocket-client==0.15

# Clone the Python bindings for Bullet.
cwd=$(pwd)
bpb_dir=/tmp/boost-python-bullet
git clone https://github.com/Klumhru/boost-python-bullet.git $bpb_dir
cd $bpb_dir
python3 setup.py install -j

# Unit tests for Boost-Python-Bullet library.
nosetests3
cd "$cwd"

# Unit tests for Azrael.
py.test-3
