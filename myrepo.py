#! /usr/bin/python
#
# myrepo.py - Manage your yum repo and RPMs:
#
#  * Setup your own yum repos
#  * build SRPMs and deploy SRPMs and RPMs into your repos.
#
# Copyright (C) 2011 Satoru SATOH <satoru.satoh@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Requirements: createrepo, ssh, packagemaker (see below)
#
# SEE ALSO: createrepo(8)
# SEE ALSO: https://github.com/ssato/rpmkit/blob/pmaker.py
#

from Cheetah.Template import Template
from itertools import groupby, product

import ConfigParser as cp
import copy
import doctest
import glob
import logging
import multiprocessing
import optparse
import os
import os.path
import platform
import pprint
import re
import rpm
import socket
import subprocess
import sys
import tempfile
import unittest



def memoize(fn):
    """memoization decorator.
    """
    cache = {}

    def wrapped(*args, **kwargs):
        key = repr(args) + repr(kwargs)
        if not cache.has_key(key):
            cache[key] = fn(*args, **kwargs)
        return cache[key]

    return wrapped


def compile_template(template, params, is_file=False):
    """
    TODO: Add test case that $template is a filename.

    >>> tmpl_s = "a=$a b=$b"
    >>> params = {'a':1, 'b':'b'}
    >>> 
    >>> assert "a=1 b=b" == compile_template(tmpl_s, params)
    """
    if is_file:
        tmpl = Template(file=template, searchList=params)
    else:
        tmpl = Template(source=template, searchList=params)

    return tmpl.respond()


@memoize
def list_archs(arch=None):
    """List 'normalized' architecutres this host (mock) can support.
    """
    default = ["x86_64", "i386"]  # This order should be kept.
    ia32_re = re.compile(r"i.86") # i386, i686, etc.

    if arch is None:
        arch = platform.machine()

    if ia32_re.match(arch) is not None:
        return ["i386"]
    else:
        return default


@memoize
def list_dists():
    """List available dist names, e.g. ["fedora-14", "rhel-6"]
    """
    mockdir = "/etc/mock"
    arch = list_archs()[0]
    reg = re.compile("%s/(?P<dist>[^-]+-[^-]+)-%s.cfg" % (mockdir, arch))

    return [reg.match(c).groups()[0] for c in sorted(glob.glob("%s/*-*-%s.cfg" % (mockdir, arch)))]


def is_local(fqdn_or_hostname):
    """
    >>> is_local("localhost")
    True
    >>> is_local("localhost.localdomain")
    True
    >>> is_local("repo-server.example.com")
    False
    >>> is_local("127.0.0.1")  # special case:
    False
    """
    return fqdn_or_hostname.startswith("localhost")


def shell(cmd, workdir=None, log=True, dryrun=False, stop_on_error=True):
    """
    @cmd      str   command string, e.g. "ls -l ~".
    @workdir  str   in which dir to run given command?
    @log      bool  whether to print log messages or not.
    @dryrun   bool  if True, just print command string to run and returns.
    @stop_on_error bool  if True, RuntimeError will not be raised.
    
    TODO: Popen.communicate might be blocked. How about using Popen.wait
    instead?

    >>> assert 0 == shell("echo ok > /dev/null", os.curdir, False)
    >>> assert 0 == shell("ls null", "/dev", False)
    >>> try:
    ...    rc = shell("ls /root", os.curdir, False)
    ... except RuntimeError:
    ...    pass
    >>> assert 0 == shell("ls /root", os.curdir, False, True)
    """
    if workdir is None:
        workdir = os.path.abspath(os.curdir)

    logging.info("Run: %s [%s]" % (cmd, workdir))

    if dryrun:
        logging.info("Exit as requested (dry run mode).")
        return 0

    try:
        proc = subprocess.Popen([cmd], shell=True, cwd=workdir)
        proc.wait()
        rc = proc.returncode
    except Exception, e:
        # NOTE: e.message looks not available in python < 2.5:
        #raise RuntimeError("Error (%s) during executing: %s" % (repr(e.__class__), e.message))
        raise RuntimeError("Error (%s) during executing: %s" % (repr(e.__class__), str(e)))

    if rc == 0:
        return rc
    else:
        if stop_on_error:
            raise RuntimeError(" Failed: %s,\n rc=%d" % (cmd, rc))
        else:
            logging.error("cmd=%s, rc=%d" % (cmd, rc))
            return rc


