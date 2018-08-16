#!/usr/bin/env python

from __future__ import print_function, absolute_import

# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

"""
A library to scan a control panel menu items, click on them, wait for request completion and report
performance metrics.

Features:
- Native Chrome and Firefox browsers support
- Automatic menu and sub-menu discovery (by xpath patterns)
- Login form detection and authentication
- Run multiple native browsers in background under different users
- Automatic ajax activity detection in browser and wait for click completion
- Python-based browser repeaters to simulate bigger load
- Waterfall-like requests view
- Page click requests errors tracking
- Cached/Uncached clicks/pages
- Direct URL click / xpath click
- Headless / traditional browsers
"""

import os
import sys
import logging
import traceback
import time
import re
import shutil
import copy
import datetime
import socket
import platform
import math
from tempfile import gettempdir
from optparse import OptionParser, OptionGroup
from multiprocessing import Process, Queue, cpu_count
from psutil import virtual_memory

from perftrackerlib import __version__ as __version__
from perftrackerlib.client import ptSuite, ptTest, ptVM, ptComponent
from .browser_base import BrowserExc, DEFAULT_NAV_TIMEOUT, DEFAULT_AJAX_THRESHOLD
from .browser_python import BrowserPython
from .browser_chrome import BrowserChrome
from .browser_firefox import BrowserFirefox
from .html_report import ptBrowserHtmlReport
from .page import PageStats, PageStatsSummary
from .utils import gen_urls_from_index_file
from .cp_engine import CPEngineBase
from ..helpers.texttable import TextTable
from selenium.webdriver.remote.remote_connection import LOGGER as selenium_logger

bindir, basename = os.path.split(sys.argv[0])
basename = basename.split(".")[0]

BROWSERS = (BrowserChrome, BrowserFirefox, BrowserPython)

OPT_DELAY_BETWEEN_CLICK_SEC = 1.0
OPT_DEFAULT_AJAX_THRESHOLD = DEFAULT_AJAX_THRESHOLD
OPT_DEFAULT_NAV_TIMEOUT = DEFAULT_NAV_TIMEOUT


class CPLogFormatter(logging.Formatter):
    LOG_LVL_MAP = {logging.CRITICAL: "CRI",
                   logging.ERROR: "ERR",
                   logging.WARNING: "WRN",
                   logging.INFO: "INF",
                   logging.DEBUG: "DBG",
                   logging.NOTSET: "n/a"
                   }

    def __init__(self, *args, **kwargs):
        return super(CPLogFormatter, self).__init__("%(message)s", *args, **kwargs)

    def format(self, record):
        if 'browser' in record.__dict__:
            name = record.__dict__['browser']
        else:
            name = record.name[0:10].split(".")[0]
        record.msg = '%s [%3s] %-10s - %s' % (datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3],
                                              self.LOG_LVL_MAP[record.levelno], name, record.msg)
        return super(CPLogFormatter, self).format(record)


class CPCrawlerException(RuntimeError):
    pass


