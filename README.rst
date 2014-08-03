======
Azrael
======

Create interactive virtual worlds governed by real world physics.

Conventional 3D engines provide an all-in-one option to simulate virtual
worlds, visualise them, enforce physics, and takes player inputs into
account. Azrael, on the other hand, only enforces the physics and provides a
network API to populate it with objects and interact with them. Azrael is thus
fully distributed, including the rendering and object control (eg. artificial
intelligence), which may run in the cloud or on your local computer connecting
to the Azrael server.

Example
=======
Say you want dock a space ship to a space station. You cannot set the
space ship's position directly but you *can* influence it with boosters (ie
apply forces). To do so you may write a program in your favourite language that
queries the world to determine your position relative to the station and
activate the boosters as necessary to dock. Similarly, another program
(possibly on a different computer) can simultaneously query the world and
visualise it. Again, this program is independent of Azrael and your controller.

Feel free to replace the the space ship with a drone that automatically pilots
from A to B, or a car that drives itself through traffic, or an intelligent
suspension system in a vehicle, or computer controlled players. You may also
design larger systems like a fully automated naval port or an airport.


How and Why
===========
Azrael will feature a scaleable physics engine to simulate worlds of
unprecedented size, detail, and accuracy. The rise of cloud computing provides
the infrastructure and Azrael will provide the software - at least that is the
plan.

Why do I bother? Because I believe everyone should be able to create their
Utopia; design, build and launch a space shuttle; create a car that drives
itself, or design a fully automated naval port, come up with a concept for a
space shuttle, or an artificial spine, or fictitious space stations with
automated hangars. Only a select few (if any) are currently in the position to
work on such technologies due to the high costs in building them, but if the
materials were just computer models that behaved like their counterparts in the
real world...


Current Status
===============
Azrael is currently only a proof-of-concept useful for developers. It utilises
Bullet for the physics, provides basic APIs to control objects, and ships with
a simple 3D viewer.

The first major milestone is to build a minimum viable prototype (MVP) that
features:

* decent physics,
* ability to combine primitive objects into more complex ones (eg. build a
  space ship with a passive hull element and active booster elements, or an
  entire factory composed of thousands objects),
* API to connect to these objects and control their active elements,
* ability to query the world (mostly for visualisation).

This has proven to be a surprisingly complex undertaking due to the many loosely
coupled components. However, once the basics are all in place it will hopefully
be easier to hone the individual components... with Oculus Rift 
support, gorgeous 3D rendering (maybe served up via Amazon's AppStream?), a
scaleable physics engine to create the largest physics simulation in
existence...


Installation
============

On Ubuntu 14.04, you can install and test the Azrael stack (without the OpenGL
viewer) with these commands:

.. code-block:: bash

   sudo apt-get install libassimp3 libassimp-dev python3-pymongo scons cython3
   sudo apt-get install python3-zmq libbullet-dev mongodb rabbitmq-server
   sudo apt-get install python3-pip python3-numpy python3-pytest IPython3
   sudo apt-get install python3-tornado python3-pil git
   sudo pip3 install cytoolz setproctitle websocket-client==0.15
   git clone https://github.com/olitheolix/azrael
   cd azrael/azrael/bullet
   scons
   cd ../../
   py.test

To also test the OpenGL viewer:

.. code-block:: bash

   sudo apt-get install python3-opengl libglu1-mesa-dev python3-pyside.qtopengl
   ./start.py


License
=======

Azrael is licensed under the terms of the AGPL v3.

The license emulates that of MongoDB. In colloquial terms: share any
modifications you make, but feel free to use your own license for
code that connects to Azrael (eg. object controllers or rendering front ends).
