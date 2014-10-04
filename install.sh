#!/bin/bash

# Install dependencies for Azrael core from Debian repos.
apt-get install libassimp3 libassimp-dev python3-pymongo scons cython3 \
python3-zmq libbullet-dev mongodb rabbitmq-server \
python3-pip python3-numpy python3-pytest IPython3 python3-matplotlib \
python3-tornado python3-pil python3-netifaces

# Install dependencies for Azrael core via PIP.
pip3 install cytoolz setproctitle websocket-client==0.15

# Compile the Cython code.
cd azrael/bullet
scons
cd ../../