class CPBrowserRunner:
    def __init__(self, cp_engines, opts, urls, users, browser_id, logfile, workdir, pt_suite):
        self.cp_engines = cp_engines
        self.opts = opts
        self.urls = urls
        self.browser_id = int(browser_id)
        self.workdir = workdir
        self.page_stats_summary = PageStatsSummary()
        self.user = users[(self.browser_id - 1) % len(users)] if users else None
        self.pt_suite = pt_suite
        self._html_report = None

        self.browser_class = BROWSERS[0]
        for b in BROWSERS:
            if b.engine == self.opts.browser:
                self.browser_class = b
                break

        self.logdir = os.path.join(workdir, "browser.%d" % browser_id)
        self.crawler_logfile = os.path.join(self.logdir, logfile if logfile else "%s.log" % basename)
        self.browser_logfile = os.path.join(self.logdir, "%s.log" % self.browser_class.engine)

        self.stdout_fname = os.path.join(self.logdir, "%s.stdout" % basename) if self.browser_id else None
        self.stderr_fname = os.path.join(self.logdir, "%s.stderr" % basename) if self.browser_id else None

        self._stdout_orig = sys.stdout
        self._stderr_orig = sys.stderr

        if self.browser_id:
            self.opts.log2file = True

    def init(self):
        shutil.rmtree(self.logdir, ignore_errors=True)
        os.makedirs(self.logdir, mode=0o777)

        self.browser = self.browser_class(headless=not self.opts.view, cleanup=False,
                                          telemetry_fname=self.opts.telemetry,
                                          log_path=self.browser_logfile,
                                          nav_timeout=self.opts.nav_timeout,
                                          ajax_threshold=self.opts.ajax_threshold)

        if self.browser_id:
            sys.stdout = open(self.stdout_fname, 'w')
            sys.stderr = open(self.stderr_fname, 'w')

            self.opts.telemetry = os.path.join(self.workdir, "telemetry.log")

        if self.opts.html_report and self.browser_id == 0:
            self._html_report = ptBrowserHtmlReport(self.opts.html_report, title=self.urls[0])
            self._html_report.gen_index_html()

    def fini(self):
        if self.browser_id:
            sys.stdout = self._stdout_orig
            sys.stderr = self._stderr_orig

        if self._html_report:
            p = self._html_report.gen_index_html()
            print("See HTML report here: %s" % p)

    def _detect_cp_type(self):
        for cp in self.cp_engines:
            self.browser.log_info("Trying to recognize: %s ..." % cp.type)
            c = cp(self.browser, self.user, self.opts.password, self._html_report)
            if not c.cp_init_context():
                continue
            if not len(c.menu_xpaths):
                continue
            for cpmx in c.menu_xpaths[0]:
                c.switch_to_frame(cpmx.frame, verbose=False)
                if self.browser.driver.find_elements_by_xpath(cpmx.link_xpath):
                    self.browser.log_info("%s control panel detected" % c.type)
                    c.switch_to_default_content()
                    return c
                c.switch_to_default_content()
        return None

    def _login(self, url, wait_completion=True):
        self.browser.navigate_to(url, cached=False)
        for cp in self.cp_engines:
            self.browser.log_info("Trying to login into: %s ..." % cp.type)
            c = cp(self.browser, self.user, self.opts.password)
            if not c.cp_init_context():
                continue
            if c.cp_do_login(url, timeout_s=None if wait_completion else 2.0):
                return True
        logging.error("Login to %s under %s:%s failed" % (url, self.user, self.opts.password))
        sys.exit(-1)

    def _pt_suite_init(self, cp):
        if not self.opts.pt_project:
            return

        suite_ver = self.opts.pt_version if self.opts.pt_version else __version__
        suite_name = "cp_crawler"
        product_ver = self.opts.pt_product_version if self.opts.pt_product_version else cp.cp_get_product_version()
        product_name = self.opts.pt_product_name if self.opts.pt_product_name else cp.cp_get_product_name()

        self.pt_suite.suite_ver = suite_ver
        self.pt_suite.suite_name = suite_name
        self.pt_suite.product_ver = product_ver
        self.pt_suite.product_name = product_name

        if not self.opts.pt_title and product_name and product_ver:
            self.pt_suite.job_title = "%s %s" % (product_name, product_ver)

        ram = virtual_memory()

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()

        client = self.pt_suite.addNode(ptVM("client", version=platform.platform(), ip=ip, cpus=cpu_count(),
                                       ram_mb=int(ram.total / (1024 * 1024)) if ram else 0))
        client.addNode(ptComponent(self.browser.browser_get_name(), self.browser.browser_get_version()))

    def _pt_upload(self):
        if not self.opts.pt_project:
            return

        self.pt_suite.upload()

    def _pt_update_results(self, page):
        if self.opts.pt_project is None or page is None:
            return

        basename = page.get_full_name()
        if basename is None:
            return

        for s, m, f, g in (("Rendering", "msec", "dur", "Page rendering"),
                           ("Footprint", "KB", "ram_usage_kb", "Browser memory footprint")):
            name = "%s [%s, %s]" % (basename, s, m)
            group = "%s (%s)" % (g, m)
            test = self.pt_suite.getTest(name, group=group)
            if test is None:
                test = ptTest(name, less_better=True, group=group, metrics=m, description=page.url)
                self.pt_suite.addTest(test)

            test.add_score(page.__dict__[f])
            test.duration_sec += int(math.ceil(page.dur))

        self._pt_upload()

    def _run(self):

        self.browser.print_browser_info()

        urls = copy.copy(self.urls)

        CP = None

        if self.user:
            if self.opts.uncached:
                logging.error("Can't combine --user and --uncached mode")
                return None
            if len(self.urls) == 0:
                logging.error("Login URL is not specified")
                return None

            self._login(urls[0][1], wait_completion=self.opts.login_wait and self.opts.add_login_landing)

            CP = self._detect_cp_type()

            if self.opts.add_login_landing:
                curr_url = self.browser.browser_get_current_url()
                if curr_url not in [u[1] for u in urls]:
                    urls = [('Login landing page', curr_url)] + urls

        if self.opts.menu_walk:
            if not self.user:
                name, url = urls[0]
                page = self.browser.navigate_to(url, name=name)

            if CP is None:
                CP = self._detect_cp_type()

            if not CP:
                logging.error("Can't recognize Control Panel, aborting")
                sys.exit(-1)
            items = CP.cp_do_scan_menu()
            if items:
                urls = items

        if CP is None:
            CP = CPEngineBase(self.browser, html_report=self._html_report)

        CP.cp_handle_opts(self.opts)
        self._pt_suite_init(CP)

        if self.opts.randomize_urls:
            import random
            for i in range(len(urls)):
                j = random.randint(0, len(urls) - 1)
                urls[i], urls[j] = urls[j], urls[i]

        print("")
        PageStats.print_title("URLs to navigate")
        print("  " + "\n  ".join(["%s%s" % (("%-25s - " % u[0]) if u[0] else "", u[1]) for u in urls]))

        pages = {}

        cached = not self.opts.uncached

        print_title = True
        for name, url in urls:
            try:
                page = CP.cp_do_navigate(url, cached=cached, name=name)
                self._pt_update_results(page)
                if not page:
                    raise CPCrawlerException("Page navigation (%s) failed, aborting" % url)

                pages[url] = page
            except BrowserExc as e:
                logging.error("Browser exception @ %s: %s\n%s" % (name, url, e))
                continue

            if self.opts.html_report:
                img_path = self._html_report.add_page(url, page=page)
                self.browser.browser_get_screenshot_as_file(img_path)
                self._html_report.gen_thumbnails(url)

            if self.opts.requests:
                description = ["SCREEN: %s" % page.get_full_name(), "URL: %s" % page.url]
                if print_title:
                    page.print_page_req_groups_stats(title=print_title, description=description)
                else:
                    page.print_page_req_groups_stats(title=print_title, description=description)
                print_title = False

        if self.opts.requests:
            print_title = True
            for page in pages.values():
                description = ["SCREEN: %s" % page.get_full_name(), "URL: %s" % page.url]
                page.print_page_requests_stats(title=print_title, description=description)
                print_title = False

        need_to_exit = False

        browser_page_stats = []
        simulators_page_stats = []

        if self.opts.python_browsers:
            simulators = []
            for n in range(0, self.opts.python_browsers):
                log_path = os.path.join(self.logdir, "%s.%d.log" % (BrowserPython.engine, n))
                simulators.append(BrowserPython(log_path=log_path))

        for name, url in urls:
            if url not in pages:
                continue

            page = pages[url]

            if self.opts.python_browsers:
                map(lambda x: x.loop_start([page], sleep_sec=self.opts.delay), simulators)

            description = ["BROWSER:      %s" % self.browser.browser_get_name(),
                           "SIMULATORS:   %d browser(s) in background" % (self.opts.python_browsers),
                           ] if self.opts.python_browsers else []

            page_full_name = page.get_full_name()
            page_url = page.url

            description.append("%11s %s" % ("SCREEN (CACHED):" if cached else "SCREEN (UNCACHED):", page_full_name))
            if page_url != page_full_name:
                description.append("%11s %s" % ("URL:", page_url))

            self.browser.page_stats[page.get_key()].print_page_timeline_header(title=not len(browser_page_stats),
                                                                               description=description)

            try:
                for n in range(0, self.opts.loops):
                    if n == 0 and not self.opts.python_browsers:
                        # use already fetched page
                        self.browser.page_stats[page.get_key()].print_page_timeline(pages[url], title=str(n + 1))
                        continue

                    time.sleep(self.opts.delay)
                    try:
                        if self.opts.reset_dom:
                            CP.browser.navigation_reset()
                        page = CP.cp_do_navigate(url, cached=cached, name=name)
                        self._pt_update_results(page)
                        if not page:
                            raise CPCrawlerException("Page navigation (%s) failed, aborting" % url)

                        self.browser.page_stats[page.get_key()].print_page_timeline(page, title=str(n + 1))
                    except BrowserExc as e:
                        logging.error(e)
                        # break
            except KeyboardInterrupt:
                need_to_exit = True

            br_ps = self.browser.page_stats[page.get_key()]
            br_ps.id = self.browser.browser_get_name()
            avg = br_ps.get_avg()
            self.browser.page_stats[page.get_key()].print_page_timeline(avg, title="Average", hr=True)
            browser_page_stats.append(br_ps)

            if self.opts.python_browsers:
                map(lambda x: x.loop_stop(), simulators)
                map(lambda x: x.loop_wait(), simulators)

                py_ps = PageStats("%d python simulator(s)" % (self.opts.python_browsers))
                for s in simulators:
                    py_ps.iterations += s.page_stats[page.get_key()].iterations

                simulators_page_stats.append(py_ps)

            if need_to_exit:
                break

        for ps in browser_page_stats:
            self.page_stats_summary.add_page_stats(ps)
        for ps in simulators_page_stats:
            self.page_stats_summary.add_page_stats(ps)

    def run(self):

        if self.opts.log2file or self.opts.log_file:
            logging.basicConfig(filename=self.crawler_logfile, level=logging.DEBUG)
            print("Redirecting %sverbose logs to %s" %
                  ("browser.%d " % self.browser_id if self.browser_id is not None else "", self.crawler_logfile))
        else:
            level = logging.DEBUG if self.opts.verbose > 1 else logging.INFO if self.opts.verbose else logging.WARNING
            logging.basicConfig(level=level)

        logger = logging.getLogger()
        for handler in logger.root.handlers:
            handler.setFormatter(CPLogFormatter())

        self.init()

        if self.opts.session:
            self.browser.domain_set_session(self.urls[0], self.opts.session)

        try:
            self._run()
            print("")
        except KeyboardInterrupt:
            pass
        except BrowserExc as e:
            print(e)
        except RuntimeError:
            self.fini()
            raise
        finally:
            self.browser.browser_stop()
            self.fini()

        if not self.browser_id:
            if self.page_stats_summary:
                self.page_stats_summary.print_summary(title='Final summary')

            if self.opts.wait:
                print("Press Ctrl+C to exit...")
                try:
                    time.sleep(10000)
                except KeyboardInterrupt:
                    pass
        else:
            print("browser.%d done" % self.browser_id)


