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
the real world I can have my own space shuttle, design my own sub-marine,
invent my own Mars rover with awesome navigation abilities on a fictitious
terrain. And so can you. No job at NASA required.


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
contemporary 3D rendering (maybe cloud based?), and a scalable physics engine
to create the largest Newtonian simulation on the planet...

Please drop me a line if you have any questions.


Installation
============

On Ubuntu 14.04 you can install and start the Azrael core like so:

.. code-block:: bash

   git clone https://github.com/olitheolix/azrael
   cd azrael
   sudo bash install.sh


Try It Out
==========

Start Azrael with

.. code-block:: bash

   python3 start.py --noviewer

Then point Firefox to http://localhost:8080 to render the scene. Chrome will
work as well if you turn on experimental JavaScript first (browse to
chrome://flags to enable it).

To see some movement run one of the demo controllers in a separate shell:

.. code-block:: bash

    python3 controllers/demo_sphere.py 

or

.. code-block:: bash

    python3 controllers/demo_swarm.py 


License
=======

Azrael is licensed under the terms of the AGPL v3.
