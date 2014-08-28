# Copyright 2014, Oliver Nagy <olitheolix@gmail.com>
#
# This file is part of Azrael (https://github.com/olitheolix/azrael)
#
# Azrael is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# Azrael is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with Azrael. If not, see <http://www.gnu.org/licenses/>.

"""
OpenGL viewer for Azrael (Python 3 only).

You will need 'python3-pyside.qtopengl' and 'pyopengl'. On Ubuntu 14.04 you can
install them with the following commands:

  >> sudo apt-get install python3-pyside.qtopengl python3-opengl

"""

# Add the viewer directory to the Python path.
import os
import sys
_this_directory = os.path.dirname(os.path.abspath(__file__))
p = os.path.join(_this_directory, '..')
sys.path.insert(0, p)
del p

import subprocess
import numpy as np
import model_import
import OpenGL.GL as gl

import azrael.wscontroller as wscontroller

from PySide import QtCore, QtGui, QtOpenGL


def perspective(fov, ar, near, far):
    """
    Return the perspective matrix.

    * ``fov``: field of view (radians, *not* degrees)
    * ``ar``: aspect ratio (ie. width / height)
    * ``near``: near clipping plane
    * ``far``: far clipping plane
    """
    fov = 1 / np.tan(fov / 2)
    mat = np.zeros((4, 4))
    mat[0, 0] = fov / ar
    mat[1, 1] = fov
    mat[2, 2] = (far + near) / (far - near)
    mat[2, 3] = -2 * far * near / (far - near)
    mat[3, 2] = 1
    return mat.astype(np.float32)


class Quaternion:
    """
    A Quaternion class.

    This class implements a sub-set of the available Quaternion
    algebra. The operations should suffice for most 3D related tasks.
    """
    def __init__(self, w=None, v=None):
        """
        Construct Quaternion with scalar ``w`` and vector ``v``.
        """
        # Sanity checks. 'w' must be a scalar, and 'v' a 3D vector.
        assert isinstance(w, float)
        assert isinstance(v, np.ndarray)
        assert len(v) == 3

        # Store 'w' and 'v' as Numpy types in the class.
        self.w = np.float64(w)
        self.v = np.array(v, dtype=np.float64)

    def __mul__(self, q):
        """
        Multiplication.

        The following combination of (Q)uaternions, (V)ectors, and (S)calars
        are supported:

        * Q * S
        * Q * V
        * Q * Q2

        Note that V * Q and S * Q are *not* supported.
        """
        if isinstance(q, Quaternion):
            # Q * Q2:
            w = self.w * q.w - np.inner(self.v, q.v)
            v = self.w * q.v + q.w * self.v + np.cross(self.v, q.v)
            return Quaternion(w, v)
        elif isinstance(q, (int, float)):
            # Q * S:
            return Quaternion(q * self.w, q * self.v)
        elif isinstance(q, (np.ndarray, tuple, list)):
            # Q * V: convert Quaternion to 4x4 matrix and multiply it
            # with the input vector.
            assert len(q) == 3
            tmp = np.zeros(4, dtype=np.float64)
            tmp[:3] = np.array(q)
            res = np.inner(self.toMatrix(), tmp)
            return res[:3]
        else:
            print('Unsupported Quaternion product.')
            return None

    def __repr__(self):
        """
        Represent Quaternion as a vector with 4 elements.
        """
        tmp = np.zeros(4, dtype=np.float64)
        tmp[:3] = self.v
        tmp[3] = self.w
        return str(tmp)

    def norm(self):
        """
        Norm of Quaternion.
        """
        return np.sqrt(self.w ** 2 + np.inner(self.v, self.v))

    def toMatrix(self):
        """
        Return the corresponding rotation matrix for this Quaternion.
        """
        # Shorthands.
        x, y, z = self.v
        w = self.w

        # Standard formula.
        mat = np.array([
            [1 - 2*y*y - 2*z*z, 2*x*y - 2*z*w, 2*x*z + 2*y*w, 0],
            [2*x*y + 2*z*w, 1 - 2*x*x - 2*z*z, 2*y*z - 2*x*w, 0],
            [2*x*z - 2*y*w, 2*y*z + 2*x*w, 1 - 2*x*x - 2*y*y, 0],
            [0, 0, 0, 1]])
        return mat.astype(np.float32)


