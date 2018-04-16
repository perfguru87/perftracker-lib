# (C) 2017 Ingram Micro Inc.  All rights reserved.
# Odin is a registered copyright of Ingram Micro Inc. 2017. All rights reserved.
# http://www.odin.com

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
