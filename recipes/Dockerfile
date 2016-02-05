# Build all the Anaconda packages required by Azrael.
#
# From this directory (where this 'Dockerfile' is located) build and run the
# container with the following command:
#
#  >> docker build -t build_azanaconda_packages -f Dockerfile .. && docker run -ti build_azanaconda_packages
#
# This will also display the upload instructions for Anaconda.org.

# Anaconda base image.
FROM continuumio/miniconda3:latest
MAINTAINER Oliver Nagy <olitheolix@gmail.com>

# Add the Anaconda binaries to the path.
ENV PATH /opt/miniconda3/bin:$PATH

# Create "/demo" to hold the Azrael repo.
RUN mkdir -p /demo/

# Install compilers and Anaconda packages.
RUN apt-get update && apt-get install -y build-essential
RUN conda install -y \
    IPython \
    anaconda-client \
    cmake \
    conda-build \
    cython \
    libgcc \
    numpy \
    pytest

# Copy the local repo into the container. Then remove all temporary files.
ADD . /demo/azrael
RUN find . -type d -iname '__pycache__' | xargs rm -rf
RUN find . -type f -iname '*~' | xargs rm -f

# Remove all stale Bullet build files.
WORKDIR /demo/azrael/azrael/bullet
RUN python setup.py clean

# Build the Anaconda packages.
WORKDIR /demo/azrael/recipes
RUN conda build --python 3.4 --python 3.5 assimp
RUN conda build --python 3.4 --python 3.5 azbullet

# Display Anaconda login and upload instructions.
CMD echo "To upload packages to Anaconda.org:" && \
    echo "  >> anaconda login" && \
    echo "  >> anaconda upload --force /opt/conda/conda-bld/linux-64/*.tar.bz2" && \
    bash