class Camera:
    """
    A basic FPS camera.
    """
    def __init__(self):
        # Camera at origin...
        self.position = np.array([0, 0, 0], dtype=np.float64)

        # looking along positive z-direction...
        self.view = np.array([0, 0, 1], dtype=np.float64)

        # ... with its head up.
        self.up = np.array([0, 1, 0], dtype=np.float64)

        # This vector points to the right when viewed through
        # the camera, yet coincides with *negative* 'x' in world coordinates.
        self.right = np.cross(self.view, self.up)

        # Sensitivity; only used in the convenience methods moveForward,
        # moveBackward, strafeLeft, strafeRight.
        self.translationSensitivity = 0.2

        # Initial camera orientation.
        self.phi = 0
        self.theta = 0

    def cameraMatrix(self):
        """
        Return the camera matrix.
        """
        # Translation matrix.
        trans = np.eye(4)
        trans[:3, 3] = -self.position

        # Rotation matrix to undo the camera orientation.
        rot = np.zeros((4, 4))
        rot[:3, :3] = np.vstack((self.right, self.up, self.view))
        rot[3, 3] = 1

        # Combine the matrices into one.
        return np.dot(rot, trans)

    def rotate(self, left, up):
        """
        Convenience method: rotate the camera.

        The ``left`` and ``up`` values specify the horizontal- and
        vertical rotation (in radians).
        """
        self.phi += left
        self.theta += up

        # Compute the viewing direction (z-axis in camera space).
        self.view[0] = np.sin(self.phi) * np.cos(self.theta)
        self.view[1] = np.sin(self.theta)
        self.view[2] = np.cos(self.theta) * np.cos(self.phi)

        # Compute the left-vector (x-axis in camera space).
        self.right[0] = -np.cos(self.phi)
        self.right[1] = 0
        self.right[2] = np.sin(self.phi)

        # Compute the up-vector (y-axis in camera space) from the previous two
        # vectors.
        self.up = -np.cross(self.view, self.right)

    def moveForward(self):
        """
        Convenience method: move camera forward a bit.
        """
        self.position += self.translationSensitivity * self.view

    def moveBackward(self):
        """
        Convenience method: move camera backward a bit.
        """
        self.position -= self.translationSensitivity * self.view

    def strafeLeft(self):
        """
        Convenience method: strafe a bit to the left.
        """
        self.position -= self.translationSensitivity * self.right

    def strafeRight(self):
        """
        Convenience method: strafe a bit to the right.
        """
        self.position += self.translationSensitivity * self.right


