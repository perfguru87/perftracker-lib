#!/usr/bin/env python

from __future__ import print_function

# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

"""The library to parse time from a text string
"""

import sys
import datetime
import time

FORMATS = ['%Y-%m-%d %H:%M:%S %f', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M',
           '%b %d %H:%M:%S %f', '%b %d %H:%M:%S.%f', '%b %d %H:%M', '%b %d %H:%M:%S',
           '%b %d %Y %H:%M:%S %f', '%b %d %Y %H:%M:%S.%f', '%b %d %Y %H:%M', '%b %d %Y %H:%M:%S',
           '%b %d %Y %I:%M:%S%p', '%b %d %Y %I:%M%p', '%b %d %Y %I:%M:%S%p %f', '%b %d %Y %I:%M:%S%p.%f']


class TimeParserException(RuntimeError):
    pass


class TimeParser:
    def __init__(self):
        self.fmt = None
        self.words_cnt_guess = 0
        self.words_cnt_max = 0
        self.words_cnt_min = None
        self.formats = [None] + FORMATS

        for fmt in self.formats:
            if not fmt:
                continue
            words = len(fmt.split())
            if words > self.words_cnt_max:
                self.words_cnt_max = words
            if self.words_cnt_min is None or words < self.words_cnt_min:
                self.words_cnt_min = words

    def _parse_text(self, fmt, text):
        try:
            if fmt in ['%b %d %H:%M:%S %f', '%b %d %H:%M', '%b %d %H:%M:%S']:
                return datetime.datetime.strptime(text, fmt).replace(datetime.datetime.now().year)
            return datetime.datetime.strptime(text, fmt)
        except ValueError:
            return None

    def _parse_list(self, words, words_cnt):
        text = ' '.join(words[0:words_cnt])
        if self.formats[0]:
            d = self._parse_text(self.formats[0], text)
            if d:
                # fast path ends here
                return d, len(text)

        for fmt in self.formats:
            if fmt:
                d = self._parse_text(fmt, text)
                if d:
                    self.formats[0] = fmt
                    return d, len(text)
        return None, None

    def parse(self, text):
        ar = text.split(' ')
        if len(ar) >= self.words_cnt_guess:
            d, n = self._parse_list(ar, self.words_cnt_guess)
            if d:
                # fast path ends here
                return d, text[n:]

        for words in range(self.words_cnt_min, self.words_cnt_max + 1):
            d, n = self._parse_list(ar, words)
            if d:
                self.words_cnt_guess = words
                return d, text[n:]

        raise TimeParserException("can't parse datetime from: %s" % text)


##############################################################################
# Autotests
##############################################################################


def _test():
    tp = TimeParser()

    for line in ["2011-07-22 00:00:01 abc", "May 05 11:45:00 xyz", "Oct 12 2008 1:33:45PM a b c"]:
        d = tp.parse(line)
        print("Parsing: %s -> %s" % (line, str(d)))

    try:
        print(tp.parse("2011 x y z"))
        raise Exception("bogus time parser")
    except TimeParserException:
        pass

    # small performance test
    lines = 10000
    t = time.time()
    for n in range(0, lines):
        d = tp.parse('2011-07-22 00:00:01 any line here')
    print("Parsing rate: %.0f lines/sec" % (lines / (time.time() - t)))

    print("OK")


if __name__ == "__main__":
    _test()