def rshell(cmd, user, host, workdir, log=True, dryrun=False, stop_on_error=True):
    """
    @user     str  (remote) user to run given command.
    @host     str  on which host to run given command?

    >>> rc = shell("test -x /sbin/service && /sbin/service sshd status > /dev/null 2> /dev/null")
    >>> if rc == 0:
    ...     rc = rshell("ls /dev/null", get_username(), "127.0.0.1", os.curdir, log=False)
    ...     assert rc == 0, rc
    """
    if not is_local(host):
        cmd = "ssh %s@%s 'cd %s && %s'" % (user, host, workdir, cmd)
        workdir = os.curdir

    return shell(cmd, workdir, log, dryrun, stop_on_error)



class Command(object):
    """Object to wrap command to run.
    """

    def __init__(self, cmd, user=None, host="localhost", workdir=os.curdir,
            log=True, dryrun=False, stop_on_error=True):
        self.cmd = cmd
        self.user = get_username()
        self.host = host
        self.log = log
        self.dryrun = dryrun
        self.stop_on_error = stop_on_error

        if is_local(host) and "~" in workdir:
            self.workdir = os.path.expanduser(workdir)
        else:
            self.workdir = workdir

    def __str__(self):
        return "%s in %s on %s@%s" % (self.cmd, self.workdir, self.user, self.host)

    def __eq__(self, other):
        return self.cmd == other.cmd and \
            self.user == other.user and \
            self.host == other.host and \
            self.workdir == other.workdir and \
            self.log == other.log and \
            self.dryrun == other.dryrun and \
            self.stop_on_error == other.stop_on_error

    def run(self):
        return rshell(self.cmd, self.user, self.host, self.workdir, self.log, self.dryrun, self.stop_on_error)



def rm_rf(dir):
    """'rm -rf' in python.
    """
    if not os.path.exists(dir):
        return

    if os.path.isfile(dir):
        os.remove(dir)
        return

    assert dir != '/'                    # avoid "rm -rf /"
    assert os.path.realpath(dir) != '/'  # likewise

    for x in glob.glob(os.path.join(dir, '*')):
        if os.path.isdir(x):
            rm_rf(x)
        else:
            os.remove(x)

    if os.path.exists(dir):
        os.removedirs(dir)


@memoize
def is_git_available():
    return os.system("git --version > /dev/null 2> /dev/null") == 0


@memoize
def hostname():
    return socket.gethostname() or os.uname()[1]


@memoize
def get_username():
    """Get username.
    """
    return os.environ.get("USER", False) or os.getlogin()


@memoize
def get_email():
    if is_git_available():
        try:
            email = subprocess.check_output("git config --get user.email 2>/dev/null", shell=True)
            return email.rstrip()
        except Exception, e:
            logging.warn("get_email: " + str(e))
            pass

    return get_username() + "@%(server)s"


@memoize
def get_fullname():
    """Get full name of the user.
    """
    if is_git_available():
        try:
            fullname = subprocess.check_output("git config --get user.name 2>/dev/null", shell=True)
            return fullname.rstrip()
        except Exception, e:
            logging.warn("get_fullname: " + str(e))
            pass

    return os.environ.get("FULLNAME", False) or get_username()


@memoize
def get_distribution():
    """Get name and version of the distribution of the system based on
    heuristics.
    """
    fedora_f = "/etc/fedora-release"
    rhel_f = "/etc/redhat-release"

    if os.path.exists(fedora_f):
        name = "fedora"
        m = re.match(r"^Fedora .+ ([0-9]+) .+$", open(fedora_f).read())
        version = m is None and "14" or m.groups()[0]

    elif os.path.exists(rhel_f):
        name = "rhel"
        m = re.match(r"^Red Hat.* ([0-9]+) .*$", open(fedora_f).read())
        version = m is None and "6" or m.groups()[0]
    else:
        raise RuntimeError("Not supported distribution!")

    return (name, version)


def rpm_header_from_rpmfile(rpmfile):
    """Read rpm.hdr from rpmfile.
    """
    return rpm.TransactionSet().hdrFromFdno(open(rpmfile, "rb"))


