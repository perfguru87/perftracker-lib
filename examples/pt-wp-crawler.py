#!/usr/bin/env python

from __future__ import print_function

import os
import sys
import time
from tempfile import gettempdir

bindir, basename = os.path.split(os.path.abspath(__file__))
sys.path.append(os.path.join(bindir, ".."))

basename = basename.split(".")[0]

from optparse import OptionParser, OptionGroup, IndentedHelpFormatter
from perftrackerlib.browser.cp_crawler import CPCrawler, CPCrawlerException
from perftrackerlib.browser.wpa_cp_engine import CPWPAdminConsole
from distutils.version import LooseVersion

# from perftrackerlib import __version__ as perftrackerlib_version
# PERFTRACKERLIB_VERSION_REQUIRED = '0.0.5'
# if LooseVersion(perftrackerlib_version) < LooseVersion(PERFTRACKERLIB_VERSION_REQUIRED):
#    print("Error: perftrackerlib version >= %s must be installed, found %s" %
#          (PERFTRACKERLIB_VERSION_REQUIRED, perftrackerlib_version))
#    sys.exit(-2)
#
# see perftrackerlib/browser/wpa_cp_engine.py as reference implementation
#

def main():
    usage = "usage: %prog [options] URL [URL2 [URL3 ...]]"

    description = "Example: -m -U user -P user https://demo.wpjobboard.net/wp-login.php"

    workdir = os.path.join(gettempdir(), "%s.%d" % (basename, os.getpid()))
    logfile = os.path.join(workdir, basename + ".log")

    cpc = CPCrawler(workdir=workdir, logfile=logfile)

    op = OptionParser(usage=usage, description=description, formatter=IndentedHelpFormatter(width=120))
    cpc.add_options(op, passwd='pass', ajax_threshold=0.5)

    opts, args = op.parse_args()

    if not args:
        op.error("URL is not specified, %s" % description)
        sys.exit(-1)

    cpc.init_opts(opts, args)

    cpc.crawl([CPWPAdminConsole])


if __name__ == "__main__":
    main()
