#!/usr/bin/env python

from __future__ import print_function, absolute_import

# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

"""
Base browser library
"""

import sys
import time
import tempfile
import re
import logging
import os
import threading
import traceback
import datetime
import platform

if sys.version_info[0] < 3:
    import httplib
else:
    import http.client as httplib

# time to wait for the incomplete requests
DEFAULT_NAV_TIMEOUT = 60.0

# time to wait for browser ajax activity (in seconds) to consider page load is fully complete
DEFAULT_AJAX_THRESHOLD = 2.0

"""
TODO:
- Network connection simulation (3G, LTE, etc) (Use tc on linux, pfctl on Mac ?)
- IE support (needed for Windows)
- handle 'Server not found'
"""

"""
Glossary

Browser classes:

  BrowserBase class    - base browser class representing API available to the library users
  |- BrowserWebdriver  - base class for webdriver (i.e. selenium) based browsers (Chrome, Firefox)
  |  |- BrowserChrome   - Chrome browser
  |  `- FirefoxBrowser  - Firefox browser
  `- BrowserPython      - Python browser
     `- CPBase          - Control Panel base class

Page classes:

  PageStats             - class collecting all the page request to given URL
  Page                  - class describing a page request and response (i.e. navigation item in the prowser)
  PageRequest           - class describing individual sub-requests of a page (css, js, html, etc)
  PageTimeline          - represents page timeline
  PageWithActions       - represents some kind of the html page model with focus on actions (URLs)

"""

from .page import Page, PageStats, PageTimeline


################################################################
# Exceptions
################################################################


class BrowserExc(Exception):
    def __init__(self, msg=""):
        Exception.__init__(self, "%s" % msg)
        self.message = "browser module exception: %s" % msg


class BrowserExcTimeout(BrowserExc):
    def __init__(self, msg=""):
        BrowserExc.__init__(self, "%s" % msg)
        self.message = "browser module timeout: %s" % msg


class BrowserExcNotImplemented(BrowserExc):
    pass


class BrowserExcNotSupported(BrowserExc):
    """
    Raise this exception if for instance given method is intentionally not supported in a class
    """
    def __init__(self):
        BrowserExc.__init__(self)
        tb = traceback.extract_tb()  # FIXME
        self.message += "method %s is not supported in %s" % (str(tb), "FIXME Class")


class BrowserExcError(BrowserExc):
    def __init__(self, message):
        BrowserExc.__init__(self)
        self.message += message


################################################################
# Browser class
################################################################

_browser_id = {}


