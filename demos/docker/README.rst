This directory contains docker-compose files to run pre-packaged demos.

For instance, to launch the Asteroids demo and view the result in Firefox:

.. code-block:: bash

    >> docker-compose -f asteroids_autopilot.yml up
    >> firefox localhost:8080