def is_noarch(srpm):
    """Determine if given srpm is noarch (arch-independent).
    """
    return rpm_header_from_rpmfile(srpm)[rpm.RPMTAG_ARCH] == "noarch"



class TestMemoizedFuncs(unittest.TestCase):

    def test_memoize(self):
        fun_0 = lambda a: a * 2
        memoized_fun_0 = memoize(fun_0)

        self.assertEquals(fun_0(2), memoized_fun_0(2))
        self.assertEquals(memoized_fun_0(3), memoized_fun_0(3))

    def test_list_archs(self):
        """list_archs() depends on platform.machine() which returns read-only
        system dependent value so full covered test is almost impossible.

        Tests here covers some limited cases.
        """
        self.assertListEqual(list_archs("i586"), ["i386"])
        self.assertListEqual(list_archs("i686"), ["i386"])
        self.assertListEqual(list_archs("x86_64"), ["x86_64", "i386"])

    def test_list_dists(self):
        """TODO: write tests
        """
        pass

    def test_is_git_available(self):
        """TODO: write tests
        """
        pass

    def test_hostname(self):
        self.assertEquals(hostname(), subprocess.check_output("hostname").rstrip())

    def test_username(self):
        self.assertEquals(get_username(), subprocess.check_output("id -un", shell=True).rstrip())

    def test_get_email(self):
        """TODO: write tests
        """
        pass

    def test_get_fullname(self):
        """TODO: write tests
        """
        pass

    def test_get_distribution(self):
        """TODO: write tests
        """
        pass



class TestMiscFuncs(unittest.TestCase):

    def setUp(self):
        self.workdir = tempfile.mkdtemp(dir="/tmp", prefix="myrepo-tests")

    def tearDown(self):
        rm_rf(self.workdir)

    def test_rm_rf_twice(self):
        d = self.workdir

        rm_rf(d)
        rm_rf(d)

    def test_rm_rf_dirs(self):
        d = self.workdir

        for c in "abc":
            os.makedirs(os.path.join(d, c))

        os.makedirs(os.path.join(d, "c", "d"))

        open(os.path.join(d, 'x'), "w").write("test")
        open(os.path.join(d, 'a', 'y'), "w").write("test")
        open(os.path.join(d, 'c', 'd', 'z'), "w").write("test")

        rm_rf(d)



class Distribution(object):

    def __init__(self, dist, arch="x86_64"):
        """
        @dist  str   Distribution label, e.g. "fedora-14"
        @arch  str   Architecture, e.g. "i386"
        """
        self.label = "%s-%s" % (dist, arch)
        (self.name, self.version) = self.parse_dist(dist)
        self.arch = arch

        self.arch_pattern = (arch == "i386" and "i*86" or self.arch)

    @classmethod
    def parse_dist(self, dist):
        return dist.split('-')

    def mockdir(self):
        return "/var/lib/mock/%s/result" % self.label

    def build_cmd(self, srpm):
        """
        NOTE: mock will print log messages to stderr (not stdout).
        """
        # suppress log messages from mock in accordance with log level:
        if logging.getLogger().level >= logging.WARNING:
            fmt = "mock -r %s %s > /dev/null 2> /dev/null"
        else:
            fmt = "mock -r %s %s"

        return fmt % (self.label, srpm)



class TestDistribution(unittest.TestCase):

    def setUp(self):
        self.workdir = tempfile.mkdtemp(dir="/tmp", prefix="myrepo-tests")

    def tearDown(self):
        rm_rf(self.workdir)


    def test__init__(self):
        d = Distribution("fedora-14", "x86_64")

        self.assertEquals(d.name, "fedora")
        self.assertEquals(d.version, "14")
        self.assertEquals(d.arch, "x86_64")

    def test_mockdir(self):
        d = Distribution("fedora-14", "x86_64")

        self.assertEquals(d.mockdir(), "/var/lib/mock/fedora-14-x86_64/result")

    def test_build_cmd(self):
        d = Distribution("fedora-14", "x86_64")

        logging.getLogger().setLevel(logging.WARNING)
        c = d.build_cmd("python-virtinst-0.500.5-1.fc14.src.rpm")
        cref = "mock -r fedora-14-x86_64 python-virtinst-0.500.5-1.fc14.src.rpm > /dev/null 2> /dev/null"
        self.assertEquals(c, cref)

        logging.getLogger().setLevel(logging.INFO)
        c = d.build_cmd("python-virtinst-0.500.5-1.fc14.src.rpm")
        cref = "mock -r fedora-14-x86_64 python-virtinst-0.500.5-1.fc14.src.rpm"
        self.assertEquals(c, cref)

    def test_arch_pattern(self):
        d = Distribution("fedora-14", "x86_64")
        self.assertEquals(d.arch_pattern, "x86_64")

        d = Distribution("fedora-14", "i386")
        self.assertEquals(d.arch_pattern, "i*86")



