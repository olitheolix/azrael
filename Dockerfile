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
RUN apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv 7F0CEB10
RUN echo "deb http://repo.mongodb.org/apt/ubuntu "$(lsb_release -sc)"/mongodb-org/3.0 multiverse" | tee /etc/apt/sources.list.d/mongodb-org-3.0.list

# Install Ubuntu packages for Azrael.
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    libassimp-dev \
    libassimp3 \
    mongodb-org \
    wget \
    && apt-get clean

# Install Miniconda (Python 3 version).
RUN wget -O miniconda3.sh \
    http://repo.continuum.io/miniconda/Miniconda3-3.10.1-Linux-x86_64.sh \
    && bash miniconda3.sh -b -p /opt/miniconda3 \
    && rm miniconda3.sh

# Add the path to the Anaconda binaries to the path.
ENV PATH /opt/miniconda3/bin:$PATH

# Install basic set of packages to speed up the build of this container.
RUN conda install --name root \
    numpy \
    pyzmq \
    cython \
    cytoolz \
    pymongo \
    pytest \
    ipython \
    pillow -y \
    && conda clean -p -t -y

# Clone Azrael from GitHub.
RUN git clone https://github.com/olitheolix/azrael /demo/azrael

# This will let Azrael know it runs inside a Docker container.
ENV INSIDEDOCKER 1

# Move into Azrael's home directory.
WORKDIR /demo/azrael
RUN find . -type d -iname '__pycache__' | xargs rm -rf

# Update the Anaconda environment to ensure all necessary packages are installed.
RUN conda env update --name root --file environment_docker.yml \
    && conda clean -p -t -y

# Move into Bullet wrapper directory to compile- and test the extension modules.
WORKDIR /demo/azrael/azrael/bullet
RUN python setup.py build_ext --inplace \
    && rm -rf build/ \
    && py.test -x

# Move into Azrael's home directory.
WORKDIR /demo/azrael

# Run Azrael's entire test suite.
RUN py.test -x

# Expose the ports for Clerk and Clacks.
EXPOSE 5555 8080

# Default command: start the force grid demo.
CMD ["python", "demos/demo_forcegrid.py", "--noviewer", \
     "--reset=30", "--cubes=3,3,1", "--linear=1", "--circular=1"]
