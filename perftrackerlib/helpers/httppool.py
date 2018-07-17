#!/usr/bin/env python

from __future__ import print_function

# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"


"""
    HTTP connection pool with LIFO logic, and 2 implementations of connections: pycurl (fast) and httplib (slow).
    HTTPS is supported.
"""
import threading
import socket
import re
import logging
import six
import pycurl

try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

if six.PY2:
    import httplib
    from StringIO import StringIO as BytesIO
else:
    import http.client as httplib
    from io import BytesIO

try:
    # Python < 2.6 doesn't verify SSL certification
    # disable SSL certificate validation on python >= 2.7.9 as well
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context
except ImportError:
    pass


class HTTPConnectionPycurl:
    def __init__(self, prefix, key_file=None, cert_file=None):
        self.prefix = prefix
        self.curl = pycurl.Curl()
        self.curl.setopt(pycurl.SSL_VERIFYPEER, 0)
        self.curl.setopt(pycurl.SSL_VERIFYHOST, 0)
        if key_file:
            self.curl.setopt(pycurl.SSLKEY, key_file)
        if cert_file:
            self.curl.setopt(pycurl.SSLCERT, cert_file)
        self.curl.setopt(pycurl.ENCODING, "")
        self.buf = None
        self.status = 0
        self.response_headers = None
        self._response_string = None
        self.reason = ''
        self.cleaning_needed = False

    def close(self):
        self.curl.close()

    def request(self, verb, path, body, headers):
        c = self.curl
        hdrs = [str(h + ": " + v) for h, v in six.iteritems(headers)] if headers else []
        verb = verb.upper()
        if verb == 'GET':
            if self.cleaning_needed:
                c.setopt(pycurl.POST, 0)
                c.unsetopt(pycurl.CUSTOMREQUEST)
                c.setopt(pycurl.NOBODY, 0)
                self.cleaning_needed = False
            if body:
                self.cleaning_needed = True
                c.setopt(pycurl.POST, 0)
                c.setopt(pycurl.CUSTOMREQUEST, verb)
                c.setopt(pycurl.NOBODY, 0)
                c.setopt(pycurl.POSTFIELDS, body or "")
        elif verb == 'POST':
            self.cleaning_needed = True
            c.unsetopt(pycurl.CUSTOMREQUEST)
            c.setopt(pycurl.NOBODY, 0)
            c.setopt(pycurl.POST, 1)
            c.setopt(pycurl.POSTFIELDS, body or "")
            hdrs.append("Expect:")
        elif verb == 'PUT' or verb == "DELETE":
            self.cleaning_needed = True
            c.setopt(pycurl.POST, 0)
            c.setopt(pycurl.CUSTOMREQUEST, verb)
            c.setopt(pycurl.NOBODY, 0)
            c.setopt(pycurl.POSTFIELDS, body or "")
        elif verb == 'HEAD':
            self.cleaning_needed = True
            c.setopt(pycurl.POST, 0)
            c.unsetopt(pycurl.CUSTOMREQUEST)
            c.setopt(pycurl.NOBODY, 1)
        else:
            raise pycurl.error("unsupported verb: " + verb)
        c.setopt(pycurl.URL, str(self.prefix + path))
        c.setopt(pycurl.HTTPHEADER, hdrs)
        self.buf = BytesIO()
        self.response_headers = []
        c.setopt(pycurl.WRITEFUNCTION, self.buf.write)
        c.setopt(pycurl.HEADERFUNCTION, self._header_handler)
        c.perform()

    def getresponse(self):
        self.status = self.curl.getinfo(pycurl.HTTP_CODE)
        m = re.match(r'HTTP\/\S*\s*\d+\s*(.*?)\s*$', self._response_string)
        if m:
            self.reason = m.group(1)
        else:
            self.reason = ''
        return self

    def set_debuglevel(self, level):
        self.curl.setopt(pycurl.VERBOSE, 1 if level else 0)
        if level:
            self.curl.setopt(pycurl.DEBUGFUNCTION, self._debug)

    def _debug(self, debug_type, debug_msg):
        if debug_type in (0, 3, 4, 5, 6):
            return  # skip details(0), body (3,4), and ssl (5,6)
        if type(debug_msg) == bytes:
            debug_msg = debug_msg.decode("utf-8")
        if debug_type == 2:
            debug_msg = debug_msg.replace("\r\n", "\n")
        logging.log(logging.DEBUG - 1, "pycurl(%d): %s" % (debug_type, debug_msg.strip()))

    def read(self):
        return self.buf.getvalue()

    def getheaders(self):
        return self.response_headers

    def getheader(self, header, default=None):
        for h, v in self.response_headers:
            if h.lower() == header.lower():
                return v
        return default

    def _header_handler(self, line):
        if type(line) == bytes:
            # HTTP standard specifies that headers are encoded in iso-8859-1.
            line = line.decode('iso-8859-1')
        x = line.split(':', 1)
        if len(x) != 2:
            # check status message
            if line.startswith("HTTP/"):
                self._response_string = line
            return
        self.response_headers.append((x[0].strip(), x[1].strip()))


