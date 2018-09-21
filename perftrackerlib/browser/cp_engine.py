#!/usr/bin/env python

from __future__ import print_function, absolute_import

# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

"""
Any control panel engine (helper)
"""

import sys
import os
import logging
import time
import re

from .browser_base import BrowserBase, BrowserExc, BrowserExcTimeout
from .browser_python import BrowserPython
from selenium.common.exceptions import ElementNotVisibleException
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import WebDriverException
from selenium.common.exceptions import StaleElementReferenceException


reHTML = re.compile('<.*?>')


def remove_html_tags(text):
    return re.sub(reHTML, '', text)


class CPMenuItemXpath:
    def __init__(self, level, frame, link_xpath, title_xpath, menu_url_clicks=True, menu_dom_clicks=True):
        self.level = level  # menu level, 0 - 10...
        self.frame = frame  # menu frame name
        self.link_xpath = link_xpath  # clickable menu item element xpath
        self.title_xpath = title_xpath  # relative xpath to fetch the menu item title
        self.menu_url_clicks = menu_url_clicks
        self.menu_dom_clicks = menu_dom_clicks


class CPMenuItem:
    def __init__(self, level, title, link, xpath, parent, menu_url_clicks=True, menu_dom_clicks=True):
        """
        menu_url_clicks - collect direct URL links to menu items
        menu_dom_clicks - collect DOM (xpath) links to menu items
        """
        self.level = level
        self.link = link
        self.xpath = xpath
        self.children = []
        self._scanned_menu_items = set()

        self.parent = parent
        if parent:
            self.title = parent.title + " -> " + title
        else:
            self.title = title
        self.menu_url_clicks = menu_url_clicks
        self.menu_dom_clicks = menu_dom_clicks

        if link:
            print("  %s - %s" % (self.title, link))  # ugly :-(

    def is_scanned(self, key, check_in_parent=False):
        if check_in_parent and self.parent:
            return self.parent.is_scanned(key, check_in_parent=check_in_parent)
        return key in self._scanned_menu_items

    def mark_as_scanned(self, key):
        p = self
        while p.parent:
            p = p.parent
        p._scanned_menu_items.add(key)
        self._scanned_menu_items.add(key)

    def add_child(self, title, link, xpath, menu_xpath):
        ch = CPMenuItem(self.level + 1, title, link, xpath, self,
                        menu_url_clicks=self.menu_url_clicks and menu_xpath.menu_url_clicks,
                        menu_dom_clicks=self.menu_dom_clicks and menu_xpath.menu_dom_clicks,
                        )
        self.children.append(ch)

        self.mark_as_scanned(title)
        self.mark_as_scanned(link)
        return ch

    def get_items(self, items=None):
        """ return a list of [item#, title, link] """
        if not items:
            items = {}
        for c in self.children:
            if self.menu_url_clicks:
                items[c.link] = [len(items), c.title, c.link]
            if self.menu_dom_clicks and c.xpath:
                xpath = "%s^%s" % (c.link, c.xpath)
                items[xpath] = [len(items), c.title + " (DOM click)", xpath]
            items = c.get_items(items)
        return items


class CPLoginForm:
    def __init__(self, user_tags=None, user_ids=None, pass_tags=None, pass_ids=None,
                 sbmt_tags=None, sbmt_ids=None, sbmt_xpath=None):

        def _capitalize_list(tags):
            ret = [k for k in tags]
            for k in tags:
                if type(k) is tuple:
                    ret.append((k[0].capitalize(), k[1].capitalize()))
                else:
                    ret.append(k.capitalize())
            return ret

        if user_tags is None:
            user_tags = _capitalize_list([("input", "user"), ("input", "username"), ("input", "login")])
        if user_ids is None:
            user_ids = _capitalize_list([("input", "user_login")])
        if pass_tags is None:
            pass_tags = _capitalize_list([("input", "pass"), ("input", "password"), ("input", "login_password")])
        if pass_ids is None:
            pass_ids = _capitalize_list([("input", "user_pass")])
        if sbmt_tags is None:
            sbmt_tags = _capitalize_list([("button", "login"), ("button", "login_submit")])
        if sbmt_ids is None:
            sbmt_ids = _capitalize_list([("button", "login"), ("button", "submit"), ("button", "signin_button")])

        self.user_tags = user_tags
        self.user_ids = user_ids
        self.pass_tags = pass_tags
        self.pass_ids = pass_ids
        self.sbmt_tags = sbmt_tags
        self.sbmt_ids = sbmt_ids
        self.sbmt_xpath = sbmt_xpath if sbmt_xpath else []

        assert isinstance(self.sbmt_xpath, list)


