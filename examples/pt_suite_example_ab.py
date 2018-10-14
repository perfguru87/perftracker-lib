#!/usr/bin/env python

from __future__ import print_function, absolute_import
 
# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

from optparse import OptionParser, OptionGroup
import os
import sys
import logging
import re

bindir, basename = os.path.split(sys.argv[0])
sys.path.insert(0, os.path.join(bindir, ".."))

from perftrackerlib.client import ptSuite, ptHost, ptVM, ptComponent, ptProduct, ptTest
from perftrackerlib import __version__

reRPS = re.compile("Requests per second:\s+(\d+\.\d+).*")
reERR = re.compile("Failed requests:\s+(\d+).*")
reREQ = re.compile("Complete requests:\s+(\d+).*")

EXIT_AB_ERROR = -1
EXIT_URL_VALIDATION = -2
EXIT_NO_URLS = -3

class ABLauncher:
    def __init__(self, suite, urls, concurrencies=None, iterations=3, requests=100):
        if concurrencies is None:
            concurrencies = []
        assert type(concurrencies) == list
        assert type(urls) == list
        assert len(urls)
        assert isinstance(suite, ptSuite)

        self.suite = suite
        self.urls = [u.strip() for u in urls if u]
        self.concurrencies = concurrencies
        self.iterations = int(iterations)
        self.requests = int(requests)

        self.fmt = "%11s %8s %8s %8s  %s"

    def print_ab_header(self):
        print(self.fmt % ("Concurrency", "Req/sec", "Requests", "Errors", "Cmdline"))

    def parse_ab_stdout(self, concurrency, cmdline, stdout, test):
        score = 0
        loops = 0
        errors = 0

        for line in stdout.split("\n"):
            m = reRPS.match(line)
            if m:
                score = float(m.groups()[0])
                test.add_score(score)
                continue
            m = reREQ.match(line)
            if m:
                loops = int(m.groups()[0])
                test.loops += loops
                continue
            m = reERR.match(line)
            if m:
                errors = int(m.groups()[0])
                test.errors += errors
                continue
        print(self.fmt % (str(concurrency), "%.1f" % score, str(loops), str(errors), cmdline))

    def _validate_urls(self):
        for url in self.urls:
            for pfx in ("http://", "https://"):
                if url.startswith(pfx) and "/" in url[len(pfx):]:
                    break
            else:
                print("error: an url must be: http(s)://$DOMAIN/.* ... got: %s" % url)
                sys.exit(EXIT_URL_VALIDATION)

    def init(self):
        self._validate_urls()

        self.suite.addNode(ptHost("client", ip='127.0.0.1', scan_info=True))
        self.suite.upload()
	self.print_ab_header()

    def launch(self):
        for concurrency in self.concurrencies:
            requests = max(self.requests, concurrency)
            for url in self.urls:
                cmdline = "ab -k -c %d -n %d %s" % (concurrency, requests, url)

                test = ptTest(url, category="concurrency=%d" % concurrency,
                              group="Throughput", metrics="req/sec",
                              errors=0, loops=0, cmdline=cmdline)

                for i in range(0, self.iterations):
                    status, stdout, stderr = test.execute()
                    if status:
                        print(stderr, file=sys.stderr)
                        sys.exit(EXIT_AB_ERROR)
                    self.parse_ab_stdout(concurrency, test.cmdline, stdout, test)

                self.suite.addTest(test)
                self.suite.upload()


def main():
    op = OptionParser("PerfTracker suite example", description="%program [options] URL1 [URL2 [...]]")
    op.add_option("-v", "--verbose", action="store_true", help="enable verbose mode")
    op.add_option("-c", "--concurrency", default="1,4,16", help="comma separated list of concurrencies to use")
    op.add_option("-n", "--requests", default=100, type=int, help="total number of requests to execute on every step")
    op.add_option("-i", "--iterations", default=3, type=int, help="number of iterations for every test")
    op.add_option("-f", "--from-file", default="", help="get URLs from given file")

    suite = ptSuite(suite_ver="1.0.0", product_name="My web site", product_ver="1.0-1234")
    suite.addOptions(op)

    opts, urls = op.parse_args()

    if opts.from_file:
        f = open(opts.from_file, 'r')
        urls = f.readlines()
        f.close()

    if not urls:
        op.print_help()
        print("Example:\n    %s http://www.google.com/" % basename)
        sys.exit(EXIT_NOR_URLS)

    loglevel = logging.DEBUG if opts.verbose else logging.INFO
    logging.basicConfig(level=loglevel, format="%(asctime)s - %(module)s - %(levelname)s - %(message)s")

    suite.handleOptions(opts)

    ab = ABLauncher(suite, urls, concurrencies=[int(c.strip()) for c in opts.concurrency.split(",")],
                    requests=opts.requests, iterations=opts.iterations)
    ab.init()
    ab.launch()

if __name__ == "__main__":
    main()
