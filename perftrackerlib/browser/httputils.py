#!/usr/bin/env python

from __future__ import print_function

# -*- coding: utf-8 -*-
__author__ = "istillc0de@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

import re
import logging
import urllib
import tempfile
import os
import sys

if sys.version_info[0] < 3:
    import urlparse
    import httplib
    from httplib import HTTPResponse
    from BaseHTTPServer import BaseHTTPRequestHandler
    from StringIO import StringIO
    from HTMLParser import HTMLParser
else:
    import urllib.parse as urlparse
    import http.client as httplib
    from http.client import HTTPResponse
    from http.server import BaseHTTPRequestHandler
    from io import StringIO
    from html.parser import HTMLParser


reScriptLocation = re.compile(r"top\.location[\.href]*=\'(.*)\'")
reFormButtonUrl = re.compile(r"doSubmit\(\'(.*)\'")

###############################################################################
# Support classes for HTML page processing and action URLs extraction
#
class TagValueBase(object):
    def __init__(self, tag):
        self.tag = tag
        self.value = None
        self.inside = False

    def is_processing(self):
        return self.inside

class TagValueManual(TagValueBase):
    def __init__(self, tag):
        TagValueBase.__init__(self, tag)

    def begin(self, tag):
        if tag == self.tag:
            self.inside = True
            return True
        return False

    def end(self, tag):
        if tag == self.tag:
            self.inside = False
            return True
        return False

    def set_value(self, value):
        self.value = value

    def clear_value(self):
        self.value = None

class Request(object):
    def __init__(self, url, method=None, uid=None):
        self._params = {}              # dict of parameters {name: value} (used by POST only)

        self.url = None               # URL without host name, e.g. /turbine
        self.method = method.upper() if method else 'GET'
        self.uid = uid                # request ID

        if url:  # if url is None, Request considered as valid but incomplete
            self.reset_url(url)

    def reset_url(self, url):
        url = urlparse.urlparse(url)
        self.url = url.path

        if not self.url.startswith('/'):
            self.url = '/' + self.url

        if self.method == 'POST':
            self._params = dict(urlparse.parse_qsl(url.query))
        else:
            self._params = {}
            if url.query:
                self.url += '?' + url.query

    def add_param(self, name, value):
        if self.method == 'POST':
            self._params[name] = value
        else:
            self.url += '&%s=%s' % (name, value)

    def get_params(self):
        # converts parameters dict into string (n1=v1&n2=v2&...)
        return urllib.urlencode(self._params) if self._params else None

    def is_complete(self):
        return True if self.url else False

    def process_action(self, tag, attrs):
        if tag == 'button' and attrs.get('type','submit') == 'submit':
            match = reFormButtonUrl.search(attrs.get('onclick', ''))
            if match:
                url = urllib.unquote(match.group(1))
                url = HTMLParser().unescape(url)
                self.uid = tag + ':' + attrs.get('name', 'none')
                self.reset_url(url)
                return True

        return False


###############################################################################
# Class for HTML page processing (based on HTMLParser template)
#
# The main goal of class is gather all possible URLs of actions on page. After
# that, user would select one and use it either to build the chain of auto-redirected
# pages or for manual navigation (JFI: list of possible redirection methods
# https://code.google.com/p/html5security/wiki/RedirectionMethods).
#
class PageParser(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)

        self._body_tag = TagValueManual('body')
        self._form_tag = TagValueManual('form')
        self._script_tag = TagValueManual('script')
        self._noscript_tag = TagValueManual('noscript')

        # Objects of Request type (public)
        self.forms = []
        self.iframe_src = None
        self.body_onload = None
        self.script = None
        self.global_action = None  # action outside <form>'s

        self.form_auto_submit = False

    def handle_starttag(self, tag, attributes):
        attrs = {}
        for attr in attributes:
            attrs[attr[0].lower()] = attr[1]

        # <noscript>  (there is no any valuable information inside this tag)
        if self._noscript_tag.begin(tag) or self._noscript_tag.is_processing():
            return

        # <script>  (only set the flag, script body will be in handle_data())
        if self._script_tag.begin(tag):
            return

        # <iframe>  (process 'src' with URL)
        if tag == 'iframe':
            attr = attrs.get('src')
            if attr:
                self.iframe_src = Request(attr)
            return

        # <body>  (process 'onload' with script)
        if self._body_tag.begin(tag):
            attr = attrs.get('onload')
            if not attr:
                pass
            elif "document.forms[0].submit()" in attr:
                self.form_auto_submit = True
            else:
                match = reScriptLocation.search(attr)
                if match:
                    url = urllib.unquote(match.group(1))
                    url = HTMLParser().unescape(url)
                    self.body_onload = Request(url)
            self._body_tag.set_value(Request(None, 'POST'))
            return

        # <form>  (initialize the new form object)
        if self._form_tag.begin(tag):
            form_id = attrs.get('id') or attrs.get('name')
            self._form_tag.set_value(Request(attrs.get('action'), attrs.get('method'), form_id))
            return

        # <form> ... </form>  (fill the new form object with parameters)
        if self._form_tag.is_processing():
            # extract form parameters
            if tag == 'input' and attrs.get('type') in ['hidden', 'text', 'password'] and attrs.get('name'):
                self._form_tag.value.add_param(attrs['name'], attrs.get('value', ''))
            # if form has no action attribute, try to use one from the submit button
            if not self._form_tag.value.is_complete():
                self._form_tag.value.process_action(tag, attrs)
        # <body> ... </body>  (uhh, get buttons outside <form>)
        elif self._body_tag.is_processing():
            if not self._body_tag.value.is_complete():
                self._body_tag.value.process_action(tag, attrs)

    def handle_endtag(self, tag):
        # </form>  (copy completed form into list)
        if self._form_tag.end(tag):
            if self._form_tag.value.is_complete():
                self.forms.append(self._form_tag.value)
                self._form_tag.clear_value()
        # </body>
        elif self._body_tag.end(tag):
            if self._body_tag.value.is_complete():
                self.global_action = self._body_tag.value
        # </noscript>
        elif self._noscript_tag.end(tag):
            pass
        # </script>
        elif self._script_tag.end(tag):
            pass
        # </html>  (finish HTML processing, perform all onexit steps)
        elif tag == 'html':
            if self._script_tag.value:
                match = reScriptLocation.search(self._script_tag.value)
                if match:
                    self.script = Request(match.group(1))

    def handle_data(self, data):
        # <script> body
        if self._script_tag.is_processing():
            self._script_tag.set_value(data)