class CPEngineBase:
    type = "A control panel"
    menu_url_clicks = True  # collect direct URL links to menu items
    menu_dom_clicks = True  # collect DOM (xpath) links to menu items
    menu_xpaths = []  # [[CPMenuItemXpath(0, ...), ...], [CPMenuItemXpath(1, ...), ...]]

    login_form = CPLoginForm()

    def __init__(self, browser, user=None, password=None, html_report=None):
        self.browser = browser
        self.log_error = browser.log_error
        self.log_warning = browser.log_warning
        self.log_info = browser.log_info
        self.log_debug = browser.log_debug
        self.menu = CPMenuItem(0, self.type, None, None, None,
                               menu_url_clicks=self.menu_url_clicks, menu_dom_clicks=self.menu_dom_clicks)
        self.current_frame = None
        self.user = user
        self.password = password
        self._html_report = html_report

    #
    # Virtual methods, can be control panel specific
    #

    def cp_init_context(self):
        return True

    def cp_handle_opts(self, opts):
        return

    def cp_validate_current_page(self, url):
        return True

    def cp_get_product_version(self):
        return None

    def cp_get_product_name(self):
        return None

    def cp_get_current_url(self, url=None):
        if url and url.lower().find('javascript') < 0:
            return url
        return self.browser.browser_get_current_url()

    def cp_restore_nav_menu_url(self):
        return False

    def cp_get_menu_item_title(self, title_el):
        return remove_html_tags(title_el.get_attribute("innerHTML")).strip()

    def cp_get_menu_item_link_url(self, link_el):
        return ""

    def cp_skip_menu_item(self, link_el, title, url):
        return not link_el.is_displayed()

    def cp_do_menu_item_click(self, el, timeout_s=None, title=None):
        def wait_callback(self, el, timeout_s, title):
            self.browser.dom_wait_element_stale(el, timeout_s=timeout_s, name=title)

        self.browser.dom_click(el, timeout_s=timeout_s, name=title,
                               wait_callback=wait_callback, wait_callback_obj=self)

    def cp_do_scan_menu(self):
        self.browser.print_stats_title("Control panel menu scanner...")
        print("Control panel detected: '%s'" % self.type)  # ugly :-(
        print("Searching for menu items...\n")  # ugly :-(
        self.menu.link = self.cp_get_current_url()
        self._populate_menu(self.menu)
        self.log_info("Menu scan completed")
        items = self.menu.get_items()
        return [(i[1], i[2]) for i in sorted(items.values(), key=lambda x: x[0])]

    def cp_do_navigate(self, location, timeout=None, cached=True, stats=True, name=None):
        for retry in range(0, 3):
            page = self.browser.navigate_to(location, timeout=timeout, cached=cached, stats=stats, name=name)
            if self.cp_validate_current_page(location):
                return page
            time.sleep(1.0)

        self.log_error("Page url validation failed, aborting")
        return None

    def cp_do_login(self, url, timeout_s=None):
        return self.browser.do_login(url, self.user, self.password, self.login_form, timeout_s=timeout_s)

    def cp_do_logout(self):
        return False

    #
    # Internal / private methods
    #

    def get_current_xpath(self, link_el):
        if not link_el:
            return None

        xpath = "a"

        parent = link_el
        tag = "a"

        while True:
            parent = parent.find_element_by_xpath("..")
            if not parent:
                break

            id = parent.get_attribute('id')
            tag = parent.tag_name

            if id:
                xpath = "%s[@id='%s']/%s" % (tag, id, xpath)
                break

            xpath = "%s/%s" % (tag, xpath)

        xpath = "//%s" % xpath
        return xpath

    def switch_to_frame(self, frame, verbose=True):
        if not frame:
            return None
        self.switch_to_default_content()

        self.browser.log_info("searching for frame: '%s'" % frame)
        try:
            el = self.browser.driver.find_element_by_xpath(frame)
        except NoSuchElementException:
            if verbose:
                self.browser.log_error("Can't find frame element: '%s', page source:\n%s" %
                                       (frame, self.browser.driver.page_source))
            return None
        self.browser.dom_switch_to_frame(el)
        self.current_frame = frame
        return el

    def switch_to_default_content(self):
        self.current_frame = None
        self.browser.dom_switch_to_default_content()

    def dom_click(self, el, title=None):
        self.browser.dom_click(el, name=title)

    def _populate_menu(self, menu):

        if len(self.menu_xpaths) <= menu.level:
            return

        if menu.link != self.cp_get_current_url():
            if self.cp_restore_nav_menu_url():
                self.log_debug("Restore navigatio menu URL back to: '%s'" % menu.link)
                self.browser.navigate_to(menu.link)

        for x in self.menu_xpaths[menu.level]:

            if x.frame:
                frame = self.switch_to_frame(x.frame, verbose=False)
                if not frame:
                    continue

            self.log_debug("Looking for xpath: '%s'" % x.link_xpath)
            menu_elements = self.browser.driver.find_elements_by_xpath(x.link_xpath)
            i = 0
            while i < len(menu_elements):
                link_el = menu_elements[i]

                link_url = self.cp_get_menu_item_link_url(link_el)

                if not link_url:
                    try:
                        link_url = link_el.get_attribute('href')
                    except StaleElementReferenceException:
                        # previous click caused dom change, so re-load menu items (assuming their sequence is preserved)
                        menu_elements = self.browser.driver.find_elements_by_xpath(x.link_xpath)
                        if i >= len(menu_elements):
                            continue  # menu has shrunk suddenly
                        link_el = menu_elements[i]
                        link_url = link_el.get_attribute('href')
                    i += 1

                if not link_url:
                    link_url = link_el.get_attribute('innerHTML').strip()
                    link_url = remove_html_tags(link_url)
                    if "/" not in link_url and "#" not in link_url:
                        link_url = ""  # the link is not known at the moment, can't do nothing

                if x.title_xpath:
                    title_els = link_el.find_elements_by_xpath(x.title_xpath)
                    if not title_els or not len(title_els) or not title_els[0].get_attribute("innerHTML"):
                        self.log_error("WARNING: can't get title for menu element: %s\nusing: %s" %
                                       (link_url, x.title_xpath))
                        continue
                    title_el = title_els[0]
                else:
                    title_el = link_el

                title = self.cp_get_menu_item_title(title_el)

                msg = "menu item: '%s' => '%s'" % (title, link_url)

                if menu.is_scanned(title):
                    self.log_info("skip %s [already scanned]" % msg)
                    continue

                if link_url == "javascript:void(0);":
                    self.log_info("skip %s [void js link]" % msg)
                    continue

                if self.cp_skip_menu_item(link_el, title, link_url):
                    self.log_info("skip %s [cp_skip_menu_item() = True]" % msg)
                    continue

                curr_xpath = self.get_current_xpath(link_el)

                self.log_info("found %s" % msg)
                try:
                    self.cp_do_menu_item_click(link_el, title=title)
                except WebDriverException as e:
                    self.log_info(" ... skipping the '%s' menu item: %s" % (title, str(e)))
                except ElementNotVisibleException:
                    self.log_info(" ... skipping the '%s' menu item since it is not visible" % title)
                    continue
                except BrowserExc as e:
                    self.log_debug("dom_click() raised exception: %s" % str(e))
                    self.log_warning("WARNING: can't wait for '%s' " % (title) + "menu click completion, skipping it")
                    continue

                curr_url = self.cp_get_current_url(link_url)
                self.browser.history.append(curr_url)

                if menu.is_scanned(curr_url, check_in_parent=True):
                    self.log_debug("skipping menu item with url '%s', it was already scanned" % curr_url)
                    continue

                self.log_info(" ... '%s' menu item has URL: %s, xpath: %s" % (title, curr_url, curr_xpath))

                ch = menu.add_child(title, curr_url, curr_xpath, x)

                if self._html_report:
                    img_path = self._html_report.add_page(url=curr_url, title=ch.title)
                    self.browser.browser_get_screenshot_as_file(img_path)
                    self._html_report.gen_thumbnails(curr_url)

                self._populate_menu(ch)
                self._populate_menu(menu)
                break

            if x.frame:
                self.switch_to_default_content()


##############################################################################
# Autotests
##############################################################################


if __name__ == "__main__":
    CPEngineBase(BrowserPython())
    print("OK")
