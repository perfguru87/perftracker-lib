from __future__ import print_function, absolute_import

# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

import sys
import os
import optparse
import requests
import json
import datetime
import uuid
import inspect
import logging
import pipes
import subprocess
import bz2
import random
import citizenshell
from math import sqrt
from dateutil import parser

from optparse import OptionParser, OptionGroup

from perftrackerlib.helpers.tee import Tee
from perftrackerlib.helpers.decorators import cached_property
from perftrackerlib.helpers.ptshell import ptShell, ptShellFromFile

from dateutil.tz import tzlocal
from collections import OrderedDict

if sys.version_info >= (3, 0):
    import http.client as httplib
else:
    import httplib

API_VER = '1.0'
PT_SERVER_DEFAULT_URL = "http://127.0.0.1:9000"

TEST_STATUSES = ['NOTTESTED', 'SKIPPED', 'INPROGRESS', 'SUCCESS', 'FAILED']


def pt_float(value):
    if value > 100 or value < -100:
        return int(round(value))
    elif value < 0.00000001:
        return 0

    val = abs(float(value))
    thr = 100
    prec = 0
    while val < thr:
        prec += 1
        thr /= 10.0
    fmt = "%." + str(prec) + "f"
    return float(fmt % (val)) * (1 if value > 0 else -1)


def get_timestamp_from_datetime(time):
    assert isinstance(time, datetime.datetime)
    time = time.replace(tzinfo=tzlocal())
    epoch = datetime.datetime(1970, 1, 1, tzinfo=tzlocal())
    return int((time - epoch - time.utcoffset()).total_seconds() * 1000)


class ptRuntimeException(Exception):
    pass


class ptJsonEncoder(json.JSONEncoder):
    def default(self, obj):
        j = OrderedDict()
        if not inspect.isclass(type(obj)):
            return json.dumps(obj)
        if isinstance(obj, datetime.datetime):
            return obj.replace(tzinfo=tzlocal()).isoformat()
        if isinstance(obj, uuid.UUID):
            return str(obj)

        for key in obj.__dict__.keys():
            if key.startswith("_"):
                continue
            val = obj.__dict__[key]
            if val is None or not val:
                continue
            if type(val) == str:
                try:
                    val = val.decode(errors='ignore').encode('utf-8')
                except AttributeError as e:
                    pass
            j[key] = val
        return j

    @staticmethod
    def pretty(obj):
        return json.dumps(obj, cls=ptJsonEncoder, sort_keys=True, indent=4, separators=(',', ': '))


class ptServer:
    def __init__(self, pt_server_url=None):
        if pt_server_url is None:
            pt_server_url = PT_SERVER_DEFAULT_URL
        self.url = None
        self.api_url = None
        self.setUrl(pt_server_url)

    def setUrl(self, pt_server_url):
        if not pt_server_url.startswith("http"):
            logging.debug("adding http:// prefix to server url: %s" % pt_server_url)
            pt_server_url = "http://%s" % pt_server_url
        self.url = pt_server_url.rstrip("/")
        self.api_url = "%s/api/v%s" % (self.url, API_VER)

    def getProjectId(self, project_name):
        if not project_name:
            return None

        resp = self.get("/0/project/")

        if resp.status_code != httplib.OK:
            raise ptRuntimeException("can't get the list of existing projects: %d, %s" %
                                     (j['http_status'], j.get('message', str(j))))

        for project_json in resp.json:
            if project_json['name'] == project_name:
                return project_json['id']

        msg = "\n".join(["project name validation failed, project '%s' doesn't exist" % project_name,
                         "available projects are: %s" % (", ".join(["'%s'" % p['name'] for p in resp.json]))])
        raise ptRuntimeException(msg)

    def _http_request(self, method, url, decode_json=True, *args, **kwargs):

        url = "%s/%s" % (self.api_url, url.lstrip("/"))

        logging.debug("%s %s ..." % (method, url))

        # FIXME: handle retry
        headers = {'Content-Type': 'application/json'} if method == "GET" else {}
        try:
            response = requests.__dict__[method](url, headers=headers, *args, **kwargs)
        except requests.exceptions.ConnectionError as e:
            raise ptRuntimeException(str(e))

        if decode_json or response.status_code != httplib.OK:
            text = response.text.encode(response.encoding if response.encoding else 'utf-8', 'strict')
            text = text.decode('utf-8', 'strict')
            try:
                j = json.loads(text)
                response.json = j
            except ValueError as e:
                raise ptRuntimeException("%s\nresponse:%s" % (str(e), str(text.encode('utf-8'))))

        if response.status_code == httplib.OK:
            if logging.getLogger().getEffectiveLevel() >= logging.DEBUG:
                if decode_json:
                    logging.debug("%s %s ... response:\n%s" % (method, url, ptJsonEncoder.pretty(j)))
                else:
                    logging.debug("%s %s ... response size %d" % (method, url, len(response.content)))
        else:
            logging.error("%s %s status: %s, message: %s" %
                          (method, url, response.status_code, text))

        return response

    def post(self, url, decode_json=True, *args, **kwargs):
        return self._http_request('post', url, decode_json=decode_json, *args, **kwargs)

    def get(self, url, decode_json=True, *args, **kwargs):
        return self._http_request('get', url, decode_json=decode_json, *args, **kwargs)

    def delete(self, url, decode_json=True, *args, **kwargs):
        return self._http_request('delete', url, decode_json=decode_json, *args, **kwargs)

    def patch(self, url, decode_json=True, *args, **kwargs):
        return self._http_request('patch', url, decode_json=decode_json, *args, **kwargs)


