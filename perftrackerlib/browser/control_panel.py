#!/usr/bin/env python

from __future__ import print_function

# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

"""
Any control panel helper
"""

import logging
import time
import re

from perftrackerlib.browser.browser_base import BrowserExc, BrowserExcTimeout, DEFAULT_WAIT_TIMEOUT
from selenium.common.exceptions import ElementNotVisibleException
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import WebDriverException

reHTML = re.compile('<.*?>')
def removeHtmlTags(text):
    return re.sub(reHTML, '', text)

class CPMenuItemXpath:
    def __init__(self, level, frame, link, title, menu_url_clicks = True, menu_dom_clicks = True):
        self.level = level
        self.frame = frame
        self.link = link
        self.title = title
        self.menu_url_clicks = menu_url_clicks
        self.menu_dom_clicks = menu_dom_clicks

class CPMenuItem:
    def __init__(self, level, title, link, xpath, parent, menu_url_clicks = True, menu_dom_clicks = True):
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
            print "  %s - %s" % (self.title, link)  # ugly :-(

    def is_scanned(self, key):
        if self.parent:
            return self.parent.is_scanned(key)
        return key in self._scanned_menu_items

    def mark_as_scanned(self, key):
        p = self
        while p.parent:
            p = p.parent
        p._scanned_menu_items.add(key)

    def add_child(self, title, link, xpath, menu_xpath):
        ch = CPMenuItem(self.level + 1, title, link, xpath, self,
            menu_url_clicks = self.menu_url_clicks and menu_xpath.menu_url_clicks,
            menu_dom_clicks = self.menu_dom_clicks and menu_xpath.menu_dom_clicks,
            )
        self.children.append(ch)

        self.mark_as_scanned(title)
        self.mark_as_scanned(link)
        return ch

    def get_items(self, items = None):
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


