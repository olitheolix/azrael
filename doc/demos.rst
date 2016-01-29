Demo Videos
===========

The videos below were recorded on my local compouter with Azrael running on an
AWS `c4.large` instance. The ping from my computer to AWS was ~15ms. All videos
were sped up for viewing convenience.

.. note:: the videos show a fairly old version of Azrael. The principles are
   still the same but the commands shown in the videos are not. For a more up
   to date live demo please take a look at the
   `PyCon Australia 2015 <https://youtu.be/JG8-yurFBXM?list=PLs4CJRBY5F1IZYVBLXGX1DRYXHMjUjG8k>`_
   or try the latest demos yourself.


Scene Rendering with Qt- And Browser Client
-------------------------------------------

The Qt- and browser based viewers stay in sync via Azrael.

.. raw:: html

    <video autoplay="autoplay" loop="loop" width="100%">
      
      <source src="https://s3-ap-southeast-2.amazonaws.com/olitheolix/azrael/bothviewers.mp4" type="video/mp4" />
      <source src="https://s3-ap-southeast-2.amazonaws.com/olitheolix/azrael/bothviewers.ogv" type="video/ogg" />
      <source src="https://s3-ap-southeast-2.amazonaws.com/olitheolix/azrael/bothviewers.webm" type="video/ogg" />
      Your browser does not support the video tag.
    </video>
    <p>


Control A Sphere
----------------
The sphere has three engines (left, middle, right). The engines themselves are
currently invisible because I am a lousy mesh designer. Nevertheless, they can
exert forces onto the sphere.

To control those engines, and by implication the sphere, we send commands
to them via the Python script seen in the demo. The net effect is that the
sphere accelerates forwards and picks up spin.

.. raw:: html

    <video autoplay="autoplay" loop="loop" width="100%">
      <source src="https://s3-ap-southeast-2.amazonaws.com/olitheolix/azrael/sphere.mp4" type="video/mp4" />
      <source src="https://s3-ap-southeast-2.amazonaws.com/olitheolix/azrael/sphere.ogv" type="video/ogg" />
      <source src="https://s3-ap-southeast-2.amazonaws.com/olitheolix/azrael/sphere.webm" type="video/ogg" />
      Your browser does not support the video tag.
    </video>
    <p>


Control The Cubes
-----------------
This is similar to the previous demo except that this time the Python script
sends control commands to the engines of the cubes.

.. raw:: html

    <video autoplay="autoplay" loop="loop" width="100%">
      <source src="https://s3-ap-southeast-2.amazonaws.com/olitheolix/azrael/swarm.mp4" type="video/mp4" />
      <source src="https://s3-ap-southeast-2.amazonaws.com/olitheolix/azrael/swarm.ogv" type="video/ogg" />
      <source src="https://s3-ap-southeast-2.amazonaws.com/olitheolix/azrael/swarm.webm" type="video/ogg" />
      Your browser does not support the video tag.
    </video>
    <p>


Force Grid
----------
Every simulation supports a spatial force grid which applies to all
objects. With this you can simulate global effects like free space (all values
are zero), gravity (constant value every where), or turbulence likes wind.

This demo in particular alternates the grid values between two
states. The first induces a circular motion, the second pulls all cubes to the
center. However, the effect is spatially limited, which is why some cubes
eventually escape.

.. raw:: html

    <video autoplay="autoplay" loop="loop" width="100%">
      <source src="https://s3-ap-southeast-2.amazonaws.com/olitheolix/azrael/tumbler.mp4" type="video/mp4" />
      <source src="https://s3-ap-southeast-2.amazonaws.com/olitheolix/azrael/tumbler.ogv" type="video/ogg" />
      <source src="https://s3-ap-southeast-2.amazonaws.com/olitheolix/azrael/tumbler.webm" type="video/ogg" />
      Your browser does not support the video tag.
    </video>
    <p>

Disclaimer: the support for spatial force fields is rudimentary at best and
only serves to explore the concept.


LIVE Demo
---------

I do not maintain a 24/7 live demo because running a c4 instance is expensive.
However, if you feel lucky today then point your Firefox or Chrome 
`click here <http://54.66.206.238:8080>`_ - maybe it is running today.

Alternatively, spin up a Linux instance on your favorite cloud, open ports 5555 and 8080,
and install Docker (Compose). Then launch the demo container as explained in the
`Readme <https://github.com/olitheolix/azrael>`_ file.
