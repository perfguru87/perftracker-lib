#!/usr/bin/env python

from __future__ import print_function, absolute_import

# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

"""
The Firefox browser helper
"""

import logging
import re
import os
import datetime
import time
import json
import sys

from ..helpers.timeparser import TimeParser
from ..helpers.largelogfile import LargeLogFile
from ..helpers import timehelpers

from .utils import parse_url, get_val
from .browser_webdriver import BrowserWebdriver, abort
from .browser_base import BrowserExc
from .page import PageRequest, PageTimeline
from . import httputils

try:
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException
    import psutil
except ImportError as e:
    abort(e)


# reFF = re.compile("(\d+-\d+-\d+ \d+:\d+\:\d+.\d+) UTC - [-\d]+\[([\d\w]+)\]:\s+(.*)\n")
reFF = re.compile(" UTC - [-\d]+\[([\d\w]+)\]:\s+(.*)\n")
reFFTxnInit = re.compile("^nsHttpTransaction::Init \[this=([\d\w]+).*$")
reFFProcessData = re.compile("^nsHttpTransaction::ProcessData \[this=([\d\w]+) count=(\d+)\].*$")
reFFReadFromcache = re.compile("^nsHttpChannel::ReadFromCache \[this=([\d\w]+)] Using cached copy of: (.*)$")
reFFDestroyTxn = re.compile("^Destroying nsHttpTransaction @([\d\w]+).*$")


class BrowserFirefox(BrowserWebdriver):
    engine = "firefox"
    skip_urls = ["cdn.mozilla.net", "mozilla.org", "mozilla.com", "ocsp.digicert.com", "openh264.org"]

    def __init__(self, *args, **kwargs):
        BrowserWebdriver.__init__(self, *args, **kwargs)
        self._last_seen_dt = datetime.datetime.utcnow()

    def _skip_url(self, page, url):
        if url and url.startswith("about:"):
            return True

        return BrowserWebdriver._skip_url(self, page, url)

    def _browser_get_rss_kb(self):
        return psutil.Process(self.pid).memory_info().rss / 1024

    def browser_start(self):
        os.environ['NSPR_LOG_FILE'] = self.log_path
        os.environ['NSPR_LOG_MODULES'] = 'timestamp,nsHttp:5,nsSocketTransport:5,nsStreamPump:5,nsHostResolver:5'

        profile = webdriver.FirefoxProfile()
        profile.accept_untrusted_certs = True

        # sometimes (bug? race?) firefox fails to start wihout clear reason, so lets try to restart it several times
        retry = 5
        while True:
            try:
                self.driver = webdriver.Firefox(firefox_profile=profile)
            except WebDriverException as e:
                if retry:
                    self.log_warning("firefox start failed, retrying...")
                    time.sleep(1)
                    retry -= 1
                    continue
                self.log_error("Firefox browser start failed, see browser logs here: %s" % self.log_path)
                if "Can't load the profile" in str(e):
                    # http://stackoverflow.com/questions/6682009/selenium-firefoxprofile-exception-cant-load-the-profile
                    self.log_error("Try to update Firefox and selenium: pip install -U selenium")
                if "geckodriver" in str(e):
                    self.log_error("Try to install geckodriver from https://github.com/mozilla/geckodriver/releases and"
                                   " put it to PATH")
                raise BrowserExc(str(e))
            break

        # old native firefox driver
        if self.driver.binary:
            return self.driver.binary.process.pid

        # geckodriver
        return self.driver.service.process.pid

    def navigation_reset(self):
        self.navigate_to("about:buildconfig")

    def _browser_get_events(self, page):
        thread2req = {}
        thread2resp = {}
        thread2txn = {}
        path2prot = {}

        tp = TimeParser()

        start = self._last_seen_dt

        self.log_debug("Reading %s starting from %s" % (self.log_path, start))

        log = LargeLogFile(self.log_path,
                           start.strftime("%Y-%m-%d %H:%M:%S.000000"),
                           "2099-01-01 00:00:00.000000")

        for dt, line in log.readlines_with_time():

            if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
                self.log_debug("LOG: %s" % line.strip())

            m = reFF.match(line)
            if not m:
                continue

            self._last_seen_dt = dt

            ts = timehelpers.dt2ts_utc(dt) * 1000
            thread = m.group(2)
            msg = m.group(3)

            m = reFFTxnInit.match(msg)
            if m:
                thread2txn[thread] = m.group(1)
                continue

            m = reFFProcessData.match(msg)
            if m:
                txn = m.group(1)
                thread2txn[thread] = txn
                req = page.get_request(txn)
                if req:
                    req.length += int(m.group(2))
                continue

            if msg.startswith("uri="):
                url = msg[4:]
                prot, domain, path = parse_url(url)
                path2prot["%s%s" % (domain, path)] = prot

            if msg.startswith("nsHttpChannel::ReadFromCache"):
                m = reFFReadFromcache.match(msg)
                if m:
                    txn = m.group(1)
                    r = PageRequest(page, txn)
                    r.method = "GET"
                    r.url = m.group(2)
                    r.status = 200
                    r.start(ts)
                    r.complete(ts)
                    r.cached = True
                    page.process_activity("read request from cache", ts)
                    page.add_request(r)

            m = reFFDestroyTxn.match(msg)
            if m:
                txn = m.group(1)
                r = page.get_request(txn)
                if r and not r.completed:
                    self.log_debug("WARNING: request '%s' has been completed abnormally" % r.id)
                    r.complete(ts)
                continue

            if thread not in thread2txn:
                continue

            txn = thread2txn[thread]

            if msg.startswith("http request"):
                thread2req[thread] = []
                page.add_request(PageRequest(page, txn))
                continue

            if thread in thread2req:
                if msg == "]":
                    req = page.get_request(txn)
                    r = httputils.HTTPRequestFromStr("\n".join(thread2req[thread]))
                    req.method = r.command

                    p = "%s%s" % (r.headers['host'], r.path)
                    _, domain, path = parse_url("http://" + p)
                    path = "%s%s" % (domain, path)

                    skip = False

                    if self._skip_url(page, path):
                        skip = True
                        self.log_debug("ignore/skip request to: %s" % path)
                    elif path in path2prot:
                        req.url = "%s://%s" % (path2prot[path], p)
                    else:
                        self.log_warning("Can't determine protocol for url: %s, skipping!" % p)
                        skip = True

                    if skip:
                        del thread2req[thread]
                        page.del_request(req)
                        continue

                    req.header = r.headers.dict

                    del thread2req[thread]
                    page.process_activity("request", ts)
                    req.start(ts)
                else:
                    thread2req[thread].append(msg)

            if msg.startswith("http response"):
                if page.get_request(txn):
                    thread2resp[thread] = []
                    continue

            if thread in thread2resp:
                if msg == "]":
                    req = page.get_request(txn)
                    if not req:
                        continue
                    r = httputils.HTTPResponseFromStr("\n".join(thread2resp[thread]))
                    # print("\n".join(thread2resp[thread]))
                    len = r.getheader('Content-Length')
                    if len:
                        req.content_length = int(len)
                    req.status = r.status
                    type = r.getheader("Content-Type")
                    if type:
                        req.set_type(type)
                    req.keepalive = r.getheader("Connection") in ("Keep-Alive", "keep-alive")
                    req.gzipped = r.getheader("Content-Encoding") == "gzip"

                    del thread2resp[thread]
                    page.process_activity("response", ts)
                    req.complete(ts)
                else:
                    thread2resp[thread].append(msg)


##############################################################################
# Autotests
##############################################################################


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        b = BrowserFirefox()
    except BrowserExc as e:
        sys.exit(-1)
    b.navigate_to("https://example.com/")
    b.browser_stop()
