#!/usr/bin/env python

from optparse import OptionParser, OptionGroup
import os
import sys
import logging
from math import sqrt

bindir, basename = os.path.split(sys.argv[0])
sys.path.insert(0, os.path.join(bindir, ".."))

from perftrackerlib.client import ptSuite, ptHost, ptVM, ptComponent, ptProduct, ptTest


def main(suite):
    s1 = suite.addNode(ptHost("s1", ip="192.168.0.1", hostname="s1.mydomain", version="ESX 7.0", cpus=32, ram_gb=128))
    vm1 = s1.addNode(ptVM("account-server-vm", ip="192.168.100.1", version="CentOS 7.4", cpus=16, ram_gb=64))
    vm1 = s1.addNode(ptVM("test-client-vm", ip="192.168.100.2", version="CentOS 7.4", cpus=16, ram_gb=64))

    chunk = 50

    for accounts_in_db in range(0, 1050, chunk):

        volume = "%d accounts in DB" % (1000 * accounts_in_db)

        group = "Provisioning tests"

        suite.addTest(ptTest("Create accounts in 1 thread",
                             group=group, category=volume, metrics="accounts/sec", duration_sec=900,
                             description="POST /accounts in 1 thread (create %d accounts)" % (chunk * 0.1),
                             scores=[60 / sqrt(sqrt(sqrt(accounts_in_db + 100)))]))  # fake score

        suite.addTest(ptTest("Create accounts in 16 threads",
                             group=group, category=volume, metrics="accounts/sec", duration_sec=3200,
                             description="POST /accounts in 16 threads (create %d accounts)" % (chunk * 0.9),
                             scores=[600 / (1.1 * sqrt(accounts_in_db + 100))]))  # fake score

        group = "Read-only tests"

        suite.addTest(ptTest("GET information for some account in 1 thread",
                             group=group, category=volume, metrics="accounts/sec", duration_sec=30,
                             description="GET /account/1 in 1 thread (30 sec)",
                             scores=[120 - sqrt(accounts_in_db + 10)]))  # fake score

        suite.addTest(ptTest("GET information for some account in 8 threads",
                             group=group, category=volume, metrics="accounts/sec", duration_sec=30,
                             description="GET /account/1 in 8 threads (30 sec)",
                             scores=[430 - 2 * sqrt(accounts_in_db + 10)]))  # fake score

        suite.addTest(ptTest("GET information for some account in 64 threads",
                             group=group, category=volume, metrics="accounts/sec", duration_sec=30,
                             description="GET /account/1 in 64 threads (30 sec)",
                             scores=[850 - 1.5 * sqrt(accounts_in_db + 10)]))  # fake score

        suite.addTest(ptTest("GET list of 10 first accounts in 1 thread",
                             group=group, category=volume, metrics="lists/sec", duration_sec=30,
                             description="GET /accounts/?limit=10 in 1 thread (30 sec)",
                             scores=[95 - 0.3 * sqrt(accounts_in_db + 10)]))  # fake score

        suite.addTest(ptTest("GET list of 10 first accounts in 8 thread",
                             group=group, category=volume, metrics="lists/sec", duration_sec=30,
                             description="GET /accounts/?limit=10 in 1 thread (30 sec)",
                             scores=[105 - 0.4 * sqrt(accounts_in_db + 10)]))  # fake score

        suite.addTest(ptTest("GET list of 10 first accounts in 64 thread",
                             group=group, category=volume, metrics="lists/sec", duration_sec=30,
                             description="GET /accounts/?limit=10 in 64 thread (30 sec)",
                             scores=[115 - 0.3 * sqrt(accounts_in_db + 10)]))  # fake score

        group = "Modificating tests"

        suite.addTest(ptTest("Update accounts in 1 thread",
                             group=group, category=volume, metrics="accounts/sec", duration_sec=89,
                             description="PUT /accounts in 1 thread (update 100 accounts)",
                             scores=[110 - 0.2 * sqrt(accounts_in_db + 10)]))  # fake score

        suite.addTest(ptTest("Update accounts in 16 threads",
                             group=group, category=volume, metrics="accounts/sec", duration_sec=970,
                             description="PUT /accounts in 16 threads (update 1600 accounts)",
                             scores=[130 - 0.3 * sqrt(accounts_in_db + 10)]))  # fake score

        suite.addTest(ptTest("Delete accounts in 1 thread",
                             group=group, category=volume, metrics="accounts/sec", duration_sec=520,
                             description="PUT /accounts in 1 thread (update 100 accounts)",
                             scores=[20 - 0.2 * sqrt(accounts_in_db + 10)]))  # fake score

        suite.addTest(ptTest("Delete accounts in 16 threads",
                             group=group, category=volume, metrics="accounts/sec", duration_sec=540,
                             description="PUT /accounts in 16 threads (update 1600 accounts)",
                             scores=[320 - 0.1 * sqrt(accounts_in_db + 10)]))  # fake score

        suite.upload()


if __name__ == "__main__":

    op = OptionParser("PerfTracker suite example")
    op.add_option("-v", "--verbose", action="store_true", help="enable verbose mode")

    suite = ptSuite(suite_ver="1.0.0", product_name="Account Server", product_ver="1.0-1234")
    suite.addOptions(op)

    opts, args = op.parse_args()
    logging.basicConfig(level=logging.DEBUG if opts.verbose else logging.INFO)
    suite.handleOptions(opts)

    main(suite)