###############################################################################
# Class for retrieving HTML page actions
#
class PageActionsExtractor:
    def __init__(self, body):
        self.pp = None
        self.body = body

        try:
            self.pp = PageParser()
            self.pp.feed(body)
        except Exception as ex:
            logging.debug("Page not completely processed due to: %s", ex)
            logging.debug("see corresponded html in file: %s", log2file(body))
            # do not raise here, because it happens quite often on some complex pages

    def get_action(self, uid=None):
        # Search for action with specific uid and returns Request object corresponded this action.
        # If uid is None, the auto-redirected action is searching, accordingly hardcoded rules.
        # If no any actions found, None is returned.
        #
        # uid -- can be either <form id> or <form button id>; in later case, the uid has
        # 'button:' prefix (e.g. for button id='login', uid='button:login')

        if not self.pp:
            return None

        if not uid:  # looking for auto-redirected request
            if self.pp.script:
                return self.pp.script

            if self.pp.iframe_src:
                return self.pp.iframe_src

            if self.pp.forms and self.pp.form_auto_submit:
                return self.pp.forms[0]

            if self.pp.body_onload:
                return self.pp.body_onload
        else:  # Looking for particular request
            if self.pp.forms:
                for form in self.pp.forms:
                    if form.uid == uid:
                        return form
            if self.pp.global_action:
                if self.pp.global_action.uid == uid:
                    return self.pp.global_action

        return None

###############################################################################
# Helper functions
#
def unescape(s):
    s = s.replace("&lt;", "<")
    s = s.replace("&gt;", ">")
    s = s.replace("&quot;", '"')
    s = s.replace("&apos;", "'")
    s = s.replace("&amp;", "&")
    return s


def log2file(text):
    """
    Pretty simple function, saves the text into temporary file and returns it's name
    :param text: string to log
    :return: temporary file name
    """
    handle, name = tempfile.mkstemp(suffix='.html', prefix='log_', text=True)
    os.write(handle, text)
    os.close(handle)
    return name

class HTTPRequestFromStr(BaseHTTPRequestHandler):
    def __init__(self, request_text):
        self.rfile = StringIO(request_text)
        self.raw_requestline = self.rfile.readline()
        self.error_code = self.error_message = None
        self.parse_request()

    def send_error(self, code, message):
        self.error_code = code
        self.error_message = message

class HTTPResponseFromStr(HTTPResponse):
    def __init__(self, response_text):
        try:
            self.init(response_text)
        except httplib.UnknownProtocol as e:
            # FIXME: handle HTTP/2.0 that is 'unknown' for httplib (to check go to www.google.com)
            logging.debug(str(e) + " retrying with HTTP/2.0 replaced by HTTP/1.1")
            self.init(response_text.replace("HTTP/2.0", "HTTP/1.1"))

    def init(self, response_text):
        class FakeSocket:
            def __init__(self, response_str):
                self._file = StringIO(response_str)
            def makefile(self, *args, **kwargs):
                return self._file

        source = FakeSocket(response_text)
        HTTPResponse.__init__(self, source)
        self.begin()
