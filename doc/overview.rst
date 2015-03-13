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


Azrael's Philosophy
===================

The cornerstone of Azrael is the clean separation of physics, object control
(or AI), and rendering. The physics engine moves object accordings to the 
forces acting upon them, the object controllers send commands via the network
to the force generators (eg booster), and the rendering engine queries the
simulation to visualise it.

Ideally, every object in the simulation will be remote controlled from a
different computer, virtual machine, or at simply a separate process on the
same machine. The programming language does not matter because the interface
uses plain JSON. You may therefore develop your algorithms in whatever
programming language you deem appropriate.

The goal is to eventually make the physics engine itself scalable across
multiple computers to simulate worlds of unprecedented size, detail, and
accuracy. All hail cloud computing :)

Why do I bother? Because in a reasonably realistic virtual world I can have my
own space shuttle, design my own sub-marine, invent my own Mars rover with
awesome navigation abilities, launch my own Rosetta mission, or build my own
automated fleet of space ships. And so can you. No job at NASA required.


Project Status
==============

So far it is mostly useful for developers. It wraps Bullet for the physics,
provides the basic API to define and control objects, and comes with
OpenGL/WebGl viewers to render the scene.


Installation
============

On Ubuntu 14.04 (and probably most other recent Linux distributions) you can
either clone the entire repository from GitHub or download a pre-built Docker 
container. For details on either see https://github.com/olitheolix/azrael

For the standalone OpenGL viewer (requries an OpenGL 3.x compatible GPU) you
will also need these:

.. code-block:: bash

   sudo apt-get install python3-opengl libglu1-mesa-dev python3-pyside.qtopengl


License
=======

Azrael is licensed under the terms of the AGPL v3.
