======
Azrael
======

A game engine for scientists, engineers, and enthusiasts.

Azrael is a proof-of-concept project where every object is subject to the laws
of physics and can be controlled via the network.

You can send commands to object parts, for instance the engines to accelerate
it. It is up to you whether you want to control these parts manually, or devise
an algorithm with the latest and greatest machine learning to automate it.

Unlike traditional game engines, the graphics engine, physics engine, and
object control (AI) are independent and will most likely not even run on the
same machine.

The API is language agnostic. Albeit written in Python, the data exchange is
pure JSON and the transport layer is either a Websocket (JavaScript/browsers)
or ZeroMQ (pretty much everything but JavaScript).

The `project page <https://olitheolix.com/azrael/>`_ contains a high level
overview. Interested programmers may find the
`Tutorial Section <https://olitheolix.com/azrael-doc/tutorials.html>`_ more
useful.

To find out what I am working on, check out my
`Trello Board <https://trello.com/b/3XJRlgt9>`_.

How and Why
===========

The cornerstone of Azrael is the clean separation of physics, object control
(or AI), and rendering. The physics engine moves object according to the 
applied forces. The API allows to  send commands via the network to
modify these forces and also to query the simulation.

Ideally, every object in the simulation will be remote controlled from a
different computer, virtual machine, or at least a separate process on a single
computer.

The goal is to eventually make the physics engine itself scalable across
multiple computers to simulate worlds of unprecedented size, detail, and
accuracy. All hail cloud computing :)

Why do I bother? Because in a reasonably realistic virtual world I can have my
own space shuttle, design my own sub-marine, invent my own Mars rover with
awesome navigation abilities, launch my own Rosetta mission, invent my own
reusable rocket ... no job at ESA, NASA or SpaceX required.

How It (Might) Works
===================

Classical Physics engines assume they run on a single computer, which means
data access is fast/free and the number of CPU cores is limited. In the Cloud
it is the other way around. Beating the network latency and designing a loosely
coupled system that nevertheless produces coherent physics are the major
challenges.

My current approach is as follows:

* compile potential collision sets (broadphase) in Azrael,
* send each set via the network to a Worker,
* wait until all sets have been computed.

The Workers are little more than standard Physics Engines (currently Bullet)
with some wrapper code to interface with Azrael.

Feel free to drop me a line if you have any questions or suggestions.


Project Status
==============

Azrael currently features a basic API to upload meshes, define boosters to
exert force, send commands to these boosters, and query the scene in
general (for rendering and object control).

It also ships with two simple viewers. One is a standalone PyQT/OpenGL program,
whereas the other uses JavaScript and runs in a browser.


Installation
============

From Source
-----------
Azrael requires Python 3.4 or higher. To use the source code you must have

* `Anaconda <https://store.continuum.io/cshop/anaconda/>`_ installed and
  'conda' in your path,
* a running MongoDB instance (listening on its default port 27017),
* (K)Ubuntu 14.04 or 15.04 (but should work on other Debian based systems as
  well).

.. code-block:: bash

   git clone https://github.com/olitheolix/azrael
   cd azrael
   sudo apt-get install build-essential cmake git libassimp-dev wget

   # Create the Anaconda environment 'azrael' and compile the extension modules.
   ./create_anaconda_env.sh

   # Activate the environment, run the tests, and start the demo.
   source activate azrael
   py.test -x
   python demos/demo_default.py --noviewer --cubes 4,4,1

See `Viewing the Scene in the Browser`_ for details on how to visualise the demo.


Docker
------
To try the demo without installing source code you will need `Docker
<http://www.docker.com/>`_ and
`Docker-Compose<https://docs.docker.com/compose/>`_.

.. code-block:: bash

   wget https://github.com/olitheolix/azrael/raw/master/docker-compose.yml
   docker-compose up

See next section for details on how to visualise the demo.


Viewing the Scene in the Browser
--------------------------------

You will need a recent version of Firefox or Chrome. Once Azrael is up you
can view the scene at http://localhost:8080.

Note: it may take a minute or two for the URL to come live the first time
because MongoDB may have to initialise its database first.

Use the WASD keys, or the mouse, to fly through the scene.


License
=======

Azrael is licensed under the terms of the AGPL v3.
