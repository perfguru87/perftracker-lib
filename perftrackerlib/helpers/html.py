#!/usr/bin/env python

from __future__ import print_function, absolute_import

# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

"""The library to work with HTML entities
"""

_html_escape_table = {
    "&": "&amp;",
    '"': "&quot;",
    "'": "&apos;",
    ">": "&gt;",
    "<": "&lt;",
    "\\": "&#92;"
}


def pt_html_escape(text):
    return "".join(_html_escape_table.get(c, c) for c in text)


##############################################################################
# Autotests
##############################################################################


if __name__ == "__main__":
    pt_html_escape("<a href='http://www.google.com/?a=1&b=2'>link</a>")
    print("OK")
