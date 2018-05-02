#!/bin/env python
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys
from os import sys, path

root = os.path.join(os.path.dirname(os.path.realpath(__file__)))
sys.path.append(root)
from execute import execute

libs = [("perftrackerlib/helpers/timeparser.py", 98),
        ("perftrackerlib/helpers/largelogfile.py", 98),
        ("perftrackerlib/helpers/httppool.py", 35),
        ("perftrackerlib/helpers/texttable.py", 82),
        ("perftrackerlib/browser/browser_base.py", 45),
        ("perftrackerlib/browser/browser_webdriver.py", 20),
        ("perftrackerlib/browser/browser_python.py", 55),
        ("perftrackerlib/browser/utils.py", 19),
        ("perftrackerlib/browser/page.py", 15),
        ("perftrackerlib/browser/cp_engine.py", 30),
        ("perftrackerlib/browser/browser_chrome.py", 80),
        ("perftrackerlib/browser/browser_firefox.py", 35),
        ("perftrackerlib/browser/cp_crawler.py", 50),
        ]


def test_one(cmdline):
    print("Testing: %s ..." % cmdline, end=' ')
    sys.stdout.flush()
    execute(cmdline)
    print("OK")


def lib2mod(lib):
    modname = lib[0:len(lib) - 3] if lib.endswith(".py") else lib
    return modname.replace("/", ".")


def coverage_one(lib, coverage_target):
    # Use '# pragma: no cover' to exclude code
    # see http://coverage.readthedocs.io/en/coverage-4.2/excluding.html

    print("coverage run %s ..." % lib, end=' ')
    execute("coverage run -m \"%s\"" % lib2mod(lib))
    _, out, ext = execute("coverage report | grep %s" % lib)
    try:
        coverage = out.split()[3]
        if not coverage.endswith("%"):
            raise RuntimeError("can't parse: %s" % coverage)
        coverage = int(coverage[:-1])
        if coverage < coverage_target:
            print("FAILED, code coverage is %d%%, must be >= %d%%" % (coverage, coverage_target))
            print("NOTE: to debug the problem manually run:")
            print("          coverage run %s" % os.path.join(root, lib))
            print("          coverage report -m")
            sys.exit(-1)
        print("OK, %d%%" % coverage)
    except RuntimeError as e:
        print("FAILED, can't parse coverage")
        raise


def test_all():
    csopts = "--max-line-length=120 --ignore=E402"
    test_one("pycodestyle %s *.py" % csopts)
    for lib, _ in libs:
        test_one("pycodestyle %s \"%s\"" % (csopts, os.path.join(root, lib)))

    for lib, coverage_target in libs:
        coverage_one(lib, coverage_target)

    for lib, _ in libs:
        mod = lib2mod(lib)
        test_one("python2.7 -m \"%s\"" % mod)
        test_one("python3 -m \"%s\"" % mod)

#   test_one("2to3 -p \"%s\"" % root)
#   for t in tests:
#       test_one("python2 -m \"tests.%s\"" % t)
#       test_one("python3 -m \"tests.%s\"" % t)


if __name__ == '__main__':
    test_all()

    print(("=" * 80))
    print("Good job, no errors")