class ViewerWidget(QtOpenGL.QGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Camera instance.
        self.camera = Camera()

        # Handle to shader program (will be set later).
        self.shaders = None

        # Place the window in the top left corner.
        self.setGeometry(0, 0, 640, 480)

        # Binary movement flags to indicate which keys are currently pressed.
        self.movement = {
            'forward': False,
            'backward': False,
            'left': False,
            'right': False}

        # Backup the current mouse position so that we can make it visible
        # again at the some position if the user chooses to use the mouse for
        # the desktop instead of the controlling the camera.
        self.lastMousePos = self.cursor().pos()

        # todo: find out how to keep the mouse inside the window.
        self.centerPos = self.width() // 2, self.height() // 2
        self.centerCursor()

        # If True, the mouse will control the camera instead of the cursor on
        # the desktop GUI.
        self.mouseGrab = False

        # Specify the field of view, aspect ratio, near- and far plane.
        self.fov = 45.0 * np.pi / 180.0
        self.aspect_ratio = 4 / 3
        self.near = 0.01
        self.far = 1000

        # Compute perspective matrix.
        self.matPerspective = perspective(self.fov, self.aspect_ratio,
                                          self.near, self.far)

        # The timer will re-start itself and trigger OpenGL updates.
        self.drawTimer = self.startTimer(500)

        # Frame counter. Mostly for debugging purposes.
        self.frameCnt = 0

    def getGeometryCube(self, pos=np.zeros(3)):
        buf_vert = 0.5 * np.array([
            -1.0, -1.0, -1.0,   -1.0, -1.0, +1.0,   -1.0, +1.0, +1.0,
            +1.0, +1.0, -1.0,   -1.0, -1.0, -1.0,   -1.0, +1.0, -1.0,
            +1.0, -1.0, +1.0,   -1.0, -1.0, -1.0,   +1.0, -1.0, -1.0,
            +1.0, +1.0, -1.0,   +1.0, -1.0, -1.0,   -1.0, -1.0, -1.0,
            -1.0, -1.0, -1.0,   -1.0, +1.0, +1.0,   -1.0, +1.0, -1.0,
            +1.0, -1.0, +1.0,   -1.0, -1.0, +1.0,   -1.0, -1.0, -1.0,
            -1.0, +1.0, +1.0,   -1.0, -1.0, +1.0,   +1.0, -1.0, +1.0,
            +1.0, +1.0, +1.0,   +1.0, -1.0, -1.0,   +1.0, +1.0, -1.0,
            +1.0, -1.0, -1.0,   +1.0, +1.0, +1.0,   +1.0, -1.0, +1.0,
            +1.0, +1.0, +1.0,   +1.0, +1.0, -1.0,   -1.0, +1.0, -1.0,
            +1.0, +1.0, +1.0,   -1.0, +1.0, -1.0,   -1.0, +1.0, +1.0,
            +1.0, +1.0, +1.0,   -1.0, +1.0, +1.0,   +1.0, -1.0, +1.0])

        N = 3
        M = len(buf_vert) // N
        buf_vert = np.reshape(buf_vert, (M, N)) + pos
        return buf_vert.flatten()

    def loadGeometry(self):
        ok, all_ids = self.ctrl.getAllObjectIDs()

        for ctrl_id in all_ids:
            # Do not add anything if we already have the object.
            if ctrl_id in self.controllers:
                continue

            # Query the template ID associated with ctrl_id.
            ok, templateID = self.ctrl.getTemplateID(ctrl_id)
            if not ok:
                continue

            # Query the object template.
            ok, buf_vert = self.ctrl.getGeometry(templateID)
            if not ok:
                continue

            # This is to mask a bug in Clacks: newly spawned objects can become
            # active before their geometry hits the DB. Since this viewer
            # script does not check if the geometry has changed it may get an
            # empty geometry first and then never check again.
            if len(buf_vert) == 0:
                continue

            # Add to set.
            self.controllers.add(ctrl_id)

            # GPU needs float32 values.
            buf_vert = buf_vert.astype(np.float32)

            # Store the number of vertices.
            self.numVertices[ctrl_id] = len(buf_vert) // 3

            # Create random colors for every vertex; each color consists of
            # four float32 values that denote RGBA, respectively.
            buf_col = np.random.rand(4 * self.numVertices[ctrl_id])
            buf_col = buf_col.astype(np.float32)

            # Create a new VAO (Vertex Array Object) and bind it. All GPU
            # buffers created below can then be activated at once by binding
            # this VAO (see paintGL).
            self.vertex_array_object[ctrl_id] = gl.glGenVertexArrays(1)
            gl.glBindVertexArray(self.vertex_array_object[ctrl_id])

            # Create two GPU buffers (no need to specify a size here).
            vertexBuffer, colorBuffer = gl.glGenBuffers(2)

            # Copy the vertex data to the first GPU buffer.
            gl.glBindBuffer(gl.GL_ARRAY_BUFFER, vertexBuffer)
            gl.glBufferData(gl.GL_ARRAY_BUFFER, buf_vert, gl.GL_STATIC_DRAW)

            # Associate the vertex buffer with the Layout 0 variable in the
            # shader (see 'passthrough.vs') and specify its layout. Then enable
            # the buffer to ensure the GPU will draw it.
            gl.glVertexAttribPointer(0, 3, gl.GL_FLOAT, gl.GL_FALSE, 0, None)
            gl.glEnableVertexAttribArray(0)

            # Repeat with color data. Each vertex gets a color, specified in
            # terms of RGBA values (each a float32).
            gl.glBindBuffer(gl.GL_ARRAY_BUFFER, colorBuffer)
            gl.glBufferData(gl.GL_ARRAY_BUFFER, buf_col, gl.GL_STATIC_DRAW)

            # Color data is associated with Layout 1 (first parameter), has
            # four elements per vertex (second parameter), and each element is
            # a float32 (third parameter). The other three parameters are of no
            # interest here.
            gl.glVertexAttribPointer(1, 4, gl.GL_FLOAT, gl.GL_FALSE, 0, None)
            gl.glEnableVertexAttribArray(1)

            # Only draw visible triangles.
            gl.glEnable(gl.GL_DEPTH_TEST)
            gl.glDepthFunc(gl.GL_LESS)
            print('Added geometry for <{}>'.format(ctrl_id))

    def initializeGL(self):
        """
        Create the graphic buffers and compile the shaders.
        """
        # Make sure the system is live.
        try:
            self.ctrl = wscontroller.WSControllerBase(
                'ws://127.0.0.1:8080/websocket')
        except ConnectionRefusedError as err:
            print('Viewer: could not connect to Clacks')
            self.close()
            sys.exit(1)
            return

        if not self.ctrl.pingClerk():
            print('Viewer: could not ping Clerk')
            self.close()
            sys.exit(1)
            return
        print('Client connected')

        # Create a projectile object. The collision shape is a cube (hence the
        # 'cs[0] = 4' statement).
        buf_vert = self.getGeometryCube()
        cs = np.ones(4, np.float64)
        cs[0] = 4
        templateID = 'cube'.encode('utf8')
        ok, _ = self.ctrl.addTemplate(templateID, cs, buf_vert, [], [])
        if not ok:
            print('Could not add new object template')
            self.close()
        else:
            self.cube_id = templateID
            print('Created ID <{}>'.format(self.cube_id))

        # Spawn a cube (templateID=3 defaults to one).
        ok, tmp = self.ctrl.spawn(
            'Echo'.encode('utf8'), self.cube_id, np.zeros(3), np.zeros(3))
        if not ok:
            print('Cannot spawn object (<{}>)'.format(tmp))
            self.close()
        else:
            self.player_id = tmp
            del tmp
        print('Spawned object <{}>'.format(self.player_id))

        self.controllers = set()
        self.numVertices = {}
        self.vertex_array_object = {}

        # Background color.
        gl.glClearColor(0, 0, 0, 0)
        self.shaders = self.linkShaders(_this_directory + '/passthrough.vs',
                                        _this_directory + '/passthrough.fs')

        # Activate the shader to obtain handles to the global variables defined
        # in the vertex shader.
        gl.glUseProgram(self.shaders)
        tmp1 = 'projection_matrix'.encode('utf8')
        tmp2 = 'model_matrix'.encode('utf8')
        self.h_prjMat = gl.glGetUniformLocation(self.shaders, tmp1)
        self.h_modMat = gl.glGetUniformLocation(self.shaders, tmp2)

    def paintGL(self):
        """
        Paint the OpenGL scene.

        Qt calls this method whenever it needs re-painting (eg. window
        movement), or when the updateGL() method was called somewhere
        explicitly. In this script we use a timer to periodically trigger the
        updateGL() method for a smooth viewing experience.
        """
        # Update the position/orientation of the camera depending on the
        # currently pressed keys and mouse position.
        self.updateCamera()

        # Load the geometry of newly added objects.
        self.loadGeometry()

        # --------------------------------------------------------------------
        # Draw the scene.
        # --------------------------------------------------------------------
        # Clear the scene.
        gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)

        for ctrl_id in self.controllers:
            # Activate the VAO and shader program.
            gl.glBindVertexArray(self.vertex_array_object[ctrl_id])
            gl.glUseProgram(self.shaders)

            # Query the object's position to construct the model matrix.
            ok, sv = self.ctrl.getStateVariables(ctrl_id)
            if not ok:
                continue
            sv = sv[ctrl_id]

            # Build the scaling matrix.
            scale_mat = sv.scale * np.eye(4)
            scale_mat[3, 3] = 1

            # Convert the Quaternion into a rotation matrix.
            q = sv.orientation
            rot_mat = Quaternion(q[3], q[:3]).toMatrix()
            del q

            # Build the model matrix.
            model_mat = np.eye(4)
            model_mat[:3, 3] = sv.position
            model_mat = np.dot(model_mat, np.dot(rot_mat, scale_mat))

            # Compute the combined camera- and projection matrix.
            cameraMat = self.camera.cameraMatrix()
            matVP = np.array(np.dot(self.matPerspective, cameraMat))

            # The GPU needs 32bit floats.
            model_mat = model_mat.astype(np.float32)
            model_mat = model_mat.flatten(order='F')
            matVP = matVP.astype(np.float32)
            matVP = matVP.flatten(order='F')

            # Upload the model- and projection matrices to the GPU.
            gl.glUniformMatrix4fv(self.h_modMat, 1, gl.GL_FALSE, model_mat)
            gl.glUniformMatrix4fv(self.h_prjMat, 1, gl.GL_FALSE, matVP)

            # Draw all triangles, and unbind the VAO again.
            gl.glDrawArrays(gl.GL_TRIANGLES, 0, self.numVertices[ctrl_id])
            gl.glBindVertexArray(0)

    def resizeGL(self, width, height):
        """
        Qt will call this if the viewport size changes.
        """
        gl.glViewport(0, 0, width, height)

    def compileShader(self, fname, shader_type):
        """
        Compile the ``shader_type`` stored in the file ``fname``.
        """
        shader = gl.glCreateShader(shader_type)
        gl.glShaderSource(shader, open(fname).read())
        gl.glCompileShader(shader)

        # Check for shader compilation errors.
        result = gl.glGetShaderiv(shader, gl.GL_COMPILE_STATUS)
        if result == 0:
            raise RuntimeError(gl.glGetShaderInfoLog(shader))
        return shader

    def linkShaders(self, vertex_shader, fragment_shader):
        """
        Compile- and link the vertex- and fragment shader.
        """
        # Compile the shaders.
        vs = self.compileShader(vertex_shader, gl.GL_VERTEX_SHADER)
        fs = self.compileShader(fragment_shader, gl.GL_FRAGMENT_SHADER)

        # Link shaders into a program.
        program = gl.glCreateProgram()
        gl.glAttachShader(program, vs)
        gl.glAttachShader(program, fs)
        gl.glLinkProgram(program)

        # Check for linking errors.
        result = gl.glGetProgramiv(program, gl.GL_LINK_STATUS)
        if result == 0:
            raise RuntimeError(gl.glGetProgramInfoLog(program))
        return program

    def updateCamera(self):
        """
        Translate and rotate the camera depending on the currently pressed keys
        and move position.
        """
        # Move the camera position depending on the currently pressed keys.
        if self.movement['forward']:
            self.camera.moveForward()
        if self.movement['backward']:
            self.camera.moveBackward()
        if self.movement['right']:
            self.camera.strafeRight()
        if self.movement['left']:
            self.camera.strafeLeft()

        pos = self.camera.position
        pos = pos + 30 * self.camera.view
        self.ctrl.suggestPosition(self.player_id, pos)

        # Do not update the camera rotation if the mouse is not grabbed.
        if not self.mouseGrab:
            return

        # Get current cursor position.
        c = self.cursor()
        xpos, ypos = c.pos().x(), c.pos().y()

        # Convert mouse offset from default position to left/up rotation, then
        # reset the cursor to its default position.
        sensitivity = 0.003
        up = sensitivity * (self.centerPos[1] - ypos)
        left = sensitivity * (self.centerPos[0] - xpos)
        self.centerCursor()

        # Rotate the camera.
        self.camera.rotate(left, up)

    def centerCursor(self):
        """
        Place the cursor in the pre-defined center position.
        """
        c = self.cursor()
        center = QtCore.QPoint(*self.centerPos)
        c.setPos(center)
        c.setShape(QtCore.Qt.BlankCursor)
        self.setCursor(c)

    def keyPressEvent(self, key):
        """
        Qt will call this if a key was pressed.

        This method will simply set the corresponding movement flags, which
        will be used in the painGL method to actually update the camera
        position and orientation.
        """
        # Convert input to a string character. Qt will sometimes lump
        # characters together if they arrive quicker than the event loop can
        # call this event handler (eg. if you keep pressing 'e' the key.text()
        # function may return 'eee'). To ensure everything works as expected,
        # use cut off the excess characters.
        char = key.text()
        if len(char) > 1:
            char = char[0]
        if char == 'e':
            self.movement['forward'] = True
        elif char == 'd':
            self.movement['backward'] = True
        elif char == 'f':
            self.movement['right'] = True
        elif char == 's':
            self.movement['left'] = True
        elif key.key() == QtCore.Qt.Key_Return:
            self.mouseGrab = not self.mouseGrab
            c = self.cursor()
            if self.mouseGrab:
                self.lastMousePos = c.pos()
                self.centerCursor()
                c.setShape(QtCore.Qt.BlankCursor)
            else:
                c.setPos(self.lastMousePos)
                c.setShape(QtCore.Qt.ArrowCursor)
            self.setCursor(c)
            del c
        elif char == 'q':
            self.close()
        else:
            print('Unknown key <{}>'.format(key.text()))

    def keyReleaseEvent(self, key):
        """
        Triggered by Qt when a key is released.

        This method unsets the flag set by ``keyPressEvent``.
        """
        char = key.text()
        if char == 'e':
            self.movement['forward'] = False
        elif char == 'd':
            self.movement['backward'] = False
        elif char == 'f':
            self.movement['right'] = False
        elif char == 's':
            self.movement['left'] = False
        else:
            pass

    def mousePressEvent(self, event):
        button = event.button()
        if button == 1:
            pos = self.camera.position
            vel = 2 * self.camera.view

            ok, ctrl_id = self.ctrl.spawn(
                'Echo'.encode('utf8'), self.cube_id, pos, vel=vel,
                scale=0.25, imass=20)
            if not ok:
                print('Could not spawn Echo (<{}>)'.format(ctrl_id))
                return
        elif button == 2:
            pos = self.camera.position
            vel = 0.5 * self.camera.view

            ok, ctrl_id = self.ctrl.spawn(
                'EchoBoost'.encode('utf8'), self.cube_id, pos, vel=vel,
                scale=1, imass=1)
            if not ok:
                print('Could not spawn EchoBoost (<{}>)'.format(ctrl_id))
                return
        else:
            print('Unknown button <{}>'.format(button))

    def timerEvent(self, event):
        """
        Periodically call updateGL to process mouse/keyboard events and
        update the scene.
        """
        self.killTimer(event.timerId())
        self.drawTimer = self.startTimer(20)
        self.updateGL()
        self.frameCnt += 1


def main():
    # Boiler plate for Qt application.
    app = QtGui.QApplication(['Viewer 3D'])
    widget = ViewerWidget()
    widget.show()
    app.exec_()


if __name__ == '__main__':
    main()
