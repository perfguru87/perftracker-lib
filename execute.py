#!/usr/bin/env python

from __future__ import print_function, absolute_import

# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

import logging
import subprocess


def execute(cmd, exc_on_err=True):
    logging.debug("executing: %s" % (cmd))
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout_text, stderr_text = p.communicate()
    p.wait()
    status = p.returncode
    if status and exc_on_err:
        raise RuntimeError("'%s' execution failed with status %d:\n%s\n%s" % (cmd, status, stdout_text, stderr_text))
    logging.debug("'%s' status %d, stdout:\n%s\nstderr:\n%s" % (cmd, status, stdout_text, stderr_text))

    return (status, stdout_text, stderr_text)
