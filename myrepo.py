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

import ConfigParser as cp
import copy
import glob
import logging
import multiprocessing
import optparse
import os
import subprocess
import sys



def zip3(xs, ys, zs):
    """
    >>> zip3([0,3],[1,4],[2,5])
    [(0, 1, 2), (3, 4, 5)]
    """
    return [(x,y,z) for (x,y),z in zip(zip(xs, ys), zs)]


def shell(cmd_s, workdir="", log=True, dryrun=False):
    """
    @cmd_s    str  command string, e.g. 'ls -l ~/public_html/yum/'.
    @workdir  str  in which dir to run given command?
    @log      bool whether to print log messages or not.
    @dryrun   bool if True, just print command string to run and returns.
    
    TODO: Popen.communicate might be blocked. How about using Popen.wait
    instead?

    >>> (o, e) = shell('echo "ok" > /dev/null', '.', False)
    >>> assert o == "", 'out=' + o
    >>> assert e == "", 'errmsg=' + e
    >>> 
    >>> try:
    ...    (o, e) = shell('ls /root', '.', False)
    ... except RuntimeError:
    ...    pass
    """
    if not workdir:
        workdir = os.path.abspath(os.curdir)

    logging.debug(" Run: %s [%s]" % (cmd_s, workdir))

    if dryrun:
        logging.info(" exit as we're in dry run mode.")
        return ("", "")

    try:
        pipe = subprocess.Popen([cmd_s], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, cwd=workdir)
        (output, errors) = pipe.communicate()
    except Exception, e:
        # NOTE: e.message looks not available in python < 2.5:
        #raise RuntimeError("Error (%s) during executing: %s" % (repr(e.__class__), e.message))
        raise RuntimeError("Error (%s) during executing: %s" % (repr(e.__class__), str(e)))

    if pipe.returncode == 0:
        return (output, errors)
    else:
        raise RuntimeError(" Failed: %s,\n err:\n'''%s'''" % (cmd_s, errors))


def rshell(self, cmd, user, host, workdir, log=True, dryrun=False):
    """
    @user     str  (remote) user to run given command.
    @host     str  on which host to run given command?
    """
    is_remote = not host.startswith('localhost')

    if is_remote:
        cmd = "ssh %s@%s 'cd %s && %s'" % (user, host, workdir, cmd)

    return shell(cmd, workdir='.', log=log, dryrun=dryrun)


def pshell(cmds):
    """
    @cmds  [str]  A list of string represents commands to run.

    >>> oes = pshell(['ls /dev/null', 'ls /dev/zero'])  # :: [(o,e)]
    """
    cpus = multiprocessing.cpu_count()
    n = len(cmds)
    if n > cpus:
        n = cpus

    logging.debug("# of workers = %d, jobs:\n%s" % (n, "\n\t".join(cmds)))

    return multiprocessing.Pool(n).map_async(shell, cmds)