class RepoOperations(object):
    """Yum repository operations.
    """

    @classmethod
    def sequence_(cls, cmds):
        rcs = []

        for c in cmds:
            rc = c.run()
            rcs.append(rc)

        return rcs

    @classmethod
    def destdir(cls, repo):
        return os.path.join(repo.topdir, repo.distdir)

    @classmethod
    def build(cls, repo, srpm):
        cs = [repo.build_cmd(srpm, d) for d in repo.dists_by_srpm(srpm)]

        return cls.sequence_(cs)

    @classmethod
    def deploy(cls, repo, srpm, build=True):
        if build:
            rcs = cls.build(repo, srpm)
            assert all((r == 0 for r in rcs))

        destdir = cls.destdir(repo)
        cs = [repo.copy_cmd(srpm, os.path.join(destdir, "sources"))]

        for d in repo.dists_by_srpm(srpm):
            if is_noarch(srpm):
                rpms = glob.glob("%s/*.noarch.rpm" % d.mockdir())
            else:
                rpms = glob.glob("%s/*.%s.rpm" % (d.mockdir(), d.arch_pattern))

            for p in rpms:
                cs.append(repo.copy_cmd(p, os.path.join(destdir, d.arch)))

        cls.sequence_(cs)
        cls.update(repo)

    @classmethod
    def deploy_release_rpm(cls, repo, workdir=None):
        """Generate (yum repo) release package.

        @workdir str   Working directory
        """
        if workdir is None:
            workdir = tempfile.mkdtemp(dir="/tmp", prefix="%s-release-" % repo.name)

        c = repo.release_file_content()

        reldir = os.path.join(workdir, "etc", "yum.repos.d")
        release_file_path = os.path.join(reldir, "%s.repo" % repo.name)

        os.makedirs(reldir)
        open(release_file_path, 'w').write(c)

        cmd = Command(repo.release_rpm_build_cmd(workdir, release_file_path), repo.user)
        cmd.run()

        srpms = glob.glob("%s/%s-release-%s/%s-release*.src.rpm" % (workdir, repo.name, repo.distversion, repo.name))
        if not srpms:
            logging.error("Failed to build src.rpm")
            sys.exit(1)

        srpm = srpms[0]

        cls.deploy(repo, srpm)
        cls.update(repo)

    @classmethod
    def init(cls, repo):
        """Initialize yum repository.
        """
        destdir = cls.destdir(repo)

        xs = ["mkdir -p %s" % os.path.join(destdir, d) for d in ["sources"] + repo.archs] 
        cs = [Command(c, repo.user, repo.server) for c in xs]

        cls.sequence_(cs)

        cls.deploy_release_rpm(repo)

    @classmethod
    def update(cls, repo):
        """'createrepo --update ...', etc.
        """
        destdir = cls.destdir(repo)
        cs = []

        # hack:
        if len(repo.archs) > 1:
            c = "for d in %s; do (cd $d && ln -sf ../%s/*.noarch.rpm ./); done" % \
                (" ".join(repo.archs[1:]), repo.dists[0].arch)
            cs.append(Command(c, repo.user, repo.server, destdir, stop_on_error=False))

        dirs = [os.path.join(destdir, d) for d in ["sources"] + repo.archs]
        c = "test -d repodata && createrepo --update --deltas --oldpackagedirs . --database . || createrepo --deltas --oldpackagedirs . --database ."

        cs += [Command(c, repo.user, repo.server, d) for d in dirs]

        return cls.sequence_(cs)



