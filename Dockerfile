# Clean Build: docker build --rm=true --no-cache=true -t="<user>/<name>:<tag>" .
# Incremental Build: docker build -t="<user>/<name>:<tag>" .
# Run interactive: docker run -p 8080:8080 -ti "<user>/<name>:<tag>"
# Run standalone: docker run -d -v /var -v /demo -p 8080:8080 <user>/<name>:<tag> "./demo_forcegrid.py --noviewer --numcubes 4,4,1"

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

# Install PIP packages for Azrael.
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

# Expose the webserver and ZeroMQ port.
EXPOSE 8080 5555

# Export the /demo folder (this is where MongoDB stores its files and
# where Azrael puts its logs) to prevent Docker from tracking it via
# its Union FS.
VOLUME /demo

WORKDIR /demo/azrael

#ENTRYPOINT ["/usr/bin/python3", "entrypoint.py"]
ENTRYPOINT ["/bin/bash"]

# Default command: start MongoDB and Azrael.
CMD ["-h"]
