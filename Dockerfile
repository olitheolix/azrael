# An all-in-one container for Azrael.
# To start a specific demo:
#
#   >> docker run -d -p 8080:8080 \
#             olitheolix/azrael:latest \
#             demos/demo_forcegrid.py --noviewer --cubes=4,4,1
#
# Since the container contains a full MongoDB installation, you may
# want to export the MongoDB data directory to a temporary directory
# or otherwise your image will grow rapidly over time:
#
#   >> docker run -d -p 8080:8080 -v /tmp/azrael:/demo/azrael/volume \
#             olitheolix/azrael:latest \
#             demos/demo_forcegrid.py --noviewer --cubes=4,4,1

# Ubuntu 14.04 base image.
FROM ubuntu:14.04
MAINTAINER Oliver Nagy <olitheolix@gmail.com>

# Create "/demo" and "/demo/mongodb" to hold the Azrael repo and
# MongoDB files, respectively.
RUN mkdir -p /demo/mongodb

# Add APT credentials for MongoDB.
RUN sudo apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv 7F0CEB10
RUN echo "deb http://repo.mongodb.org/apt/ubuntu "$(lsb_release -sc)"/mongodb-org/3.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-3.0.list

# Install Ubuntu packages for Azrael.
RUN apt-get update && apt-get install -y \
    IPython3 \
    git \
    libassimp-dev \
    libassimp3 \
    libboost-python-dev \
    mongodb-org \
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
    pip3 install \
      cytoolz \
      pymongo==2.7 \
      pytest-cov \
      setproctitle \
      websocket-client==0.15 &&\
    pip3 install --install-option \
    git+https://github.com/Klumhru/boost-python-bullet.git@d9ffae09157#egg=boost-python-bullet  && \
    apt-get remove -y python3-pip && \
    apt-get autoremove -y && apt-get -y clean

# Clone Azrael from GitHub.
RUN git clone https://github.com/olitheolix/azrael /demo/azrael

# Expose the ports for Clerk and Clacks.
EXPOSE 5555 8080

# Special environment variable to let Azrael know it runs in Docker.
ENV INSIDEDOCKER 1

# Home directory.
WORKDIR /demo/azrael

# Default command: start the force grid demo.
CMD ["/usr/bin/python3", "demos/demo_forcegrid.py", "--noviewer", \
     "--reset=30", "--cubes=3,3,1", "--linear=1", "--circular=1"]
