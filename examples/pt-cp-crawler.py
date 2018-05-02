#!/usr/bin/env python

from __future__ import print_function

import os
import sys
import time
from tempfile import gettempdir

bindir, basename = os.path.split(os.path.abspath(__file__))
sys.path.append(os.path.join(bindir, ".."))

basename = basename.split(".")[0]

from optparse import OptionParser, OptionGroup
from perftrackerlib.browser.cp_crawler import CPCrawler
from perftrackerlib.browser.cp_engine import CPEngineBase, CPMenuItemXpath, DEFAULT_WAIT_TIMEOUT


class CPExtJsConsole(CPEngineBase):
    type = "My ExtJS-based console"
    menu_dom_clicks = False
    menu_xpaths = [[CPMenuItemXpath(0, None, "//div[contains(@class, 'navigation-btn')]", None)],
                   [CPMenuItemXpath(1, None, "//div[contains(@class, 'navigation-sub-menu-item')]", None)]
                   ]

    def _get_page_title(self):
        divs = self.browser.driver.find_elements_by_xpath("//div[contains(@class, 'title-text')]")
        for div in divs:
            if not div.is_displayed():
                continue
            return div.text
        return ''

    def get_menu_item_title(self, title_el):
        text = title_el.get_attribute("innerHTML")
        return text.split("<")[0]

    def get_current_url(self, url=None):
        return self.browser.browser_get_current_url()

    def skip_menu_item(self, link_el, title):
        return not link_el.is_displayed()

    def menu_item_click(self, el, timeout_s=DEFAULT_WAIT_TIMEOUT, title=None):
        # BackupConsole doesn't re-render the page, it means default
        # dom click wait callback will not work and we need own

        text = self._get_page_title()

        def wait_callback(self, el, timeout_s, title):
            # FIXME: is there a better way to check frame is loaded then to check the title has changed?
            time.sleep(1.0)

            deadline = time.time() + min(timeout_s, 5.0)
            while text != self._get_page_title() and time.time() < deadline:
                time.sleep(1.0)

        self.browser.dom_click(el, timeout_s=timeout_s, name=title, wait_callback=wait_callback, wait_callback_obj=self)


def main():
    usage = "usage: %prog [options] URL [URL2 [URL3 ...]]"

    workdir = os.path.join(gettempdir(), "%s.%d" % (basename, os.getpid()))
    logfile = os.path.join(workdir, basename + ".log")

    cpc = CPCrawler(workdir=workdir, logfile=logfile)

    op = OptionParser(usage=usage)
    cpc.add_options(op)

    opts, args = op.parse_args()

    if not args:
        op.error("URL is not specified")
        sys.exit(-1)

    cpc.init_opts(opts, args)

    cpc.crawl([CPExtJsConsole])


if __name__ == "__main__":
    main()