class BrowserBase:
    engine = 'basebrwsr'

    def __init__(self, headless=True, resolution=(1440, 900), cleanup=True, telemetry_fname=None,
                 log_path='auto', nav_timeout=DEFAULT_NAV_TIMEOUT, ajax_threshold=DEFAULT_AJAX_THRESHOLD):
        self.history = []
        self.page_stats = {}

        self._name = self._init_name()

        self.resolution = resolution
        self.driver = None
        self.display = None
        self.pid = None
        self.nav_timeout = nav_timeout
        self.ajax_threshold = ajax_threshold

        if log_path == 'auto':
            self.log_path = tempfile.NamedTemporaryFile(delete=cleanup).name
        else:
            self.log_path = log_path

        if telemetry_fname:
            self.telemetry_log = open(telemetry_fname, 'a', 0)
        else:
            self.telemetry_log = None

        if self.log_path:
            self.log_info("log path: %s" % self.log_path)

        self._browser_display_init(headless, resolution)
        self.pid = self.browser_start()
        if not self.pid:
            raise BrowserExc("Browser initialization failed")

        self._base_rss_kb = self._browser_get_rss_kb()

        # looping

        self._loop_locations = []
        self._loop_stop = True
        self._loop_thread = None
        self._loop_sleep_sec = 0

    def _init_name(self):
        global _browser_id
        id = _browser_id.get(self.engine, 0)
        _name = "%s#%02d" % (self.engine, id)
        _browser_id[self.engine] = id + 1
        return _name

    def __del__(self):
        self.browser_stop()

    # === browser* methods ===#

    def _browser_clear_caches(self):
        """
        clear browser caches
        """
        self.history = []

    def _browser_navigate(self, location, cached=True, name=None):
        raise NotImplementedError

    def _browser_wait(self, page, timeout=None):
        """
        wait for navigation request completion
        """
        raise NotImplementedError

    def _browser_warmup_page(self, location, name=None):
        """
        warmup (i.e. cache) a page
        """
        raise NotImplementedError

    def _browser_display_init(self, headless, resolution):
        return

    def _browser_get_current_url(self):
        raise NotImplementedError

    def browser_get_name(self):
        raise NotImplementedError

    def browser_get_version(self):
        raise NotImplementedError

    def browser_get_platform(self):
        raise platform.platform()

    def _browser_get_rss_kb(self):
        return 0

    def browser_get_ram_usage_kb(self):
        return self._browser_get_rss_kb() - self._base_rss_kb

    def browser_get_screenshot_as_file(self, filename):
        raise NotImplementedError

    def browser_get_page_timeline(self, page):
        return PageTimeline(page)

    def browser_start(self):
        raise NotImplementedError

    def browser_stop(self):
        """
        exit from the driver
        """
        raise NotImplementedError

    def browser_reset(self):
        """Reset cookies and connection pools"""
        pass

    # === domain methods === #

    def domain_get_cookies(self, url):
        raise NotImplementedError

    def domain_set_cookies(self, url, cookies):
        raise NotImplementedError

    def domain_set_cookie(self, url, key, val=None, path=None):
        raise NotImplementedError

    def domain_set_header(self, url, key, val):
        raise NotImplementedError

    def domain_set_session(self, url, session_id):
        raise NotImplementedError

    # ==== logging === #

    def log_debug(self, msg):
        logging.debug(msg, extra={'browser': self._name})

    def log_info(self, msg):
        logging.info(msg, extra={'browser': self._name})

    def log_warning(self, msg):
        logging.warning(msg, extra={'browser': self._name})

    def log_error(self, msg):
        logging.error(msg, extra={'browser': self._name})

    def event_log(self, p):
        if not self.telemetry_log:
            return
        self.telemetry_log.write(p.serialize())

    # === Navigation looping === #

    def _loop(self):
        try:
            while not self._loop_stop:
                for loc in self._loop_locations:
                    self.navigate_to(loc)
                time.sleep(self._loop_sleep_sec)

        except httplib.BadStatusLine as e:
            pass
        except RuntimeError:
            logging.error("traceback:\n" + traceback.format_exc())

    def loop_start(self, locations, sleep_sec=0):
        self.log_debug("loop_start():\n   %s" % "\n   ".join([str(loc) for loc in locations]))
        if self._loop_thread:
            self.loop_stop()

        self._loop_locations = locations
        self._loop_sleep_sec = sleep_sec
        self._loop_stop = False
        self._loop_thread = threading.Thread(target=self._loop)
        self._loop_thread.start()

    def loop_stop(self):
        self.log_debug("loop_stop()")
        self._loop_stop = True

    def loop_wait(self):
        self.log_debug("loop_wait()")
        self._loop_thread.join()
        self._loop_thread = None

    # === navigation API === #

    def navigate_to(self, location, timeout=None, cached=True, stats=True, name=None):
        """
        navigate to given url or page in cached/uncached mode
        """
        url = location.url if isinstance(location, Page) else location

        scheme = url.split(":")[0]

        if scheme not in ("http", "https", "file", "about", "chrome"):
            url = "http://%s" % url

        if isinstance(location, Page):
            location.url = url
        else:
            location = url

        if cached is None:
            self.log_info("Navigate to: %s" % url)
        else:
            self.log_info("Navigate to: %s %s" % (url, "CACHED" if cached else "UNCACHED"))

            if cached and url not in self.history:
                self._browser_warmup_page(location, name=name)
            elif not cached and url in self.history:
                self._browser_clear_caches()

        p = self._browser_navigate(location, cached=cached, name=name)
        self._browser_wait(p, timeout=timeout)

        self.history.append(url)

        if stats:
            key = p.get_key()
            if key not in self.page_stats:
                self.page_stats[key] = PageStats(len(self.page_stats))
            self.page_stats[key].add_iteration(p)

        self.event_log(p)
        self.log_info("Navigation completed: %s %s, dur %d ms" % (url, "CACHED" if cached else "UNCACHED", p.dur))
        return p

    def navigation_reset(self):
        pass

    # === printing facilities === #

    @staticmethod
    def print_stats_title(title):
        print("")
        print(title.upper())
        print("=" * len(title))
        print("")

    def print_browser_info(self):
        raise NotImplementedError


##############################################################################
# Autotests
##############################################################################


if __name__ == "__main__":
    try:
        b = BrowserBase()
    except NotImplementedError:
        print("OK")
        sys.exit(0)
    sys.exit(-1)
