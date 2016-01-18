# Azrael in a Docker container.
#
# To start the demo you need 'docker-compose' and the 'docker-compose.yml' file.
#
#   >> docker-compose up

# Anaconda base image.
FROM continuumio/miniconda3:latest
MAINTAINER Oliver Nagy <olitheolix@gmail.com>

# Install support packages from Ubuntu repositories.
RUN rm /bin/sh && ln -s /bin/bash /bin/sh \
    && apt-get update && apt-get install -y git procps

# Create the application directory and clone Azrael from GitHub.
RUN mkdir -p /demo/
WORKDIR /demo/azrael
RUN git clone https://github.com/olitheolix/azrael /demo/azrael

# Setup the Anaconda environment for Azrael.
RUN apt-get install -y build-essential \
    && conda config --add channels olitheolix \
    && conda env create --name azrael --file environment_docker.yml \
    && conda clean -p -s -t -y \
    && apt-get remove -y build-essential \
    && apt-get -y autoremove \
    && apt-get -y autoclean \
    && apt-get -y clean

# Tell Azrael to connect to Docker networks instead of 'localhost'.
ENV INSIDEDOCKER 1

# Finalise container setup.
EXPOSE 5555 8080
CMD ["/demo/azrael/support/start.sh", "forcegrid"]