class ptArtifact:
    def __init__(self, pt_server=None, uuid1=None, filename='', description='', ttl_days=180,
                 mime=None, inline=False, compression=False, linked_uuids=None, validate=True):
        assert isinstance(pt_server, ptServer)
        assert linked_uuids is None or type(linked_uuids) is list

        self.uuid = uuid1 if uuid1 else uuid.uuid1()
        self.mime = mime  # None means auto
        self.size = 0
        self.filename = filename
        self.description = description
        self.ttl_days = ttl_days
        self.uploaded_dt = datetime.datetime.now()
        self.expires_dt = datetime.datetime.now() + datetime.timedelta(days=self.ttl_days)
        self.inline = inline
        self.compression = compression
        self.linked_uuids = set([str(u) for u in linked_uuids]) if linked_uuids else set()
        self.unlinked_uuids = set()

        self._pt_server = pt_server
        self._url_list = "/0/artifact/"
        self._url = "/0/artifact/%s" % (self.uuid)
        self._url_download = "/0/artifact_content/%s" % (self.uuid)

        if validate:
            self.validate()

    def validate(self):
        assert self._pt_server is not None

    def delete(self):
        return self._pt_server.delete(self._url)

    def info(self):
        return self._pt_server.get(self._url)

    def link(self, uuids):
        assert type(uuids) is list
        uuids = [str(u) for u in uuids]
        self.linked_uuids |= set(uuids)
        data = {'linked_uuids': json.dumps(list(self.linked_uuids))}
        return self._pt_server.post(self._url, data=data)

    def unlink(self, uuids):
        assert type(uuids) is list
        uuids = [str(u) for u in uuids]
        self.linked_uuids |= set(uuids)
        self.unlinked_uuids -= set(uuids)
        data = {'unlinked_uuids': json.dumps(list(self.unlinked_uuids))}
        return self._pt_server.post(self._url, data=data)

    def update(self):
        assert self.uuid is not None

        # FIXME: copy-paste
        data = {'description': self.description, 'ttl_days': self.ttl_days, 'mime': self.mime,
                'filename': self.filename, 'inline': self.inline,
                'linked_uuids': json.dumps(list(self.linked_uuids)),
                'unlinked_uuids': json.dumps(list(self.unlinked_uuids))
                }

        return self._pt_server.post(self._url, data=data)

    def upload(self, filepath):
        assert self.uuid is not None

        if not self.filename:
            self.filename = os.path.basename(filepath)

        f = open(filepath, 'rb')
        if self.compression:
            data = bz2.compress(f.read())
        else:
            data = f.read()
        f.close()

        files = {'file': data}

        # FIXME: copy-paste
        data = {'description': self.description, 'ttl_days': self.ttl_days, 'mime': self.mime,
                'filename': self.filename, 'inline': self.inline, 'compression': self.compression,
                'linked_uuids': json.dumps(list(self.linked_uuids)),
                'unlinked_uuids': json.dumps(list(self.unlinked_uuids))
                }

        return self._pt_server.post(self._url, files=files, data=data)

    def list(self, limit=10, offset=0):
        resp = self._pt_server.get(self._url_list)
        if resp.status_code != httplib.OK:
            return resp, []

        ret = []

        def _bool(val):
            return val in ("True", "true", True, "Yes", "yes", "y", 1)

        for item in resp.json:
            a = ptArtifact(self._pt_server, uuid1=item['uuid'])
            a.ttl_days = int(item['ttl_days'])
            a.description = item['description']
            a.uploaded_dt = parser.parse(item['uploaded_dt'])
            a.expires_dt = parser.parse(item['expires_dt'])
            a.mime = item['mime']
            a.filename = item['filename']
            a.size = int(item['size'])
            a.inline = _bool(item['inline'])
            a.compression = _bool(item['compression'])
            ret.append(a)

        return resp, ret

    def download(self, filepath=None):
        resp = self._pt_server.get(self._url_download, decode_json=False)
        if resp.status_code == httplib.OK:
            if filepath is not None:
                f = open(filepath, 'wb')
                f.write(resp.content)
                f.close()
        return resp


