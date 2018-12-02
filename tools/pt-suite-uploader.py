#!/usr/bin/env python

from __future__ import print_function, absolute_import

# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

from optparse import OptionParser, OptionGroup, IndentedHelpFormatter
import os
import sys
import logging
import re
import subprocess
import json

bindir, basename = os.path.split(sys.argv[0])
sys.path.insert(0, os.path.join(bindir, ".."))

from perftrackerlib.client import ptSuite, ptHost, ptVM, ptComponent, ptProduct, ptTest
from perftrackerlib.helpers.textparser import ptParser

from perftrackerlib import perftrackerlib_require_version
perftrackerlib_require_version('0.0.27')


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


def _bool(val):
    return val in ("True", "true", True, "Yes", "yes", "y", 1)


def parse_test(json_data):
    if 'tag' not in json_data:
        return None

    d = json_data
    try:
        t = ptTest(d['tag'],
                   scores=[float(d['score'])] if d.get('score', None) else d['scores'],
                   deviations=[float(d['deviation'])] if d.get('deviation', None) else d.get('deviations', []),
                   duration_sec=float(d['duration_sec']) if d.get('duration_sec', None) else 0,
                   loops=int(d['loops']) if d.get('loops', None) else 1,
                   metrics=d['metrics'],
                   cmdline=d.get('cmdline', ''),
                   less_better=_bool(d.get('less_better', False)),
                   errors=int(d.get('errors', 0)),
                   warnings=int(d.get('warnings', 0)),
                   group=d.get('group', ''),
                   category=d.get('category', ''),
                   description=d.get('description', ''))
    except TypeError as e:
        logging.error("can't parse: %s" % (str(d)))
        raise

    return t


def validate_test(test, line):
    if test is None:
        return False

    if not test.tag:
        logging.debug("'tag' is not found: %s" % line)
        return False

    if len(test.scores) == 0:
        logging.warning("'scores' is not found: %s" % line)
        return False

    logging.info("parsed: %s" % repr(test))
    return True


def run(cmdline):
    status, contents, err = execute(cmdline)
    if status:
        print("command line failed with status %d" % status)
        sys.exit(-1)

    contents = contents.strip()
    if type(contents) == bytes:
        contents = contents.decode()
    return contents


def read_file(filename):
    f = open(filename, 'r')
    content = f.read()
    f.close()

    content = content.strip()
    if type(content) == bytes:
        content = content.decode()

    return content


def parse_json(suite, text):
    data = json.loads(text)

    if 'tests' in data:
        suite.initFromJson(data)
    else:
        for d in data:
            t = parse_test(d)
            if validate_test(t, str(d)):
                suite.addTest(t)


def parse_text(suite, text):
    r = re.compile("(?P<tag>\w+):\s+(?P<val>.*)$")

    data = []

    for line in text.split("\n"):
        test = ptTest("")

        for kv in line.split(";"):
            m = r.match(kv.strip())
            if not m:
                continue
            tag = m.group('tag').lower()
            val = m.group('val')

            try:
                if tag == 'score':
                    test.scores = [float(val)]
                elif tag == 'deviation':
                    test.deviations = [float(val)]
                elif tag in ('scores', 'deviations'):
                    test.__dict__[tag] = [float(v) for v in json.loads(val)]
                elif tag in ('duration_sec',):
                    test.__dict__[tag] = float(val)
                elif tag in ('loops', 'errors', 'warnings'):
                    test.__dict__[tag] = int(val)
                elif tag in ('tag', 'metrics', 'cmdline', 'group', 'category', 'description'):
                    test.__dict__[tag] = val
                elif tag in ('less_better', ):
                    test.__dict__[tag] = _bool(val)
            except ValueError as e:
                logging.error("error in line: %s" % line)
                logging.error(str(e))
                sys.exit(-1)

        if validate_test(test, line):
            suite.addTest(test)

    logging.info("%d tests found" % len(suite.tests))
    if not len(suite.tests):
        print("aborting")
        sys.exit(-1)


class formatter(IndentedHelpFormatter):
    def __init__(self):
        IndentedHelpFormatter.__init__(self, indent_increment=2, max_help_position=30, width=80, short_first=1)

    def format_description(self, description):
        if not description:
            return ""
        ret = "Description:"
        if description.startswith("\n"):
            ret += description
        else:
            ret += "\n%s\n" % description
        return ret


def main():
    usage = "usage: %prog [options] -- command line"

    description = """

  The %%prog laucnhes given command line an parse output in the following format:

  1. Text format (default):

    mandatory fields:
      tag: $STR; score: $FLOAT;
      tag: $STR; score: $FLOAT;
      ...

    optional fields:
      time: $FLOAT; metrics: $STR; loops: $INT; cmdline: $STR; less_better: true; errors: $INT; warnings: $INT; group: $STR; category: $STR;

  2. JSON format (-j)

    [
      {
        /* Mandatory fields */
        "name":       "string",
        "score":       float,

        /* Optional fields */
        "time":        float, /* seconds */
        "metrics":     "string",
        "loops":       int,
        "cmdline":     "string",
        "less_better": true,
        "errors":      int,
        "warnings":    int,
        "group":       "string",
        "category":    "string"
      },
      {
        ...
      }
    ]
"""

    op = OptionParser(description=description, usage=usage, formatter=formatter())
    op.add_option("-v", "--verbose", action="store_true", help="enable verbose mode")
    op.add_option("-j", "--json", help="get results from json file, not from command line")
    op.add_option("-f", "--file", help="get results from text file, not from command line")

    suite = ptSuite()
    suite.addOptions(op)

    opts, args = op.parse_args()

    loglevel = logging.DEBUG if opts.verbose else logging.INFO
    logging.basicConfig(level=loglevel, format="%(asctime)s - %(module)17s - %(levelname).3s - %(message)s", datefmt='%H:%M:%S')

    if opts.json:
        parse_json(suite, read_file(opts.json))
        suite.handleOptions(opts)
    elif opts.file:
        parse_text(suite, read_file(opts.file))
        suite.handleOptions(opts)
    else:
        suite.handleOptions(opts)
        if len(args) == 0:
            op.print_usage()
            print("error: command line is required")
            sys.exit(-1)
        parse_text(suite, run(suite, subprocess.list2cmdline(args)))

    logging.info("%d tests found" % len(suite.tests))
    if not len(suite.tests):
        print("aborting")
        sys.exit(-1)

    suite.upload()


if __name__ == "__main__":
    main()
