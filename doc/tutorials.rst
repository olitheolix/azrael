=========
Tutorials
=========

A learning-by-doing introduction to using Azrael. Here is the basic workflow to
create-, interact-, and generall "get stuff moving" in Azrael.

.. figure::  images/Workflow.png
   :width: 50em
   :align: center

The following tutorials illustrate the individual steps in sufficient detail to
get started.


Start- and Stop Azrael
======================

This first tutorial shows how to start and stop Azrael.

Azrael consists of several loosly coupled processes. All of these must be
running before it does anything useful. The easiest way to not re-invent the
wheel here - it is just bolier plate code after all - is to reuse the
code from the demos.

Let's get started. Create a file `tut_1.py` somewhere with the following
content:

.. literalinclude:: tutorials/tut_1_1.py
   :language: python
   :emphasize-lines: 28, 33
   :linenos:

All this does is start Azrael, keep it running for a few seconds, then shut it
down again.

To run this demo execute the following commands:

.. code-block:: bash

   export PYTHONPATH='path-to-azrael-goes-here'
   python3 tut_1.py

On my machine this produces the following output (don't worry about what it
actually says):

.. code-block:: bash

    INFO - azrael.leonard.LeonardDistributedZeroMQ - myinfo
    INFO - azrael.clerk.Clerk - Attempt to bind <tcp://127.0.0.1:5555>
    INFO - azrael.clerk.Clerk - Listening on <tcp://127.0.0.1:5555>
    INFO - azrael.leonard.LeonardDistributedZeroMQ - Setup complete
    INFO - azrael.leonard.LeonardWorkerZeroMQ - Worker 1 connected
    INFO - azrael.leonard.LeonardWorkerZeroMQ - Worker 2 connected
    INFO - azrael.leonard.LeonardWorkerZeroMQ - Worker 3 connected

Admittedly, this demo is not very exciting in itself but a good sanity test
that everything works.


View The Scene (Empty)
======================

This tutorial slightly extends the previous so that we can view the scene. The
code itself is almost identical, except that it does not stop Azrael until we
press `<ctrl>-c`.

Create a new file called `tut_2.py` with the following content:

.. literalinclude:: tutorials/tut_2_1.py
   :language: python
   :emphasize-lines: 28, 33
   :linenos:

If you run this code and point your (recent version of Firefox/Chrome) browser
to http://localhost:8080 then you will see the scene. It should look like this:

.. figure::  images/tut_2_1.jpg
   :width: 100%
   :align: center
   

Create a Template and Spawn Two Objects From It
===============================================

To fill the empty scene we are now going to add an object. Adding objects is a
two step process:

* add a template for that object
* spawn (or more) instance of that template

Templates describe the object geometry, boosters, and other
properties:

.. figure::  images/Template.png
   :width: 50em
   :align: center

The boosters are of no concern in this tutorial, but the geometry fragments
are. Each object consists of one or more such fragments. Each has its own
triangle mesh, texture map, and UV coordinates (for mapping that texture to the
triangle vertices). There is no technical reason why any object needs more than
one fragment but it is often more convenient to break up a model into more
managable sub-model.

In this tutorial we will create a cube without any textures. Consequently, we
need to construct the triangle mesh that comprises the cube, and can pass empty
arrays for the UV- and RGB (texture) map.

Here is the complete code if you want to try it out immediately. It introduces
quite a few new functions, some of which I will explain below.

.. literalinclude:: tutorials/tut_3_1.py
   :language: python
   :emphasize-lines: 28, 33
   :linenos:

This time if you browse to http://localhost:8080 you will see two cubes
floating in space.

.. figure::  images/tut_3_1.jpg
   :width: 100%
   :align: center
   
By the way, you can also fly through the scene with your mouse. Use the left
mouse button to navigate, and the other two to move forwards and backwards.


Object With Boosters
====================

This is similar to the previous example except that we will no add a
booster. The sole purpose of having a booster is to exert force onto the object
which, in turn, allows us to control that object.

A booster in Azrael is an abstract concept. It does not have any geometry
attached to it but specifies the position on (or in) the object at which you
want to apply a force during the scene. Furthermore, it has a direction that
specifies the force direction.

In the next example we add one bootster to the template, spawn one object, and
apply a random force value every second. The net effect is a somewhat
erratically moving cube. Note that it will only move along the *x*-axis since
this is the booster direction.

.. literalinclude:: tutorials/tut_4_2.py
   :language: python
   :emphasize-lines: 28, 33
   :linenos:


Object State
============

TBA

* Spawn multiple objects with different masses
* Set them on a collision path
* Query their State Variables
* Modify their State Variables


Object Textures
===============

TBA

* Endow objects with a texture

