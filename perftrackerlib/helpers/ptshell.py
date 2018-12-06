from __future__ import print_function, absolute_import

# -*- coding: utf-8 -*-
__author__ = "perfguru87@gmail.com"
__copyright__ = "Copyright 2018, The PerfTracker project"
__license__ = "MIT"

import citizenshell
import logging
from perftrackerlib.helpers.decorators import cached_property
from functools import wraps


class ShellError(Exception):
    pass


class Os:
    def __init__(self, shell):
        assert isinstance(shell, ptShell)
        self._shell = shell
        self._family = None
        self._version = None
        self._hostname = ''

        self._inited = False

    @cached_property
    def family(self):
        return self._init()._family

    @cached_property
    def version(self):
        return self._init()._version

    @cached_property
    def hostname(self):
        if self.family in ("Linux", "Darwin"):
            return self._shell.execute_fetch_one("hostname")

        logging.warning("os.hostname: %s OS is not supported" % str(self.family))
        return self._hostname

    def _init(self):
        if self._inited:
            return self

        f = self._shell.execute

        status, out, _ = f("python -c 'from __future__ import print_function; import platform; "
                           "print(platform.platform())'")
        self._version = out.strip()
        if self._version.startswith("Linux"):
            self._family = "Linux"
            self._hostname = f("hostname")
        elif self._version.startswith("Darwin"):
            self._family = "Darwin"
            self._version = self._shell.execute_fetch_one("system_profiler SPSoftwareDataType | "
                                                          "grep \"System Version\" | cut -d\":\" -f 2")
        elif self._version.startswith("Windows"):
            self._family = "Windows"
        else:
            raise ShellError("%s: can't recognize the OS family" % (str(self._shell)))

        self._inited = True
        return self


class Hw:
    def __init__(self, shell, os_info=None):
        assert isinstance(shell, ptShell)
        self._shell = shell
        self._os_info = os_info

        self._uuid = ''
        self._serial = ''
        self._vendor = ''
        self._model = ''
        self._ram_kb = 0

        self._cpu_model = ''
        self._cpu_freq_ghz = 0
        self._cpu_count = 0
        self._cpu_sockets = 1
        self._cpu_cores = 1
        self._cpu_threads = 1

        self._inited = False

    def _init(self):
        if self._inited:
            return self

        if self.os_info.family == "Linux":
            f = self._shell.execute_fetch_one

            self._uuid = f("cat /sys/class/dmi/id/product_uuid")
            self._serial = f("cat /sys/class/dmi/id/product_serial")
            self._vendor = f("cat /sys/class/dmi/id/sys_vendor")
            self._model = f("cat /sys/class/dmi/id/product_name")
            self._ram_kb = f("cat /proc/meminfo | grep MemTotal | awk '{ print $2 }'", int)

            self._cpu_model = f("cat /proc/cpuinfo | grep 'model name' | head -n 1 | cut -d':' -f 2")
            self._cpu_freq_ghz = round(f("cat /proc/cpuinfo | grep 'cpu MHz' "
                                         "| head -n 1 | cut -d':' -f 2", float) / 1000, 1)
            self._cpu_count = f("cat /proc/cpuinfo | grep processor | wc -l", int)
            self._cpu_sockets = min(1, f("cat /proc/cpuinfo | grep 'physical id' | sort | uniq | wc -l", int))
            self._cpu_cores = min(1, f("cat /proc/cpuinfo | grep 'core id' | sort | uniq | wc -l", int))

            cores = self._cpu_sockets * self._cpu_cores
            self._cpu_threads = self._cpu_count / cores

        elif self.os_info.family == "Darwin":
            _, out, _ = self._shell.execute("system_profiler SPHardwareDataType")

            self._vendor = "Apple Inc."

            for line in out.split("\n"):
                if "Model Identifier" in line:
                    self._model = line.split(":")[1].strip()
                elif "Processor Name" in line:
                    self._cpu_model = line.split(":")[1].strip()
                elif "Number of Processors" in line:
                    self._cpu_sockets = int(line.split(":")[1].strip())
                elif "Total Number of Cores" in line:
                    self._cpu_cores = int(line.split(":")[1].strip())
                elif "Processor Speed" in line:
                    self._cpu_freq_ghz = float(line.split(":")[1].split()[0].strip().replace(',', '.'))
                elif "Memory" in line:
                    self._ram_kb = int(line.split()[1].strip()) * 1024 * 1024
                elif "Serial Number" in line:
                    self._serial = line.split(":")[1].strip()
                elif "Hardware UUID" in line:
                    self._uuid = line.split(":")[1].strip()

            self._cpu_count = self._shell.execute_fetch_one("sysctl -n hw.ncpu", type=int)

            cores = self._cpu_sockets * self._cpu_cores
            self._cpu_threads = self._cpu_count / cores

        else:
            logging.warning("the %s.%s function is not implemented for OS: %s" %
                            (self.__class__.__name__, f.__name__, self.os_info.family))

        self._inited = True

        return self

    @cached_property
    def uuid(self):
        return self._init()._uuid

    @cached_property
    def serial(self):
        return self._init()._serial

    @cached_property
    def vendor(self):
        return self._init()._vendor

    @cached_property
    def model(self):
        return self._init()._model

    @cached_property
    def cpu_model(self):
        return self._init()._cpu_model

    @cached_property
    def cpu_freq_ghz(self):
        return self._init()._cpu_freq_ghz

    @cached_property
    def cpu_count(self):
        return self._init()._cpu_count

    @cached_property
    def cpu_topology(self):
        return "%dS x %dC x %dT" % \
               (self._init()._cpu_sockets, self._init()._cpu_cores, self._init()._cpu_threads)

    @cached_property
    def ram_kb(self):
        return self._init()._ram_kb

    @cached_property
    def os_info(self):
        return Os(self._shell) if self._os_info is None else self._os_info


