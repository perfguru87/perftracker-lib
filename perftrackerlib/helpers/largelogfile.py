#!/usr/bin/env python

from __future__ import print_function, absolute_import

# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

"""The library to work efficiently with very large log files
"""

import os
import sys
import gzip
import bz2
import datetime
import logging

from .timeparser import TimeParser, TimeParserException


class LargeFileException(RuntimeError):
    pass


class FileWithBackspaces:
    def __init__(self, file_obj):
        self._file_obj = file_obj
        self._next_line = None
        self._backspaces = [r'', r'', r'\x08']

    def readline(self):
        if self._next_line:
            line = self._next_line
        else:
            line = self._file_obj.readline()

        if not line:
            return line

        self._next_line = self._file_obj.readline()
        while self._next_line:
            # handle backspace
            if not self._next_line[0] in self._backspaces:
                return line

            # loop below (a) just skips '\x08\n' and (b) cuts '\x08'
            while self._next_line:
                if not self._next_line[0] in self._backspaces:
                    break
                for b in self._backspaces:
                    self._next_line = self._next_line.lstrip(b)
                if self._next_line != "\n":
                    break
                self._next_line = self._file_obj.readline()

            line = line.rstrip('\n').rstrip('\r') + self._next_line
            self._next_line = self._file_obj.readline()

        return line

    def rewind(self):
        self.seek(0, os.SEEK_SET)

    def seek(self, offset, whence=0):
        self._next_line = None
        return self._file_obj.seek(offset, whence)

    def tell(self):
        t = self._file_obj.tell()
        if self._next_line:
            return t - len(self._next_line)
        return t

    def close(self):
        self._file_obj.close()


class LargeLogFile:
    """
    Extracts parts of a log file based on a begin_time and end_time (both are optional)
    Uses binary search logic for fast search
    """

    def __init__(self, filename, begin_time=None, end_time=None):
        self.filename = filename
        self._timeparser = TimeParser()

        if begin_time is not None:
            if type(begin_time) == str:
                x, y = self._timeparser.parse(begin_time)
                begin_time, _ = self._timeparser.parse(begin_time)
            assert type(begin_time) == datetime.datetime, "Unsupported begin_time type: " + str(type(begin_time))

        if end_time is not None:
            if type(end_time) == str:
                end_time, _ = self._timeparser.parse(end_time)
            assert type(end_time) == datetime.datetime, "Unsupported end_time type: " + str(type(end_time))

        self.begin_time = begin_time
        self.end_time = end_time

        self._range_begin_pos = None
        self._range_end_pos = None
        self._curr_line_begin_pos = None
        self._curr_line_end_pos = None

        self._open()

    def _open(self):  # pragma: no cover
        if self.filename == '-':
            self.begin_time = None
            self.end_time = None
            self._file_obj = sys.stdin
            return

        if self.filename.endswith(".gz"):
            f = gzip.open(self.filename, 'r')
        elif self.filename.endswith(".bz2"):
            f = bz2.BZ2File(self.filename, 'r')
        else:
            f = open(self.filename, 'r')  # FIXME: we need rb for correct behaviour on Windows
        self._file_obj = FileWithBackspaces(f)

        self._range_begin_pos = self._find_pos(self.begin_time) if self.begin_time else None
        self._range_end_pos = self._find_pos(self.end_time, before=False) if self.end_time else None

        self.rewind()

        if self._range_begin_pos:
            self._file_obj.seek(self._range_begin_pos, os.SEEK_SET)

    def close(self):
        if self._file_obj != sys.stdout:
            self._file_obj.close()
            self._file_obj = None

    def rewind(self):
        self._file_obj.rewind()
        self._curr_line_begin_pos = self._file_obj.tell()
        self._curr_line_end_pos = None

    def fetch_line(self):

        while True:
            self._curr_line_begin_pos = self._file_obj.tell()
            line = self._file_obj.readline()
            self._curr_line_end_pos = self._file_obj.tell()

            if self._curr_line_begin_pos is not None and self._range_end_pos is not None and \
                    self._curr_line_begin_pos >= self._range_end_pos:
                return None, None

            if not line:
                return None, None
            try:
                dt, tail = self._timeparser.parse(str(line))
                return dt, tail.strip()
            except TimeParserException:
                pass

    def readlines_with_time(self):
        while True:
            dt, tail = self.fetch_line()
            if not dt:
                break
            yield dt, tail

    def _find_pos(self, needle_dt, before=True):
        """
        Binary search a file for matching lines.
        Returns the first line in the file which has datetime >= needle_dt
        """

        # Must be greater than the maximum length of any line.
        max_line_len = 2 ** 16

        self._file_obj.seek(0, os.SEEK_END)

        start = pos = 0
        end = self._file_obj.tell()

        # Limit the number of times we search
        for repeat in range(50):

            if end <= start:
                return end

            last = pos
            prev_line_end_pos = self._curr_line_end_pos
            delta = ((end - start) // 2)

            # Move the cursor to a newline boundary, ensure it is moved
            while prev_line_end_pos == self._curr_line_end_pos:
                pos = start + delta
                self._file_obj.seek(pos)

                line_dt, line_tail = self.fetch_line()
                if not line_dt:
                    # last try
                    delta = 0
                    prev_line_end_pos = self._curr_line_end_pos
                    continue

                if delta == 0:
                    if before:
                        return start if line_dt >= needle_dt else end
                    else:
                        return start if line_dt >= needle_dt else end
                delta //= 2

            if not line_dt:
                return start

            if line_dt == needle_dt or pos == last:

                # Seek back until we no longer have a match
                while True:
                    self._file_obj.seek(max(0, -max_line_len), os.SEEK_SET)
                    dt, _ = self.fetch_line()
                    if dt != needle_dt:
                        break

                # Seek forward to the first match
                for rpt in range(max_line_len):
                    dt, _ = self.fetch_line()
                    if dt == needle_dt:
                        break

                return self._curr_line_begin_pos

            elif line_dt < needle_dt:
                start = self._curr_line_end_pos
            else:
                end = self._curr_line_begin_pos
        else:
            raise LargeFileException('Binary search failed')  # pragma: no cover


##############################################################################
# Autotests
##############################################################################


def _coverage():
    dir_path = os.path.dirname(os.path.realpath(__file__))

    for filename in ['large_file.txt', 'large_file.gz', 'large_file.tgz']:
        for case in [(10, None, None),
                     (9, None, "2018-06-05 04:05:01"),
                     (6, "2018-05-05 02:01:00.012000", None),
                     (0, "2018-05-05 00:00:00", "2018-05-05 00:00:03"),
                     (10, "2018-05-05 00:00:00", "2020-05-05 00:00:00"),
                     (2, "2018-05-05 00:00:00", datetime.datetime.strptime('May 5 2018  1:02AM', '%b %d %Y %I:%M%p')),
                     (5, "2018-05-05 03:04:00", "2018-06-10 03:04:00")]:
            lines, begin, end = case
            f = LargeLogFile(os.path.join(dir_path, '.testdata', 'large_file.txt'), begin, end)
            seen_lines = [l for l in f.readlines_with_time()]
            if lines != len(seen_lines):
                raise RuntimeError("file %s, case '%s' failed! %d lines found instead of %d:\n  %s" %
                                   (filename, case, len(seen_lines), lines,
                                    "\n  ".join(["%s %s" % (d, l) for d, l in seen_lines])))
            print("file %s, case '%s': OK" % (filename, str(case)))
            f.close()

    print("OK")


if __name__ == "__main__":
    _coverage()
