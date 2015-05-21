This directory contains the Cython wrapper for Bullet.

To compile this wrapper you will need Cython (and a compiler). Then type (no
root required):

  >> python setup.py build_ext --inplace

to build the extension module. To try it our run the 'hello.py' script. That
script mimics the Hello World demo shipped with Bullet itself.

The 'setup.py' script automatically downloads-, compiles, and installs the
Bullet library into a local sub-directory (azrael/bullet/bulletlib/*)

The 'setup.py' script will then proceed to compile the Cython wrapper and
produce an extension module called 'azBullet'. You can import this module like
any other Python module (ie 'import azBullet')

The 'azBullet' wrapper is not tied to Azrael and can be used as a standalone
module in other projects. However, the 'azBullet' bindings are tailored to
Azrael; if a particular class or method is not required then it was probably
not wrapped.