class ptShell:
    def __init__(self, shell=None):
        if shell is None:
            shell = citizenshell.LocalShell()
        assert isinstance(shell, citizenshell.abstractshell.AbstractShell)
        self.shell = shell
        self._hw_info = None
        self._os_info = None

    @cached_property
    def hw_info(self):
        return Hw(self, self.os_info)

    @cached_property
    def os_info(self):
        return Os(self)

    def __str__(self):
        if isinstance(self.shell, citizenshell.LocalShell):
            return "localhost"
        if isinstance(self.shell, citizenshell.SecureShell):
            return ""  # self.os_info.hostname
        return str(self.shell)

    def _debug(self, msg):
        logging.debug("%s: %s" % (str(self), msg))

    def execute(self, cmdline, raise_exc=True):
        self._debug("%s ..." % cmdline)
        ret = self.shell(cmdline)
        if ret.exit_code():
            msg = "ERROR: %s: %s, exit status: %d\n%s %s" % (str(self), cmdline, ret.exit_code(), ret.stderr(),
                                                             ret.stdout())
            if raise_exc:
                raise ShellError(msg)
            self._debug(msg)

        return ret.exit_code(), "\n".join(ret.stdout()), "\n".join(ret.stderr())

    def execute_fetch_one(self, cmdline, type=None):
        status, out, err = self.execute(cmdline, raise_exc=None)
        if status:
            ret = None
        else:
            ret = out.strip()
        if type:
            try:
                return type(ret)
            except ValueError:
                self._debug("ERROR: can't cast '%s' to '%s'" % (str(ret), str(type)))
                return type()
        return ret


class ptShellFromFile(citizenshell.abstractshell.AbstractShell):
    def __init__(self, from_file, **kwargs):
        citizenshell.abstractshell.AbstractShell.__init__(self)
        self.from_file = from_file

    def execute(self, cmdline, raise_exc=True, **kwargs):
        with open(self.from_file) as output:
            return 0, "".join(output.readlines()), ""


##############################################################################
# Autotests
##############################################################################


def _coverage():
    logging.basicConfig(level=logging.DEBUG)

    sh = ptShell(citizenshell.LocalShell())

    print("os family:    ", sh.os_info.family)
    print("os version:   ", sh.os_info.version)
    print("hostname:     ", sh.os_info.hostname)
    print("uuid:         ", sh.hw_info.uuid)
    print("uuid:         ", sh.hw_info.uuid)
    print("serial:       ", sh.hw_info.serial)
    print("vendor:       ", sh.hw_info.vendor)
    print("model:        ", sh.hw_info.model)
    print("cpu_model:    ", sh.hw_info.cpu_model)
    print("cpu_freq_ghz: ", sh.hw_info.cpu_freq_ghz)
    print("cpu_count:    ", sh.hw_info.cpu_count)
    print("cpu_topology: ", sh.hw_info.cpu_topology)
    print("ram_kb:       ", sh.hw_info.ram_kb)


if __name__ == "__main__":
    _coverage()
