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


Philosophy
==========

The cornerstone of Azrael is the clean separation of physics, object control
(or AI), and rendering. The physics engine moves object accordings to the 
forces acting upon them, the clients control the forces via the network,
and the rendering engine queries the simulation to visualise it.

Why do I bother? Because in a reasonably realistic virtual world I can have my
own space shuttle, design my own sub-marine, invent my own autonomous Mars
rover, launch my own Rosetta mission, design my own reusable rocket, or build
my own automated fleet of space ships. And so can you. No job at NASA required.


Architecture
============

Azrael is still in a proof-of-concept stage but the following architecture is
already in place.

.. figure:: images/Architecture.png
   :width: 50em
   :align: center

In this figure *every* block is an independent micro service, and *every* array
is a network connection. In other words, every block can run a different
machine.

Azrael provides two interfaces types: ZeroMQ and HTTP (Websockets). Both have
the exact same feature set as the HTTP server.

ZeroMQ clients connect to a `Clerk` instance, whereas web clients connect to
`Clacks` (a Tornado server) which relays all commands to `Clerk`.

`Clerk` is the centerpiece in managing all the information in and out of
Azrael. In particular it has access to the template database, the instance
database (i.e. spawned templates), and their physics state (eg position and
velocity). It is also the one and only interface to the physics engine
`Leonard` and responsible for sanitising all input data for it.

`Leonards` is responsible for the rigid body physics and runs decoupled from
the rest of Azrael. It traverses several steps. First it checks if `Clerk` has
enqueued any new commands and process them. Then it partitions the world into
collision sets (broadphase step for those familiar with physics engines) and
sends them to `Physics Workers` for processing.

The `Workers` are independent, self contained processes possibly running on one
or more computers in a network. They can only be reached via the network and
wrap a `Bullet <http://bulletphysics.org/>`_ instance to progress the
physics. Once they have a result they write that back into the `State
Variables` database and request the next job.

Once all jobs are completed `Leonard` will refresh its internal cache from the
`State Variables` database and start over again, eg. check the command queue,
partition the world, distributed the partitions to the Workers, and wait for
the results.

This approach to computing physics is certainly fraught with plenty of network
communication overhead. However, if it works (and it looks like it does) then
the physics engine will *scale*. Sure, if you have one big object cluster that
cannot be partitioned at all then this architectures will also not help because
a single `Worker` has to do it all, but you have many smaller clusters then
there is no realy limit to how complex the overall simulation can be... and I
bet there is also a scalable solution for large clusters...


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
