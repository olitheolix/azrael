# Clean Build: docker build --rm=true --no-cache=true -t="<user>/<name>:<tag>" .
# Incremental Build: docker build -t="<user>/<name>:<tag>" .
# Launch: docker run -p 8080:8080 -ti "<user>/<name>:<tag>"

# Base image is Ubuntu 14.04
FROM ubuntu:14.04
MAINTAINER Oliver Nagy <olitheolix@gmail.com>

# Create Mongo data directory and Azrael project directory.
RUN mkdir -p /data/db && mkdir demo

# Add APT credentials for MongoDB.
RUN apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv 7F0CEB10
RUN echo 'deb http://downloads-distro.mongodb.org/repo/ubuntu-upstart' \
         ' dist 10gen' | tee /etc/apt/sources.list.d/10gen.list

# Install Ubuntu packages for Azrael.
RUN apt-get update && apt-get install -y \
    IPython3 \
    cython3 \
    git \
    libassimp-dev \
    libassimp3 \
    libbullet-dev \
    mongodb-10gen \
    python3-matplotlib \
    python3-netifaces \
    python3-numpy \
    python3-pil \
    python3-pip \
    python3-pymongo \
    python3-pytest \
    python3-tornado \
    python3-zmq \
    rabbitmq-server \
    scons

# Install PIP packages for Azrael.
RUN pip3 install cytoolz setproctitle websocket-client==0.15

# Clone Azrael from GitHub.
WORKDIR /demo
RUN git clone https://github.com/olitheolix/azrael
WORKDIR /demo/azrael

# Compile the Cython extensions.
WORKDIR /demo/azrael/azrael/bullet
RUN scons
WORKDIR /demo/azrael

# Expose the webserver port.
EXPOSE 8080

# Default command: start MongoDB and Azrael.
CMD /usr/bin/mongod --smallfiles & ./start.py --noviewer --numcubes 4,4,1
