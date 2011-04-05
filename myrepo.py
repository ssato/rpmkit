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
# Requirements: createrepo, ssh, xpack (see below)
#
# SEE ALSO: createrepo(8)
# SEE ALSO: https://github.com/ssato/rpmkit/blob/xpack.py
#

from Cheetah.Template import Template
from itertools import chain

import ConfigParser as cp
import copy
import doctest
import glob
import logging
import optparse
import os
import os.path
import pprint
import re
import rpm
import subprocess
import sys
import tempfile
import unittest



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


def shell(cmd, workdir="", log=True, dryrun=False, stop_on_error=True):
    """
    @cmd      str   command string, e.g. "ls -l ~".
    @workdir  str   in which dir to run given command?
    @log      bool  whether to print log messages or not.
    @dryrun   bool  if True, just print command string to run and returns.
    @stop_on_error bool  if True, RuntimeError will not be raised.
    
    TODO: Popen.communicate might be blocked. How about using Popen.wait
    instead?

    >>> (o, e) = shell("echo ok > /dev/null", '.', False)
    >>> assert e == "", "errmsg=" + e
    >>> 
    >>> (o, e) = shell("ls null", "/dev", False)
    >>> assert e == "", "errmsg=" + e
    >>> 
    >>> try:
    ...    (o, e) = shell("ls /root", '.', False)
    ... except RuntimeError:
    ...    pass
    """
    if not workdir:
        workdir = os.path.abspath(os.curdir)

    logging.info(" Run: %s [%s]" % (cmd, workdir))

    if dryrun:
        logging.info(" exit as we're in dry run mode.")
        return ("", "")

    try:
        pipe = subprocess.Popen([cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, cwd=workdir)
        (output, errors) = pipe.communicate()
    except Exception, e:
        # NOTE: e.message looks not available in python < 2.5:
        #raise RuntimeError("Error (%s) during executing: %s" % (repr(e.__class__), e.message))
        raise RuntimeError("Error (%s) during executing: %s" % (repr(e.__class__), str(e)))

    if pipe.returncode == 0:
        return (output, errors)
    else:
        if stop_on_error:
            raise RuntimeError(" Failed: %s,\n err:\n'''%s'''" % (cmd, errors))
        else:
            logging.error(" cmd=%s, error=%s" % (cmd, errors))
            return ("", errors)


def rshell(cmd, user, host, workdir, log=True, dryrun=False, stop_on_error=True):
    """
    @user     str  (remote) user to run given command.
    @host     str  on which host to run given command?
    """
    is_remote = not host.startswith("localhost")

    if is_remote:
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
        self.workdir = workdir
        self.log = log
        self.dryrun = dryrun
        self.stop_on_error = stop_on_error

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

    >>> d = tempfile.mkdtemp(dir="/tmp")
    >>> rm_rf(d)
    >>> rm_rf(d)
    >>> 
    >>> d = tempfile.mkdtemp(dir="/tmp")
    >>> for c in "abc":
    ...     os.makedirs(os.path.join(d, c))
    >>> os.makedirs(os.path.join(d, "c", "d"))
    >>> open(os.path.join(d, 'x'), "w").write("test")
    >>> open(os.path.join(d, 'a', 'y'), "w").write("test")
    >>> open(os.path.join(d, 'c', 'd', 'z'), "w").write("test")
    >>> 
    >>> rm_rf(d)
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


def get_username():
    """Get username.
    """
    return os.environ.get("USER", False) or os.getlogin()


def get_email(use_git):
    if use_git:
        try:
            (email, e) = shell("git config --get user.email 2>/dev/null")
            if not e:
                return email.rstrip()
        except RuntimeError, e:
            logging.warn(str(e))
            pass

    return os.environ.get("MAIL_ADDRESS", False) or "%s@localhost.localdomain" % get_username()


def get_fullname(use_git):
    """Get full name of the user.
    """
    if use_git:
        try:
            (fullname, e) = shell("git config --get user.name 2>/dev/null")
            if not e:
                return fullname.rstrip()
        except RuntimeError, e:
            logging.warn(str(e))
            pass

    return os.environ.get("FULLNAME", False) or get_username()


def rpm_header_from_rpmfile(rpmfile):
    """Read rpm.hdr from rpmfile.
    """
    return rpm.TransactionSet().hdrFromFdno(open(rpmfile, "rb"))


def is_noarch(srpm):
    """Determine if given srpm is noarch (arch-independent).
    """
    return rpm_header_from_rpmfile(srpm)[rpm.RPMTAG_ARCH] == "noarch"



class Distribution(object):
    """Distribution object.

    >>> d = Distribution("fedora-14", "x86_64")
    >>> (d.name, d.version, d.arch)
    ('fedora', '14', 'x86_64')
    >>> d.mockdir()
    '/var/lib/mock/fedora-14-x86_64/result'
    >>> logging.getLogger().setLevel(logging.WARNING)
    >>> d.build_cmd("python-virtinst-0.500.5-1.fc14.src.rpm")
    'mock -r fedora-14-x86_64 python-virtinst-0.500.5-1.fc14.src.rpm 2>&1 2> /dev/null'
    >>> logging.getLogger().setLevel(logging.INFO)
    >>> d.build_cmd("python-virtinst-0.500.5-1.fc14.src.rpm")
    'mock -r fedora-14-x86_64 python-virtinst-0.500.5-1.fc14.src.rpm 2>&1'
    """

    def __init__(self, dist, arch="x86_64"):
        """
        @dist  str   Distribution label, e.g. "fedora-14"
        @arch  str   Architecture, e.g. "i386"
        """
        self.label = "%s-%s" % (dist, arch)
        (self.name, self.version) = self.parse_dist(dist)
        self.arch = arch

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
            fmt = "mock -r %s %s 2>&1 2> /dev/null"
        else:
            fmt = "mock -r %s %s 2>&1"

        return fmt % (self.label, srpm)


class Repo(object):
    """Yum repository objects.
    """

    # defaults:
    use_git = os.system("git --version > /dev/null 2> /dev/null") == 0

    user = get_username()
    #email = get_email(use_git)
    fullname = get_fullname(use_git)

    dist = "fedora-14"
    archs = "x86_64,i386"
    repodir = "yum"

    email_format = "%(user)s@%(server)s"
    name_format = "%(distname)s-%(hostname)s-%(user)s"
    baseurl_format = "http://%(server)s/%(topdir)s/%(distdir)s/"

    def __init__(self, server=False,
                       user=False,
                       email=False,
                       email_format=False,
                       fullname=False,
                       name=False,
                       name_format=False,
                       dist=False,
                       archs=False,
                       repodir=False,
                       baseurl_format=False,
                       *args, **kwargs):
        """
        @server    server's hostname to provide this yum repo via http
        @user      username on the server
        @email     email address
        @email_format  Format string to email address
        @fullname  full name, e.g. "John Doe".
        @name      repository name, e.g. "rpmfusion-free"
        @name_format  Format string to generate repository name
        @dist      distribution string, e.g. "fedora-14"
        @archs     architecture list, e.g. "i386,x86_64"
        @repodir   repo's topdir relative to ~/public_html/, e.g. yum.
        @baseurl_format   base url format, e.g. "http://%(server)s/%(topdir)s/%(distdir)s".
        """
        assert server, "server parameter must be given."
        self.server = server
        self.hostname = server.split('.')[0]

        if user:
            self.user = user

        if email_format:
            self.email_format = email_format

        if email:
            self.email = email
        else:
            self.email = self.gen_email()

        if fullname:
            self.fullname = fullname

        if dist:
            self.dist = dist

        if repodir:
            self.repodir = repodir

        if archs:
            self.archs = archs.split(',')

        self.multiarch = "i386" in self.archs and "x86_64" in self.archs

        (self.distname, self.distversion) = Distribution.parse_dist(self.dist)
        self.dists = [Distribution(self.dist, arch) for arch in self.archs]
        self.distdir = os.path.join(*Distribution.parse_dist(self.dist))

        self.topdir = "%(user)s/%(repodir)s" % {"user": self.user, "repodir": self.repodir}

        if baseurl_format:
            self.baseurl_format = baseurl_format

        if name_format:
            self.name_format = name_format

        if name:
            self.name = name
        else:
            self.name = self.gen_name()

        self.deploy_topdir = "~%(user)s/public_html/%(repodir)s/" % {"user": self.user, "repodir": self.repodir}
        self.is_remote = not self.server.startswith("localhost")

    def gen_email(self):
        """Generate email address.

        >>> repo = Repo("rhns.local", user="foo")
        >>> repo.gen_email()
        'foo@rhns.local'
        >>> repo = Repo("rhns.local", user="foo", email_format="%(user)s@example.com")
        >>> repo.gen_email()
        'foo@example.com'
        """
        params = {
            "server": self.server,
            "hostname": self.hostname,
            "user": self.user,
        }
        return self.email_format % params

    def baseurl(self):
        """

        >>> bp = "http://%(server)s/%(topdir)s/%(distdir)s/"
        >>> (s, u, r, d) = ("yum.local", "foo", "repos", "fedora-14") 
        >>> repo = Repo(server=s, user=u, dist=d, repodir=r, baseurl_format=bp)
        >>> repo.topdir
        'foo/repos'
        >>> repo.baseurl()
        'http://yum.local/foo/repos/fedora/14/'
        """
        params = {
            "server": self.server,
            "user": self.user,
            "topdir": self.topdir,
            "distdir": self.distdir,
            # ...: TODO
        }
        return self.baseurl_format % params

    def gen_name(self):
        """Generate repository name.

        >>> repo = Repo("rhns.local", user="foo", dist="rhel-5")
        >>> repo.gen_name()
        'rhel-rhns-foo'
        >>> repo = Repo("rhns.local", user="foo", dist="rhel-5", name_format="%(distname)s-%(user)s")
        >>> repo.gen_name()
        'rhel-foo'
        """
        params = {
            "server": self.server,
            "hostname": self.hostname,
            "user": self.user,
            "dist": self.dist,
            "distname": self.distname,
            "distversion": self.distversion,
            # ...: TODO
        }
        return self.name_format % params

    def copy_cmd(self, src, dst):
        """
        >>> r0 = Repo("localhost.localdomain", "foo")
        >>> c0 = r0.copy_cmd("~/.screenrc", "/tmp")
        >>> 
        >>> r1 = Repo("rhns.local", "foo")
        >>> c1 = r1.copy_cmd("~/.screenrc", "/tmp")
        >>> 
        >>> assert c0 == Command("cp -a ~/.screenrc /tmp", "foo"), c0
        >>> assert c1 == Command("scp -p ~/.screenrc foo@rhns.local:/tmp", "foo"), c1
        """
        if self.is_remote:
            cmd = "scp -p %s %s@%s:%s" % (src, self.user, self.server, dst)
        else:
            cmd = "cp -a %s %s" % (src, dst)

        logging.debug("copy: " + cmd)

        return Command(cmd, self.user)

    def build_cmd(self, srpm, dist):
        """Returns Command object to build src.rpm
        """
        return Command(dist.build_cmd(srpm), self.user, "localhost", os.curdir)

    def seq_run(self, cmds, stop_on_error=True):
        oes = []
        loglevel = logging.getLogger().level

        for c in cmds:
            (o, e) = c.run()
            oes.append((o, e))

            if loglevel < logging.WARNING:
                sys.stdout.write(o)

            ## FIXME: shell() must be fixed to return exitcode along with (o, e)
            ## to implement this behavior correctly.
            #if stop_on_error and e:
            #    logging.error(" Failed: %s,\n error=%s" % (str(c), e))
            #    sys.exit(1)

        return oes

    def dists_by_srpm(self, srpm):
        return (is_noarch(srpm) and self.dists[:1] or self.dists)

    def build(self, srpm):
        cs = [self.build_cmd(srpm, d) for d in self.dists_by_srpm(srpm)]

        return self.seq_run(cs)

    def deploy(self, srpm):
        self.build(srpm)

        destdir = os.path.join(self.deploy_topdir, self.distdir)

        cs = [self.copy_cmd(srpm, os.path.join(destdir, "sources"))]

        for d in self.dists_by_srpm(srpm):
            if is_noarch(srpm):
                rpms = glob.glob("%s/*.noarch.rpm" % d.mockdir())
            else:
                rpms = glob.glob("%s/*.%s.rpm" % (d.mockdir(), d.arch))

            for p in rpms:
                cs.append(self.copy_cmd(p, os.path.join(destdir, d.arch)))

        self.seq_run(cs)

        self.update()

    def deploy_release_rpm(self, workdir=False):
        """Generate (yum repo) release package.

        @workdir str   Working directory
        """
        if not workdir:
            workdir = tempfile.mkdtemp(dir="/tmp", prefix="%s-release-" % self.name)

        dist = self.dists[0]  # this package will be noarch (arch-independent).

        tmpl = """[${repo.name}]
name=Custom yum repository on ${repo.server} by ${repo.user} (\$basearch)
baseurl=${repo.baseurl}\$basearch/
enabled=1
gpgcheck=0

[${repo.name}-source]
name=Custom yum repository on ${repo.server} by ${repo.user} (source)
baseurl=${repo.baseurl}sources/
enabled=0
gpgcheck=0
"""
        params = {"repo": self, "dist": dist}

        c = compile_template(tmpl, params)

        reldir = os.path.join(workdir, "etc", "yum.repos.d")
        f = os.path.join(reldir, "%s.repo" % self.name)

        os.makedirs(reldir)
        open(f, 'w').write(c)

        params["pkg"] = {
            "release_file": f,
            "workdir": workdir,
        }

        tmpl = """echo ${pkg.release_file} | \\
xpack -n ${repo.name}-release --license MIT -w ${pkg.workdir} \\
    --group "System Environment/Base" \\
    --url ${repo.baseurl} \\
    --summary "Yum repo files for ${repo.name}" \\
    --packager "${repo.fullname}" --mail "${repo.email}" \\
    --ignore-owner --pversion ${dist.version}  \\
    --no-rpmdb --no-mock --debug \\
    --destdir ${pkg.workdir} - """

        cmd = Command(compile_template(tmpl, params), self.user)
        cmd.run()

        srpms = glob.glob("%s/%s-release-%s/%s-release*.src.rpm" % (workdir, self.name, dist.version, self.name))
        if not srpms:
            logging.error("Failed to build src.rpm")
            sys.exit(1)

        srpm = srpms[0]

        self.build(srpm)
        self.deploy(srpm)
        self.update()

    def init(self):
        """Initialize yum repository.
        """
        destdir = os.path.join(self.deploy_topdir, self.distdir)

        xs = ["mkdir -p %s" % os.path.join(destdir, d) for d in ["sources"] + self.archs] 
        cs = [Command(c, self.user, self.server, '~') for c in xs]

        self.seq_run(cs)

        self.deploy_release_rpm()

    def update(self):
        """
        "createrepo --update ...", etc.
        """
        destdir = os.path.join(self.deploy_topdir, self.distdir)
        cs = []

        # hack:
        if len(self.archs) > 1:
            c = "for d in %s; do (cd $d && ln -sf ../%s/*.noarch.rpm ./); done" % \
                (" ".join(self.archs[1:]), self.dists[0].arch)
            cs.append(Command(c, self.user, self.server, destdir, stop_on_error=False))

        dirs = [os.path.join(destdir, d) for d in ["sources"] + self.archs]
        c = "test -d repodata && createrepo --update --deltas --database . || createrepo --deltas --database ."

        cs += [Command(c, self.user, self.server, d) for d in dirs]

        return self.seq_run(cs)



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
        confs = (
            "/etc/myreporc",
            os.environ.get("MYREPORC", os.path.join(home, ".myreporc")),
        )
    else:
        confs = (config,)

    cparser = cp.SafeConfigParser()
    loaded = False

    for c in confs:
        if os.path.exists(c):
            logging.debug("Loading config: %s" % c)
            cparser.read(c)
            loaded = True

    if not loaded:
        return {}

    if profile:
        defaults = dict((k, parse_conf_value(v)) for k,v in cparser.items(profile))
    else:
        defaults = cparser.defaults()

    return defaults



class TestFuncsWithSideEffects(unittest.TestCase):

    def setUp(self):
        logging.info("start") # dummy log
        self.workdir = tempfile.mkdtemp(dir="/tmp", prefix="xpack-tests")

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
        assert params["a"] == "aaa"
        assert params["b"] == "bbb"

    def test_init_defaults_by_conffile_config_and_profile_0(self):
        conf = """\
[profile0]
a: aaa
b: bbb
"""
        path = os.path.join(self.workdir, "config")
        open(path, "w").write(conf)

        params = init_defaults_by_conffile(path, "profile0")
        assert params["a"] == "aaa"
        assert params["b"] == "bbb"



def test(verbose):
    doctest.testmod(verbose=verbose)

    (major, minor) = sys.version_info[:2]
    if major == 2 and minor < 5:
        unittest.main(argv=sys.argv[:1])
    else:
        unittest.main(argv=sys.argv[:1], verbosity=(verbose and 2 or 0))


def opt_parser():
    defaults = init_defaults_by_conffile()

    p = optparse.OptionParser("""%prog COMMAND [OPTION ...] [ARGS]

Commands: i[init], b[uild], d[eploy], u[pdate]

Examples:
  # initialize your yum repos:
  %prog init -s yumserver.local -u foo -m foo@example.com -F "John Doe" --repodir "~/public_html/yum"

  # build SRPM:
  %prog build xpack-0.1-1.src.rpm 

  # build SRPM and deploy RPMs and SRPMs into your yum repos:
  %prog deploy --dists fedora-14 xpack-0.1-1.src.rpm 
  %prog d --dists rhel-6 --archs x86_64 xpack-0.1-1.src.rpm 
  """
    )

    for k in ("user", "email", "fullname", "dist", "archs", "repodir", "email_format", "name_format", "baseurl_format"):
        if not defaults.get(k, False):
            defaults[k] = getattr(Repo, k, False)

    defaults["server"] = False
    defaults["name"] = False
    defaults["tests"] = False
    defaults["verbose"] = False
    defaults["debug"] = False

    p.set_defaults(**defaults)

    p.add_option("-C", "--config", help="Configuration file")

    p.add_option("-s", "--server", help="Server to provide your yum repos.")
    p.add_option("-u", "--user", help="Your username on the server [%default]")
    p.add_option("-m", "--email", help="Your email address [%default]")
    p.add_option("", "--email-format", help="Format of email address. If nothing is given with --email, email will be generated w/ using this. [%default]")
    p.add_option("-F", "--fullname", help="Your full name [%default]")
    p.add_option("-R", "--repodir", help="Top directory of your yum repo [%default]")

    p.add_option("-d", "--dist", help="Target distribution name [%default]")
    p.add_option("-A", "--archs", help="Comma separated list of architectures [%default]")

    p.add_option("-q", "--quiet", dest="verbose", action="store_false", help="Quiet mode")
    p.add_option("-v", "--verbose", action="store_true", help="Verbose mode")
    p.add_option("-D", "--debug", action="store_true", help="Debug mode")

    p.add_option("-T", "--test", action="store_true", help="Run test suite")

    iog = optparse.OptionGroup(p, "Options for 'init' command")
    iog.add_option('', "--name", help="Name of your yum repo.")
    iog.add_option('', "--name-format",
        help="Name format of your yum repo name. If nothing is given with --name option, the name will be generated w/ using this. [%default]")
    iog.add_option('', "--baseurl-format", help="Base URL format [%default]")
    p.add_option_group(iog)

    return p


def main():
    (CMD_INIT, CMD_UPDATE, CMD_BUILD, CMD_DEPLOY) = (1, 2, 3, 4)

    p = opt_parser()
    (options, args) = p.parse_args()

    if options.verbose:
        logging.getLogger().setLevel(logging.INFO)
    else:
        logging.getLogger().setLevel(logging.WARNING)

    if options.debug:
        logging.getLogger().setLevel(logging.DEBUG)

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
    elif a0.startswith('d'):
        cmd = CMD_DEPLOY
    else:
        logging.error(" Unknown command '%s'" % a0)
        sys.exit(1)

    if options.config:
        params = init_defaults_by_conffile(options.config)
        p.set_defaults(**params)

        # re-parse to overwrite configurations with given options.
        (options, args) = p.parse_args()

    config = copy.copy(options.__dict__)

    # Kept for DEBUG:
    #pprint.pprint(config)
    #sys.exit()

    if not config.get("server", False):
        config["server"] = raw_input("Server > ")

    if not config.get("dist", False):
        config["dist"] = raw_input("Distribution, e.g. fedora-14 > ")

    config["topdir"] = config["repodir"]

    repo = Repo(**config)
 
    if cmd == CMD_INIT:
        repo.init()

    elif cmd == CMD_UPDATE:
        repo.update()

    else:
        if len(args) < 2:
            logging.error(" 'build' and 'deploy' command requires an argument to specify srpm[s]")
            sys.exit(1)

        if cmd == CMD_BUILD:
            f = repo.build

        elif cmd == CMD_DEPLOY:
            f = repo.deploy

        for srpm in args[1:]:
            f(srpm)


if __name__ == '__main__':
    main()

# vim: set sw=4 ts=4 expandtab:
