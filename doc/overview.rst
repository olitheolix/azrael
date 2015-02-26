========
Overview
========

A game engine for scientists, engineers, and enthusiasts.

Azrael is a proof-of-concept project where every object is subject to the laws
of physics and can be controlled via the network.

Once connected to an object you can send commands to its constituent parts, for
instance its engines to accelerate a space-ship/car/submarine whatever. Whether
you want to control these parts manually, or use a program that employs the
latest and greatest machine learning to automate it is up to you.

You can also query the environments and pass this information on to your
favourite graphics engine to visualise it for you.

Unlike traditional game engines, the graphics engine, physics engine, and
object control (AI) are independent and will most likely not even run on the
same machine.

The API is language Agnostic. Albeit written in Python, the data exchange is
JSON based and the transport layer is either a Websocket (JavaScript/browsers)
or a ZeroMQ socket (pretty much everything but JavaScript).

For a high level overview including demo videos, please visit the
`project page <https://olitheolix.com/azrael/>`_.


How and Why
===========

The cornerstone of Azrael is the clean separation of physics, object control
(or AI), and rendering. The physics engine moves object according to the 
forces acting upon them, the object controllers can send commands to force
generators (eg booster) via the network, and the rendering engine can query the
simulation to visualise it.

Ideally, every object in the simulation will be remote controlled from a
different computer, virtual machine, or at least a separate process on a single
computer. The programming language should not matter to allow system designers
to use whatever they are comfortable with to develop the algorithms.

The goal is to eventually make the physics engine itself scalable across
multiple computers to simulate worlds of unprecedented size, detail, and
accuracy. All hail cloud computing :)

Why do I bother? Because in a reasonably realistic virtual world I can have my
own space shuttle, design my own sub-marine, invent my own Mars rover with
awesome navigation abilities, launch my own Rosetta mission, or build an
automated fleet of space ships. And so can you. No job at NASA required.


Project Status
==============

So far it is mostly useful for developers. It wraps Bullet for the physics,
provides basic APIs to control objects, and ships with a simple 3D viewer.

The first major milestone towards a minimum viable prototype (MVP) are:

* decent physics,
* ability to combine primitive objects to form more complex ones
* API to connect and control these objects
* ability to query the world (mostly for visualisation).

This proved surprisingly difficult (read "fun") due to the many loosely coupled
components. However, once the basics are in place it will hopefully become
easier to hone the individual components... with Oculus Rift support,
contemporary 3D rendering (maybe cloud based?), a scalable physics engine to
create the largest Newtonian simulation on the planet...


Installation
============

To install Azrael on Ubuntu 14.04 you need to install the dependencies listed in
`install.sh`. To start Azrael type

.. code-block:: bash

   ./start.py --noviewer

and then open http://localhost:8080/static/webviewer.html in your (WebGL
supporting) browser.

If you also want the standalone OpenGL viewer, and have an OpenGL 3.x
compatible GPU, then install these packages

.. code-block:: bash

   sudo apt-get install python3-opengl libglu1-mesa-dev python3-pyside.qtopengl

and start Azrael with:

.. code-block:: bash

   ./start.py


License
=======

Azrael is licensed under the terms of the AGPL v3.
