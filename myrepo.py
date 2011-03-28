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
# Requirements: createrepo, scp in ssh, xpack (see below)
#
# SEE ALSO: createrepo(8)
# SEE ALSO: https://github.com/ssato/rpmkit/blob/xpack.py
#

from Cheetah.Template import Template
from itertools import chain

import ConfigParser as cp
import copy
import glob
import logging
import multiprocessing
import optparse
import os
import rpm
import subprocess
import sys
import tempfile
import unittest



if os.system('git --version > /dev/null 2> /dev/null') == 0:
    USE_GIT = True
else:
    USE_GIT = False



def concat(xss):
    """
    >>> concat([[]])
    []
    >>> concat([[1,2,3],[4,5]])
    [1, 2, 3, 4, 5]
    """
    return list(chain(*xss))


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


def shell(cmd, workdir="", log=True, dryrun=False):
    """
    @cmd      str   command string, e.g. 'ls -l ~'.
    @workdir  str   in which dir to run given command?
    @log      bool  whether to print log messages or not.
    @dryrun   bool  if True, just print command string to run and returns.
    
    TODO: Popen.communicate might be blocked. How about using Popen.wait
    instead?

    >>> (o, e) = shell('echo "ok" > /dev/null', '.', False)
    >>> assert e == "", 'errmsg=' + e
    >>> 
    >>> try:
    ...    (o, e) = shell('ls /root', '.', False)
    ... except RuntimeError:
    ...    pass
    """
    if not workdir:
        workdir = os.path.abspath(os.curdir)

    logging.debug(" Run: %s [%s]" % (cmd, workdir))

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
        raise RuntimeError(" Failed: %s,\n err:\n'''%s'''" % (cmd, errors))


def rshell(cmd, user, host, workdir, log=True, dryrun=False):
    """
    @user     str  (remote) user to run given command.
    @host     str  on which host to run given command?
    """
    is_remote = not host.startswith('localhost')

    if is_remote:
        cmd = "ssh %s@%s 'cd %s && %s'" % (user, host, workdir, cmd)

    return shell(cmd, workdir='.', log=log, dryrun=dryrun)



class Command(object):

    def __init__(self, cmd, user, host="localhost", workdir=os.curdir, log=True, dryrun=False):
        self.cmd = cmd
        self.user = user
        self.host = host
        self.workdir = workdir
        self.log = log
        self.dryrun = dryrun

    def __str__(self):
        return "%s in %s on %s@%s" % (self.cmd, self.workdir, self.user, self.host)

    def run(self):
        return rshell(self.cmd, self.user, self.host, self.workdir, self.log, self.dryrun)



def shell_recur(cmds=[], res_acc=[]):
    """
    @cmds  [cmd]  A list of Command objects.

    >>> cmds = Command(
    (['ls /dev/null', 'ls /dev/zero'])
    >>> oes = shell_recur(['ls /dev/null', 'ls /dev/zero'])  # :: [(o,e)]
    [("/dev/null", ""), ("/dev/zero", "")]
    """
    if not cmds:
        return res_acc

    try:
        (o,e) = rshell(cmds[0].run)
        return rshell_recur(cmds[1:], res_acc + [(o,e)])

    except RuntimeError, e:
        return res_acc + [(o,e)]


def pshell(cmdss, timeout=60*10):
    """
    @cmds  [[cmd]]  A list of list of Command objects.
    @timeout  int   Timeout to wait for all jobs completed.

    >>> oes = pshell([['ls /dev/null', 'ls /dev/zero'], ['echo OK']])  # :: [(o,e)]
    """
    cpus = multiprocessing.cpu_count()

    n = len(cmdss)
    if n > cpus:
        n = cpus

    logging.debug("# of workers = %d, jobs:\n%s" % \
        (n, "\n\t".join(concat([[str(c) for c in cmds] for cmds in cmdss]))))

    results = multiprocessing.Pool(n).apply_async(rshell_recur, cmdss)
    return results.get(timeout=timeout)


