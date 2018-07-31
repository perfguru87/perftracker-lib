#!/usr/bin/env python

from __future__ import print_function, absolute_import

# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

"""
WordPress admin panel crawler example
"""

import time

from .cp_engine import CPEngineBase, CPMenuItemXpath, CPLoginForm
from .browser_chrome import BrowserChrome


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

    def cp_skip_menu_item(self, link_el, title, link_url):
        if title in ("Customize", "Header", "Editor"):
            return True
        return CPEngineBase.cp_skip_menu_item(self, link_el, title, link_url)

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


##############################################################################
# Autotests
##############################################################################


if __name__ == "__main__":
    CPWPAdminConsole(BrowserChrome())
    print("OK")
