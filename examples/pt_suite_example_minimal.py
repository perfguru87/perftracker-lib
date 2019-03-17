#!/usr/bin/env python

from optparse import OptionParser
import os
import sys
import logging
import random

bindir, basename = os.path.split(sys.argv[0])
sys.path.insert(0, os.path.join(bindir, ".."))

from perftrackerlib.client import ptSuite, ptTest


def main(suite):
    suite.addTest(ptTest("Simple benchmark",
                         description="A simple benchmark output",
                         metrics="loops/sec", scores=[random.randint(10, 20) / 10.0],
                         loops=100))

    suite.upload()


if __name__ == "__main__":

    op = OptionParser("PerfTracker suite example")
    op.add_option("-v", "--verbose", action="store_true", help="enable verbose mode")

    suite = ptSuite(suite_ver="1.0.0", product_name="My product", product_ver="1.0-123", project_name="Default project")
    suite.addOptions(op)

    opts, args = op.parse_args()

    loglevel = logging.DEBUG if opts.verbose else logging.INFO
    logging.basicConfig(level=loglevel, format="%(asctime)s - %(module)s - %(levelname)s - %(message)s")

    main(suite)
