#!/usr/bin/env python

from __future__ import print_function, absolute_import

# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

"""The library to work efficiently with very large log files
"""

import re
from pydoc import locate


class ptRowParser:
    def __init__(self, regexp, obj_cb, parse_once=True):
        self.regexp = re.compile(regexp)
        self._regexp = regexp
        self.obj_cb = obj_cb
        self.parse_once = parse_once

    def search(self, line, match=True):
        m = self.regexp.match(line) if match else self.regexp.search(line)

        if m:
            if type(self.obj_cb) == list:
                for obj_cb in self.obj_cb:
                    obj_cb(m)
            else:
                self.obj_cb(m)
            return True
        return False


class ptParser:
    def __init__(self):
        self.row_parsers = []

    def add_row_parser(self, regexp, obj_cb, parse_once=True):
        self.row_parsers.append(ptRowParser(regexp, obj_cb, parse_once))

    def parse_text(self, lines, match=True):
        for line in lines:
            n_parsers = len(self.row_parsers)

            for n in range(0, n_parsers):
                if self.row_parsers[n].search(line, match):
                    if self.row_parsers[n].parse_once:
                        del self.row_parsers[n]
                    break


##############################################################################
# Autotests
##############################################################################


def _coverage():

    class TestClass:
        def __init__(self):
            self.int = 0
            self.float = 0.0
            self.str = 'abc'

        def parse(self, m):
            for key in ('int', 'float', 'str'):
                try:
                    self.__dict__[key] = locate(key)(m.group(key))
                except IndexError:
                    pass

    t1 = TestClass()
    t2 = TestClass()
    t3 = TestClass()

    p = ptParser()

    p.add_row_parser("int: (?P<int>\d+), float: (?P<float>[\d\.]+), str: (?P<str>.*)", t1.parse, parse_once=False)
    p.add_row_parser("int: (?P<int>\d+), float: (?P<float>[\d\.]+), xstr: (?P<str>.*)", t2.parse)
    p.add_row_parser("int: (?P<int>\d+), str: (?P<str>.*)", [t1.parse, t3.parse])

    text = ["int: 12, float: 1.23, str: xxx",
            "int: 13, float: 1.24, xstr: xxx",
            "int: 14, str: yyy",
            "int: 15, float: 1.25, str: zzz",
            "int: 16, float: 1.26, xstr: aaa",
            ]

    p.parse_text(text)
    p.add_row_parser(" case #3 int: (\d+), float: ([\d\.]+), str: (\s*)", [(t1, 'int', int)], parse_once=False)

    assert t1.int == 15
    assert t1.float == 1.25
    assert t1.str == "zzz"

    assert t2.int == 13
    assert t2.float == 1.24
    assert t2.str == "xxx"

    assert t3.int == 14
    assert t3.float == 0.0
    assert t3.str == "yyy"

    print("OK")


if __name__ == "__main__":
    _coverage()
