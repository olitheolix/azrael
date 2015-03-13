=========
Tutorials
=========

A learning-by-doing introduction to using Azrael.

The basic workflow to "get stuff moving" is this:

Spawn Azrael Stack -> Define Templates -> Spawn Templates -> Send Commands ->
Visualise

What follows are a few simple tutorials to illustrate these steps.


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
   :width: 640px
   :align: center
   

Create a Template and Spawn Two Objects From It
===============================================

To fill the empty scene we are now going to add an object. Adding objects is a
two step process. First, we need a template for that object and upload it to
Azrael. Second, we need to spawn an instance of that template (we can spawn as
many instances of the same template as we like).

Here is the complete code if you want to try it out immediately. It introduces
quite a few new functions, some of which I will explain below.

.. literalinclude:: tutorials/tut_3_1.py
   :language: python
   :emphasize-lines: 28, 33
   :linenos:

This time if you browse to http://localhost:8080 you will see two cubes
floating in space.

.. figure::  images/tut_3_1.jpg
   :width: 640px
   :align: center
   
By the way, you can also fly through the scene with your mouse. Use the left
mouse button to navigate, and the other two to move forwards and backwards.


Object With Boosters
====================

This is similar to the previous example, but this time the template will gain a
`Booster` to move and control it.

A booster in Azrael is merely a fixed point on the object at which you can
apply a force. The direction of the force matches the orientation of the
booster. That orientation must be specified when the booster is defined in the
template. However, the boosters move and rotate with the object.

For this example we add a single bootster to the template, create one instance
of that template, and apply random force values. The net effect is a cube that
will move somewhat erratically, but only along the *x*-axis since this is how
the booster is oriented.

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

