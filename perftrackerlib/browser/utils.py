#!/usr/bin/env python

from __future__ import print_function, absolute_import

# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

"""
A set of various free function helpers
"""

import os
import re
import sys
import logging

try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

if sys.version_info[0] < 3:
    import httplib
else:
    import http.client as httplib


reRawCookie = re.compile(r"[Ss]et-[Cc]ookie:\s*(.*)\r\n")


def gen_urls_from_index_file(path):
    urls = []
    for p in path:
        if os.path.exists(p):
            if os.path.isdir(p):
                import glob
                urls += ["file://%s" % f for f in glob.glob(os.path.join(p, "*.htm*"))]
            else:
                urls += ["file://" + p]
        else:
            from .browser_python import BrowserPython
            b = BrowserPython()
            if not p.startswith("http"):
                p = "http://%s" % p
            txt = b.http_get(p)

            if txt.find("<title>Index of") >= 0:
                r = re.compile(">([-\w]+\.htm[l]?)<")
                for line in txt.splitlines():
                    m = r.search(line)
                    if m:
                        urls.append("%s%s" % (p, m.group(1)))
            else:
                urls += [p]
    return urls


def get_val(d, keys, default):
    v = d
    try:
        for k in keys:
            v = v[k]
    except KeyError:
        return default
    return v


_parsed_url = {}


def parse_url(url, server=False, args=False):
    global _parsed_url

    if not server and not args and url in _parsed_url:
        return _parsed_url[url]

    scheme = url.split(":")[0]

    _url = url if scheme in ("http", "https", "file") else "http://%s" % url

    p = urlparse(_url)
    scheme = p.scheme if p.scheme and p.scheme != "" else "http"

    if not p.netloc and not url.startswith("file://"):
        msg = "Can't parse network location for the following url: %s" % url
        logging.error(msg)
        from .browser_base import BrowserExc
        raise BrowserExc(msg)

    if server:
        return "%s://%s" % (scheme, p.netloc)

    path = p.path if p.path else "/"

    if args:
        pfx = "%s://%s" % (scheme, p.netloc)
        if url.startswith(pfx):
            return scheme, p.netloc, url[len(pfx):]

    netloc = p.netloc
    drop_port = ":443" if scheme == 'https' else ":80"
    if 'http' in scheme and p.netloc[-len(drop_port):] == drop_port:
        netloc = netloc.split(":")[0]

    _parsed_url[url] = scheme, netloc, path
    return _parsed_url[url]


def get_common_url_prefix(urls):
    netlocs = set()
    for url in urls:
        prot, netloc, _ = parse_url(url)
        netlocs.add("%s://%s" % (prot, netloc))

    if len(netlocs) == 1:
        return next(iter(netlocs))
    return ""


def extract_cookies(http_response):
    """
    Httplib specific function: HTTPResponse has some issue regarding
    to multiple 'set-cookie' headers. It just do ','.join(cookies), and
    there will be a trouble if cookie has ',' inside body (and it usually has!)
    So in case of multiple 'set-cookie' headers we should retrieve them
    manually (not so hard, actually)
    :param http_response: HTTPResponse object
    :return: list of strings with cookies
    """
    cookies = []
    if type(http_response) in (httplib.HTTPConnection, httplib.HTTPSConnection):
        raw_cookies = http_response.msg.getallmatchingheaders('set-cookie')
        if not raw_cookies:
            return []
        if len(raw_cookies) == 1:
            return [http_response.getheader('set-cookie')]

        for raw_cookie in raw_cookies:
            m = reRawCookie.search(raw_cookie)
            cookies.append(m.group(1))
        return cookies
    # for other implementations (e.g. pycurl just assume list of response headers is correct)
    return [value for hdr, value in http_response.getheaders() if hdr.lower() == "set-cookie"]
