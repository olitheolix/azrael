========
Overview
========

Create interactive virtual worlds governed by real world physics.

Azrael is a proof-of-concept project where every object is subject to the laws
of physics and can be controlled via the network.

Once connected to an object you can send commands to its constituent parts, for
instance its engines to accelerate a space ship in certain direction, or a car,
or a submarine. Whether you want to control these parts manually, or use a
program that employs the latest and greatest machine learning to automate it is
up to you.

Furthermore, you can ask the object for what it "sees" in its
neighbourhood. Pass this information on to your favourite graphics engine and
you can visualise the world.

Unlike classical game engines the graphics engine, physics engine, and object
control (AI) are independent components. Most likely they will not even run on
the same machine, or even the same network.

The network API also ensures that Azrael is language Agnostic. Albeit written
in Python, the binary protocol is JSON based and provides interfaces for
Websockets (JavaScript/browsers) and ZeroMQ (anything but JavaScript).

How and Why
===========

The cornerstone of Azrael is the clean separation between physics, rendering,
and object control (or AI). The physics engine moves object according to the
forces that act upon them, and the object controllers can influence these
forces from any computer according to the objects abilities.

Ideally, every object in the simulation will be remote controlled from a
different computer, virtual machine, or at least a separate process on a single
computer. The programming language does not matter.

This is in stark contrast to contemporary game engines which usually prescribe
the programming language and your controllers/AI have to compete for computing
resources.

The goal is to eventually make the physics engine itself scalable across
multiple computers to simulate worlds of unprecedented size, detail, and
accuracy. All hail cloud computing :)

Why do I bother? Because in a virtual world that behaves reasonably similar to
the real world I can have my own space shuttle, design a sub-marine, invent my
own Mars rover and test its navigation abilities on a fictitious terrain, or
build a fully automated port. And so can you. No job at NASA required.


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


Help Wanted
===========

The project spans a multitude of technologies and challenges: ZeroMQ, RabbitMQ,
MongoDB, OpenGL (via PyQt), Websockets, Tornado, Python, Cython, some C++
around Bullet, Sphinx documentation, 3D models that can be distributed via
GitHub without violating any licenses, and more. The skill threshold is rather
low for almost all components since they are ludicrously primitive for now.


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

To also test the OpenGL viewer you will need a GPU that supports OpenGL 3.x (if
you bought it in the last 2 years GPU it probably does). 

.. code-block:: bash

   sudo apt-get install python3-opengl libglu1-mesa-dev python3-pyside.qtopengl
   ./start.py

One day it would be nice if you could simply use the browser. The Websocket
interface in in place but JavaScript is not my forte...

License
=======

Azrael is licensed under the terms of the AGPL v3.
