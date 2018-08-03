#!/usr/bin/env python

from __future__ import print_function, absolute_import

# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

"""
A library to generate HTML report with pages information
"""

import os
from collections import OrderedDict
from PIL import Image

from perftrackerlib import __version__ as __version__
from perftrackerlib.helpers.timeline import ptDoc, ptSection
from .page import Page


class ptBrowserHtmlReport:
    def __init__(self, output_dir, title=''):
        self.pages = OrderedDict()
        self._url2id = {}
        self.output_dir = output_dir
        self.title = title
        self.doc = ptDoc(title=title)

        self.sdir = os.path.join(self.output_dir, 'screenshots')
        if not os.path.exists(self.sdir):
            os.makedirs(self.sdir)

    def add_page(self, url, title=None, page=None, render_html=True):
        if self.pages.get(url, None) is None:
            self.pages[url] = []
        if not page and title:
            page = Page(None, url, name=title)
        if page:
            self.pages[url].append(page)
        if render_html:
            self.gen_index_html()
        return self.get_screenshot_file_path(url)

    def url2id(self, url):
        if url not in self._url2id:
            self._url2id[url] = len(self._url2id)
        return self._url2id[url]

    def get_screenshot_file_path(self, url, sfx=""):
        return os.path.join(self.sdir, '%d%s.png' % (self.url2id(url), str(sfx)))

    def gen_thumbnails(self, url):
        if url not in self._url2id:
            return

        p = self.get_screenshot_file_path(url)
        i = Image.open(p)
        for w in 1024, 256:
            ratio = w / float(i.size[0])
            h = int((float(i.size[1]) * ratio))
            img = i.resize((w, h), Image.ANTIALIAS)
            img.save(self.get_screenshot_file_path(url, "_%d" % w))
            img.close()

        i.close()
        # os.unlink(p)

    def render_html(self):

        html = """
<!DOCTYPE html>
<html lang='en'>
<head>
  <title>%s</title>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <link rel='stylesheet' href='https://maxcdn.bootstrapcdn.com/bootstrap/3.3.7/css/bootstrap.min.css'>
  <script src='https://ajax.googleapis.com/ajax/libs/jquery/3.3.1/jquery.min.js'></script>
  <script src='https://maxcdn.bootstrapcdn.com/bootstrap/3.3.7/js/bootstrap.min.js'></script>
<style type='text/css'>
.modal-lg { max-width: 1050px !important; width: 90%% !important; }
.modal-lg img { width: 100%%; }
</style>
</head>
<body>
<div class='jumbotron text-center'><h2>Pages</h2></div>
<div class='container'>
""" % (str(self.title))

        for url, pages in self.pages.items():
            img_256 = self.get_screenshot_file_path(url, sfx="_256")
            img_1024 = self.get_screenshot_file_path(url, sfx="_1024")

            if len(pages) and pages[-1] and pages[-1].name:
                page_name = pages[-1].name
            else:
                page_name = ""

            if len(pages) and pages[-1] and pages[-1].ts_start:
                p = pages[-1]
                reqs = p.get_uncached_reqs()
                details = []
                details.append("%d requests" % len(reqs))
                details.append("%d msec" % int(p.dur))
                details.append("%.0f KB" % (sum([r.length for r in reqs]) / 1024.0))
                details.append("page is not tested yet")
            else:
                details = ["page is not tested yet"]

            html += "<div class='row'>"

            html += "<div class='col-sm-8'>"
            html += "<h3>%s</h3><p><a href='%s'>%s</a><br>%s</p>" % (page_name, url, url, "<br>".join(details))
            html += "</div>"

            html += "<div class='col-sm-4'>"
            html += "<a data-toggle='modal' data-target='#modal%d'><img src='%s'></a>" % (self.url2id(url), img_256)
            html += "</div>"

            html += "</div>"

            html += """
  <!-- Modal -->
  <div class="modal" id="modal%d" role="dialog">
    <div class="modal-dialog modal-lg">
      <div class="modal-content">
        <div class="modal-header">
          <button type="button" class="close" data-dismiss="modal">&times;</button>
          <h4 class="modal-title">%s</h4>
        </div>
        <div class="modal-body">
          <img src='%s'>
        </div>
      </div>
    </div>
  </div>
""" % (self.url2id(url), page_name, img_1024)

        html += "</div>"
        html += "</body></html>"
        return html

    def gen_index_html(self):
        p = os.path.join(self.output_dir, 'index.html')
        f = open(p, 'w')
        f.write(self.render_html())
        f.close()
        return p


##############################################################################
# Autotests
##############################################################################


if __name__ == "__main__":
    r = ptBrowserHtmlReport('')
    r.add_page('', None)
    r.render_html()
    print("OK")
