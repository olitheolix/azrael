# Clean Build: docker build --rm=true --no-cache=true -t azrael . 
# Launch: docker run -p 8080:8080 -t -i azrael bash
FROM ubuntu

# Update system and install GIT.
RUN apt-get update
RUN apt-get upgrade -y
RUN apt-get install -y git

# Create project directory and clone Azrael repo into it.
RUN mkdir demo
WORKDIR /demo
RUN git clone https://github.com/olitheolix/azrael
WORKDIR /demo/azrael

# Install dependencies for Azrael.
RUN /bin/bash ./install.sh

# Default command: start MongoDB and Azrael.
CMD /etc/init.d/mongodb start && ./start.py --noviewer
