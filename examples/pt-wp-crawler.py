#!/usr/bin/env python

from __future__ import print_function

import os
import sys
import time
from tempfile import gettempdir

bindir, basename = os.path.split(os.path.abspath(__file__))
sys.path.append(os.path.join(bindir, ".."))

basename = basename.split(".")[0]

from optparse import OptionParser, OptionGroup, IndentedHelpFormatter
from perftrackerlib.browser.cp_crawler import CPCrawler, CPCrawlerException
from perftrackerlib.browser.cp_engine import CPEngineBase, CPLoginForm, CPMenuItemXpath
from distutils.version import LooseVersion

from perftrackerlib import __version__ as perftrackerlib_version
PERFTRACKERLIB_VERSION_REQUIRED = '0.0.5'
if LooseVersion(perftrackerlib_version) < LooseVersion(PERFTRACKERLIB_VERSION_REQUIRED):
    print("Error: perftrackerlib version >= %s must be installed, found %s" %
          (PERFTRACKERLIB_VERSION_REQUIRED, perftrackerlib_version))
    sys.exit(-2)


class CPWPAdminConsole(CPEngineBase):
    type = "WordPress admin console"
    menu_dom_clicks = False
    menu_xpaths = [[CPMenuItemXpath(0, None,
                                    "//a[contains(@class, 'menu-top')]",
                                    "./div[contains(@class, 'wp-menu-name')]")],
                   [CPMenuItemXpath(1, None, "//ul[contains(@class, 'wp-submenu')]/li/a", None)]
                   ]

    login_form = CPLoginForm(sbmt_ids=[('input', 'wp-submit')])

    def _get_page_title(self):
        divs = self.browser.driver.find_elements_by_xpath("//div[contains(@id, 'wpbody-content')]/div/h1")
        for div in divs:
            if not div.is_displayed():
                continue
            return div.text
        return ''

    def cp_get_menu_item_title(self, title_el):
        text = title_el.get_attribute("innerHTML")
        return text.split("<")[0]

    def cp_validate_current_page(self, url):
        curr_url = self.cp_get_current_url()

        if "reauth=1" in curr_url:
            self.browser.log_error("WARNING: seems like WP control panel session is expired, trying to re-login")
            time.sleep(2.0)
            if not self.cp_do_login(url):
                raise CPCrawlerException("Re-login failed")
            return False

        return True

    def cp_skip_menu_item(self, link_el, title):
        if title in ("Customize", "Header", "Editor"):
            return True
        return CPEngineBase.cp_skip_menu_item(self, link_el, title)

    def cp_menu_item_click(self, el, timeout_s=None, title=None):
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

    description = "Example: -m -U admin -P pass https://demos1.softaculous.com/WordPress/wp-login.php"

    workdir = os.path.join(gettempdir(), "%s.%d" % (basename, os.getpid()))
    logfile = os.path.join(workdir, basename + ".log")

    cpc = CPCrawler(workdir=workdir, logfile=logfile)

    op = OptionParser(usage=usage, description=description, formatter=IndentedHelpFormatter(width=120))
    cpc.add_options(op, passwd='pass', ajax_threshold=0.5)

    opts, args = op.parse_args()

    if not args:
        op.error("URL is not specified")
        sys.exit(-1)

    cpc.init_opts(opts, args)

    cpc.crawl([CPWPAdminConsole])


if __name__ == "__main__":
    main()
