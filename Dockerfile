# Azrael in a Docker container.
#
# See the demos/docker folder for canned demos using docker-compose.

# Anaconda base image.
FROM continuumio/miniconda3:latest
MAINTAINER Oliver Nagy <olitheolix@gmail.com>

# Install support packages from Ubuntu repositories.
RUN rm /bin/sh && ln -s /bin/bash /bin/sh \
    && apt-get update && apt-get install -y git procps

# Clone Azrael from GitHub and delete the .git folder.
RUN git clone https://github.com/olitheolix/azrael /azrael && rm -rf /azrael/.git

# Setup the Anaconda environment for Azrael.
RUN apt-get install -y build-essential \
    && conda env create --name azrael --file /azrael/environment_docker.yml \
    && conda clean -p -s -t -y \
    && apt-get remove -y build-essential \
    && apt-get -y autoremove \
    && apt-get -y autoclean \
    && apt-get -y clean

# Tell Azrael to use the Docker networks instead of 'localhost'.
ENV INSIDEDOCKER 1

# Finalise container setup.
WORKDIR /azrael
EXPOSE 5555 5556 8080
ENTRYPOINT ["/azrael/devtools/entrypoint.sh"]