class Repo(object):
    """Yum repository.
    """
    name = "%(distname)s-%(hostname)s-%(user)s"
    subdir = "yum"
    topdir = "~%(user)s/public_html/%(subdir)s"
    baseurl = "http://%(server)s/%(user)s/%(subdir)s/%(distdir)s"
    gpgcheck = False

    release_file_tmpl = """\
[${repo.name}]
name=Custom yum repository on ${repo.server} by ${repo.user} (\$basearch)
baseurl=${repo.baseurl}\$basearch/
enabled=1
gpgcheck=${repo.gpgcheck}

[${repo.name}-source]
name=Custom yum repository on ${repo.server} by ${repo.user} (source)
baseurl=${repo.baseurl}sources/
enabled=0
gpgcheck=0
"""
    release_file_build_tmpl = """\
echo "${repo.release_file},uid=0,gid=0,rpmattr=%config" | \\
pmaker -n ${repo.name}-release --license MIT \\
    -w ${repo.workdir} \\
    --itype filelist.ext \\
    --upto sbuild \\
    --group "System Environment/Base" \\
    --url ${repo.baseurl} \\
    --summary "Yum repo files for ${repo.name}" \\
    --packager "${repo.fullname}" \\
    --mail "${repo.email}" \\
    --pversion ${repo.distversion}  \\
    --no-rpmdb --no-mock \\
    ${repo.logopt} \\
    --destdir ${repo.workdir} - 
"""

    def __init__(self, server, user, email, fullname, dist, archs,
            name=None, subdir=None, topdir=None, baseurl=None, gpgcheck=False,
            *args, **kwargs):
        """
        @server    server's hostname to provide this yum repo
        @user      username on the server
        @email     email address or its format string
        @fullname  full name, e.g. "John Doe".
        @name      repository name or its format string, e.g. "rpmfusion-free", "%(distname)s-%(hostname)s-%(user)s"
        @dist      distribution string, e.g. "fedora-14"
        @archs     architecture list, e.g. ["i386", "x86_64"]
        @subdir    repo's subdir
        @topdir    repo's topdir or its format string, e.g. "/var/www/html/%(subdir)s".
        @baseurl   base url or its format string, e.g. "file://%(topdir)s".
        """
        self.server = server
        self.user = user
        self.fullname = fullname
        self.dist = dist
        self.archs = archs

        self.hostname = server.split('.')[0]
        self.multiarch = "i386" in self.archs and "x86_64" in self.archs

        (self.distname, self.distversion) = Distribution.parse_dist(self.dist)
        self.dists = [Distribution(self.dist, arch) for arch in self.archs]
        self.distdir = os.path.join(self.distname, self.distversion)

        self.subdir = subdir is None and self.subdir or subdir
        self.gpgcheck = gpgcheck and "1" or "0"

        self.email = self._format(email)

        if name is None:
            name = Repo.name

        if topdir is None:
            topdir = Repo.topdir

        if baseurl is None:
            baseurl = Repo.baseurl

        # expand parameters in format strings:
        self.name = self._format(name)
        self.topdir = self._format(topdir)
        self.baseurl = self._format(baseurl)

    def _format(self, fmt_or_var):
        return "%" in fmt_or_var and fmt_or_var % self.__dict__ or fmt_or_var

    def copy_cmd(self, src, dst):
        if is_local(self.server):
            cmd = "cp -a %s %s" % (src, ("~" in dst and os.path.expanduser(dst) or dst))
        else:
            cmd = "scp -p %s %s@%s:%s" % (src, self.user, self.server, dst)

        return Command(cmd, self.user)

    def build_cmd(self, srpm, dist):
        """Returns Command object to build src.rpm
        """
        return Command(dist.build_cmd(srpm), self.user, "localhost", os.curdir)

    def dists_by_srpm(self, srpm):
        return (is_noarch(srpm) and self.dists[:1] or self.dists)

    def release_file_content(self):
        # this package will be noarch (arch-independent).
        dist = self.dists[0]
        params = {"repo": self, "dist": dist}

        return compile_template(self.release_file_tmpl, params)

    def release_rpm_build_cmd(self, workdir, release_file_path):
        logopt = logging.getLogger().level < logging.INFO and "--verbose" or ""

        repo = copy.copy(self.__dict__)
        repo.update({
            "release_file": release_file_path,
            "workdir": workdir,
            "logopt": logopt,
        })
        params = {"repo": repo}

        return compile_template(self.release_file_build_tmpl, params)



