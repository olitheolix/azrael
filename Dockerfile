# Azrael in a Docker container.
#
# To start the demo you need 'docker-compose' and the 'docker-compose.yml' file.
#
#   >> docker-compose up

# Anaconda base image.
FROM continuumio/miniconda3:latest
MAINTAINER Oliver Nagy <olitheolix@gmail.com>

# Add the Anaconda binaries to the path.
ENV PATH /opt/miniconda3/bin:$PATH

# This will let Azrael know it runs inside a Docker container.
ENV INSIDEDOCKER 1

# Create "/demo" to hold the Azrael repo.
RUN mkdir -p /demo/

# Install Ubuntu packages for Azrael.
RUN apt-get update && apt-get install -y git

# Clone Azrael from GitHub.
RUN git clone https://github.com/olitheolix/azrael /demo/azrael

# Move into Azrael's home directory.
WORKDIR /demo/azrael

# Install the missing packages required by Azrael.
RUN apt-get install -y build-essential procps \
    && conda install -y -c https://conda.anaconda.org/olitheolix assimp azbullet \
    && conda env update --name root --file environment_docker.yml \
    && conda clean -p -s -t -y \
    && apt-get remove -y build-essential \
    && apt-get -y autoremove \
    && apt-get -y autoclean \
    && apt-get -y clean

# Expose the ports for Clerk and Clacks.
EXPOSE 5555 8080

# Default command: start the force grid demo.
CMD ["python", "demos/demo_forcegrid.py", "--noviewer", \
     "--reset=30", "--cubes=3,3,1", "--linear=1", "--circular=1"]

