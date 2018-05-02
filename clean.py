#!/bin/env python
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys
from os import sys, path

root = os.path.join(os.path.dirname(os.path.realpath(__file__)))
sys.path.append(root)
from execute import execute


def clean_one(cmdline):
    print("Running: %s ..." % cmdline, end=' ')
    sys.stdout.flush()
    execute(cmdline)
    print("OK")


def clean_all():
    clean_one("rm -rf '%s/perftrackerlib/__pycache__/'" % root)
    clean_one("rm -rf '%s/test/__pycache__/'" % root)
    clean_one("rm -rf '%s/build/'" % root)
    clean_one("rm -rf '%s/dist/'" % root)
    clean_one("rm -rf '%s/perftracerlib.egg-info'" % root)
    clean_one("find %s/ -name \*.pyc | xargs rm -f" % root)


if __name__ == '__main__':
    clean_all()