class TestRepo(unittest.TestCase):

    def setUp(self):
        self.workdir = tempfile.mkdtemp(prefix="myrepo-repo-tests")
        self.config = init_defaults()

        # overrides some parameters:
        self.config["dist"] = self.config["dists"][0]
        self.config["topdir"] = os.path.join(self.workdir, "repos", "%(subdir)s")
        self.config["baseurl"] = "file://%(topdir)s/%(distdir)s"

        self.config["dist"] = ["%s-%s" % get_distribution()][0]
        self.config["archs"] = ",".join(list_archs())

    def tearDown(self):
        rm_rf(self.workdir)

    def test_copy_cmd(self):
        repo = Repo("localhost",
                    self.config["user"],
                    self.config["email"],
                    self.config["fullname"],
                    self.config["dist"],
                    self.config["archs"],
                    topdir=self.config["topdir"],
                    baseurl=self.config["baseurl"]
        )

        (src, dst) = ("foo.txt", "bar.txt")

        c0 = repo.copy_cmd(src, dst)
        c1 = Command("cp -a %s %s" % (src, dst), self.config["user"])
        self.assertEquals(c0, c1)

        (src, dst) = ("foo.txt", "~/bar.txt")

        c2 = repo.copy_cmd(src, dst)
        c3 = Command("cp -a %s %s" % (src, ("~" in dst and os.path.expanduser(dst) or dst)), self.config["user"])
        self.assertEquals(c2, c3)

        server = "repo-server.example.com"
        repo = Repo(server,
                    self.config["user"],
                    self.config["email"],
                    self.config["fullname"],
                    self.config["dist"],
                    self.config["archs"],
                    topdir=self.config["topdir"],
                    baseurl=self.config["baseurl"]
        )

        c4 = repo.copy_cmd(src, dst)
        c5 = Command("scp -p %s %s@%s:%s" % (src, self.config["user"], server, dst), self.config["user"])
        self.assertEquals(c4, c5)

    def test_release_file_content(self):
        repo = Repo("localhost",
                    self.config["user"],
                    self.config["email"],
                    self.config["fullname"],
                    self.config["dist"],
                    self.config["archs"],
                    topdir=self.config["topdir"],
                    baseurl=self.config["baseurl"]
        )

        repo.release_file_content()
        #compile_template(self.release_file_tmpl, params)



def parse_conf_value(s):
    """Simple and naive parser to parse value expressions in config files.

    >>> assert 0 == parse_conf_value("0")
    >>> assert 123 == parse_conf_value("123")
    >>> assert True == parse_conf_value("True")
    >>> assert [1,2,3] == parse_conf_value("[1,2,3]")
    >>> assert "a string" == parse_conf_value("a string")
    >>> assert "0.1" == parse_conf_value("0.1")
    """
    intp = re.compile(r"^([0-9]|([1-9][0-9]+))$")
    boolp = re.compile(r"^(true|false)$", re.I)
    listp = re.compile(r"^(\[\s*((\S+),?)*\s*\])$")

    def matched(pat, s):
        m = pat.match(s)
        return m is not None

    if not s:
        return ""

    if matched(boolp, s):
        return bool(s)

    if matched(intp, s):
        return int(s)

    if matched(listp, s):
        return eval(s)  # TODO: too danger. safer parsing should be needed.

    return s


def init_defaults_by_conffile(config=None, profile=None):
    """
    Initialize default values for options by loading config files.
    """
    if config is None:
        home = os.environ.get("HOME", os.curdir) # Is there case that $HOME is empty?

        confs = ["/etc/myreporc"]
        confs += sorted(glob.glob("/etc/myrepo.d/*.conf"))
        confs += [os.environ.get("MYREPORC", os.path.join(home, ".myreporc"))]
    else:
        confs = (config,)

    cparser = cp.SafeConfigParser()
    loaded = False

    for c in confs:
        if os.path.exists(c):
            logging.info("Loading config: %s" % c)
            cparser.read(c)
            loaded = True

    if not loaded:
        return {}

    d = profile and cparser.items(profile) or cparser.defaults().iteritems()

    return dict((k, parse_conf_value(v)) for k, v in d)