class CPCrawler:
    def __init__(self, workdir=None, logfile=None, pt_job_title=None, pt_server_url=None):

        self.workdir = workdir if workdir else os.path.join(gettempdir(), "%s.%d" % (basename, os.getpid()))
        self.logfile = logfile
        self.opts = None
        self.urls = []

        self.pt_suite = ptSuite("UI crawler job" if pt_job_title is None else pt_job_title,
                                pt_server_url=pt_server_url)

    def _gen_users(self, users_ar):
        if not users_ar:
            return None

        users = []
        for u in users_ar:
            for _u in u.split(","):
                if "{" in _u:
                    m = re.search("(?P<pfx>.*?){(?P<from>\d+)-(?P<to>\d+)}(?P<sfx>.*)", _u)
                    if not m:
                        raise CPCrawlerException("can't parse users range from '%s',"
                                                 "valid pattern is 'prefix{from-to}suffix'" % _u)
                    for n in range(int(m.group('from')), int(m.group('to')) + 1):
                        users.append(m.group('pfx') + str(n) + m.group('sfx'))
                else:
                    users.append(_u)
        return users

    def add_options(self, op, passwd="password",
                    nav_timeout=OPT_DEFAULT_NAV_TIMEOUT,
                    ajax_threshold=OPT_DEFAULT_AJAX_THRESHOLD,
                    delay_between_click_sec=OPT_DELAY_BETWEEN_CLICK_SEC):

        og = OptionGroup(op, "Control Panel crawler options")
        og.add_option("-v", "--verbose", action="count", default=0,
                      help="run in verbose mode, use -vvv for max verbosity")
        og.add_option("", "--log-file", type="string", help="log into the file (default %s)" % self.logfile)
        og.add_option("", "--log2file", action="store_true", help="enable --verbose mode and log to the --log-file")
        og.add_option("-V", "--view", action="store_true", help="Show browser screen")
        og.add_option("-g", "--html-report", type="string",
                      help="generate HTML report with screenshots and other information")
        og.add_option("-t", "--telemetry", type="string",
                      help="log pages to given file (append only, concurrent-process-safe)")
        og.add_option("-w", "--wait", action="store_true", help="don\'t close the browser and wait till test is killed")
        og.add_option("-l", "--loops", type="int", default=7, help="number of iterations, default %default")

        og.add_option("-b", "--browser", choices=[b.engine for b in BROWSERS], default=BROWSERS[0].engine,
                      help="browser to use: %s (default is '%%default')" %
                      ",".join(['\'%s\'' % b.engine for b in BROWSERS]))
        og.add_option("-r", "--requests", action="store_true",
                      help="print information about individual network requests")
        og.add_option("-o", "--perf-atomic-format", action="store_true", help="perf-atomic output format")
        op.add_option_group(og)

        og = OptionGroup(op, "Authentication options")
        og.add_option("-U", "--user", action="append", type="string", default=None,
                      help="try to login with given user name before the test (comma-separated list accepted)")
        og.add_option("-P", "--password", type="string", default=passwd, help="password, default: %default")
        op.add_option_group(og)

        og = OptionGroup(op, "Navigation options")
        og.add_option("-m", "--menu-walk", action="store_true",
                      help="search for menu items and click on every menu item")
        og.add_option("-L", "--skip-login-landing-url", action="store_false", dest="add_login_landing", default=True,
                      help="skip login landing page URL")
        og.add_option("", "--dont-wait-login-landing", action="store_false", dest="login_wait", default=True,
                      help="do not wait for full login landing page load")
        og.add_option("-R", "--randomize-urls", action="store_true", help="randomize menu items sequence")
        og.add_option("-f", "--urls-file", type='string', help="get URLs from file (instead of command line)")
        og.add_option("-i", "--dir-index", action="store_true",
                      help="treat given page as apache directory listing index page and parse URLs from there")
        og.add_option("-u", "--uncached", action="store_true", help="invalidate browser cache before each request")
        og.add_option("-s", "--session", type="string", help="session ID")
        og.add_option("-e", "--reset-dom", action="store_true", help="reset DOM model after every nav click")

        op.add_option_group(og)

        og = OptionGroup(op, "Page navigation timings")
        og.add_option("-d", "--delay", type="float", default=delay_between_click_sec,
                      help="delay between GET requests, default %default sec")
        og.add_option("-T", "--nav-timeout", type="float", dest='nav_timeout', default=nav_timeout,
                      help="navigation timeout, sec (default %default)")
        og.add_option("-A", "--ajax-threshold", type="float", dest='ajax_threshold', default=ajax_threshold,
                      help="page considered as complete if no ajax requests issued after the "
                           "AJAX_THRESHOLD, sec (default %default)")
        op.add_option_group(og)

        og = OptionGroup(op, "Mass load mode")
        og.add_option("-X", "--real-browsers", type="int", default=0,
                      help="run REAL_BROWSERS instances of the real browsers, users (if any) "
                           "will be spread equally by the instances")
        og.add_option("-x", "--python-browsers", type="int", default=0,
                      help="run PYTHON_BROWSERS satellite/clone python browsers per every real "
                           "browser to increase load on server")
        og.add_option("-D", "--instances-delay", type="float", default=0.3,
                      help="delay between instances start (sec) (default %default)")
        og.add_option("-W", "--work-dir", type="string",
                      help="work directory with the tool logs and final HTML report, default %default")
        op.add_option_group(og)

        self.pt_suite.addOptions(op)

    def init_opts(self, opts, urls, init_logging=True):

        if opts.urls_file:
            if not urls:
                urls = []
            try:
                f = open(opts.urls_file)
                for line in f.readlines():
                    urls.append(line.strip())
                f.close()
            except Exception as e:
                raise CPCrawlerException("ERROR: %s" % e)

        if not urls:
            raise CPCrawlerException("URL is not specified")

        if opts.work_dir:
            self.workdir = opts.work_dir
            self.logfile = basename + ".log"

        if opts.log_file:
            self.logfile = opts.log_file
        self.opts = opts
        if opts.dir_index:
            self.urls = [(None, u) for u in gen_urls_from_index_file(urls)]
        else:
            self.urls = [(None, u) for u in urls]

        shutil.rmtree(self.workdir, ignore_errors=True)
        os.makedirs(self.workdir, mode=0o777)

        if init_logging:
            self.init_logging(opts)

        self.pt_suite.handleOptions(opts)

    def init_logging(self, opts):
        if opts.log2file or opts.log_file:
            logging.basicConfig(filename=self.logfile, level=logging.DEBUG)
            print("Redirecting verbose logs to %s" % self.logfile)
        else:
            level = logging.DEBUG if opts.verbose > 1 else logging.INFO if opts.verbose else logging.WARNING
            logging.basicConfig(level=level)
            if opts.verbose < 3:
                selenium_logger.setLevel(logging.WARNING)

        logger = logging.getLogger()
        for handler in logger.root.handlers:
            handler.setFormatter(CPLogFormatter())

    def crawl(self, cp_engines=None):

        def _browser_launch(queue, cp_engines, opts, urls, users, browser_id, logfile, workdir, pt_suite):
            cpbr = CPBrowserRunner(cp_engines, opts, urls, users, browser_id, logfile, workdir, pt_suite)
            if browser_id:
                try:
                    cpbr.run()
                except RuntimeError:
                    logging.error(traceback.format_exc())
            else:
                cpbr.run()
            if queue:
                queue.put(cpbr)
            return cpbr

        if not cp_engines:
            cp_engines = [CPEngineBase]

        if self.opts is None:
            raise CPCrawlerException("the init_opts() method must be called before run()")

        users = self._gen_users(self.opts.user)

        if users and len(users) > 1 and len(users) > self.opts.real_browsers:
            raise CPCrawlerException("ERROR: number of users (%d) can't be higher than number of browsers (%d)"
                                     % (len(users), self.opts.real_browsers))

        if self.opts.real_browsers > 0:
            real_browsers = []
            cpbr_objs = {}

            for i in range(1, self.opts.real_browsers + 1):
                cpbr_objs[i] = Queue()
                b = Process(target=_browser_launch, args=(cpbr_objs[i], cp_engines, self.opts, self.urls, users, i,
                                                          self.logfile, self.workdir, self.pt_suite))
                b.start()
                real_browsers.append(b)
                time.sleep(self.opts.instances_delay)

            delay = 3
            telemetry_fname = os.path.join(self.workdir, "telemetry.log")
            report_fname = os.path.join(self.workdir, "report.html")

            print("")
            print("Notes:")
            print("   * Tests executed by %d %s browsers%s%s" %
                  (self.opts.real_browsers, self.opts.browser,
                   " and %d python browsers" % (self.opts.real_browsers * self.opts.python_browsers)
                   if self.opts.python_browsers else "",
                   " on %d users:\n       %s" % (len(users), "\n       ".join(users)) if users else ""))
            print("   * All data is stored in %s" % self.workdir)
            print("   * The %s file is updated every %d sec" % (report_fname, delay))
            print("")

            while True:
                time.sleep(delay)
                all_dead = True
                for b in real_browsers:
                    if not b.is_alive():
                        continue
                    all_dead = False

                if all_dead:
                    break

            page_stats_summary = PageStatsSummary()

            for i in range(1, self.opts.real_browsers + 1):
                cpbr = cpbr_objs[i].get()
                if os.path.exists(cpbr.stderr_fname):
                    f = open(cpbr.stderr_fname, 'r')
                    data = f.read()
                    f.close()
                    if data:
                        print("browser.%d stderr:\n%s" % (i, data))

                for ps in cpbr.page_stats_summary.page_stats:
                    page_stats_summary.add_page_stats(ps)

            report_fname = os.path.join(self.workdir, "report.html")

        else:
            cpbr = _browser_launch(None, cp_engines, self.opts, self.urls, users, 0, self.logfile,
                                   self.workdir, self.pt_suite)
            page_stats_summary = cpbr.page_stats_summary

        return page_stats_summary.page_stats


##############################################################################
# Autotests
##############################################################################


if __name__ == "__main__":
    usage = "usage: %prog [options] URL [URL2 [URL3 ...]]"

    op = OptionParser(usage=usage)
    og = OptionGroup(op, "My specific options")
    op.add_option("-c", "--config", type="string", help="Some config file")
    op.add_option_group(og)

    cpc = CPCrawler()
    cpc.add_options(op)

    opts, urls = op.parse_args()

    # override options to simplify the test
    opts.loops = 1
    urls = ["https://example.com/"]

    cpc.init_opts(opts, urls)

    cpc.crawl()
