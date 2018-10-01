from __future__ import print_function, absolute_import

# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

import os
import sys
import logging
import tempfile


# tee sys.stdout or sys.stderr to a file
class Tee(object):
    def __init__(self, stream_name):
        assert stream_name == 'stdout' or stream_name == 'stderr'

        _, self.filename = tempfile.mkstemp()
        logging.debug("copying sys.%s stream to %s" % (stream_name, self.filename))

        self._stream_name = stream_name
        self._file = open(self.filename, 'w')
        self._stream = sys.__dict__[stream_name]
        sys.__dict__[self._stream_name] = self

    def __del__(self):
        self._file.flush()
        sys.__dict__[self._stream_name] = self._stream
        self._file.close()
        os.unlink(self.filename)

    def write(self, data):
        self._stream.write(data)
        self._file.write(data)
        self._file.flush()

    def flush(self):
        self._file.flush()


##############################################################################
# Autotests
##############################################################################


def _coverage():
    t = Tee('stdout')
    sys.stdout.flush()
    print("OK")
    assert open(t.filename, 'r').readline().strip() == "OK"
    del sys.stdout


if __name__ == "__main__":
    _coverage()