def rm_rf(dir):
    """'rm -rf' in python.

    >>> d = tempfile.mkdtemp(dir='/tmp')
    >>> rm_rf(d)
    >>> rm_rf(d)
    >>> 
    >>> d = tempfile.mkdtemp(dir='/tmp')
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

    assert dir != '/'                    # avoid 'rm -rf /'
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
    return os.environ.get('USER', False) or os.getlogin()


def get_mail(use_git=USE_GIT):
    if use_git:
        try:
            (email, e) = shell('git config --get user.email 2>/dev/null')
            if not e:
                return email
        except RuntimeError, e:
            logging.warn(str(e))
            pass

    return os.environ.get('MAIL_ADDRESS', False) or "%s@localhost.localdomain" % get_username()


def get_fullname(use_git=USE_GIT):
    """Get full name of the user.
    """
    if use_git:
        try:
            (fullname, e) = shell('git config --get user.name 2>/dev/null')
            if not e:
                return fullname
        except RuntimeError, e:
            logging.warn(str(e))
            pass

    return os.environ.get('FULLNAME', False) or get_username()


def rpm_header_from_rpmfile(rpmfile):
    """Read rpm.hdr from rpmfile.
    """
    return rpm.TransactionSet().hdrFromFdno(open(rpmfile, "rb"))


def is_noarch(srpm):
    """Determine if given srpm is noarch (arch-independent).
    """
    return h[rpm.RPMTAG_ARCH] == 'noarch'



class TestFuncsWithSideEffects(unittest.TestCase):

    def setUp(self):
        logging.info("start") # dummy log
        self.workdir = tempfile.mkdtemp(dir='/tmp', prefix='xpack-tests')

    def tearDown(self):
        rm_rf(self.workdir)



class Distribution(object):

    def __init__(self, dist):
        self.label = dist
        (self.name, self.version, self.arch) = self.parse(dist)

        self.deploy_srpm = False
        self.symlink = False

    @classmethod
    def parse(self, dist):
        """
        >>> Distribution.parse('fedora-14-x86_64')
        ['fedora', '14', 'x86_64']
        """
        return dist.split('-')

    def mockdir(self):
        """
        >>> d = Distribution('fedora-14-x86_64')
        >>> d.mockdir()
        '/var/lib/mock/fedora-14-x86_64/result'
        """
        return "/var/lib/mock/%s/result" % self.label

    def build_cmd(self, srpm):
        return "mock -r %s %s" % (self.label, srpm)



class Repo(object):
    """Yum repository.
    """

    server = 'localhost'
    user = get_username()
    mail = get_mail()
    fullname  = get_fullname()
    dir = '~/public_html/yum'
    dist = 'fedora-14-x86_64'

    baseurl = "http://%s/%s/%s/%s" % (server, user, \
        dir.split(os.path.sep)[-1], os.path.sep.join(dist.split('-')[:2]))

    name = "%s-%s-%s" % (dist.split('-')[0], server.split('.')[0], user)

    def __init__(self, server=None, user=None, mail=None,
                    fullname=None, baseurl=None, name=None,
                    dir=None, dist=None,
                    *args, **kwargs):
        """
        @server    server's fqdn to provide this yum repo via http
        @user      your username on the server
        @mail      your mail address
        @fullname  your full name.
        @baseurl   base url, e.g. 'http://yum-server.example.com/foo/yum/fedora/14/'.
        @name      repository name, e.g. 'rpmfusion-free'
        @dir       repo topdir, e.g. ~/public_html/yum/.
        @dist      distribution string, e.g. 'fedora-14-x86_64'
        """
        if server is not None:
            self.server = server

        if user is not None:
            self.user = user

        if mail is not None:
            self.mail = mail

        if fullname is not None:
            self.fullname = fullname

        if dist is not None:
            self.dist = Distribution(dist)
        else:
            self.dist = Distribution(Repo.dist)

        if baseurl is None:
            self.baseurl = "http://%s/%s/yum/%s/%s/" % \
                (self.server, self.user, self.dist.name, self.dist.version)
        else:
            self.baseurl = baseurl

        if name is None:
            self.name = "%s-%s-%s" % (self.dist.name, self.server.split('.')[0], self.user)
        else:
            self.name = name

        if dir is None:
            dir = Repo.dir

        self.topdir = os.path.join(dir, self.dist.name, self.dists.version)
        self.is_remote = not self.server.startswith('localhost')

    def copy_cmd(self, src, dst):
        if self.is_remote:
            cmd = "scp -p %s %s@%s:%s" % (src, self.user, self.server, dst)
        else:
            cmd = "cp -a %s %s" % (src, dst)

        return cmd

    def build_cmd(self, srpm):
        return self.dist.build_cmd(srpm)

    def deploy_cmds(self, srpm):
        mockdir = self.dist.mockdir()
        arch = self.dist.arch
        repodir = self.topdir

        cmds = []

        if d.deploy_srpm:
            srpm = glob.glob("%s/*.src.rpm" % mockdir)[0]  # FIXME
            cmd = self.copy_cmd(srpm, os.path.join(repodir, "sources"))
            cmds.append(cmd)

        for _rpm in glob.glob("%s/*.noarch.rpm" % mockdir) + glob.glob("%s/*.%s.rpm" % (mockdir, arch)):
            cmd = self.copy_cmd(_rpm, os.path.join(repodir, arch))
            cmds.append(cmd)

        return cmds

    def deploy_release_package_cmds(self,
            workdir=tempfile.mkdtemp(dir='/tmp', prefix='yum-repo-release-'),
            tmpl=None):
        """Generate (yum repo) release package.

        @tmpl     str   Template string
        """
        cmds = []

        if tmpl is None:
            tmpl = """
