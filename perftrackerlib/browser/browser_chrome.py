#!/usr/bin/env python

from __future__ import print_function, absolute_import

# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

"""
The Chrome browser helper
"""


import logging
import re
import os
import datetime
import json
import sys
import tempfile
import atexit
import shutil

from .utils import parse_url, get_val
from .browser_base import BrowserExc
from .browser_webdriver import BrowserWebdriver, abort
from .page import PageEvent, PageRequest

try:
        from selenium import webdriver
        from selenium.common.exceptions import WebDriverException
        import psutil
except ImportError as e:
        abort(e)


reChromeEvents = re.compile("DEVTOOLS EVENT ([\w\.]+)([\n\W\w]*)")


class BrowserChrome(BrowserWebdriver):
    engine = "chrome"
    skip_urls = ["google.com", "gstatic.com"]

    def _skip_url(self, page, url):
        if url and url.startswith("chrome-search:"):
            return True

        return BrowserWebdriver._skip_url(self, page, url)

    def _add_event(self, page, name, params):
        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
            self.log_debug(name + '\n' + json.dumps(params, indent=4))

        if not self._ts_offset:
            # 1. some Chrome browsers log 'wallTime'
            try:
                self._ts_offset = 1000 * (float(params['wallTime']) - float(params['timestamp']))
                self.log_debug("_ts_offset = %d, detected from request wallTime timestamp" % self._ts_offset)
            except KeyError:
                pass

            if name == "Network.requestWillBeSent":
                # 2. but some do not log 'wallTime', so lets align browser timestamp with time of first request
                try:
                    _, netloc, _ = parse_url(params['documentURL'])
                    if netloc == self._first_navigation_netloc:
                        self._ts_offset = 1000 * (self._first_navigation_ts - float(params['timestamp']))
                        self.log_debug("_ts_offset = %d, detected from requestWillBeSent event" % self._ts_offset)
                except KeyError:
                    raise BrowserExc("can't determine timestamp offset between wall time and browser log timestamps")

            if not self._ts_offset:
                self.log_debug("skip event '%s'" % name)
                return

        try:
            ts = 1000 * float(params['timestamp']) + self._ts_offset
            page.process_activity(name, ts)
        except KeyError:
            ts = None

        e = PageEvent(name, params)
        if name == "Network.requestWillBeSent":
            if params['request']['url'].startswith("data:"):
                return

            req_id = params['requestId']
            if page.get_request(req_id):
                self.log_debug("WARNING: Response has been already received for req %s" % req_id)

            url = params['request']['url']
            if self._skip_url(page, url):
                self.log_debug("ignore/skip request to: %s" % url)
                return

            r = PageRequest(page, req_id)
            r.method = params['request']['method']
            r.header = params['request']['headers']
            if r.method == "POST" and 'postData' in params['request']:
                r.params = params['request']['postData']
            r.url = url
            r.start(ts)
            page.add_request(r)

        elif name in ("Network.responseReceived", "Network.dataReceived", "Network.requestServedFromCache",
                      "Network.loadingFinished", "Network.loadingFailed"):
            req_id = params['requestId']
            if not page.get_request(req_id):
                url = get_val(params, ['response', 'url'], '')
                if url.startswith("data:"):
                    return

                if self._skip_url(page, url):
                    self.log_debug("ignore/skip response from: %s" % url)
                    return

                self.log_debug("WARNING: got '%s' for unsent request %s" % (name, req_id))
                return

            r = page.get_request(req_id)

            if get_val(params, ['response', 'fromDiskCache'], False):
                r.cached = True

            if name == "Network.responseReceived":
                r.set_type(params['type'])
                r.connection_reused = get_val(params, ['response', 'connectionReused'], False)
                r.status = get_val(params, ['response', 'status'], 'unknown')
                r.keepalive = get_val(params, ['response', 'headers', 'Connection'], '') in ("Keep-Alive", "keep-alive")
                r.gzipped = get_val(params, ['response', 'headers', 'Content-Encoding'], '') == "gzip"
                r.content_length = int(get_val(params, ['response', 'headers', 'Content-Length'], 0))

                # response header normally contains cookie
                cookie = get_val(params, ['response', 'requestHeaders', 'Cookie'], None)
                if cookie:
                    r.header['Cookie'] = cookie

                if not r.status:
                    self.log_debug("WARNING: Can't parse status for request %s" % req_id)
                r.complete(ts)

            elif name == "Network.dataReceived":
                r.length += int(params['dataLength'])
                r.completed = False

            elif name == "Network.requestServedFromCache":
                r.cached = True
                r.complete(ts)

            elif name == "Network.loadingFinished":
                r.complete(ts)

            elif name == "Network.loadingFailed":
                r.status = params['errorText']
                r.set_type(params['type'])
                r.complete(ts)

    def _browser_parse_logs(self, page, logs):
        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
            self.log_debug("LOGS: %s" % json.dumps(logs, indent=4))

        if 'value' not in logs:
            return
        for val in logs['value']:
            if val['message'].startswith("{"):
                try:
                    j = json.loads(val['message'])
                    self._add_event(page, j['message']['method'], j['message']['params'])
                    continue
                except ValueError:
                    pass

            if type(val['message']) == str:
                v = val['message']
            else:
                v = val['message'].decode('string-escape')
            if v.startswith("DEVTOOLS EVENT"):
                m = reEvents.match(v)
                if m:
                    self._add_event(page, m.group(1), m.group(2))

    def _browser_get_events(self, page):
        self._browser_parse_logs(page, self.driver.execute('getLog', {'type': 'browser'}))
        self._browser_parse_logs(page, self.driver.execute('getLog', {'type': 'performance'}))

    def _browser_get_rss_kb(self):
        rss = 0
        proc = psutil.Process(self.pid)
        if not proc:
            self.log_error("Something went wrong and browser is dead!")
            sys.exit(-1)
        children = proc.get_children() if hasattr(proc, 'get_children') else proc.children()
        for p in children:
            rss += p.memory_info().rss
        return rss / 1024

    def browser_start(self):
        d = tempfile.mkdtemp()
        self.log_debug("Temporary user data directory: %s" % d)
        atexit.register(shutil.rmtree, d)

        options = webdriver.ChromeOptions()
        options.add_argument("--window-size=%d,%d" % (self.resolution[0], self.resolution[1]))
        options.add_argument("--no-sandbox")
        options.add_argument("--user-data-dir=%s" % d)
        options.add_argument("--disable-setuid-sandbox")

        descaps = options.to_capabilities()

        descaps['loggingPrefs'] = {'performance': 'DEBUG', 'browser': 'ALL', 'driver': 'ALL'}

        # w/a for hanging Chrome, see https://github.com/SeleniumHQ/docker-selenium/issues/87
        os.environ["DBUS_SESSION_BUS_ADDRESS"] = "/dev/null"

        try:
            self.driver = webdriver.Chrome(desired_capabilities=descaps,
                                           service_args=['--verbose', '--log-path=%s' % self.log_path])
        except WebDriverException as e:
            abort(e)

        return self.driver.service.process.pid

    def navigation_reset(self):
        self.navigate_to("chrome://version/")


##############################################################################
# Autotests
##############################################################################


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        b = BrowserChrome()
    except BrowserExc as e:
        sys.exit(-1)
    b.navigate_to("https://example.com/")
    b.browser_stop()
