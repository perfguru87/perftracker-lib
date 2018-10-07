#!/usr/bin/env python

from __future__ import print_function

# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

"""Python interface for timeline.js library: http://almende.github.io/chap-links-library/timeline.html
"""

import os
import re
import sys
import datetime

from .html import pt_html_escape

try:
    from dateutil import tz

    def _to_local_tz(s):
        try:
            return s.astimezone(tz.tzlocal())
        except ValueError:
            return s
except ImportError:
    def _to_local_tz(s):
        return s


if sys.version_info >= (3, 0):
    basestring = str


def _unicode2str(data):
    if isinstance(data, basestring):
        return str(data)
    elif isinstance(data, collections.Mapping):
        return dict(map(_unicode2str, data.iteritems()))
    elif isinstance(data, collections.Iterable):
        return type(data)(map(_unicode2str, data))
    else:
        return data


class ptPhase:
    def __init__(self, bg_color="#61b7d1", fg_color="#000", description=""):
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.description = description


class ptTaskPhase:
    def __init__(self, width, title="", hint=""):
        self.width = width
        self.title = title
        if hint == "":
            hint = title
        self.hint = hint


class ptParser:
    r = re.compile("")

    def parse(self, s):
        m = self.r.search(s)
        if not m:
            return None
        return "new uDate(%d, %d, %d, %d, %d, %d, %d)" % \
               (int(m.group('y')), int(m.group('mo')) - 1, int(m.group('d')),
                int(m.group('h')), int(m.group('mi')), int(m.group('s')), self.get_usec(m))


class ptParserDate(ptParser):
    r = re.compile("^(?P<y>\d+)-(?P<mo>\d\d)-(?P<d>\d\d) (?P<h>\d\d):(?P<mi>\d\d):(?P<s>\d\d)$")

    def get_usec(self, match):
        return 0


class ptParserDateMsec(ptParser):
    r = re.compile("^(?P<y>\d+)-(?P<mo>\d\d)-(?P<d>\d\d) (?P<h>\d\d):(?P<mi>\d\d):(?P<s>\d\d).(?P<ms>\d\d\d)$")

    def get_usec(self, match):
        return int(match.group('ms')) * 1000


class ptParserDateUsec(ptParser):
    r = re.compile("^(?P<y>\d+)-(?P<mo>\d\d)-(?P<d>\d\d) (?P<h>\d\d):(?P<mi>\d\d):(?P<s>\d\d).(?P<us>\d\d\d\d\d\d)$")

    def get_usec(self, match):
        return int(match.group('us'))


class ptParserUsec(ptParser):
    r = re.compile("^(?P<us>\d+)$")

    def parse(self, s):
        m = self.r.search(s)
        return "new uDate(%s)" % (m.group('us')) if m else None


class ptTask:
    def __init__(self, begin, end, title="", comment="", data_id="", cssClass="", group=None, hint=None, phases=None):
        """
        Supported ptTask begin/end format:
        1) YYYY-MM-DD HH:SS:MM
        2) YYYY-MM-DD HH:SS:MM.MSEC
        3) YYYY-MM-DD HH:SS:MM.USEC
        4) USEC
        """

        self.begin = begin
        self.end = end
        self.props = {}

        self._parsers = [ptParserDate(), ptParserDateMsec(), ptParserDateUsec(), ptParserUsec()]
        self._parser = self._parsers[0]

        data_id = (" data-id=\"%s\"" % data_id) if data_id else ""

        if phases:
            if hint:
                s = '<div class="timeline-event-phases" title="%s"%s>' % (pt_html_escape(hint), data_id)
            else:
                s = '<div class="timeline-event-phases">'
                for p in range(0, len(phases)):
                    s += '<div class="timeline-event-phase%d" style="width: %d%%;" title="%s">' % \
                         (p, phases[p].width, pt_html_escape(phases[p].hint))
                    if phases[p].title:
                        s += '<span>%s</span>' % phases[p].title
                    s += '</div>'
                s += '</div>'
                self.props['content'] = s
        elif title or comment:
            if comment:
                title += "<br><small>%s</small>" % comment
            if hint:
                title = '<span title="%s"%s>%s</span>' % (pt_html_escape(hint), data_id, title)
            self.props['content'] = title

        if cssClass:
            self.props['className'] = cssClass
        if group:
            self.props['group'] = group

    def _str2udate(self, s):
        if s == "":
            return " "

        if type(s) == int:
            return "new uDate(%d)" % s

        if type(s) == datetime.datetime:
            t = _to_local_tz(s)
            return "new uDate(%s, %s, %s, %s, %s, %s, %s)" % \
                   (t.year, t.month - 1, t.day, t.hour, t.minute, t.second, t.microsecond)

        ret = self._parser.parse(s)
        if ret:
            return ret  # fast path

        for p in self._parsers:
            ret = p.parse(s)
            if ret:
                self._parser = p
                return ret

        print("unsupported task date/time format: %s" % s, file=sys.stderr)
        return False

    def get_begin_end(self):
        return self._str2udate(self.begin), self._str2udate(self.end)

    def get_props(self, columns):
        ar = []
        for c in columns:
            ar.append("'%s'" % (self.props.get(c, '')))
        return ar


class ptEvent(ptTask):
    def __init__(self, time, title, comment="", cssClass="", group=""):
        TlTask.__init__(self, time, "", title, comment, cssClass, group)


TIMELINE_ID = 0


class ptTimeline:
    def __init__(self, title=None, width="100%", height="auto", begin=None, end=None, js_opts=None, groups_title=None,
                 cluster=True):

        global TIMELINE_ID
        self.tasks = []
        self.title = title
        self.width = width
        self.height = height

        self.begin = begin
        self.end = end

        self.cluster = cluster  # group events into clusters on zoom-out

        if js_opts:
            self.js_opts = js_opts
        else:
            self.js_opts = {'axisOnTop': 'true', 'showNavigation': 'true'}
        if groups_title:
            self.js_opts['groupsTitle'] = "'%s'" % groups_title

        self.columns = []

        self.id = TIMELINE_ID
        TIMELINE_ID += 1

    def add_task(self, task):
        assert isinstance(task, ptTask)
        for key, val in task.props.items():
            if key not in self.columns:
                self.columns.append(key)
        self.tasks.append(task)

    def gen_js(self):

        s = "var vis%d;\n" % self.id

        s += """
             var dt%d = new google.visualization.DataTable();
             function createTimeline%d() {
                 // Create and populate a data table.
                 dt%d.addColumn('datetime', 'start');
                 dt%d.addColumn('datetime', 'end');
             """ % (self.id, self.id, self.id, self.id)

        for c in self.columns:
            s += "dt%d.addColumn('%s', '%s');\n" % (self.id, 'string', c)

        if len(self.tasks):
            s += "dt%d.addRows([" % self.id

            for t in self.tasks:
                b, e = t.get_begin_end()
                s += "[%s],\n" % (', '.join([b, e] + t.get_props(self.columns)))

            s += "]);\n"

        s += "options = {width: '%s', height: '%s', " % (self.width, self.height)
        s += "layout: 'box', cluster: %s, snapEvents: true, eventMargin: 0, eventMarginAxis: 4," % \
             (str(self.cluster).lower())

        if self.begin and self.end:
            s += "start: '%s', end: '%s', " % (self.begin, self.end)

        for key, val in self.js_opts.items():
            s += "%s: %s," % (key, _unicode2str(val))

        s += """
             };
             vis%d = new links.Timeline(document.getElementById('timeline%d'), options);
             google.visualization.events.addListener(vis%d, 'rangechange', onrangechange%d);
             vis%d.draw(dt%d);
             """ % (self.id, self.id, self.id, self.id, self.id, self.id)

        s += "}"
        return s

    def gen_html(self):
        ret = "<div id='timeline%d'></div>" % self.id
        if self.title:
            ret = "<h3>%s</h3>%s" % (self.title, ret)
        return ret


class ptSection:
    def __init__(self, title=None, autofit=False):
        self.title = title
        self.autofit = autofit
        self.timelines = []
        self.phases = []

    def add_phase(self, phase):
        assert isinstance(phase, ptPhase)
        self.phases.append(phase)
        return phase

    def add_timeline(self, timeline):
        assert isinstance(timeline, ptTimeline)
        self.timelines.append(timeline)
        return timeline

    def gen_title(self):
        return ("<h1>%s</h1>" % self.title) if self.title else ""

    def gen_html(self):
        s = ""
        if len(self.phases):
            s += "<style type=\"text/css\">\n"
            for p in range(0, len(self.phases)):
                s += ".timeline-event-phase%d { background-color: %s !important; color: %s !important; }\n" % \
                     (p, self.phases[p].bg_color, self.phases[p].fg_color)
            s += "</style>\n"

        s += """
            <script type="text/javascript">
            google.load("visualization", "1", {packages:['table']});

            // Set callback to run when API is loaded
            google.setOnLoadCallback(drawVisualization);
            """

        for t in self.timelines:
            s += t.gen_js()

        s += """
            function drawVisualization() {
                var start = undefined, end = undefined;
            """

        for t in self.timelines:
            s += """
                 createTimeline%d();

                 var range = vis%d.getVisibleChartRange();
                 if (!start || start > range.start)
                     start = range.start;
                 if (!end || end < range.end)
                     end = range.end;
                 """ % (t.id, t.id)

        if self.autofit:
            for t in self.timelines:
                s += "vis%d.setVisibleChartRange(start, end);\n" % t.id
        else:
            for t in self.timelines:
                s += "onrangechange%d();\n" % t.id

        s += "}"

        for t in self.timelines:
            s += """
                 function onrangechange%d() {
                     var range = vis%d.getVisibleChartRange();
                 """ % (t.id, t.id)

            for _t in self.timelines:
                if _t.id == t.id:
                    continue
                s += "vis%d.setVisibleChartRange(range.start, range.end);\n" % _t.id

            s += "}\n"

        s += "</script>"

        for t in self.timelines:
            s += t.gen_html()

        if len(self.phases):
            s += "<table style='margin-top: 5px; float:right;'>"
            s += "<tr style='font-size: 10px;'>"
            s += "<td><b>Tasks phases:</b></td>"
            for p in range(0, len(self.phases)):
                s += """
                     <td style='padding: 1px 1px 1px 10px;'>
                         <div class='timeline-event'>
                             <div class='timeline-event-phase timeline-event-phase%d'>&nbsp;</div>
                         </div>
                     </td>
                     <td style='padding: 1px 0px 1px 5px;'>%s</td>
                     """ % (p, self.phases[p].description)
            s += "</tr></table>"

        return s


