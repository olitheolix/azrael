import time
import numpy as np
import azrael.startup
from azrael.types import Template, FragMeta, FragRaw, Booster
from azrael.types import CollShapeMeta, CollShapeSphere, RigidBodyData


def defineCube():
    """
    Return the vertices of a cubes with side length 1.

    Nothing interesting happens here.
    """
    vert = 0.5 * np.array([
        -1.0, -1.0, -1.0,   -1.0, -1.0, +1.0,   -1.0, +1.0, +1.0,
        -1.0, -1.0, -1.0,   -1.0, +1.0, +1.0,   -1.0, +1.0, -1.0,
        +1.0, -1.0, -1.0,   +1.0, +1.0, +1.0,   +1.0, -1.0, +1.0,
        +1.0, -1.0, -1.0,   +1.0, +1.0, -1.0,   +1.0, +1.0, +1.0,
        +1.0, -1.0, +1.0,   -1.0, -1.0, -1.0,   +1.0, -1.0, -1.0,
        +1.0, -1.0, +1.0,   -1.0, -1.0, +1.0,   -1.0, -1.0, -1.0,
        +1.0, +1.0, +1.0,   +1.0, +1.0, -1.0,   -1.0, +1.0, -1.0,
        +1.0, +1.0, +1.0,   -1.0, +1.0, -1.0,   -1.0, +1.0, +1.0,
        +1.0, +1.0, -1.0,   -1.0, -1.0, -1.0,   -1.0, +1.0, -1.0,
        +1.0, +1.0, -1.0,   +1.0, -1.0, -1.0,   -1.0, -1.0, -1.0,
        -1.0, +1.0, +1.0,   -1.0, -1.0, +1.0,   +1.0, -1.0, +1.0,
        +1.0, +1.0, +1.0,   -1.0, +1.0, +1.0,   +1.0, -1.0, +1.0
    ])
    return vert.tolist()


def createTemplate():
    # Create the vertices for a unit cube.
    vert = defineCube()

    # Define initial fragment size and position relative to rigid body.
    scale = 1
    pos, rot = (0, 0, 0), (0, 0, 0, 1)

    # Define the one and only geometry fragment for this template.
    data_raw = FragRaw(vert, [], [])
    frags = {'frag_foo': FragMeta('raw', scale, pos, rot, data_raw)}
    del scale, pos, rot

    # We will need that collision shape to construct the rigid body below.
    cs_sphere = CollShapeMeta(cstype='Sphere',
                              position=(0, 0, 0),
                              rotation=(0, 0, 0, 1),
                              csdata=CollShapeSphere(radius=1))

    # Create the rigid body.
    body = azrael.types.RigidBodyData(
        scale=1,
        imass=1,
        restitution=0.9,
        rotation=(0, 0, 0, 1),
        position=(0, 0, 0),
        velocityLin=(0, 0, 0),
        velocityRot=(0, 0, 0),
        cshapes={'foo_sphere': cs_sphere},
        axesLockLin=(1, 1, 1),
        axesLockRot=(1, 1, 1),
        version=0)

    # Compile and return the template.
    return Template('my_first_template', body, frags, {}, {})


def main():
    # Start the Azrael stack.
    az = azrael.startup.AzraelStack()
    az.start()

    # Instantiate a Client to communicate with Azrael.
    client = azrael.client.Client()

    # Verify that the client is connected.
    assert client.ping().ok

    # Create the template and send it to Azrael.
    template = createTemplate()
    assert client.addTemplates([template]).ok

    # Spawn two objects from the just added template. The only difference is
    # their position in space.
    spawn_param = [
        {'templateID': template.aid, 'rbs': {'position': [0, 0, -2]}},
        {'templateID': template.aid, 'rbs': {'position': [0, 0, 2]}},
    ]
    ret = client.spawn(spawn_param)
    assert ret.ok
    print('Spawned {} object(s). IDs: {}'.format(len(ret.data), ret.data))
    print('Point your browser to http://localhost:8080 to see them')

    # Wait until the user presses <ctrl-c>.
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        pass

    # Terminate the stack.
    az.stop()


if __name__ == '__main__':
    main()
