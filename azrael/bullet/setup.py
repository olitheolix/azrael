# Copyright 2015, Oliver Nagy <olitheolix@gmail.com>
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
Build and test with:
  >> source conda_path/activate azrael
  >> python setup.py cleanall
  >> python setup.py build_ext --inplace

Hello world example:
  >> python hello.py

Unit test:
  >> py.test
"""
import os
import sys
import shutil
import tempfile
import subprocess
import numpy as np

from Cython.Build import cythonize
from distutils.core import setup, Extension


def compileBullet(tarball: str, libdir: str, double_precision: bool):
    """
    Compile Bullet as a shared library.

    This function will extract the ``tarball`` (must be tgz archive) into a
    temporary directory, compile it there, and place the results in ``libdir``.

    The ``double_precision`` flag specifies whether Bullet should use single-
    or double precision floats.

    ..note::
       No root privileges are requires, unless ``libdir`` is inaccessible to
       the user.

    :param str tarball: Bullet archive, eg. 'bullet3-2.83.5.tgz'.
    :param str libdir: directory where the library will be installed
    :param double_precision: whether to compile with 64Bit arithmetic or not.
    :return: None
    """
    with tempfile.TemporaryDirectory() as name:
        # Move to the temporary directory.
        try:
            os.chdir(name)
        except FileNotFoundError:
            print('Cannot change into temporary directory')
            sys.exit(1)

        # Unpack the tgz archive into the temporary directory.
        cmd = ['tar', '-xvzf', tarball]
        assert subprocess.call(cmd, stdout=subprocess.DEVNULL) == 0

        # Move into the newly created directory and generate the Makefiles. To
        # see more options I recommend to unpack the archive somewhere and then
        # run 'cmake-gui'.
        os.chdir('bullet3-2.83.5')
        cmd = [
            'cmake', '.', '-G', 'Unix Makefiles',
            '-DBUILD_BULLET2_DEMOS:BOOL=0',
            '-DBUILD_BULLET3:BOOL=0',
            '-DBUILD_CPU_DEMOS:BOOL=0',
            '-DBUILD_DEMOS:BOOL=0',
            '-DBUILD_OPENGL3_DEMOS:BOOL=0',
            '-DBUILD_SHARED_LIBS=ON',
            '-DBUILD_UNIT_TESTS:BOOL=0',
            '-DCMAKE_BACKWARDS_COMPATIBILITY:STRING=2.4',
            '-DCMAKE_INSTALL_PREFIX:PATH={libdir}',
            '-DINCLUDE_INSTALL_DIR:PATH={libdir}/include/bullet',
            '-DLIB_DESTINATION:STRING={libdir}/lib/',
            '-DPKGCONFIG_INSTALL_PREFIX:STRING={libdir}/lib/pkgconfig/',
            '-DUSE_GLUT:BOOL=0',
            '-DUSE_GRAPHICAL_BENCHMARK:BOOL=0',
        ]

        # Specify the precision flag.
        if double_precision:
            cmd.append('-DUSE_DOUBLE_PRECISION:BOOL=1')
        else:
            cmd.append('-DUSE_DOUBLE_PRECISION:BOOL=0')

        # Replace all occurrences of {libdir} in the 'cmd' strings with the
        # actual library path.
        cmd = [_.format(libdir=libdir) for _ in cmd]
        assert subprocess.call(cmd) == 0

        # Run 'make install -j' to build and install Bullet.
        cmd = ['make', '-j', 'install']
        assert subprocess.call(cmd) == 0


def getBulletTarball():
    """
    Return absolute path to Bullet tarball.

    :return: path to Bullet tarball, eg '/opt/bullet/bullet3-2.83.5.tgz'
    """
    # Name of tarball.
    tarball = 'bullet3-2.83.5.tgz'

    # Absolute path to tarball.
    tarball_abs = os.path.join(os.getcwd(), tarball)

    # Do not download if it already exists.
    if os.path.exists(tarball_abs):
        print('Tarball <{}> already downloaded'.format(tarball))
        return tarball_abs

    # Download the Bullet tarball.
    url = 'https://github.com/bulletphysics/bullet3/archive/2.83.5.tar.gz'
    cmd = ['wget', url, '-O' + tarball]
    print('Downloading Bullet: ', cmd)
    ret = subprocess.call(cmd)
    if ret != 0:
        print('Error downloading Bullet - abort')
        sys.exit(1)

    # Sanity check.
    assert os.path.exists(tarball_abs)

    # Return the absolute path to the just downloaded tarball.
    return tarball_abs


def main():
    """
    Compile Bullet, then compile the Cython extension.
    """
    # Specify the precision we would like to use.
    double_precision = True

    # Note: the name of the library *MUST* match the name of the pyx file. You
    # are also *NOT* allowed to rename the library file name once it was built!
    # If you do, Python will throw an error when importing the module.
    libname = 'azBullet'

    # Backup the current working directory because we will change it.
    cwd = os.getcwd()

    # Get absolute path to Bullet tarball (download if necessary).
    tarball = getBulletTarball()

    # Install path for Bullet library and its headers. The specific path
    # depends on whether we are building via an Anaconda recipe or just
    # for dev purposes on local host (in the latter case the '--inplace'
    # argument must be given for everything to compile and link properly).
    if os.getenv('CONDA_BUILD') == '1':
        dir_prefix = os.getenv('PREFIX')
        assert dir_prefix is not None
    else:
        dir_prefix = os.path.dirname(os.path.abspath(__file__))
        dir_prefix = os.path.join(dir_prefix, 'bulletlib')

    # If 'cleanall' was provided then delete the Bullet library.
    if 'clean' in sys.argv:
        print('rm -rf {}'.format(dir_prefix))
        shutil.rmtree(dir_prefix, ignore_errors=True)

        tmp = './build/'
        print('rm -rf {}'.format(tmp))
        shutil.rmtree(tmp, ignore_errors=True)

        tmp = '{}.egg-info'.format(libname)
        print('rm -rf {}'.format(tmp))
        shutil.rmtree(tmp, ignore_errors=True)

        # Remove the Cython generated cpp file.
        subprocess.call('rm -f {}.cpp'.format(libname), shell=True)

        # Delete the cpython extension module.
        subprocess.call('rm -f {}.cpython-*.so'.format(libname), shell=True)

        # Do not proceed any further because we are only cleaning up.
        return

    # Attempt to build the Bullet library.
    try:
        compileBullet(tarball, dir_prefix, double_precision)
    except Exception as err:
        raise err
    finally:
        # Whatever happens, make sure we get back to the original
        # directory.
        os.chdir(cwd)

    # If Bullet was compiled with double precision types then it is paramount
    # that all source files define the 'BT_USE_DOUBLE_PRECISION' macro.
    if double_precision:
        macros = [('BT_USE_DOUBLE_PRECISION', None)]
    else:
        macros = []

    # Let distutils' Extension function take care of the compiler options.
    ext = Extension(
        name=libname,
        sources=[libname + '.pyx'],
        include_dirs=[os.path.join(dir_prefix, 'include/bullet'),
                      np.get_include()],
        library_dirs=[os.path.join(dir_prefix, 'lib')],
        runtime_library_dirs=[os.path.join(dir_prefix, 'lib')],
        libraries=['BulletCollision', 'BulletDynamics', 'LinearMath'],
        define_macros=macros,
        extra_compile_args=['-Wall', '-Wextra', '-pedantic', '-std=c++11',
                            '-Wno-unused-parameter', '-Wno-unused-function',
                            '-Wno-unused-variable'],
        language='c++',
    )

    # Build the extension module.
    setup(
        name=libname,
        version='0.1',
        description='Bullet Wrapper for Azrael',
        author='Oliver Nagy',
        author_email='olitheolix@gmail.com',
        url='https://olitheolix.com/azrael',
        ext_modules=cythonize(ext),
    )


if __name__ == '__main__':
    main()
