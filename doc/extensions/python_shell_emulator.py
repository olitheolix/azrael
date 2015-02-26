"""
Read Python3 commands from STDIN, then process them in a print-eval fashion.

This script is usually used in conjunction with the ``inline-python``
extension for Sphinx.

Note: This script emulates Python3 only.
"""
import sys
import code


class PythonShell(code.InteractiveInterpreter):
    """
    A Python interpreter that echoes the commands.b
    """
    def showtraceback(self):
        """
        Print traceback, then quit immediately with an error.
        """
        super().showtraceback()
        sys.exit(1)

    def showsyntaxerror(self, filename):
        """
        Print traceback, then quit immediately with an error.
        """
        super().showsyntaxerror(filename)
        sys.exit(1)

    def runall(self):
        """
        Run a print-eval loop on the input from STDIN.
        """
        # Sanitise the data coming from STDIN.
        codeLines = (_.rstrip() for _ in sys.stdin)

        # Process all input lines.
        incomplete = False
        for line in codeLines:
            if incomplete:
                # Add another line to the command because the last one was
                # apparently incomplete.
                print('... {}'.format(line))
                cmd += '\n' + line
            else:
                # Start a new command.
                print('>>> {}'.format(line))
                cmd = line
            incomplete = self.runsource(cmd)


if __name__ == '__main__':
    mine = PythonShell()
    mine.runall()