[${repo.name}]
name=Custom yum repository on ${repo.server} by ${repo.user} (${repo.dist.label})
baseurl=${repo.baseurl}/${repo.dist.arch}/
enabled=1
gpgcheck=0

[${repo.name}-source]
name=Custom yum repository on ${repo.server} by ${repo.user} (${repo.dist.label} source)
baseurl=${repo.baseurl}/sources/
enabled=0
gpgcheck=0
"""
        params = {'repo': self}

        c = compile_template(tmpl, params)

        reldir = os.path.join(workdir, 'etc', 'yum.repos.d')
        f = os.path.join(reldir, "%s.repo" % self.name)

        os.makedirs(reldir)
        open(f, 'w').write(c)

        self.release_file = f
        self.workdir = workdir

        tmpl = """echo ${repo.release_file} | \
xpack -n ${repo.name}-release --license MIT -w ${repo.workdir} \
    --group "System Environment/Base" \
    --url ${repo.baseurl} \
    --summary "Yum repo files for ${repo.name}" \
    --packager "${repo.fullname}" --mail ${repo.mail} \
    --ignore-owner --pversion ${repo.dist.version}  \
    --no-rpmdb --no-mock --upto sbuild --debug \
    --destdir ${repo.workdir} - """

        cmd = compile_template(tmpl, params)
        cmds.append(cmd)

        srpm = "%s/%s-%s/%s-release*.src.rpm" % (workdir, self.name, self.dist.version, self.name)
        cmd = self.copy_cmd(srpm, os.path.join(self.topdir, "sources"))
        cmds.append(cmd)

        return cmds



class LazyRepoCommands(object):

    def __init__(self, repos=[]):
        """
        @repos  [Repo]  Repository objects
        """
        self.repos = repos

        # These must be the same among repos.
        self.server = self.repos[0].server
        self.user = self.repos[0].user
        self.mail = self.repos[0].mail
        self.fullname = self.repos[0].fullname
        self.baseurl = self.repos[0].baseurl
        self.name = self.repos[0].name
        self.topdir = self.repos[0].topdir
        self.is_remote = self.repos[0].is_remote

        self.archs = [repo.dist.arch for repo in self.repos]

    def make_Commands(self, cmds, host=None):
        (h, w) = host is None and (self.server, '~') or (host, os.curdir)

        return [Command(cmd, self.user, h, w) for cmd in cmds]

    def init(self):
        """
        @return  [Command]  Command objects to initialize these repos.
        """
        cmds = ["mkdir -p %s" % os.path.join(self.topdir, 'sources')] + \
            ["mkdir -p %s" % os.path.join(self.topdir, arch) for arch in self.archs]

        rcs = self.make_Commands(cmds)  # remote
        lcs = self.make_Commands([repo.deploy_release_package_cmds() for repo in self.repos], 'localhost')
        
        return rcs + lcs

    def update(self):
        """
        'createrepo --update ...', etc.
        """
        cfmt = "test -d %(d)s/repodata && createrepo --update --deltas %(d)s || createrepo --deltas %(d)s"
        cmds = [cfmt % {'d': os.path.join(self.topdir, d)} for d in ['sources'] + self.archs]

        # hack:
        if 'i386' in self.archs and 'x86_64' in self.archs:
            cmds.append("cd %s/i386 && ln -sf ../x86_64/*.noarch.rpm ./" % self.topdir)

        return self.make_Commands(cmds)

    def build(self, srpm):
        return self.make_Commands((r.build_cmd(srpm) for r in self.repos), 'localhost')

    def deploy(self, srpm):
        return self.make_Commands(concat([r.deploy_cmds(srpm) for r in self.repos]))



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


def init_defaults_by_conffile(profile=None):
    """
    Initialize default values for options by loading config files.
    """
    home = os.environ.get("HOME", os.curdir) # Is there case that $HOME is empty?
    confs = (
        "/etc/myreporc",
        os.environ.get("MYREPORC", os.path.join(home, ".myreporc")),
    )

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


def opt_parser():
    defaults = init_defaults_by_conffile()

    p = optparse.OptionParser("""%prog COMMAND [OPTION ...] [ARGS]