class ptTest:
    def __init__(self, tag=None, uuid1=None, group=None, binary=None, cmdline=None, description=None,
                 loops=None, scores=None, deviations=None, category=None, metrics="loops/sec",
                 links=None, attribs=None, less_better=False, errors=None, warnings=None,
                 begin=None, end=None, duration_sec=0, status='SUCCESS', validate=True):
        """
        tag         - keyword used to match tests results in different suites: hdd sequential read
        group       - test group: memory, disk, cpu, ...)
        binary      - test binary: hdd_seq_read.exe
        cmdline     - test command line: -f /root/file/ -O 100M -s 1
        description - test description: disk seq read test\nCreates /root/file with 100MB size
                      and do sequential read by 1MB in a loop
        scores      - test iteration scores: [12.21, 14.23, 12.94]
        deviations  - test iteration deviatons: [0.02, 0.03, 0.01]
        loops       - test loops: 1000
        category    - test category to be used in charts: 1-thread
        metrics     - test metrics: MB/s
        links       - arbitrary links to other systems:
                      {'test logs': 'http://logs.domain/231241.log', 'grafana': 'http://grafana.domain/cluster3'}
        attribs     - set of test attributes: {'version': '12.4', 'branch': 'mybranch'}
        less_better - set to True if the less is value the better
        errors      - total number or list of errors: ['failed to create a file, permission denied']
        warnings    - total number or list of warnings: ['I/O request timed out, retrying....',
                      'I/O request timed out, retrying...']
        begin       - time when the test started in datetime.datetime format
        end         - time when the test ended in datetime.datetime format
        duration_sec - test duration (sec)
        status      - test status: PASS, FAIL, SKIPPED, INPROGRESS, NOTSTARTED
        """

        self.seq_num = None
        self.uuid = uuid1 if uuid1 else uuid.uuid1()
        self.tag = tag
        self.group = group
        self.binary = binary
        self.cmdline = cmdline
        self.description = description
        self.scores = [pt_float(s) for s in scores] if scores else []
        self.loops = loops
        self.deviations = [pt_float(d) for d in deviations] if deviations else []
        self.category = category
        self.metrics = metrics
        self.links = links if links else {}
        self.attribs = attribs if attribs else {}
        self.less_better = less_better
        self.errors = errors
        self.warnings = warnings
        self.begin = begin if begin else datetime.datetime.now()
        self.end = end if end else datetime.datetime.now()
        self.duration_sec = int(duration_sec)
        self.status = status

        self._auto_end = end
        self._auto_begin = begin

        if validate:
            self.validate()

    def __eq__(self, other):
        assert isinstance(other, ptTest)
        attributes = ["tag", "group", "category", "metrics", "less_better"]
        return all(map(lambda attr: getattr(self, attr) == getattr(other, attr),
                       attributes))

    def validate(self):
        assert self.tag is not None
        assert self.links is None or type(self.links) is dict
        assert self.attribs is None or type(self.attribs) is dict
        assert self.errors is None or type(self.errors) is int or type(self.errors) is list
        assert self.warnings is None or type(self.warnings) is int or type(self.warnings) is list
        assert self.scores is None or type(self.scores) is list
        assert self.loops is None or type(self.loops) is int
        assert self.deviations is None or type(self.deviations) is list
        assert (self.deviations is None) or len(self.deviations) == 0 or \
               (self.scores is not None and len(self.scores) == len(self.deviations))
        assert self.begin is None or type(self.begin) is datetime.datetime
        assert self.end is None or type(self.end) is datetime.datetime
        assert self.duration_sec is None or type(self.duration_sec) is int
        assert self.status in TEST_STATUSES

    def __repr__(self):
        return "ptTest('%s', group='%s', category='%s' scores=%s, duration_sec=%.1f, less_better=%s, status=%s)" % \
               (self.tag, self.group, self.category, str(self.scores),
                self.duration_sec, str(self.less_better), self.status)

    def execute(self, cmdline=None, shell=None, exc_on_err=False, log_file=None):
        """
        Simple test executor:
        shell - Shell instance where to execute the test, keep None for local launch: '192.168.0.100'
        path - path to search tests (list): ['/tmp/tests', '/opt/tests/bin/']
        """

        if shell is None:
            shell = ptShell()
        if not (isinstance(shell, ptShell) or isinstance(shell, ptShellFromFile)):
            raise ptRuntimeException("shell argument must be an instance of the Shell class, got: " + str(type(shell)))

        if cmdline is None:
            cmdline = self.cmdline
        if cmdline is None:
            raise ptRuntimeException("execute() must be supplied with the 'cmdline' argument, got None")

        if self._auto_begin is None:
            self.begin = datetime.datetime.now()

        status, out, err = shell.execute(cmdline, raise_exc=exc_on_err)
        if log_file:
            logging.debug("Storing the output to: %s" % log_file)
            lf = open(log_file, "a")
            if out:
                lf.write("=============== stdout =================\n\n")
                lf.write(out)
            if err:
                lf.write("=============== stderr =================\n\n")
                lf.write(err)
            lf.close()

        if self._auto_end is None:
            self.end = datetime.datetime.now()

        return status, out, err

    def add_score(self, score):
        if isinstance(score, list):
            for s in score:
                self.scores.append(pt_float(s))
        else:
            self.scores.append(pt_float(score))

    def add_deviation(self, dev):
        self.scores.append(pt_float(dev))

    def add_artifact(self, artifact):
        assert isinstance(artifact, ptArtifact)
        artifact.link([self.uuid])


