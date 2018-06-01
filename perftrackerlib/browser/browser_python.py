#!/usr/bin/env python

from __future__ import print_function, absolute_import

# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

"""
Naive Python browser, it is able to repeat requests traces collected from a real browser
"""

import os
import sys
import logging
import copy
import socket
import re
import time
import platform
from threading import Lock
from multiprocessing.dummy import Pool as ThreadPool

if sys.version_info[0] < 3:
    from Cookie import SimpleCookie
else:
    from http.cookies import SimpleCookie

from .browser_base import BrowserBase, BrowserExc
from .page import Page, PageRequest, PageRequestsGroup, PageWithActions
from .utils import parse_url, extract_cookies
from ..helpers.httppool import HTTPPool
from . import httputils


class BrowserPythonNetlocData:
    def __init__(self, browser, netloc):

        # Remove standard port number from netloc string
        # Allowed by HTTP W3C and make some web-apps happy
        if ':' in netloc:
            nl = netloc.split(':')
            if nl[1] == '80' or nl[1] == '443':
                netloc = nl[0]

        self.browser = browser
        self.netloc = netloc

        self.cookies = SimpleCookie()
        self.httpool = {}
        self.lock = Lock()

        self.header = {}
        self.header['User-Agent'] = 'Mozilla/5.0 (X11; Linux x86_64; rv:31.0) Gecko/20100101 Firefox/31.0 PYTHON'
        self.header['Connection'] = 'keep-alive'
        self.header['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        self.header['Accept-Language'] = 'en-US,en;q=0.5'
        self.header['Content-Type'] = 'application/x-www-form-urlencoded'
        self.header['Host'] = self.netloc

    def _get_http_pool(self, scheme):
        if scheme not in self.httpool:
            loc = "%s://%s" % (scheme, self.netloc)
            self.browser.log_debug("allocating connection pool to %s" % loc)
            self.httpool[scheme] = HTTPPool("%s" % loc)
        return self.httpool[scheme]

    def __del__(self):
        for pool in self.httpool.values():
            pool.clear()

    def set_cookie(self, url, key, val=None, path=None):
        self.browser.log_debug("set cookie: %s, %s=%s" % (url, key, str(val)))

        scheme, netloc, path = parse_url(url)
        with self.lock:
            if type(key) == 'dict':
                c = key
                self.cookies[c['name']] = c
            elif val:
                self.cookies[key] = val
                if path:
                    self.cookies[key]["path"] = path
            elif path in self.cookies:
                del self.cookies[key]

    def set_header(self, key, val):
        self.browser.log_debug("set header: %s=%s" % (key, val))
        with self.lock:
            if val is not None:
                self.header[key] = val
            elif key in self.header:
                del self.header[key]

    def get_cookies_str(self, url):
        """
        get_cookies_str() returns only the cookies applicable to given *url*
        """

        _, _, path = parse_url(url)

        path_cookies = {}
        for key, morsel in self.cookies.items():
            p = morsel["path"] if morsel["path"] else "/"
            if key not in path_cookies:
                path_cookies[key] = {}
            path_cookies[key][p] = morsel.value

        cookies = {}

        for key, paths in path_cookies.items():
            # sort by string length: ["/home/path", "/home", "/"]
            for p in sorted(paths.keys(), lambda x: len(x), reverse=True):
                if path.startswith(p):
                    cookies[key] = paths[p]
                    break

        return "; ".join("%s=%s" % (key, val) for key, val in cookies.items())

    def _get_redirected_request(self, req, response):
        new_req = None
        if req.status in [301, 302, 303]:
            new_req = req.duplicate()
            new_req.method = 'GET'
            new_req.params = None
            new_req.url = response.getheader('location')
        elif self.browser.js_redirects:
            page_actions = httputils.PageActionsExtractor(req.data)
            redirect = page_actions.get_action()
            if redirect:
                new_req = req.duplicate()
                new_req.method = redirect.method
                new_req.params = redirect.get_params()
                new_req.url = redirect.url
                new_req.header['Cookie'] = self.browser.browser_get_cookies_str(req.url)
            req.page_actions = page_actions

        if new_req:
            new_req.validator = None
            new_req.header['Cookie'] = self.browser.browser_get_cookies_str(req.url)
            if not new_req.url.startswith('http'):
                new_req.update_netloc(req.url)
            _, new_req.header['Host'], _ = parse_url(new_req.url)
            return new_req

        return None

    def _execute_page_request(self, pool, page, req, path_with_args):
        assert(req.method == 'POST' or not req.params)  # only POST request may have params

        with pool.borrow() as (conn, is_new):
            # conn.set_debuglevel(1)
            conn.request(req.method, path_with_args, req.params, req.header)
            self.header['Referer'] = req.url
            response = conn.getresponse()
            req.status = response.status
            req.data = response.read()

            self.browser.log_debug(" req %s HTTP response: %s, headers: %s" %
                                   (req.id, req.status, response.getheaders()))

            # handle new cookies
            for cookie in extract_cookies(response):
                if sys.version_info[0] < 3 and isinstance(cookie, unicode):
                    cookie = cookie.encode('ascii', 'ignore')
                self.cookies.load(cookie)

            # handle redirection
            new_req = self._get_redirected_request(req, response)
            if new_req:
                self.browser.log_debug(" req %s, redirect to %s" % (new_req.id, new_req.url))
                page.add_request(new_req)

                # FIXME:
                # 1. _get_netloc_data is private method of the browser.

                self.browser._get_netloc_data(new_req.url).execute_page_request(page, new_req)
                req.status = new_req.status
                req.data = new_req.data

            if req.valid_statuses and req.status not in req.valid_statuses:
                raise BrowserExc(' req %s, %s %s status %d'
                                 (req.id, req.method, req.url, req.status))

        if self.browser.validation:
            req.validate_response(req.data)

        req.complete()
        return

    def execute_page_request(self, page, req):

        scheme, netloc, path_with_args = parse_url(req.url, args=True)

        if scheme not in ("http", "https", "ftp"):
            msg = "Can't execute request on URL with unsupported scheme: %s, %s" % (scheme, netloc)
            self.browser.log_error(msg)
            raise BrowserExc(msg)

        req.start()

        pool = self._get_http_pool(scheme)
        # 10 - is technological retry count to handle closed keep-alive connections
        for loop in range(10):
            try:
                self._execute_page_request(pool, page, req, path_with_args)
                return

            except pool.temporary_errors as ex:
                raise  # aandreev
                # usually it means server has closed keep-alive connection due to timeout. lets retry
                self.browser.log_debug("HTTP Exception: %s %s: %s %s, connection closed? retrying" %
                                       (req.method, req.url, type(ex), str(ex)))
                req.status = str(type(ex))
                time.sleep(0.1 * loop)

            except pool.fatal_errors as ex:
                req.status = str(type(ex))
                req.complete()
                self.browser.log_error("HTTP Exception: %s %s: %s %s" % (req.method, req.url, type(ex), str(ex)))
                return

        req.complete()
        self.browser.log_error("HTTPException: %s %s, all retries failed" % (req.method, req.url))

    def execute_page_request_parallel(self, page, reqs, parallel=8):
        if not len(reqs):
            return
        if len(reqs) == 1:
            self.execute_page_request(page, reqs[0])
            return

        def execute(arg):
            global data
            page, req = arg
            try:
                self.execute_page_request(page, req)
            except RuntimeError:
                import traceback
                self.browser.log_error("traceback:\n" + traceback.format_exc())
            return 0

        args = [(page, req) for req in reqs]

        if parallel > len(reqs):
            parallel = len(reqs)

        pool = ThreadPool(parallel)
        pool.map(execute, args)
        pool.close()
        pool.join()


class BrowserPython(BrowserBase):
    engine = "pybrwsr"

    def __init__(self, headless=True, validation=True, cleanup=True, max_connections=8,
                 js_redirects=False, log_path=None):
        BrowserBase.__init__(self, cleanup=cleanup, log_path=log_path)

        self.validation = validation
        self.max_connections = max_connections
        self.js_redirects = js_redirects  # try to parse page to detect JS and other ways of redirect

        self._netloc_data = {}

    def _get_netloc_data(self, url):
        _, netloc, _ = parse_url(url)
        if netloc not in self._netloc_data:
            self._netloc_data[netloc] = BrowserPythonNetlocData(self, netloc)
        return self._netloc_data[netloc]

    def _browser_navigate(self, location, cached=True, name=None):
        if isinstance(location, Page):
            page = copy.deepcopy(location)
        else:
            return self._http_request("GET", location)

        if not len(page.requests_groups):
            raise BrowserExc("BrowserPython._browser_navigate() - bug: requests group is empty!")

        page.browser = self
        page.start()

        for g in page.requests_groups:
            reqs = g.get_uncached_reqs()
            if not reqs:
                continue
            self._get_netloc_data(page.url).execute_page_request_parallel(page, reqs, parallel=self.max_connections)

        page.complete(self)
        return page

    def _browser_wait(self, page, timeout=None):
        return

    def _browser_warmup_page(self, location, name=None):
        return

    def browser_get_name(self):
        return "Python HTTP/1.x browser"

    def browser_get_version(self):
        return "Python %s" % platform.python_version()

    def browser_set_cookie(self, url, key, val=None, path=None):
        self._get_netloc_data(url).set_cookie(url, key, val, path)

    def browser_get_cookies_str(self, url):
        return self._get_netloc_data(url).get_cookies_str(url)

    def browser_set_header(self, url, key, val):
        self._get_netloc_data(url).set_header(key, val)

    def browser_start(self):
        return os.getpid()

    def browser_stop(self):
        pass

    def browser_reset(self):
        self._netloc_data.clear()

    # === BrowserPython specific === #

    def _http_request(self, method, url, params=None, validator=None, header=None, valid_statuses=None):
        page = Page(self, url)
        req = PageRequest(page)

        req.header.update(self._get_netloc_data(url).header)
        req.header['Cookie'] = self._get_netloc_data(url).get_cookies_str(url)
        if header:
            req.header.update(header)

        req.url = url
        req.method = method
        req.params = params
        req.validator = validator
        req.valid_statuses = valid_statuses

        page.add_request(req)
        page.requests_groups.append(PageRequestsGroup(req))

        ret = self._browser_navigate(page)
        return ret

    def http_get(self, url, params=None, validator=None, header=None, valid_statuses=None):
        return self._http_request("GET", url, params, validator, header, valid_statuses).data

    def http_post(self, url, params=None, validator=None, header=None, valid_statuses=None):
        return self._http_request("POST", url, params, validator, header, valid_statuses).data

    def http_action(self, method, url, params=None, validator=None, header=None, valid_statuses=None):
        # Specialized version: http request executor with extended return
        page = self._http_request(method, url, params, validator, header, valid_statuses)
        request = page.requests[-1]  # get last request in redirected requests chain
        return PageWithActions(request.page_actions, page.data, request.url)

    # === printing facilities === #

    def print_browser_info(self):
        self.print_stats_title("Browser summary")
        print("  - platform: %s" % os.sys.platform)
        print("  - browser:  %s" % self.engine)
        print("  - PID:      %d" % self.pid)


##############################################################################
# Autotests
##############################################################################


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    b = BrowserPython()
    b.navigate_to("https://example.com/")
    b.browser_stop()