Commands: i[init], b[uild], d[eploy]

Examples:
  # initialize your yum repos:
  %prog init -s yumserver.local -u foo -m foo@example.com -F "John Doe" --repodir "~/public_html/yum"

  # build SRPM:
  %prog build xpack-0.1-1.src.rpm 

  # build SRPM and deploy RPMs and SRPMs into your yum repos:
  %prog deploy --dist fedora-14 xpack-0.1-1.src.rpm 
  %prog d --dist rhel-6 --archs x86_64 xpack-0.1-1.src.rpm 
  """
    )

    if not defaults.get('server'):
        defaults['server'] = Repo.server

    if not defaults.get('uesr'):
        defaults['user'] = Repo.user

    if not defaults.get('mail'):
        defaults['mail'] = Repo.mail

    if not defaults.get('fullname'):
        defaults['fullname'] = Repo.fullname

    if not defaults.get('repodir'):
        defaults['repodir'] = Repo.dir

    defaults['dists'] = Repo.dist
    defaults['tests'] = False
    defaults['name'] = Repo.name
    defaults['no_release_pkg'] = False
    defaults['verbose'] = True

    if not defaults.get('baseurl'):
        defaults['baseurl'] = Repo.baseurl

    p.set_defaults(**defaults)

    p.add_option('-s', '--server', help='Server to provide your yum repos [%default]')
    p.add_option('-u', '--user', help='Your username on the server [%default]')
    p.add_option('-m', '--mail', help='Your mail address [%default]')
    p.add_option('-F', '--fullname', help='Your full name [%default]')
    p.add_option('-R', '--repodir', help='Top directory of your yum repo [%default]')

    p.add_option('-d', '--dists', help='Target distribution name [%default]')

    p.add_option('-q', '--quiet', dest="verbose", action='store_false', help='Quiet mode')
    p.add_option('-v', '--verbose', action='store_true', help='Verbose mode')

    p.add_option('-T', '--tests', action='store_true', help='Run test suite')

    iog = optparse.OptionGroup(p, "Options for 'init' command")
    iog.add_option('', '--name', help='Name of your yum repo. ')
    iog.add_option('', '--baseurl', help='Base url of your yum repo [%default]')
    iog.add_option('', '--no-release-pkg', action='store_true',
        help='Do not build release package contains yum repo files')
    p.add_option_group(iog)

    return p


def main(argv=sys.argv[1:]):
    (CMD_INIT, CMD_UPDATE, CMD_BUILD, CMD_DEPLOY) = (1,2,3,4)

    p = opt_parser()

    if not argv:
        p.print_usage()
        sys.exit(1)

    if argv[0].startswith('-h') or argv[0].startswith('--h'):
        p.print_help()
        sys.exit(0)

    a0 = argv[0]
    if a0.startswith('i'):
        cmd = CMD_INIT 
    elif a0.startswith('b'):
        cmd = CMD_BUILD
    elif a0.startswith('d'):
        cmd = CMD_DEPLOY
    else:
        logging.error(" Unknown command '%s'" % a0)
        sys.exit(1)

    (options, args) = p.parse_args(argv[1:])

    config = copy.copy(options.__dict__)

    if not options.dist:
        config['dist'] = raw_input("Distribution > ")

    if not options.name:
        config['name'] = raw_input("Repository name > ")

    config['topdir'] = config['repodir']

    repos = [Repo(dist=d, **config) for d in config['dists']]
    repocmds = LazyRepoCommands(repos)
 
    multiprocessing.log_to_stderr()
    logger = multiprocessing.get_logger()

    if options.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.INFO)
    else:
        logging.getLogger().setLevel(logging.WARNING)
        logger.setLevel(logging.WARNING)

    if cmd == CMD_INIT:
        cs = repocmds.init()
        shell_recur(cs)

    elif cmd == CMD_UPDATE:
        cs = repocmds.update()
        shell_recur(cs)

    else:
        if not args:
            logging.error(" 'build' and 'deploy' command requires an argument to specify srpm")
            sys.exit(1)

        if cmd == CMD_DEPLOY:
            f = repocmds.build

        elif cmd == CMD_DEPLOY:
            f = repocmds.deploy

        cs = [f(srpm) for srpm in args]
        shell_recur(cs)


if __name__ == '__main__':
    main()

# vim: set sw=4 ts=4 expandtab:
