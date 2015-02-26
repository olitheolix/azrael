# An all-in-one container for Azrael.
# To start the demo:
#
#   >> docker run -d -p 8080:8080 \
#             olitheolix/azrael:latest \
#             "./demo_forcegrid.py --noviewer --numcubes 4,4,1"
#
# Since the container contains a full MongoDB installation, you may
# want to export the Mongo data directory to a temporary directory or
# otherwise your image will grow rapidly over time:
#
#   >> docker run -d -p 8080:8080 -v /tmp/azrael:/demo/mongodb \
#             olitheolix/azrael:latest \
#             "./demo_forcegrid.py --noviewer --numcubes 4,4,1"

# Ubuntu 14.04 base image.
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
RUN apt-get update && apt-get install -y \
    IPython3 \
    git \
    libassimp-dev \
    libassimp3 \
    libboost-python-dev \
    mongodb-10gen \
    python3-matplotlib \
    python3-netifaces \
    python3-numpy \
    python3-pandas \
    python3-pil \
    python3-tornado \
    python3-zmq

# Install PIP packages, download and compile the Bullet-Python
# bindings, and clean up to reduce the size of the container image.
WORKDIR /tmp
RUN apt-get install -y python3-pip && \
    pip3 install cytoolz setproctitle websocket-client==0.15 pymongo \
                 pytest-cov && \
    pip3 install --install-option -j \
    git+https://github.com/Klumhru/boost-python-bullet.git@d9ffae09157#egg=boost-python-bullet  && \
    apt-get remove -y python3-pip && \
    apt-get autoremove -y && apt-get -y clean

# Clone Azrael from GitHub.
RUN git clone https://github.com/olitheolix/azrael /demo/azrael

# Expose the necessary Tornado and ZeroMQ ports.
EXPOSE 8080 5555

# Home directory.
WORKDIR /demo/azrael

ENTRYPOINT ["/usr/bin/python3", "entrypoint.py"]
#ENTRYPOINT ["/bin/bash"]

# Default command: start MongoDB and Azrael.
CMD ["./demo_forcegrid.py --noviewer --numcubes 4,4,1"]