class ptEnvNode:
    def __init__(self, name=None, version=None, node_type=None, ip=None, hostname=None, params=None,
                 cpus=0, cpus_topology=None, cpu_info=None, ram_info=None,
                 ram_mb=0, ram_gb=0, disk_gb=0, links=None, scan_info=False,
                 ssh_user=None, ssh_password=None, validate=True):
        self.name = name
        self.version = version
        self.node_type = node_type
        self.ip = ip
        self.ssh_user = ssh_user
        self.ssh_password = ssh_password
        self.hostname = hostname
        self.uuid = uuid.uuid1()

        self.params = params
        self.cpus = cpus
        self.cpus_topology = cpus_topology
        self.cpu_info = cpu_info
        self.ram_info = ram_info

        self.ram_mb = ram_mb if ram_mb else ram_gb * 1024
        self.disk_gb = disk_gb

        self.links = links if links else {}
        if validate:
            self.validate()

        self.children = []  # start with x to show children in the end of prettified json

        self._scan_info = scan_info
        if self._scan_info and self._shell:
            if not self.hostname:
                self.hostname = self._shell.os_info.hostname
            if not self.ram_mb:
                self.ram_mb = int(round(self._shell.hw_info.ram_kb / 1024, 0))
            if not self.cpus:
                self.cpus = self._shell.hw_info.cpu_count
            if not self.cpus_topology:
                self.cpus_topology = self._shell.hw_info.cpu_topology
            if not self.cpu_info:
                self.cpu_info = "%s @ %.1fGHz" % (self._shell.hw_info.cpu_model, self._shell.hw_info.cpu_freq_ghz)
            if not self.version:
                self.version = "%s %s" % (self._shell.os_info.family, self._shell.os_info.version)

    @cached_property
    def _shell(self):
        if self.ip in (None, "127.0.0.1", "localhost"):
            return ptShell(citizenshell.LocalShell())
        if self.ssh_user:
            return ptShell(
                citizenshell.SecureShell(hostname=self.ip, username=self.ssh_user, password=self.ssh_password))
        return None

    def validate(self):
        assert self.name is not None
        assert self.cpus is None or type(self.cpus) is int
        assert self.ram_mb is None or type(self.ram_mb) is int
        assert self.disk_gb is None or type(self.disk_gb) is int
        assert self.links is None or type(self.links) is dict

    def addNode(self, node):
        assert isinstance(node, ptEnvNode)
        self.children.append(node)
        return node