class CPWebdriverBase:
    type = "A control panel"
    menu_url_clicks = True # collect direct URL links to menu items
    menu_dom_clicks = True # collect DOM (xpath) links to menu items
    menu_xpaths = [] # [[CPMenuItemXpath(0, ...), ...], [CPMenuItemXpath(1, ...), ...]]

    def __init__(self, browser):
        self.browser = browser
        self.log_error = browser.log_error
        self.log_warning = browser.log_warning
        self.log_info = browser.log_info
        self.log_debug = browser.log_debug
        self.menu = CPMenuItem(0, self.type, None, None, None,
            menu_url_clicks = self.menu_url_clicks, menu_dom_clicks = self.menu_dom_clicks)
        self.current_frame = None

    def init_context(self):
        return True

    def get_current_url(self, url=None):
        if url and url.lower().find('javascript') < 0:
            return url
        return self.browser.browser_get_current_url()

    def get_menu_item_title(self, title_el):
        return remove_html_tags(title_el.get_attribute("innerHTML"))

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

    def skip_menu_item(self, link_el, title):
        return False

    def switch_to_frame(self, frame, verbose=True):
        if not frame:
            return None
        self.switch_to_default_content()

        self.browser.log_info("searching for frame: '%s'" % frame)
        try:
            el = self.browser.driver.find_element_by_xpath(frame)
        except NoSuchElementException:
            if verbose:
                self.browser.log_error("Can't find frame element: '%s', page source:\n%s" % \
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

    def menu_item_click(self, el, timeout_s=DEFAULT_WAIT_TIMEOUT, title=None):
        def wait_callback(self, el, timeout_s, title):
            self.browser.dom_wait_element_stale(el, timeout_s=timeout_s, name=title)

        self.browser.dom_click(el, timeout_s=timeout_s, name=title,
            wait_callback = wait_callback, wait_callback_obj = self)

    def _populate_menu(self, menu):

        if len(self.menu_xpaths) <= menu.level:
            return

        for x in self.menu_xpaths[menu.level]:

            if x.frame:
                frame = self.switch_to_frame(x.frame, verbose=False)
                if not frame:
                    continue

            for link_el in self.browser.driver.find_elements_by_xpath(x.link):
                link = link_el.get_attribute('href')
                if not link:
                    link = link_el.get_attribute('innerHTML')

                if x.title:
                    title_els = link_el.find_elements_by_xpath(x.title)
                    if not title_els or not len(title_els) or not title_els[0].get_attribute("innerHTML"):
                        self.log_error("WARNING: can't get title for menu element: %s\nusing: %s" % (link, x.title))
                        continue
                    title_el = title_els[0]
                else:
                    title_el = link_el

                title = self.get_menu_item_title(title_el)
                if menu.is_scanned(title):
                    self.log_debug("skipping menu item '%s', it was already scanned" % title)
                    continue

                if link == "javascript:void(0);":
                    self.log_debug("skipping void link in '%s'" % title)
                    continue

                if self.skip_menu_item(link_el, title):
		    self.log_debug("skipping menu item '%s'" % title)
                    continue

                curr_xpath = self.get_current_xpath(link_el)

                self.log_info("clicking on the '%s' menu item, link %s" % (title, link))
                try:
                    self.menu_item_click(link_el, title=title)
                except WebDriverException as e:
                    self.log_info(" ... skipping the '%s' menu item: %s" % (title, str(e)))
                except ElementNotVisibleException:
                    self.log_info(" ... skipping the '%s' menu item since it is not visible" % title)
                    continue
                except BrowserExc as e:
                    self.log_debug("dom_click() raised exception: %s" % str(e))
                    self.log_warning("WARNING: can't wait for '%s' " % (title) + "menu click completion, skipping it")
                    continue

                curr_url = self.get_current_url(link)
                self.browser.history.append(curr_url)

                if menu.is_scanned(curr_url):
                    self.log_debug("skipping menu item with url '%s', it was already scanned" % curr_url)
                    continue

                self.log_info(" ... '%s' menu item has URL: %s, xpath: %s" % (title, curr_url, curr_xpath))

                ch = menu.add_child(title, curr_url, curr_xpath, x)
                self._populate_menu(ch)
                self._populate_menu(menu)
                break

            if x.frame:
                self.switch_to_default_content()

    def do_menu_walk(self):
        self.browser.print_stats_title("Control panel menu scanner...")
        print "Control panel detected: '%s'" % self.type  # ugly :-(
        print "Searching for menu items...\n"  # ugly :-(
        self.menu.link = self.get_current_url()
        self._populate_menu(self.menu)
        items = self.menu.get_items()
        return [(i[1], i[2]) for i in sorted(items.values(), key = lambda x: x[0])]


class CPWebdriverCCPv2(CPWebdriverBase):
    type = "CCPv2"
    menu_xpaths = [
            [CPMenuItemXpath(0, None, "//div[@id='ccp-sidebar']/descendant::a", ".//strong[1]")],
            [
                # standard CCPv2 submenu
                CPMenuItemXpath(1, None, "//div[@id='ccp-sidebar-level-2']/descendant::a",
                    ".//span[@class='list-group-item-text']"),
                # legacy submenu
                CPMenuItemXpath(1, "//iframe[@name='http://www.parallels.com/ccp/legacy']",
                    "//div[@class='tabs-area']/descendant::a", ".//span",
                    menu_url_clicks = False),
            ]
        ]

    def get_current_url(self, url=None):
        bw_id = self.browser.driver.execute_script("return aps.context.bwId")
        if bw_id == None or bw_id == "None":
            bw_id = self.browser.driver.execute_script("return aps.context._sessionId")
        if bw_id == None or bw_id == "None":
            raise BrowserExc("Can't get bwId for the CCPv2 session")

        url = self.browser.browser_get_current_url()
        if url.find("bw_id=") < 0:
            if url.find("?") < 0:
                return url + "?bw_id=%s" % bw_id
            return url + "&bw_id=%s" % bw_id
        return url

    def skip_menu_item(self, link_el, title):
        # FIXME: w/a work non-working Services tab
        if title == "Services":
            return True
        return False


class CPWebdriverPCP(CPWebdriverBase):
    type = "PCP"
    menu_dom_clicks = False
    menu_xpaths = [
            [CPMenuItemXpath(0, "//frame[@name='leftFrame']", "//div[@id='navArea']//a[@class='tree-item-content']", ".//b")],
            [CPMenuItemXpath(1, "//frame[@name='mainFrame']", "//div[@class='tabs-area']//a", ".//span")]
        ]

    def menu_item_click(self, el, timeout_s=DEFAULT_WAIT_TIMEOUT, title=None):
        # PCP menu click does not change left frame but only main frame, it means default
        # dom click wait callback will not work and we need own

        def wait_callback(self, el, timeout_s, title):
            if self.current_frame == "//frame[@name='leftFrame']":
                # FIXME: I don't know how to wait for main frame load begin if click on left frame
                time.sleep(5.0)
            else:
                try:
                    self.browser.dom_wait_element_stale(el, timeout_s=timeout_s, name=title)
                except BrowserExcTimeout:
                    self.log_warning("Ignoring '%s' POA PCP click timeout" % title)

        self.browser.dom_click(el, timeout_s=timeout_s, name=title, wait_callback = wait_callback, wait_callback_obj = self)

    def skip_menu_item(self, link_el, title):
        parent = link_el.find_element_by_xpath("..")
        if parent and parent.get_attribute('className') == "active":
            return True
        return False


class CPWebdriverCCP(CPWebdriverBase):
    type = "CCP"
    menu_xpaths = [
            [CPMenuItemXpath(0, "//frame[@name='topFrame']", "//ul[@id='navbar-content-area']//a", ".//span")],
        ]

    def get_current_url(self, url=None):
        if url and url.lower().find('javascript') < 0:
            return url
        self.switch_to_frame("//frame[@name='mainFrame']")
        url = self.browser.browser_get_current_url()
        self.switch_to_default_content()
        return url


class CPWebdriverCMP(CPWebdriverBase):
    type = "CMP"
    menu_dom_clicks = False
    menu_xpaths = [
            [CPMenuItemXpath(0, None, "//ul[@class='nav navbar-nav']//a[@role='menuitem']", None)]
            ]

    def init_context(self):
        try:
            if not self.browser.dom_find_element_by_id("headTop"):
                return False
        except BrowserExc:
            return False

        role_selector_id = "MainContent_btnTestResellerLogin"
        el = self.browser.dom_find_element_by_id(role_selector_id)
        if not el:
            self.log_error("can't find %s" % role_selector_id)
            return False

        self.browser.dom_click(el, name=role_selector_id)
        return True

    def skip_menu_item(self, link_el, title):
        if "span" in title:
            return True
        return False


class CPBackupConsole(CPWebdriverBase):
    type = "BackupConsole"
    menu_dom_clicks = False
    menu_xpaths = [
            [CPMenuItemXpath(0, None, "//div[contains(@class, 'navigation-btn')]", None)],
            [CPMenuItemXpath(1, None, "//div[contains(@class, 'navigation-sub-menu-item')]", None)]
            ]

    def _get_page_title(self):
        divs = self.browser.driver.find_elements_by_xpath("//div[contains(@class, 'acronis-title-text')]")
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

        self.browser.dom_click(el, timeout_s=timeout_s, name=title, wait_callback = wait_callback, wait_callback_obj = self)


def getCPWebdriver(browser):
    for cp in [CPBackupConsole, CPWebdriverCCPv2, CPWebdriverPCP, CPWebdriverCCP, CPWebdriverCMP]:
        c = cp(browser)
        if not c.init_context():
            continue
        for cpmx in c.menu_xpaths[0]:
            c.switch_to_frame(cpmx.frame, verbose=False)
            if browser.driver.find_elements_by_xpath(cpmx.link):
                logging.info("%s control panel detected" % c.type)
                c.switch_to_default_content()
                return c
            c.switch_to_default_content()
    return None
