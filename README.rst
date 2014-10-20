======
Azrael
======

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

The cornerstone of Azrael is the clean separation of physics, object control
(or AI), and rendering. The physics engine moves object according to the 
forces acting upon them, the object controllers can send commands to force
generators (eg booster) via the network, and the rendering engine can query the
simulation to visualise it.

Ideally, every object in the simulation will be remote controlled from a
different computer, virtual machine, or at least a separate process on a single
computer. The programming language does not matter as long as it has ZeroMQ
bindings.

This is in stark contrast to contemporary game engines which usually prescribe
the programming language and your controllers/AI have to compete for CPU and
memory.

The goal is to eventually make the physics engine itself scalable across
multiple computers to simulate worlds of unprecedented size, detail, and
accuracy. All hail cloud computing :)

Why do I bother? Because in a reasonably realistic virtual world
I can have my own space shuttle, design my own sub-marine,
invent my own Mars rover with awesome navigation abilities on a fictitious
terrain or build an automated fleet of space ships. And so can you. No job at
NASA required.

How It (Might) Work
===================

Classical Physics engines assume they run on a single computer, which means
data access is fast/free and the number of CPU cores is limited. In the Cloud
it is the other way around. Beating the network latency and designing a loosely
coupled system that nevertheless produces coherent physics are the two major
challenges.

My current idea to meet these challenges, without re-inventing more wheels than
necessary, is

* compile potential collision sets (broadphase) in Azrael,
* send each set to the next available Worker for processing,
* wait until all sets have been updated in a central database.

The Workers are little more than standard Physics Engines (currently Bullet)
with some wrapper code to interface with Azrael.

Can this even work? It already does. Is it anywhere near real time: not yet.

Please drop me a line if you have any questions or suggestions.


Project Status
==============

Azrael currently features a basic API to upload meshes, define force generators
(mimics eg boosters wheels, etc), send commands to these force generators, and
query the scene in general (for rendering).

It also ships with two simple viewers to visualise the scene. One is a
standalone PyQT/OpenGL program, the other uses JavaScript and runs in a
browser.


Installation
============

From Source
-----------
On Ubuntu 14.04 you can install Azrael and all required support libraries with
the following commands:

.. code-block:: bash

   git clone https://github.com/olitheolix/azrael
   cd azrael
   sudo bash install.sh
   python3 start.py --noviewer --numcubes 4,4,1

Docker
------

.. code-block:: bash

   docker run -p 8080:8080 -ti "olitheolix/azrael:v0.1"


View the Scene
--------------

Go to http://localhost:8080 once Azrael is up and running (may take a minute or
two if you use a Docker container). Firefox will work out of the box. Chrome
will work if you enable experimental JavaScript first (browse to chrome://flags
for the respective option). Other browser may work as well.

Use the WASD keys to fly through the scene, or navigate with the mouse
while pressing the left button.

To see some action in the scene run one (or several) of the demo controllers in
a separate shell. For instance,

.. code-block:: bash

    python3 controllers/demo_sphere.py 

will send commands to the sphere's boosters to make it spin and accelerate into
the wall of cubes, whereas

.. code-block:: bash

    python3 controllers/demo_swarm.py 

will send commands to the cubes' boosters and make them move out in a
semi-orderly fashion.

License
=======

Azrael is licensed under the terms of the AGPL v3.
