#!/usr/bin/env python

from __future__ import print_function

# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

"""The library to draw formatted text tables
"""

import sys
import datetime

BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, GRAY = [("\x1b[1;%dm" % (30+c), "\x1b[0m") for c in range(9)]

class TextTable:
    def __init__(self, max_col_width=[], col_separator = "  ", autoreplace={"0": "-"}, left_aligned=None, col_format=None):
        self._rows = []
        self._styles = []
        self._max_col_width = max_col_width
        self._col_width = []
        self._format = None
        self._total_width = 0
        self._col_separator = col_separator
        self._autoreplace = autoreplace
        self._col_type = []
        self._left_aligned = left_aligned # list of left-aligned columns
        self._col_format = col_format # list of left-aligned columns
        self._has_colors = self._has_colors(sys.stdout)
        self._columns_count = 0

    def _has_colors(self, stream):
        if not hasattr(stream, "isatty"):
            return False
        if not stream.isatty():
            return False # auto color only on TTYs

        try:
            import curses
            curses.setupterm()
            return curses.tigetnum("colors") > 2
        except:
            # guess false in case of error
            return False

    def _init_format(self):
        if self._format:
            return
        for columns in self._rows:
            if isinstance(columns, str) or isinstance(columns, unicode):
                continue
            for c in xrange(0, len(columns)):
                if len(self._col_width) <= c:
                    self._col_width.append(0)
                val = self._format_value(c, columns[c])
                self._col_width[c] = max(self._col_width[c], len(val))
                if len(self._max_col_width) > c and self._max_col_width[c] and \
                        self._col_width[c] > self._max_col_width[c]:
                    self._col_width[c] = self._max_col_width[c]
        self._format = ""
        for n in xrange(0, len(self._col_width)):
            c = self._col_width[n]
            if self._left_aligned and n in self._left_aligned:
                self._format += "%%-%ds" % c
            else:
                self._format += "%%%ds" % c
            self._format += self._col_separator
            self._total_width += c + len(self._col_separator)

    def _format_value(self, column, val):
        if val == None:
            s = ""
        try:
            if self._col_format and self._col_format.has_key(column):
                val = self._col_format[column] % val
        except:
            pass
        if isinstance(val, int) or isinstance(val, float) or isinstance(val, long) or isinstance(val, datetime.datetime) or val == None:
            s = str(val)
        else:
            s = val.encode('ascii', 'ignore')
        if self._autoreplace.has_key(s):
            return str(self._autoreplace[s])
        return s

    def add_row(self, values, style=None):
        if isinstance(values, list):
            if not self._columns_count:
                self._columns_count = len(values)
            elif len(values) != self._columns_count:
                raise Exception("columns number mismatch. It must be %d, but get: %s" % \
                    (self._columns_count, str(values)))
        self._rows.append(values)
        if not self._has_colors:
            style=None
        self._styles.append(style)

    def get_lines(self):
        lines = []
        self._init_format()
        for columns in self._rows:
            if isinstance(columns, unicode):
                columns = columns.encode('ascii', 'ignore')
            if isinstance(columns, str):
                if len(columns) == 1:
                    lines.append(columns * self._total_width)
                else:
                    lines.append(columns)
            else:
                _columns = []
                for n in xrange(0, len(columns)):
                    if len(self._max_col_width) > n and self._max_col_width[n] and \
                            len(str(columns[n])) > self._max_col_width[n]:
                        _columns.append(str(columns[n])[:self._max_col_width[n]-3] + "...")
                    else:
                        if isinstance(columns[n], unicode):
                            columns[n] = columns[n].encode('ascii', 'ignore')
                        if isinstance(columns[n], str):
                            if self._left_aligned and n in self._left_aligned:
                                fmt = str("%%-%ds" % self._col_width[n])
                            else:
                                fmt = str("%%%ds" % self._col_width[n])
                            _columns.append(fmt % self._format_value(n, columns[n]))
                        else:
                            _columns.append(self._format_value(n, columns[n]))
                try:
                    line = self._format % tuple(_columns)
                except TypeError:
                    line = str(_columns)

                if self._styles[len(lines)]:
                    begin, end = self._styles[len(lines)]
                    line = begin + line + end
                lines.append(line)
        return lines


##############################################################################
# Autotests
##############################################################################


if __name__ == "__main__":
    print("\nExample #1:")
    t = TextTable()
    t.add_row(["COL1", "COLUMN 2", "COLUMN NUMBER 3"])
    t.add_row("-")
    t.add_row([123, 456, 7890])
    t.add_row([91824, 5818251, 0])
    t.add_row([0, 12, 90])
    print("\n".join(t.get_lines()))

    print("\nExample #2 (table with max column width):")
    t = TextTable(max_col_width=[20, 15])
    t.add_row("=")
    t.add_row(["COLUMN #1", "COLUMN #2", "COLUMN #3", "COLUMN #4"])
    t.add_row("-")
    t.add_row(["Some string", 12.5, 91.9, 0])
    t.add_row(["Some longer string", 12.7, 91.9, 21.0])
    t.add_row(["Some very long string", 212.5, 0, 3221.0])
    t.add_row(["Some very very long string", 312.0, 20.5, 0.5])
    print("\n".join(t.get_lines()))
