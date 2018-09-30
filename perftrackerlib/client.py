import sys
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
from dateutil import parser

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
    def __init__(self, pt_server_url=PT_SERVER_DEFAULT_URL):
        assert pt_server_url
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
            raise ptRuntimeException("can't get the list of existing projects: %d, %s" % (j['http_status'], j.get('message', str(j))))

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
            text = response.text.encode(response.encoding if response.encoding else 'utf-8')
            try:
                j = json.loads(text)
                response.json = j
            except ValueError as e:
                raise ptRuntimeException("%s\nresponse:%s" % (str(e), str(text)))

        if response.status_code == httplib.OK:
            if logging.getLogger().getEffectiveLevel() >= logging.DEBUG:
                if decode_json:
                    logging.debug("%s %s ... response:\n%s" % (method, url, ptJsonEncoder.pretty(j)))
                else:
                    logging.debug("%s %s ... response size %d" % (method, url, len(response.content)))
        else:
            logging.error("%s %s status: %s, message: %s" % (method, url, response.status_code, j.get('message', ptJsonEncoder.pretty(j))))

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
    def __init__(self, pt_server, uuid1=None):
        assert isinstance(pt_server, ptServer)

        self.uuid = uuid1 if uuid1 else uuid.uuid1()
        self.mime = 'application/octet-stream'
        self.size = 0
        self.filename = ''
        self.description = ''
        self.ttl_bytes = 180
        self.uploaded_dt = datetime.datetime.now()
        self.expires_dt = datetime.datetime.now() + datetime.timedelta(days=self.ttl_bytes)
        self.inline = False
        self.compression = False

        self._pt_server = pt_server
        self._url_list = "/0/artifact/"
        self._url = "/0/artifact/%s" % (self.uuid)
        self._url_download = "/0/artifact_content/%s" % (self.uuid)

    def delete(self):
        return self._pt_server.delete(self._url)

    def info(self):
        return self._pt_server.get(self._url)

    def link(self, uuids):
        assert type(uuids) is list
        data = {'linked_uuids': json.dumps(uuids)}
        return self._pt_server.post(self._url, data=data)

    def unlink(self, uuids):
        assert type(uuids) is list
        data = {'unlinked_uuids': json.dumps(uuids)}
        return self._pt_server.post(self._url, data=data)

    def update(self, filename=''):
        assert self.uuid is not None
        data = {'description': self.description, 'ttl_days': self.ttl_days, 'mime': self.mime,
                'filename': self.filename, 'inline':self.inline}

        return self._pt_server.post(self._url, data=data)

    def upload(self, filepath):
        assert self.uuid is not None

        f = open(filepath, 'rb')
        if self.compression:
            data = bz2.compress(f.read())
        else:
            data = f.read()
        f.close()

        files = {'file': data}
        data = {'description': self.description, 'ttl_days': self.ttl_days, 'mime': self.mime,
                'filename': self.filename, 'inline': self.inline, 'compression': self.compression}

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

    def download(self, filepath):
        resp = self._pt_server.get(self._url_download, decode_json=False)
        if resp.status_code == httplib.OK:
            f = open(filepath, 'wb')
            f.write(resp.content)
            f.close()
        return resp


