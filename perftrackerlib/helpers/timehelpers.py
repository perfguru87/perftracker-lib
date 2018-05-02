#!/usr/bin/env python

from __future__ import print_function, absolute_import

# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

"""
Time/datetime helpers
"""

import datetime


def dt_seconds_between(dt_new, dt_old):
    delta = dt_new - dt_old
    return float(delta.days * 3600 * 24 + delta.seconds) + delta.microseconds / 1000000.0


def dt2ts_utc(d):
    return dt_seconds_between(d, datetime.datetime(1970, 1, 1))


##############################################################################
# Autotests
##############################################################################


if __name__ == "__main__":
    assert dt2ts_utc(datetime.datetime(1970, 1, 2)) == 24 * 60 * 60
    print("OK")