class ptHost(ptEnvNode):
    def __init__(self, name=None, model=None, hw_uuid=None, serial_num=None, numa_nodes=None, **kwargs):
        ptEnvNode.__init__(self, name=name, **kwargs)
        self.node_type = "Host"
        self.model = model
        self.hw_uuid = hw_uuid
        self.serial_num = serial_num

        if self._scan_info and self._shell:
            if not self.model:
                self.model = self._shell.hw_info.model
            if not self.hw_uuid:
                self.hw_uuid = self._shell.hw_info.uuid
            if not self.serial_num:
                self.serial_num = self._shell.hw_info.serial


class ptVM(ptEnvNode):
    def __init__(self, name=None, virt_type=None, **kwargs):
        """
        virt_type - KVM VM, ESX VM, k8s pod, docker image
        """
        ptEnvNode.__init__(self, name=name, **kwargs)
        self.node_type = virt_type


class ptComponent(ptEnvNode):
    def __init__(self, name=None, version=None, links=None, **kwargs):
        ptEnvNode.__init__(self, name=name, **kwargs)
        self.name = name
        self.version = version
        self.node_type = 'service'


class ptProduct:
    def __init__(self, name="", version=None):
        self.name = name
        self.version = str(version)


class ptSuite:
    def __init__(self, job_title='job title', project_name=None, cmdline=None,
                 product_name=None, product_ver=None, regression_name=None,
                 suite_name=None, suite_ver=None,
                 uuid1=None, append=False, replace=False, begin=None, end=None, links=None,
                 pt_server_url=PT_SERVER_DEFAULT_URL, save_to_file=None):
        """
        job_name   - job title on portal: '[disk tests] KVM 2.6.32'
        suite_name - suite name to filter/search: 'disk tests'
        uuid       - unique job run uuid, pass existing one to overwrite/append data
        append     - set to True to append data to existing job data with given uuid
        begin      - time when job started (must have the datetime.datetime type)
        end        - time when job ended (must have the datetime.datetime type)
        """

        self._seq_num = 0
        self.job_title = job_title
        self.cmdline = cmdline if cmdline else " ".join(map(pipes.quote, sys.argv))
        self.project_name = project_name
        self.project_id = None
        self.product_name = product_name
        self.regression_name = regression_name
        self.product_ver = product_ver
        self.suite_name = suite_name
        self.suite_ver = suite_ver
        self.uuid = uuid1 if uuid1 else uuid.uuid1()
        self.append = append
        self.replace = replace

        self._auto_end = end

        self.begin = begin if begin else datetime.datetime.now()
        self.end = end if end else datetime.datetime.now()

        self.env_nodes = []
        self.links = links if links else {}

        self._id2node = {}

        self.tests = []
        self._key2test = {}

        self.pt_server = ptServer(pt_server_url)
        self._save_to_file = save_to_file
        self._pt_options_added = False

        self._stdout_filename = None
        self._stderr_filename = None
        self._stdout_artifact = None
        self._stderr_artifact = None

        self.validate()

    def validate(self):
        assert type(self.begin) is datetime.datetime
        assert type(self.end) is datetime.datetime
        assert self.links is None or type(self.links) is dict

    def addNode(self, node):
        assert isinstance(node, ptEnvNode)
        self.env_nodes.append(node)
        return node

    def addLink(self, name, url):
        """
        name    - link name: 'monitoring dashboard'
        url     - link url:  'http://grafana.localdomain/host1'
        """
        self.links[str(name)] = str(url)

    def addGrafanaLink(self, grafana_url):
        """
        if recieved grafana_address and tag dashboards will be added without filtering node instances
        :param grafana_url: grafana url in format http://{domain_or_ip}/d/{dashboard_id}/{dashboard_name}?{params}
        """
        if "?" in grafana_url:
            grafana_url += "&"
        else:
            grafana_url += "?"
        self.addLink(name="Grafana metrics {}".format(grafana_url.split('/')[5].split('?')[0]),
                     url=grafana_url + "from={}&to={}".format(str(get_timestamp_from_datetime(self.begin)),
                                                              str(get_timestamp_from_datetime(
                                                                  datetime.datetime.now()))))

    def addTest(self, test):
        assert isinstance(test, ptTest)
        if not self.append:
            self._seq_num += 1
            test.seq_num = self._seq_num
        added_test = self.getTest(tag=test.tag, group=test.group, category=test.category)
        if added_test is None:
            self.tests.append(test)
            key = "%s-%s-%s" % (test.tag, str(test.group), str(test.category))
            self._key2test[key] = test
        elif added_test == test:
            # TODO add_deviations
            added_test.add_score(test.scores)
        else:
            raise ptRuntimeException("ptTest with received tag, group, category already exists, but other "
                                     "attributes differs")

    def addArtifact(self, uuid1=None):
        return ptArtifact(pt_server=self.pt_server, uuid1=uuid1)

    def initFromJson(self, json_obj):
        logging.debug("initializing data from json: %s" % str(json_obj))

        def _initFromJson(obj, json_obj):
            for el_name in json_obj:
                if str(el_name) not in obj.__dict__:
                    logging.debug("skipping unrecognized element: %s = %s, while obj is: %s" %
                                  (str(el_name), json_obj[el_name], obj.__dict__))
                    continue

                member = obj.__dict__[el_name]

                if member is None:
                    obj.__dict__[el_name] = json_obj[el_name]
                elif type(member) is list:
                    if len(member):
                        for j in json_obj[el_name]:
                            if hasattr(member[0], 'validate'):
                                new_obj = member[0].__class__(validate=False)
                            else:
                                try:
                                    new_obj = member[0].__class__()
                                except TypeError as e:
                                    logging.error("EXCEPTION: class: %s, error: %s" %
                                                  (member[0].__class__.__name__, str(e)))
                                    raise
                            _initFromJson(new_obj, j)
                            member.append(new_obj)
                    else:
                        obj.__dict__[el_name] = json_obj[el_name]
                elif obj.__dict__[el_name].__class__.__name__.startswith('pt'):
                    # special hack to handle ptServer, ptTest, ptArtifact, ...
                    new_obj = member.__class__()
                    _initFromJson(new_obj, json_obj[el_name])
                elif type(member) is datetime.datetime:
                    obj.__dict__[el_name] = json_obj[el_name]
                else:
                    obj.__dict__[el_name] = type(member)(json_obj[el_name])

        _initFromJson(self, json_obj)

    def getTest(self, tag, group=None, category=None):
        key = "%s-%s-%s" % (tag, str(group), str(category))
        return self._key2test.get(key, None)

    def toJson(self, pretty=False):
        if pretty:
            return json.dumps(self, cls=ptJsonEncoder, indent=4, separators=(',', ': '))
        return json.dumps(self, cls=ptJsonEncoder)

    def validateProjectName(self):
        if not self.project_name:
            return
        self.project_id = self.pt_server.getProjectId(self.project_name)
        if self.project_id is None:
            sys.exit(-1)

    def upload(self):
        if not self.project_name:
            msg = "Skipping upload() because project name is not specified"
            if self._pt_options_added:
                logging.warning("%s, either use --pt-project or ptSuite(..., project_name=, ...)" % msg)
            else:
                logging.warning("%s, pass it as ptSuite(..., project_name=, ...)" % msg)
            return

        if not self.project_id:
            self.validateProjectName()

        if self._auto_end is None:
            self.end = datetime.datetime.now()

        json_prettified = self.toJson(pretty=True)

        if self._save_to_file:
            if self._save_to_file == "-":
                print("Job json:")
                print(json_prettified)
            else:
                with open(self._save_to_file, 'w') as f:
                    f.write(json_prettified)
                logging.info("saving json data to %s" % self._save_to_file)
            return True

        json_data = self.toJson()

        logging.debug("posting data to %s:\n%s" % ('/%d/job/' % self.project_id, json_prettified))

        response = self.pt_server.post('%d/job/' % self.project_id, decode_json=False, data=json_data)

        if response.status_code != httplib.OK:
            logging.error("job json upload failed, status %d, %s" % (response.status_code, response.text))
            raise ptRuntimeException("Suite run results upload failed, status %d:\n%s" %
                                     (response.status_code, response.text))
        logging.info("status %d - job json uploaded, %s" % (response.status_code, response.text))
        return True

    def addOptions(self, option_parser, pt_url=None, pt_project=None):
        self._pt_options_added = True
        if pt_url is not None:
            logging.error("the addOptions(pt_url=...) is deprecated, use ptSuite(pt_server_url=...)")
            self.pt_server.setUrl(pt_url)
        if pt_project is not None:
            logging.error("the addOptions(pt_project=...) is deprecated, use ptSuite(project_name=...)")
            self.project_name = pt_project

        g = optparse.OptionGroup(option_parser, "PerfTracker options")
        g.add_option("--pt-to-file", type="str", help="Dump the job results json to a file instead of upload")
        g.add_option("--pt-project", type="str", help="The PerfTracker project name", default=self.project_name)
        g.add_option("--pt-url", type="str", help="The PerfTracker portal URL, default: %default",
                     default=self.pt_server.url)
        g.add_option("--pt-replace", type="str", help="replace tests results in the job with given UUID")
        g.add_option("--pt-append", type="str", help="append tests results to the job with given UUID")
        g.add_option("--pt-title", type="str", help="PerfTracker job title to be used")
        g.add_option("--pt-version", type="str", help="PerfTracker suite version")
        g.add_option("--pt-regression-tag", type="str", help="PerfTracker suite regression tag")
        g.add_option("--pt-regression-name", type="str", help="PerfTracker suite regression name")
        g.add_option("--pt-product-version", type="str", help="The version of the product being tested")
        g.add_option("--pt-product-name", type="str", help="The name of the product being tested")
        g.add_option("--pt-log-upload", action="store_true",
                     help="Upload stdout & stderr to perftracker and attach to the job")
        g.add_option("--pt-log-ttl", type="int", default=180,
                     help="stdout & stderr logs time to live (days), default %default")
        option_parser.add_option_group(g)

    def handleOptions(self, options):
        if not options:
            return

        def _exists(options, key):
            return options.__dict__.get(key, None) is not None

        if _exists(options, 'pt_to_file'):
            self._save_to_file = options.pt_to_file
        if _exists(options, 'pt_url'):
            self.pt_server.setUrl(options.pt_url)
        if _exists(options, 'pt_replace'):
            self.uuid = options.pt_replace
            self.replace = True
        if _exists(options, 'pt_project'):
            self.project_name = options.pt_project
        if _exists(options, 'pt_title'):
            self.job_title = options.pt_title
        if _exists(options, 'pt_version'):
            self.suite_ver = options.pt_version
        if _exists(options, 'pt_regression_tag'):
            self.regression_tag = options.pt_regression_tag
        if _exists(options, 'pt_regression_name'):
            self.regression_name = options.pt_regression_name
        if _exists(options, 'pt_product_name'):
            self.product_name = options.pt_product_name
        if _exists(options, 'pt_product_version'):
            self.product_ver = options.pt_product_version
        if _exists(options, 'pt_append'):
            self.uuid = options.pt_append
            self.append = True
        if _exists(options, 'pt_log_upload'):
            self._stdout_filename = Tee('stdout').filename
            self._stderr_filename = Tee('stderr').filename
            self._stdout_artifact = ptArtifact(self.pt_server, filename="stdout.txt", inline=True,
                                               compression=True, ttl_days=options.pt_log_ttl,
                                               linked_uuids=[self.uuid])
            self._stderr_artifact = ptArtifact(self.pt_server, filename="stderr.txt", inline=True,
                                               compression=True, ttl_days=options.pt_log_ttl,
                                               linked_uuids=[self.uuid])

        self.validateProjectName()

    def fini(self):
        if self._stdout_artifact and os.path.getsize(self._stdout_filename):
            self._stdout_artifact.upload(self._stdout_filename)
        if self._stderr_artifact and os.path.getsize(self._stderr_filename):
            self._stderr_artifact.upload(self._stderr_filename)

    def __del__(self):
        self.fini()


