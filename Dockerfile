# Clean Build: docker build --rm=true --no-cache=true -t="<user>/<name>:<tag>" .
# Incremental Build: docker build -t="<user>/<name>:<tag>" .
# Launch: docker run -p 8080:8080 -ti "<user>/<name>:<tag>"

# Base image is Ubuntu 14.04
FROM ubuntu:14.04
MAINTAINER Oliver Nagy <olitheolix@gmail.com>

# Create "/demo" and "/demo/mongodb" to hold the Azrael repo and
# MongoDB files, respectively.
RUN mkdir -p /demo/mongodb

# Add APT credentials for MongoDB.
RUN apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv 7F0CEB10
RUN echo 'deb http://downloads-distro.mongodb.org/repo/ubuntu-upstart' \
         ' dist 10gen' | tee /etc/apt/sources.list.d/10gen.list

# Install Ubuntu packages for Azrael.
RUN apt-get clean && rm -rf /var/lib/apt/lists/* && \
    apt-get update && apt-get install -y \
    IPython3 \
    git \
    libassimp-dev \
    libassimp3 \
    libboost-python-dev \
    mongodb-10gen \
    python3-matplotlib \
    python3-netifaces \
    python3-numpy \
    python3-pil \
    python3-pip \
    python3-pymongo \
    python3-pytest \
    python3-tornado \
    python3-zmq

# Install PIP packages for Azrael.
RUN pip3 install cytoolz setproctitle websocket-client==0.15

# Clone and compile the Boost-Python-Bullet wrapper.
WORKDIR /tmp
RUN pip3 install --install-option="-j" \
 -e git+https://github.com/Klumhru/boost-python-bullet.git#egg=boost-python-bullet

# Clone Azrael from GitHub.
WORKDIR /demo
RUN git clone https://github.com/olitheolix/azrael
WORKDIR /demo/azrael

# Expose the webserver port.
EXPOSE 8080

# Tell Docker not to track any changes in "/demo" directory (this is
# where the MongoDB is stored and where Azrael writes its log files).
VOLUME /demo

# Default command: start MongoDB and Azrael.
CMD /usr/bin/mongod --smallfiles --dbpath /demo/mongodb \
    & ./start.py --noviewer --numcubes 4,4,1
