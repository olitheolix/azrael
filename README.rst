======
Azrael
======

Create interactive virtual worlds governed by real world physics.

Azrael applies the laws of physics to all objects in the simulation and queries
about must use a network API. This means that with Azrael, the physics,
rendering, and artificial AI are independent components that can run different
machines. In contrast, most conventional 3D engines are monolithic, run all
components on a single machine, and prescribe the programming language.

The network API also ensures that Azrael is language Agnostic; any language
with either ZeroMQ bindings or Websocket functionality will work.

How and Why
===========

Azrael will feature a scaleable physics engine to simulate worlds of
unprecedented size, detail, and accuracy. The rise of cloud computing provides
the infrastructure and Azrael the logic - at least that is the plan :)

Why do I bother? Because in a virtual world that behaves reasonably similar to
the real world then I can have my space shuttle, design a sub-marine, invent an
algorithm to automatically steer a car through traffic, or build a fictitious
space port. And so can you. All for free and no strings attached. Right now
however only a select few people (if any) have access to the necessary
resources to invent, design, build, and test such technology.


Project Status
==============

So far it is a proof-of-concept only and mostly useful for developers. It wraps
Bullet for the physics, provides basic APIs to control objects, and ships with
a simple 3D viewer.

The first major milestone is towards a minimum viable prototype (MVP) are:

* decent physics,
* ability to combine primitive objects to form more complex ones
* API to connect to these objects and control their active elements
  (eg. boosters)
* ability to query the world (mostly for visualisation).

This has proven to be a surprisingly complex undertaking due to the many
loosely coupled components. However, once the basics are in place it will
hopefully be easier to hone the individual components... with Oculus Rift
support, contemporary 3D rendering (maybe cloud based?), and a scaleable
physics engine to create the largest such simulation in existence...


Help Wanted
===========

The project spans a multitude of technologies, including ZeroMQ, RabbitMQ,
MongoDB, OpenGL (via PyQt), Websockets, Tornado, Cython, a thin C++ wrapper for
Bullet, Sphinx documentation, 3D models that can be distributed via GitHub
without violating any licenses, and more. The skill threshold is rather low
since most components are ludicrously primitive for now.


Installation
============

On Ubuntu 14.04, you can install and test Azrael (without the OpenGL
viewer) like this:

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

In colloquial terms: share any modifications you make, but feel free to use
your own license for code that connects to Azrael (eg. rendering frontends and
AI algorithms).