class ptDoc:
    def __init__(self, title=None, header=None, footer=None):
        self.sections = []
        self.footer = footer if footer else "</body></html>"
        if header:
            self.header = header
        else:
            self.header = "<html><head><meta http-equiv='content-type' content='text/html; charset=utf-8'>"
            if title:
                self.header += "<title>%s</title>" % str(title)
            self.header += "</head>"
            self.header += "<body>"
        self.body = self._embed(["jsapi.js", "udate.js", "timeline.js", "formatendefault.js"])
        self.body += self._embed(["timeline.css", "table.css"])
        self.body += "<style type='text/css'>body {font: 9pt arial;}</style>"

    def add_body(self, body):
        self.body += body

    def add_section(self, section):
        assert isinstance(section, ptSection)
        self.sections.append(section)
        return section

    def _embed(self, files):
        ret = ""
        for f in files:
            p = os.path.join(os.path.abspath(os.path.dirname(__file__)), "timeline", f)
            try:
                f = open(p)
            except IOError:
                print("Can't open file: %s" % p, file=sys.stderr)
                continue

            body = f.read()
            f.close()

            if p.endswith(".js"):
                ret += "<script type='text/javascript'>%s</script>" % body
            elif p.endswith(".css"):
                ret += "<style type='text/css'>%s</style>" % body
        return ret

    def gen_html(self):
        ret = self.header + self.body
        for s in self.sections:
            ret += s.gen_html()
        ret += self.footer
        return ret


##############################################################################
# Autotests
##############################################################################

if __name__ == "__main__":
    d = ptDoc(title='timeline.py examples')
    s = d.add_section(ptSection())

    t = s.add_timeline(ptTimeline("Timeline#1"))
    t.add_task(ptTask("2018-05-05 01:00:01", "2018-05-05 02:03:04", "Task#1", "Task comments 1"))
    t.add_task(ptTask("2018-05-05 01:15:25", "2018-05-05 01:18:26", "Task#2", "Task comments 2"))
    t.add_task(ptTask("2018-05-05 02:03:04", "2018-05-05 05:06:07", "Task#3"))

    t = s.add_timeline(ptTimeline("Timeline#2 (with phases)", groups_title="Groups"))
    s.add_phase(ptPhase("#444", "#eee", "Phase#1"))
    s.add_phase(ptPhase("#555", "#eee", "Phase#2"))
    s.add_phase(ptPhase("#777", "#fff", "Phase#3"))

    t.add_task(ptTask("2018-05-05 01:00:01", "2018-05-05 02:03:04", "Task#1", "Task comments 1", group="group#1",
                      phases=[ptTaskPhase(25, "some phase#1"),
                              ptTaskPhase(35, "some phase#2"),
                              ptTaskPhase(40, "some phase#3"),
                              ]
                      ))
    t.add_task(ptTask("2018-05-05 02:00:30", "2018-05-05 02:20:00", "Task#2", "Task comments 2", group="group#1",
                      phases=[ptTaskPhase(5),
                              ptTaskPhase(10),
                              ptTaskPhase(85, "some phase#3"),
                              ]
                      ))
    t.add_task(ptTask("2018-05-05 02:20:30", "2018-05-05 02:30:00", "Task#3", "Task comments 3", group="group#2",
                      phases=[ptTaskPhase(10, "some phase#1"),
                              ptTaskPhase(20, "some phase#2"),
                              ptTaskPhase(70, "some phase#3"),
                              ]
                      ))
    t.add_task(ptTask("2018-05-05 02:24:31.123", "2018-05-05 02:24:45.123456", "Task#3", group="group#3",
                      phases=[ptTaskPhase(10, "some phase#1"),
                              ptTaskPhase(20, "some phase#2"),
                              ptTaskPhase(70, "some phase#3"),
                              ]
                      ))

    s = d.add_section(ptSection())
    t = s.add_timeline(ptTimeline("Timeline#3"))
    t.add_task(ptTask("100", "190", "Task#1"))
    t.add_task(ptTask(95, 159, "Task#2"))
    t.add_task(ptTask(125, 210, "Task#3"))

    print(d.gen_html())
