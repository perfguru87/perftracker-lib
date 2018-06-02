from optparse import OptionParser, OptionGroup
import os
import sys
import logging
import random
from math import sqrt

bindir, basename = os.path.split(sys.argv[0])
sys.path.insert(0, os.path.join(bindir, ".."))

from perftrackerlib.client import ptSuite, ptHost, ptVM, ptComponent, ptProduct, ptTest
from perftrackerlib import __version__


def main(suite):
    suite.addLink('Grafana', 'http://grafana.localdomain/')
    suite.addLink('Login page', 'http://192.168.100.3/login')

    s1 = suite.addNode(ptHost("s1", ip="192.168.0.1", hostname="server1.localdomain", version="CentOS 7.4", cpus=32, ram_gb=128))
    s2 = suite.addNode(ptHost("s2", ip="192.168.0.2", hostname="server2.localdomain", version="CentOS 7.4", cpus=32, ram_gb=128))
    s3 = suite.addNode(ptHost("s3", ip="192.168.0.3", hostname="server3.localdomain", version="CentOS 7.4", cpus=32, ram_gb=128))
    s4 = suite.addNode(ptHost("s4", ip="192.168.0.4", hostname="server4.localdomain", version="CentOS 7.4", cpus=16, ram_gb=64))

    vm1 = s1.addNode(ptVM("vm1", ip="192.168.100.1", version="CentOS 7.4", virt_type="KVM VM", cpus=4, ram_gb=32))
    vm2 = s1.addNode(ptVM("vm2", ip="192.168.100.2", version="CentOS 7.4", virt_type="KVM VM", cpus=4, ram_gb=32))
    vm3 = s2.addNode(ptVM("vm3", ip="192.168.100.3", version="CentOS 7.4", virt_type="KVM VM", cpus=8, ram_gb=64))
    vm4 = s3.addNode(ptVM("vm4", ip="192.168.100.4", version="CentOS 7.4", virt_type="KVM VM", cpus=8, ram_gb=64))

    s4.addNode(ptVM("client", ip="192.168.200.1", version="CentoOS 7.4", cpus=12, ram_gb=32, params="Python3", virt_type="KVM VM"))

    vm1.addNode(ptComponent("database", version="1.0.12"))
    vm2.addNode(ptComponent("backend", version="1.0.12"))
    vm3.addNode(ptComponent("UI#1", version="1.0.13"))
    vm4.addNode(ptComponent("UI#2", version="1.0.13"))

    g = "Latency tests"

    suite.addTest(ptTest("Simple user login test", less_better=True,
                         description="Login under a user, 1 parallel client, time includes navigation to home page",
                         group=g, metrics="sec", scores=[0.6, 0.72, 0.65 + random.randint(0, 10) / 10.0],
                         deviations=[0.05, 0.12, 0.03], loops=100,
                         links={"repo": "https://github.com/perfguru87/perftracker-client"},
                         attribs={"version": str(__version__)}))
    suite.addTest(ptTest("Simple admin login test", less_better=True,
                         description="Login under admin, 1 parallel client",
                         group=g, metrics="sec", scores=[0.8, 0.9, 1.2 + random.randint(0, 10) / 10.0],
                         deviations=[0.03, 0.09, 0.08], loops=100,
                         links={"repo": "https://github.com/perfguru87/perftracker-client"},
                         attribs={"version": str(__version__)}))

    for p in range(1, 5 + random.randint(0, 2)):
        suite.addTest(ptTest("Login time", group=g, metrics="sec", less_better=True,
                             category="%d parallel users" % (2 ** p),
                             scores=[0.3 + sqrt(p) + random.randint(0, 20) / 40.0]))

    for p in range(1, 20 + random.randint(0, 10)):
        suite.addTest(ptTest("Pages response time, 1 parallel client", group=g, metrics="sec", less_better=True,
                             category="page #%3d" % p,
                             scores=[0.3 + random.randint(0, 20) / 40.0],
                             errors=['4xx error'] if random.randint(0, 30) == 0 else [],
                             warnings=['HTTP 500'] if random.randint(0, 20) == 0 else [],
                             status="FAILED" if random.randint(0, 25) == 0 else "SUCCESS"))

    for p in range(1, 100 + random.randint(0, 100)):
        suite.addTest(ptTest("Home page response time", group=g, metrics="sec", less_better=True,
                             category="Database size %d GB" % p,
                             scores=[0.3 + (sqrt(p) + random.randint(0, 20)) / 40],
                             errors=['4xx error'] if random.randint(0, 30) == 0 else [],
                             warnings=['HTTP 500'] if random.randint(0, 20) == 0 else [],
                             status="FAILED" if random.randint(0, 25) == 0 else "SUCCESS"))

    for p in range(1, 100 + random.randint(0, 100)):
        suite.addTest(ptTest("Dashboard page response time", group=g, metrics="sec", less_better=True,
                             category="Database size %d GB" % p,
                             scores=[0.8 + (sqrt(p) + random.randint(0, 20)) / 40],
                             errors=['4xx error'] if random.randint(0, 30) == 0 else [],
                             warnings=['HTTP 500'] if random.randint(0, 20) == 0 else [],
                             status="FAILED" if random.randint(0, 25) == 0 else "SUCCESS"))

    suite.upload()

    g = "Throughput tests"

    for p in range(1, 5 + random.randint(0, 2)):
        suite.addTest(ptTest("Home page throughput", group=g, metrics="pages/sec",
                             category="%d parallel clients" % (2 ** p),
                             scores=[10 + sqrt(p) + random.randint(0, 20) / 5]))

    suite.upload()


if __name__ == "__main__":

    op = OptionParser("PerfTracker suite example")
    op.add_option("-v", "--verbose", action="store_true", help="enable verbose mode")

    suite = ptSuite(suite_ver="1.0.0", product_name="My web app", product_ver="1.0-1234")
    suite.addOptions(op, pt_project="Default project")

    opts, args = op.parse_args()

    loglevel = logging.DEBUG if opts.verbose else logging.INFO
    logging.basicConfig(level=loglevel, format="%(asctime)s - %(module)s - %(levelname)s - %(message)s")

    suite.handleOptions(opts)

    main(suite)