class ptTest:
    def __init__(self, tag, uuid1=None, group=None, binary=None, cmdline=None, description=None,
                loops=None, scores=None, deviations=None, category=None, metrics="loops/sec",
                links=None, attribs=None, less_better=False, errors=None, warnings=None,
                begin=None, end=None, duration_sec=0, status='SUCCESS'):
        """
        tag         - keyword used to match tests results in different suites: hdd sequential read
        group       - test group: memory, disk, cpu, ...)
        binary      - test binary: hdd_seq_read.exe
        cmdline     - test command line: -f /root/file/ -O 100M -s 1
        description - test description: disk sequential read test\nCreates /root/file with 100MB size and do sequential read by 1MB in a loop
        scores      - test iteration scores: [12.21, 14.23, 12.94]
        deviations  - test iteration deviatons: [0.02, 0.03, 0.01]
        loops       - test loops: 1000
        category    - test category to be used in charts: 1-thread
        metrics     - test metrics: MB/s
        links       - arbitrary links to other systems: {'test logs': 'http://logs.localdomain/231241.log', 'grafana': 'http://grafana.localdomain/cluster3'}
        attribs     - set of test attributes: {'version': '12.4', 'branch': 'mybranch'}
        less_better - set to True if the less is value the better
        errors      - total number or list of errors: ['failed to create a file, permission denied']
        warnings    - total number or list of warnings: ['I/O request timed out, retrying....', 'I/O request timed out, retrying...']
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

        self.validate()

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
               (self.tag, self.group, self.category, str(self.scores), self.duration_sec, str(self.less_better), self.status)

    def _execute_local(self, path=None, exc_on_err=False, log_file=None):

        cmd = self.binary
        if sys.platform == 'win32':
            cmd += ".exe"

        if path:
            cmd = os.path.join(path, cmd)

        if self.cmdline:
            cmd += " %s" % self.cmdline

        logging.debug("executing: %s" % (cmd))
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout_text, stderr_text = p.communicate()
        p.wait()

        if log_file:
            logging.debug("Storing the output to: %s" % log_file)
            lf = open(log_file, "a")
            if stdout_text:
                lf.write("=============== stdout =================\n\n")
                lf.write(stdout_text)
            if stderr_text:
                lf.write("=============== stderr =================\n\n")
                lf.write(stderr_text)
            lf.close()

        status = p.returncode
        if status and exc_on_err:
            raise RuntimeError("'%s' execution failed with status %d:\n%s\n%s" % (cmd, status, stdout_text, stderr_text))
        logging.debug("'%s' status %d, stdout:\n%s\nstderr:\n%s" % (cmd, status, stdout_text, stderr_text))

        return (status, stdout_text, stderr_text)

    def execute(self, host=None, path=None, exc_on_err=False, log_file=None):
        """
        Simple test executor:
        host - host IP/hostname where to execute the test, keep None for local launch: '192.168.0.100'
        path - path to search tests (list): ['/tmp/tests', '/opt/tests/bin/']
        """

        if self.binary is None:
            raise ptRuntimeException("Test binary is not specified")

        if self._auto_begin is None:
            self.begin = datetime.datetime.now()

        if host is None:
            status, out, err = self._execute_local(path, exc_on_err, log_file=log_file)
        else:
            raise ptRuntimeException("Sorry, remote host is not implemented")

        if self._auto_end is None:
            self.end = datetime.datetime.now()

        return status, out, err

    def add_score(self, score):
        self.scores.append(pt_float(score))

    def add_deviation(self, dev):
        self.scores.append(pt_float(dev))

    def add_artifact(self, artifact):
        assert isinstance(artifact, ptArtifact)
        artifact.link(self.uuid)

class ptEnvNode:
    def __init__(self, name, version=None, node_type=None, ip=None, hostname=None, params=None, cpus=0,
                 ram_mb=0, ram_gb=0, disk_gb=0, links=None):
        self.name = name
        self.version = version
        self.node_type = node_type
        self.ip = ip
        self.hostname = hostname
        self.uuid = uuid.uuid1()

        self.params = params
        self.cpus = cpus
        self.ram_mb = ram_mb if ram_mb else ram_gb * 1024
        self.disk_gb = disk_gb

        self.links = links if links else {}
        self.validate()

        self.children = []  # start with x to show children in the end of prettified json

    def validate(self):
        assert self.cpus is None or type(self.cpus) is int
        assert self.ram_mb is None or type(self.ram_mb) is int
        assert self.disk_gb is None or type(self.disk_gb) is int
        assert self.links is None or type(self.links) is dict

    def addNode(self, node):
        assert isinstance(node, ptEnvNode)
        self.children.append(node)
        return node

class ptHost(ptEnvNode):
    def __init__(self, name, model=None, hw_uuid=None, serial_num=None, numa_nodes=None, ram_info=None, cpu_info=None, **kwargs):
        ptEnvNode.__init__(self, name, **kwargs)
        self.node_type = "Host"
        self.model = model
        self.hw_uuid = hw_uuid
        self.serial_num = serial_num
        self.ram_info = ram_info
        self.cpu_info = cpu_info


class ptVM(ptEnvNode):
    def __init__(self, name, virt_type=None, **kwargs):
        """
        virt_type - KVM VM, ESX VM, k8s pod, docker image
        """
        ptEnvNode.__init__(self, name, **kwargs)
        self.node_type = virt_type


class ptComponent(ptEnvNode):
    def __init__(self, name, version=None, links=None, **kwargs):
        ptEnvNode.__init__(self, name, **kwargs)
        self.name = name
        self.version = version
        self.node_type = 'service'


class ptProduct:
    def __init__(self, name, version=None):
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
        self.save_to_file = save_to_file
        self._pt_options_added = False

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

    def addTest(self, test):
        assert isinstance(test, ptTest)
        if not self.append:
            self._seq_num += 1
            test.seq_num = self._seq_num

        self.tests.append(test)

        key = "%s-%s-%s" % (test.tag, str(test.group), str(test.category))
        self._key2test[key] = test

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

        if self._auto_end is None:
            self.end = datetime.datetime.now()

        json_prettified = self.toJson(pretty=True)

        if self.save_to_file:
            if self.save_to_file == "-":
                print ("Job json:")
                print (json_prettified)
            else:
                with open(self.save_to_file, 'w') as f:
                    f.write(json_prettified)
            return True

        json_data = self.toJson()

        logging.debug("posting data to %s:\n%s" % ('/%d/job/' % self.project_id, json_prettified))

        response = self.pt_server.post('%d/job/' % self.project_id, decode_json=False, data=json_data)

        if response.status_code != httplib.OK:
            logging.error("job json upload to %s: status %d, %s" % (url, response.status_code, response.text))
            raise ptRuntimeException("Suite run results upload failed, url: %s status %d:\n%s" %
                                     (url, response.status_code, response.text))
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
        g.add_option("--pt-url", type="str", help="The PerfTracker portal URL, default: %default", default=self.pt_server.url)
        g.add_option("--pt-replace", type="str",  help="replace tests results in the job with given UUID")
        g.add_option("--pt-append", type="str", help="append tests results to the job with given UUID")
        g.add_option("--pt-title", type="str",  help="PerfTracker job title to be used")
        g.add_option("--pt-version", type="str",  help="PerfTracker suite version")
        g.add_option("--pt-regression-tag", type="str",  help="PerfTracker suite regression tag")
        g.add_option("--pt-regression-name", type="str",  help="PerfTracker suite regression name")
        g.add_option("--pt-product-version", type="str", help="The version of the product being tested")
        g.add_option("--pt-product-name", type="str", help="The name of the product being tested")
        option_parser.add_option_group(g)

    def handleOptions(self, options):
        if not options:
            return

        def _exists(options, key):
            return options.__dict__.get(key, None) is not None

        if _exists(options, 'pt_to_file'):
            self.save_to_file = options.pt_to_file
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

        self.validateProjectName()