class Repo(object):
    """Yum repository.
    """

    def __init__(self, server, user, mail, fullname, topdir, dist, archs):
        self.server = server
        self.user = user
        self.mail = mail
        self.fullname = fullname
        self.archs = archs.split(',')

        (self.dist_name, self.dist_version) = dist.split('-')
        self.topdir = os.path.join(topdir, self.dist_name, self.dist_version)

        self.is_remote = not self.server.startswith('localhost')

    def _copy_cmd(self, src, dst):
        """
        """
        if self.is_remote:
            cmd = "scp -p %s %s@%s:%s" % (src, self.user, self.server, dst)
        else:
            cmd = "cp -a %s %s" % (src, dst)

        return cmd

    def _build_cmd(self, arch, srpm):
        return "mock -r %s-%s-%s %s" % (self.dist_name, self.dist_version, arch, srpm)

    def _build_cmds(self, srpm):
        return [self._build_cmd(arch, srpm) for arch in self.archs]

    def _deploy_cmds(self, arch, srpm):
        mockdir = "/var/lib/mock/%s-%s-%s/result" % (self.dist_name, self.dist_version, arch)
        repodir = self.topdir

        cmds = []

        srpm = glob.glob("%s/*.src.rpm" % mockdir)[0]
        srpm_dst = os.path.join(repodir, "sources")
        cmd = self._copy_cmd(srpm, srpm_dst)
        cmds.append(cmd)

        for _rpm in glob.glob("%s/*.noarch.rpm" % mockdir) + glob.glob("%s/*.%s.rpm" % (mockdir, arch)):
            cmd = self._copy_cmd(_rpm, os.path.join(repodir, arch))
            cmds.append(cmd)

        return cmds

    def _deploy(self, arch, srpm):
        return pshell(self._deploy_cmds(arch, srpm))

    def init(self):
        uhw = (self.user, self.server, self.workdir)

        rshell("mkdir -p " + os.path.join(self.topdir, 'sources'), *uhw)
        for arch in self.archs:
            rshell("mkdir -p " + os.path.join(self.topdir, arch), *uhw)

    def update(self):
        """
        Same as 'createrepo --update ...'.
        """
        uhw = (self.user, self.server, self.workdir)
        subdirs = ['sources'] + self.archs

        # hack:
        if 'i386' in self.archs and 'x86_64' in self.archs:
            rshell("cd %s/i386 && ln -sf ../x86_64/*.noarch.rpm ./" % self.topdir)

        cfmt = "test -d %(d)s/repodata && createrepo --update --deltas %(d)s || createrepo --deltas %(d)s"
        pshell([cfmt % {'d': os.path.join(self.topdir, subdir)} for subdir in subdirs])

    def build(self, srpm):
        return pshell(self._build_cmds(srpm))

    def deploy(self, srpm):
        """
        TODO: Nesting pshell calls?
        """
        for arch in self.archs:
            oes = self._deploy(srpm)

            for oe in oes:
                if e != "":  # indicates any error.
                    raise RuntimeError(" out=%s, errmsg=%s" % (o,e))



def get_username():
    """
    Get username.
    """
    return os.environ.get('USER', False) or os.getlogin()


def get_mail():
    return os.environ.get('MAILADDRESS', False) or "%s@localhost.localdomain" % get_username()


def get_fullname():
    """
    Get full name of the user.
    """
    return os.environ.get('FULLNAME', False) or get_username()


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
  %prog deploy xpack-0.1-1.src.rpm 
  %prog d --dists fedora-14,rhel-6 --arch i386,x86_64 xpack-0.1-1.src.rpm 
  """
    )

    if not defaults.get('server'):
        defaults['server'] = 'localhost'

    if not defaults.get('uesr'):
        defaults['user'] = get_username()

    if not defaults.get('mail'):
        defaults['mail'] = get_mail()

    if not defaults.get('fullname'):
        defaults['fullname'] = get_fullname()

    if not defaults.get('repodir'):
        defaults['repodir'] = "~/public_html/yum"

    defaults['dist'] = ""
    defaults['archs'] = "i386,x86_64"
    defaults['tests'] = False
    defaults['reponame'] = ""
    defaults['no_release_pkg'] = False

    p.set_defaults(**defaults)

    p.add_option('-s', '--server', help='Server to provide your yum repos [%default]')
    p.add_option('-u', '--user', help='Your username on the server [%default]')
    p.add_option('-m', '--mail', help='Your mail address [%default]')
    p.add_option('-F', '--fullname', help='Your full name [%default]')
    p.add_option('-R', '--repodir', help='Top directory of your yum repo [%default]')

    p.add_option('-D', '--dist', help='Target distribution name [%default]')
    p.add_option('-A', '--archs', help='Comma separated list of target architecures [%default]')

    p.add_option('-T', '--tests', action='store_true', help='Run test suite')

    iog = optparse.OptionGroup(p, "Options for 'init' command")
    iog.add_option('', '--reponame', help='Name of your yum repo. ')
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

    multiprocessing.log_to_stderr()
    logger = multiprocessing.get_logger()
    logger.setLevel(logging.INFO)

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

    if not options.reponame:
        config['reponame'] = raw_input("Repository name > ")

    config['topdir'] = config['repodir']

    repo = Repo(**config)

    if cmd == CMD_INIT:
        repo.init()

    elif cmd == CMD_UPDATE:
        repo.update()

    else:
        if not args:
            logging.error(" 'build' and 'deploy' command requires an argument to specify srpm")
            sys.exit(1)

        if cmd == CMD_DEPLOY:
            f = repo.build

        elif cmd == CMD_DEPLOY:
            f = repo.deploy

        for srpm in args:
            f(srpm)


if __name__ == '__main__':
    main()

# vim: set sw=4 ts=4 expandtab:
