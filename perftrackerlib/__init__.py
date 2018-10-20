#!/usr/bin/env python

from __future__ import print_function

import sys
from distutils.version import LooseVersion

__version__ = "0.0.38"
__name__ = "perftrackerlib"

def perftrackerlib_require_version(ver_required):
    if LooseVersion(__version__) < LooseVersion(ver_required):
        print("Error: perftrackerlib version >= %s must be installed, found %s" %
              (ver_required, __version__))
        sys.exit(-2)