##############################################################################
# Autotests
##############################################################################

def _coverage():
    suite = ptSuite(suite_ver="1.0.0", product_name="My web app", product_ver="1.0-1234",
                    project_name="Test", uuid1="11111111-2222-11e8-85cb-8c85907924aa")

    op = OptionParser("PerfTracker suite example")

    suite.addOptions(op)
    opts, args = op.parse_args()
    opts.pt_log_upload = True
    suite.handleOptions(opts)

    logging.basicConfig(level=logging.DEBUG)

    suite.addLink('Grafana', 'http://grafana.localdomain/')

    s1 = suite.addNode(ptHost("s1", ip="192.168.0.1", hostname="server1.domain", version="RHEL7.4", cpus=8, ram_gb=8))
    s2 = suite.addNode(ptHost("s2", ip="192.168.0.2", hostname="server2.domain", version="RHEL7.4", cpus=8, ram_gb=8))

    vm1 = s1.addNode(ptVM("vm1", ip="192.168.100.1", version="CentOS 7.4", virt_type="KVM VM", cpus=4, ram_gb=32))
    vm2 = s1.addNode(ptVM("vm2", ip="192.168.100.2", version="CentOS 7.4", virt_type="KVM VM", cpus=4, ram_gb=32))

    vm1.addNode(ptComponent("backend", version="1.2.3"))
    vm2.addNode(ptComponent("database", version="10.0"))

    for p in range(1, 5 + random.randint(0, 2)):
        suite.addTest(ptTest("Login time", group="Latency tests", metrics="sec", less_better=True,
                             category="%d parallel users" % (2 ** p),
                             scores=[0.3 + sqrt(p) + random.randint(0, 20) / 40.0]))

    for p in range(1, 5 + random.randint(0, 2)):
        suite.addTest(ptTest("Home page throughput", group="Throughput tests", metrics="pages/sec",
                             category="%d parallel clients" % (2 ** p),
                             scores=[10 + sqrt(p) + random.randint(0, 20) / 5]))

    suite.addTest(ptTest("Login time", group="Latency tests", metrics="sec", less_better=True,
                         category="2 parallel users",
                         scores=[0.3 + sqrt(2) + random.randint(0, 20) / 40.0]))

    a = suite.addArtifact(uuid1="11111111-3333-11e8-85cb-8c85907924aa")
    a.compressed = True
    a.inline = True
    a.upload(os.path.abspath(__file__))
    a.link([suite.uuid])

    suite.upload()
    j = suite.toJson()
    suite.initFromJson(json.loads(j))
    print("Done, job: %s" % suite.uuid)


if __name__ == "__main__":
    try:
        _coverage()
    except ptRuntimeException as e:
        print(e)
        sys.exit(-1)