class _ctx_manager:
    def __init__(self, pool):
        self.pool = pool

    def __enter__(self):
        self.tup = self.pool.get()
        return self.tup

    def __exit__(self, exc_type, exc_value, traceback):
        con = self.tup[0]
        if exc_type is not None or getattr(con, "_invalidate", False):
            self.pool.cnt -= 1
            self.pool._dctor(con)
            # logging.error("!!!!pool.borrow.exit - error. cnt=%d, inpool=%d", pool.cnt, len(pool._items))
        else:
            self.pool.put(con)
            # logging.error("!!!!pool.borrow.exit - ok. cnt=%d, inpool=%d", pool.cnt, len(pool._items))


class LIFOPool(object):
    def __init__(self, ctor, dctor, max_items=10, verbose=None):
        self._ctor = ctor
        self._dctor = dctor
        self.max_items = max(0, max_items)
        self.verbose = logging.getLogger().getEffectiveLevel() < logging.DEBUG if verbose is None else verbose
        self._items = []
        self._lock = threading.Lock()
        self.cnt = 0

    def __del__(self):
        self.clear()

    def clear(self):
        """Clear all pool"""
        with self._lock:
            while self._items:
                self.cnt -= 1
                self._dctor(self._items.pop())

    def get(self):
        """Get an (item, is_new) from the pool or create a new one. After use, return item via put().
        Or, better, use borrow() that ensures the item is properly returned"""
        with self._lock:
            if self._items:
                return self._items.pop(), False
            self.cnt += 1
        con = self._ctor()
        if self.verbose:
            con.set_debuglevel(1)
        return con, True

    def put(self, item):
        """Return item, previously obtained via get(). Do not return bad (not reusable) items.
        Or, better, use borrow() that ensures the item is properly returned"""
        with self._lock:
            self._items.append(item)
            while len(self._items) > self.max_items:
                self.cnt -= 1
                self._dctor(self._items.pop(0))

    def borrow(self):
        """Exception-safe fool-proof way to get and return the (item, is_new). Use with keyword 'with' like this:
        with pool.borrow() as (x, is_new):
            do_stuff(x)
        """
        return _ctx_manager(self)


class HTTPPool(LIFOPool):
    """Connection pool, keeps at most <max_conns> connections to given <server_uri>.
    Parses URI and uses appropriate HTTP/HTTPS connection objects.
    If <max_items> == 0, it is equivalent to keep-alive = False
    Connections are handled in LIFO order, thread safety is provided.
    Public properties (readonly):
        host - server host (from URI)
        port - server port (from URI)
        url - full server part of uri, like "https://yourserver.com:1234"
    """
    def __init__(self, server_uri, max_conns=10, parse_exception=Exception, key_file=None, cert_file=None,
                 verbose=None, engine="pycurl"):
        u = urlparse(server_uri)
        if u.params != '':
            raise parse_exception("Invalid URI: " + server_uri)

        if u.netloc.find(":") < 0:
            self.host = u.netloc
            self.port = {'http': 80, 'https': 443}.get(u.scheme)
        else:
            self.host, self.port = u.netloc.split(":")
            self.port = int(self.port)

        self.url = server_uri

        if engine == "pycurl":
            def ctor():
                return HTTPConnectionPycurl(server_uri, key_file=key_file, cert_file=cert_file)
            self.temporary_errors = (pycurl.error, socket.error)
            self.fatal_errors = (pycurl.error, )   # we don't know suitable errors
        elif engine == "httplib":
            if u.scheme == 'https':
                def ctor():
                    return httplib.HTTPSConnection(self.host, self.port, key_file=key_file, cert_file=cert_file)
            else:
                def ctor():
                    return httplib.HTTPConnection(self.host, self.port)
            self.temporary_errors = (httplib.BadStatusLine, httplib.ImproperConnectionState, socket.error)
            self.fatal_errors = (httplib.HTTPException, )
        else:
            raise Exception("unknown http engine")

        LIFOPool.__init__(self, ctor=ctor, dctor=lambda x: x.close(), max_items=max_conns, verbose=verbose)


##############################################################################
# Autotests
##############################################################################


def _coverage():
    p = HTTPPool("127.0.0.1")
    print("OK")


if __name__ == "__main__":
    _coverage()
