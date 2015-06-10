# Azrael in a Docker container.
#
# To start the demo you need 'docker-compose' and the 'docker-compose' file.
#
#   >> docker-compose up

# Ubuntu 14.04 base image.
FROM ubuntu:14.04
MAINTAINER Oliver Nagy <olitheolix@gmail.com>

# Create "/demo" to hold the Azrael repo.
RUN mkdir -p /demo/

# Install Ubuntu packages for Azrael.
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    libassimp-dev \
    libassimp3 \
    wget \
    && apt-get clean

# Install Miniconda (Python 3 version).
RUN wget -O miniconda3.sh \
    http://repo.continuum.io/miniconda/Miniconda3-3.10.1-Linux-x86_64.sh \
    && bash miniconda3.sh -b -p /opt/miniconda3 \
    && rm miniconda3.sh

# Add the Anaconda binaries to the path.
ENV PATH /opt/miniconda3/bin:$PATH

# Clone Azrael from GitHub.
RUN git clone https://github.com/olitheolix/azrael /demo/azrael

# This will let Azrael know it runs inside a Docker container.
ENV INSIDEDOCKER 1

# Move into Azrael's home directory.
WORKDIR /demo/azrael

# Update the Anaconda environment to ensure all necessary packages are installed.
RUN conda env update --name root --file environment_docker.yml \
    && conda clean -p -t -y

# Expose the ports for Clerk and Clacks.
EXPOSE 5555 8080

# Move into Bullet wrapper directory to compile- and test the extension modules.
WORKDIR /demo/azrael/azrael/bullet
RUN python setup.py cleanall && python setup.py build_ext --inplace && rm -rf build

# Move into Azrael's home directory.
WORKDIR /demo/azrael

# Default command: start the force grid demo.
CMD ["python", "demos/demo_forcegrid.py", "--noviewer", \
     "--reset=30", "--cubes=3,3,1", "--linear=1", "--circular=1"]
