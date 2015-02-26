"""
Execute Python code from doc-string.

The original code in the Sphinx directive will be replaced with a literal text
block that shows the input/output relationship of the code as if it had been
typed into an interactive Python shell.

Usage
-----

.. inline-python::

    x = 10
    print('Value of x is {}'.format(x))

Installation
------------

1. Copy `inline_python.py` (ie. this file) and `python_shell_emulator.py` into
   a directory `foo`.
2. In `conf.py`, add `foo` to the search path for Sphinx extensions (eg.
   sys.path.insert(0, os.path.abspath(foo))
3. In `conf.py`, add the string 'inline_python' to the ``extensions``
   variable.
"""
import os
import sys
import time
import subprocess
import sphinx.errors
import sphinx.util.compat
import docutils.nodes
import docutils.parsers.rst
import python_shell_emulator


class RunBlock(sphinx.util.compat.Directive):
    # Sphinx requires these class attributes.
    has_content = True
    required_arguments = 0
    optional_arguments = 0
    final_argument_whitespace = False
    option_spec = {
        'linenos': docutils.parsers.rst.directives.flag,
        'nostderr': docutils.parsers.rst.directives.flag,
        'nostdout': docutils.parsers.rst.directives.flag,
    }

    def run(self):
        # Add the current directories in sys.path to PYTHONPATH.
        newEnv = os.environ.copy()
        tmp = ':'.join(sys.path)
        newEnv['PYTHONPATH'] = tmp

        # Convenience shorthands.
        Popen = subprocess.Popen
        PIPE = subprocess.PIPE

        # Start the custom Python interpreter to execute the embedded code
        # snippet from the doc-string.
        progName = ['python3', os.path.abspath(python_shell_emulator.__file__)]
        proc = Popen(progName, bufsize=1, stdin=PIPE, stdout=PIPE,
                     stderr=PIPE, env=newEnv)

        # Feed the code-snippet to STDIN of the just spawned program.
        code = u'\n'.join(self.content).encode('utf8')
        t0 = time.time()
        sys.stdout.write('Running embedded Python code... ')
        sys.stdout.flush()
        try:
            stdout, stderr = proc.communicate(code, 30)
        except subprocess.TimeoutExpired:
            print('Timeout in code snippet')
            print(code)
            sys.exit(1)

        # Decode the program output.
        stdout = stdout.decode('utf8')
        stderr = stderr.decode('utf8')

        # Check if the code fragment executed properly.
        if proc.returncode != 0:
            # Dump the program output to screen for debugging purposes.
            print(stdout, stderr)
            sys.exit(1)
        else:
            etime = 1000 * (time.time() - t0)
            print('done ({}ms)'.format(int(etime)))

        # Pick the output streams according to the parameters given to the
        # ReST directive in the doc-string.
        out = ''
        if 'nostderr' not in self.options:
            out += ''.join(stderr)
        if 'nostdout' not in self.options:
            out += ''.join(stdout)

        # Construct a ReST literal block and return it to Sphinx.
        literal = docutils.nodes.literal_block(out, out)
        literal['language'] = 'python'
        literal['linenos'] = 'linenos' in self.options
        return [literal]


def setup(app):
    """
    Called by Sphinx to initialise the extension.
    """
    app.add_directive('inline-python', RunBlock)