def init_defaults():
    dists = ["%s-%s" % get_distribution()]
    archs = list_archs()
    distributions = ["%s-%s" % da for da in product(dists, archs)]

    defaults = {
        "server": hostname(),
        "user": get_username(),
        "email":  get_email(),
        "fullname": get_fullname(),
        "dists": ",".join(distributions),
        "name": Repo.name,
        "subdir": Repo.subdir,
        "topdir": Repo.topdir,
        "baseurl": Repo.baseurl,
        "gpgcheck": Repo.gpgcheck,
    }

    return defaults



class TestFuncsWithSideEffects(unittest.TestCase):

    def setUp(self):
        self.workdir = tempfile.mkdtemp(dir="/tmp", prefix="myrepo-tests")

    def tearDown(self):
        rm_rf(self.workdir)

    def test_init_defaults_by_conffile_config(self):
        conf = """\
[DEFAULT]
a: aaa
b: bbb
"""
        path = os.path.join(self.workdir, "config")
        open(path, "w").write(conf)

        params = init_defaults_by_conffile(path)
        self.assertEquals(params["a"], "aaa")
        self.assertEquals(params["b"], "bbb")

    def test_init_defaults_by_conffile_config_and_profile_0(self):
        conf = """\
[profile0]
a: aaa
b: bbb
"""
        path = os.path.join(self.workdir, "config")
        open(path, "w").write(conf)

        params = init_defaults_by_conffile(path, "profile0")
        self.assertEquals(params["a"], "aaa")
        self.assertEquals(params["b"], "bbb")



class TestAppLocal(unittest.TestCase):

    def setUp(self):
        self.prog = "python %s" % sys.argv[0]


        self.workdir = tempfile.mkdtemp(prefix="myrepo-test-tal-")

    def tearDown(self):
        rm_rf(self.workdir)

    def test_init_with_all_options_set_explicitly(self):
        config = copy.copy(init_defaults())

        # force set some parameters:
        config["server"] = "localhost"
        config["topdir"] = os.path.join(self.workdir, "%(user)s", "public_html", "%(subdir)s")
        config["baseurl"] = "file://" + config["topdir"] + "/%(distdir)s"

        config["prog"] = self.prog

        cmd = "%(prog)s --server %(server)s --user %(user)s --email %(email)s --fullname \"%(fullname)s\" "
        cmd += " --dists %(dists)s --name \"%(name)s\" --subdir %(subdir)s --topdir \"%(topdir)s\" "
        cmd += " --baseurl \"%(baseurl)s\" --gpgcheck "
        cmd += " init "
        cmd = cmd % config

        logging.info("cmd: " + cmd)
        self.assertEquals(os.system(cmd), 0)

    def test_init_with_all_options_set_explicitly_multi_dists(self):
        config = copy.copy(init_defaults())

        # force set some parameters:
        config["server"] = "localhost"
        config["topdir"] = os.path.join(self.workdir, "%(user)s", "public_html", "%(subdir)s")
        config["baseurl"] = "file://" + config["topdir"] + "/%(distdir)s"

        config["dists"] = "rhel-6-i386,fedora-14-i386"

        config["prog"] = self.prog

        cmd = "%(prog)s --server %(server)s --user %(user)s --email %(email)s --fullname \"%(fullname)s\" "
        cmd += " --dists %(dists)s --name \"%(name)s\" --subdir %(subdir)s --topdir \"%(topdir)s\" "
        cmd += " --baseurl \"%(baseurl)s\" --gpgcheck "
        cmd += " init "
        cmd = cmd % config

        logging.info("cmd: " + cmd)
        self.assertEquals(os.system(cmd), 0)

    def test_build(self):
        pass

    def test_deploy(self):
        pass

    def test_update(self):
        pass



def test(verbose):
    doctest.testmod(verbose=verbose)

    (major, minor) = sys.version_info[:2]
    if major == 2 and minor < 5:
        unittest.main(argv=sys.argv[:1])
    else:
        unittest.main(argv=sys.argv[:1], verbosity=(verbose and 2 or 0))


