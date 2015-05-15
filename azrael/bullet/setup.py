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

    :param str tarball: Bullet archive, eg. 'bullet-2.82-r2704.tgz'.
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
        os.chdir('bullet-2.82-r2704')
        cmd = [
            'cmake', '.', '-G', 'Unix Makefiles',
            '-DCMAKE_INSTALL_PREFIX:PATH={libdir}',
            '-DINCLUDE_INSTALL_DIR:PATH={libdir}/include/bullet',
            '-DBUILD_DEMOS:BOOL=0',
            '-DBUILD_CPU_DEMOS:BOOL=0',
            '-DCMAKE_BACKWARDS_COMPATIBILITY:STRING=2.4',
            '-DLIB_DESTINATION:STRING={libdir}/lib/',
            '-DPKGCONFIG_INSTALL_PREFIX:STRING={libdir}/lib/pkgconfig/',
            '-DBUILD_SHARED_LIBS=ON',
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

    :return: path to Bullet tarball, eg '/opt/bullet/bullet-2.82-r2704.tgz'
    """
    # Name of tarball.
    tarball = 'bullet-2.82-r2704.tgz'

    # Absolute path to tarball.
    tarball_abs = os.path.join(os.getcwd(), tarball)

    # Do not download if it already exists.
    if os.path.exists(tarball_abs):
        print('Tarball <{}> already downloaded'.format(tarball))
        return tarball_abs

    # Download the Bullet tarball.
    cmd = ['wget', 'https://bullet.googlecode.com/files/' + tarball]
    print('Downloading Bullet: ', cmd)
    ret = subprocess.call(cmd)
    if ret != 0:
        print('Error downloading Bullet - abort')
        sys.exit(1)

    # Sanity check.
    assert os.path.exists(tarball_abs)

    # Return the absolute path to the just download tarball.
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

    # Path where the Bullet libraries and headers should be installed.
    dir_prefix = os.path.dirname(os.path.abspath(__file__))
    dir_prefix = os.path.join(dir_prefix, 'bulletlib')

    # If 'cleanall' was provided then delete the Bullet library.
    if 'cleanall' in sys.argv:
        print('Removing Bullet library directory <{}>'.format(dir_prefix))
        shutil.rmtree(dir_prefix, ignore_errors=True)

        tmp = './build/'
        print('Removing azBullet build directory <{}>'.format(tmp))
        shutil.rmtree(tmp, ignore_errors=True)

        tmp = '{}.egg-info'.format(libname)
        print('Removing egg directory <{}>'.format(tmp))
        shutil.rmtree(tmp, ignore_errors=True)

        # Remove Cython generated cpp file.
        subprocess.call('rm {}.cpp'.format(libname), shell=True)

        # It is necessary to remove the 'cleanall' argument because distutils
        # will otherwise complain about an 'unknown argument'. In this case, we
        # will replace it with a 'clean' argument to force distutils to also
        # clean up.
        sys.argv.remove('cleanall')
        if 'clean' not in sys.argv:
            sys.argv.append('clean')

    # If the extension module was build with
    #   >> python setup.py build_ext --inplace
    # then there will be a dynamic library next to the pyx file - delete it.
    if 'clean' in sys.argv:
        subprocess.call('rm {}.cpython-*.so'.format(libname), shell=True)

    # Build the Bullet library if it does not yet exist AND the user did not
    # specify the 'clean' option.
    if ('clean' not in sys.argv) and (not os.path.exists(dir_prefix)):
        # Attempt to compile the Bullet library.
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

    # Let distutils Extension function take care to specify all the compiler
    # options.
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