def opt_parser():
    defaults = init_defaults()
    defaults.update(init_defaults_by_conffile())

    p = optparse.OptionParser("""%prog COMMAND [OPTION ...] [ARGS]

Commands: i[init], b[uild], d[eploy], u[pdate]

Examples:
  # initialize your yum repos:
  %prog init -s yumserver.local -u foo -m foo@example.com -F "John Doe"

  # build SRPM:
  %prog build packagemaker-0.1-1.src.rpm 

  # build SRPM and deploy RPMs and SRPMs into your yum repos:
  %prog deploy packagemaker-0.1-1.src.rpm
  %prog d --dists rhel-6-x86_64 packagemaker-0.1-1.src.rpm
  """
    )

    for k in ("tests", "verbose", "debug"):
        if not defaults.get(k, False):
            defaults[k] = False

    p.set_defaults(**defaults)

    p.add_option("-C", "--config", help="Configuration file")

    p.add_option("-s", "--server", help="Server to provide your yum repos.")
    p.add_option("-u", "--user", help="Your username on the server [%default]")
    p.add_option("-m", "--email", help="Your email address or its format string[%default]")
    p.add_option("-F", "--fullname", help="Your full name [%default]")

    p.add_option("", "--dists", help="Comma separated distribution labels including arch. "
        "Options are some of default [%default]")

    p.add_option("-q", "--quiet", dest="verbose", action="store_false", help="Quiet mode")
    p.add_option("-v", "--verbose", action="store_true", help="Verbose mode")

    p.add_option("-T", "--test", action="store_true", help="Run test suite")

    iog = optparse.OptionGroup(p, "Options for 'init' command")
    iog.add_option('', "--name", help="Name of your yum repo or its format string [%default].")
    iog.add_option("", "--subdir", help="Repository sub dir name [%default]")
    iog.add_option("", "--topdir", help="Repository top dir or its format string [%default]")
    iog.add_option('', "--baseurl", help="Repository base URL or its format string [%default]")
    iog.add_option('', "--gpgcheck", action="store_true", help="Whether to check GPG key")
    p.add_option_group(iog)

    return p


def main():
    (CMD_INIT, CMD_UPDATE, CMD_BUILD, CMD_DEPLOY) = ("init", "update", "build", "deploy")

    p = opt_parser()
    (options, args) = p.parse_args()

    if options.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)

    if options.test:
        verbose_test = (options.verbose or options.debug)
        test(verbose_test)
        sys.exit()

    if not args:
        p.print_usage()
        sys.exit(1)

    a0 = args[0]
    if a0.startswith('i'):
        cmd = CMD_INIT

    elif a0.startswith('u'):
        cmd = CMD_UPDATE

    elif a0.startswith('b'):
        cmd = CMD_BUILD
        assert len(args) >= 2, "'%s' command requires an argument to specify srpm[s]" % cmd

    elif a0.startswith('d'):
        cmd = CMD_DEPLOY
        assert len(args) >= 2, "'%s' command requires an argument to specify srpm[s]" % cmd

    else:
        logging.error(" Unknown command '%s'" % a0)
        sys.exit(1)

    if options.config:
        params = init_defaults()
        params.update(init_defaults_by_conffile(options.config))

        p.set_defaults(**params)

        # re-parse to overwrite configurations with given options.
        (options, args) = p.parse_args()

    config = copy.copy(options.__dict__)

    # Kept for DEBUG:
    #pprint.pprint(config)
    #sys.exit()

    dists = config["dists"].split(",")
    repos = []

    for dist, labels in groupby(dists, lambda d: d[:d.rfind("-")]):
        archs = [l.split("-")[-1] for l in labels]

        repo = Repo(
            config["server"],
            config["user"],
            config["email"],
            config["fullname"],
            dist,
            archs,
            config["name"],
            config["subdir"],
            config["topdir"],
            config["baseurl"],
            config["gpgcheck"],
        )

        repos.append(repo)
 
    def f(args):
        meth = args[0]
        repo = args[1]

        if len(args) >= 3:
            for srpm in args[2:]:
                meth(repo, srpm)
        else:
            meth(repo)

    for repo in repos:
        f([getattr(RepoOperations, cmd)] + [repo] + args[1:])

    sys.exit()

    # experimental code:
    nrepos = len(repos)

    if nrepos == 1:
        f([getattr(RepoOperations, cmd)] + [repos[0]] + args[1:])
        sys.exit()

    ncpus = mp.cpu_count()
    num = nrepos > ncpus and ncpus or nrepos

    pool = multiprocessing.Pool(num)
    result = pool.apply_async(f, [[getattr(RepoOperations, cmd)] + [repo] + args[1:] for repo in repos])
    result.get(timeout=60*20)


if __name__ == '__main__':
    main()

# vim: set sw=4 ts=4 expandtab:
