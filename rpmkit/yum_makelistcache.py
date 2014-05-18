#
# Make caches of various yum 'list' command execution results.
#
# Copyright (C) 2014 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato@redhat.com>
#
# This software is licensed to you under the GNU General Public License,
# version 3 (GPLv3). There is NO WARRANTY for this software, express or
# implied, including the implied warranties of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. You should have received a copy of GPLv3 along with this
# software; if not, see http://www.gnu.org/licenses/gpl.html
#
"""Make caches of various yum 'list' command execution results.

Usage:
    su - apache -c 'yum_makelistcache [Options ...] ...'
"""
from __future__ import print_function

import ConfigParser as configparser
import bsddb
import glob
import logging
import operator
import optparse
import os.path
import os
import re
import subprocess
import sys
import yum

try:
    import json
except ImportError:
    import simplejson as json


NAME = "yum_makelistcache"

logging.basicConfig(format="%(asctime)-15s [%(levelname)s] %(message)s")

LOG = logging.getLogger(NAME)
LOG.addHandler(logging.StreamHandler())

_RPM_DB_FILENAMES = ["Basenames", "Name", "Providename", "Requirename"]
_RPM_KEYS = ("nevra", "name", "epoch", "version", "release", "arch")


def _is_bsd_hashdb(dbpath):
    """
    FIXME: Is this enough to check if given file ``dbpath`` is RPM DB file ?
    """
    try:
        bsddb.hashopen(dbpath, 'r')
    except:
        return False

    return True


def _rpmdb_files_exist(path, rpmdb_filenames=_RPM_DB_FILENAMES):
    """
    :param path: RPM DB path
    """
    return all(os.path.exists(os.path.join(path, f)) for f in rpmdb_filenames)


def logpath(root, basename):
    return os.path.join(root, "var/log", basename)


def setup_root(root, readonly=True):
    """
    :param root: The pivot root directry where target's RPM DB files exist.
    :param readonly: Ensure RPM DB files readonly.
    :return: True if necessary setup was done w/ success else False
    """
    assert root != "/",  "Do not run this for host system's RPM DB!"

    rpmdbdir = os.path.join(root, "var/lib/rpm")

    if not os.path.exists(rpmdbdir):
        LOG.error("RPM DB dir %s does not exist!" % rpmdbdir)
        return False

    pkgdb = os.path.join(rpmdbdir, "Packages")
    if not _is_bsd_hashdb(pkgdb):
        LOG.error("%s does not look a RPM DB (Packages) file!" % pkgdb)
        return False

    if not _rpmdb_files_exist(rpmdbdir):
        LOG.error("Some RPM DB files look missing! Check it.")
        return False

    if readonly:
        for f in glob.glob("/var/lib/rpm/[A-Z]*"):
            if os.access(f, os.W_OK):
                LOG.warn("Drop write access perm. to %s" % f)
                os.chmod(f, 0o644)

    logdir = os.path.dirname(logpath(root, "list.log"))
    if not os.path.exists(logdir):
        os.makedirs(logdir)

    return True


def noop(*args, **kwargs):
    pass


def _toggle_repos(base, repos_to_act, act="enable"):
    for repo_match in repos_to_act:
        for repo in base.repos.findRepos(repo_match):
            getattr(repo, act, noop)()


def _activate_repos(base, enablerepos=[], disablerepos=['*']):
    _toggle_repos(base, disablerepos, "disable")
    _toggle_repos(base, enablerepos, "enable")


def yum_list(root, pkgnarrow="installed", enablerepos=[], disablerepos=['*'],
             keys=_RPM_KEYS):
    """
    List installed or update RPMs similar to
    "repoquery --pkgnarrow=updates --all --plugins --qf '%{nevra}'".

    :param root: RPM DB root dir in absolute path
    :param pkgnarrow: Packages list narrowing type
    :param enablerepos: List of Yum repos to enable
    :param disablerepos: List of Yum repos to disable
    :param key: List of key names to construct dict contais RPM info

    :return: List of dicts contain RPM info
    """
    base = yum.YumBase()
    base.preconf.root = root
    base.logger = base.verbose_logger = LOG
    _activate_repos(base, enablerepos, disablerepos)

    if pkgnarrow != "installed":
        base.repos.populateSack()

    ygh = base.doPackageLists(pkgnarrow)

    if pkgnarrow == "all":
        ps = ygh.available + ygh.installed
    elif hasattr(ygh, pkgnarrow):
        ps = getattr(ygh, pkgnarrow)
    else:
        LOG.error("Unknown pkgnarrow: %s" % pkgnarrow)
        ps = []

    return [dict((k, getattr(p, k, None)) for k in keys) for p in ps]


def _reg_by_dist(dist="rhel"):
    return re.compile(r"^FEDORA-" if dist == "fedora" else r"^RH[SBE]A-")


_RH_ERRATA_REG = _reg_by_dist("rhel")


def _is_errata_line(line, reg=_RH_ERRATA_REG):
    """
    >>> ls = [
    ...   "FEDORA-2014-6068 security    cifs-utils-6.3-2.fc20.x86_64",
    ...   "updates/20/x86_64/pkgtags              | 1.0 MB  00:00:03",
    ...   "This system is receiving updates from RHN Classic or RHN ...",
    ...   "RHSA-2013:1732  Low/Sec.    busybox-1:1.15.1-20.el6.x86_64",
    ...   "RHEA-2013:1596  enhancement "
    ...   "ca-certificates-2013.1.94-65.0.el6.noarch",
    ... ]
    >>> _is_errata_line(ls[0], _reg_by_dist("fedora"))
    True
    >>> _is_errata_line(ls[1], _reg_by_dist("fedora"))
    False
    >>> _is_errata_line(ls[2])
    False
    >>> _is_errata_line(ls[3])
    True
    >>> _is_errata_line(ls[4])
    True
    """
    return bool(line and reg.match(line))


def __parse_errata_type(type_s, sep="/"):
    """
    Parse errata type string in the errata list by 'yum list-sec'.

    :param type_s: Errata type string in the errata list
    :return: (errata_type, errata_severity)
        where severity is None if errata_type is not 'Security'.

    >>> __parse_errata_type("Moderate/Sec.")
    ('Security', 'Moderate')
    >>> __parse_errata_type("bugfix")
    ('Bugfix', None)
    >>> __parse_errata_type("enhancement")
    ('Enhancement', None)
    """
    if sep in type_s:
        return ("Security", type_s.split(sep)[0])
    else:
        return (type_s.title(), None)


_RPM_ARCHS = ("i386", "i586", "i686", "x86_64", "ppc", "ia64", "s390",
              "s390x", "noarch")


def parse_errata_line(line, archs=_RPM_ARCHS, ev_sep=':'):
    """
    Parse a line in the output of 'yum list-sec'.

    See also: The format string '"%(n)s-%(epoch)s%(v)s-%(r)s.%(a)s"' at the
    back of UpdateinfoCommand.doCommand_li in /usr/lib/yum-plugins/security.py

    >>> ls = [
    ...   "RHSA-2013:0587 Moderate/Sec.  openssl-1.0.0-27.el6_4.2.x86_64",
    ...   "RHBA-2013:0781 bugfix         perl-libs-4:5.10.1-131.el6_4.x86_64",
    ...   "RHBA-2013:0781 bugfix         perl-version-3:0.77-131.el6_4.x86_64",
    ...   "RHEA-2013:0615 enhancement    tzdata-2012j-2.el6.noarch",
    ... ]
    >>> xs = [parse_errata_line(l) for l in ls]

    >>> [(x["advisory"], x["type"],  # doctest: +NORMALIZE_WHITESPACE
    ...   x["severity"]) for x in xs]
    [('RHSA-2013:0587', 'Security', 'Moderate'),
     ('RHBA-2013:0781', 'Bugfix', None),
     ('RHBA-2013:0781', 'Bugfix', None),
     ('RHEA-2013:0615', 'Enhancement', None)]

    >>> [(x["name"], x["epoch"],  # doctest: +NORMALIZE_WHITESPACE
    ...   x["version"], x["release"], x["arch"]) for x in xs]
    [('openssl', '0', '1.0.0', '27.el6_4.2', 'x86_64'),
     ('perl-libs', '4', '5.10.1', '131.el6_4', 'x86_64'),
     ('perl-version', '3', '0.77', '131.el6_4', 'x86_64'),
     ('tzdata', '0', '2012j', '2.el6', 'noarch')]

    """
    (advisory, type_s, pname) = line.rstrip().split()
    (etype, severity) = __parse_errata_type(type_s)

    (rest, arch) = pname.rsplit('.', 1)
    assert arch and arch in archs, \
        "no or invalid arch string found in package name: " + pname

    (name, ev, release) = rest.rsplit('-', 2)

    if ev_sep in ev:
        (epoch, version) = ev.split(ev_sep)
    else:
        epoch = '0'
        version = ev

    return dict(advisory=advisory, type=etype, severity=severity,  # Errata
                name=name, epoch=epoch, version=version,  # RPM package
                release=release, arch=arch)


def _run(cmd, output=None, curdir=os.curdir):
    """
    :param cmd: List of command strings :: [str]
    :param output: Path to the file to save command outputs
    :param curdir: Current dir to run command

    :return: (returncode :: int, error_message :: str)

    >>> (rc, err) = _run("timeout 10 ls /".split())
    >>> rc == 0, err
    (True, '')

    >>> (rc, err) = _run("timeout 1 sleep 10".split())
    >>> rc == 0, bool(err)
    (False, True)
    """
    LOG.info("Run '%s' in %s" % (' '.join(cmd), curdir))
    try:
        if output:
            with open(output, 'w') as f:
                subprocess.check_call(cmd, cwd=curdir, stdout=f,
                                      stderr=subprocess.PIPE)
        else:
            subprocess.check_call(cmd, cwd=curdir, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
        return (0, '')
    except subprocess.CalledProcessError as exc:
        return (exc.returncode, str(exc))


def list_errata_g(root, opts=[], dist=None):
    """
    A generator to return errata found in the output result of 'yum list-sec'
    one by one.

    :param root: Pivot root dir where var/lib/rpm/ exist.
    :param opts: Extra options for yum, e.g. "--enablerepo='...' ..."
    :param dist: Distribution name or None
    """
    cs = ["yum", "--installroot=" + root] + opts + ["list-sec"]
    output = logpath(root, "yum_list-sec.log")

    (rc, err) = _run(cs, output)

    if rc == 0:
        lines = open(output).readlines()
        reg = _reg_by_dist()

        for line in lines:
            if _is_errata_line(line, reg):
                LOG.debug("Errata line: " + line)
                yield parse_errata_line(line)
            else:
                LOG.debug("Not errata line: " + line)
    else:
        LOG.error("Failed to fetch the errata list: " + err)


def _mk_repo_opts(enablerepos, disablerepos):
    """
    :note: Take care of the order of disabled and enabled repos.
    """
    return ["--disablerepo='%s'" % repo for repo in disablerepos] + \
           ["--enablerepo='%s'" % repo for repo in enablerepos]


def yum_list_errata(root, enablerepos=[], disablerepos=['*']):
    """
    List errata similar to "yum list-sec".

    :param root: RPM DB root dir in absolute path
    :param enablerepos: List of Yum repos to enable
    :param disablerepos: List of Yum repos to disable

    :return: List of dicts contain each errata info
    """
    opts = _mk_repo_opts(enablerepos, disablerepos)
    return list(list_errata_g(root, opts))


def _is_root():
    return os.getuid() == 0


def yum_download(root, enablerepos=[], disablerepos=['*']):
    """
    List errata similar to "yum list-sec".

    :param root: RPM DB root dir in absolute path
    :param enablerepos: List of Yum repos to enable
    :param disablerepos: List of Yum repos to disable

    :return: List of dicts contain each errata info
    yum update -y --downloadonly
    """
    opts = _mk_repo_opts(enablerepos, disablerepos)

    cs = [] if _is_root() else ["fakeroot"]  # avoid unneeded check.
    cs += ["yum", "--installroot=" + root] + opts + ["--downloadonly",
                                                     "update", "-y"]

    output = logpath(root, "yum_download.log")

    (rc, err) = _run(cs, output)

    if rc == 0:
        LOG.info("Download: OK")
    else:
        LOG.error("Failed to download udpates: " + err)


DEFAULT_OUT_KEYS = dict(errata=["advisory", "type", "severity", "name",
                                "epoch", "version", "release", "arch"],
                        default=_RPM_KEYS)


def load_conf(conf_path, sect="main"):
    cp = configparser.SafeConfigParser()
    try:
        cp.read(conf_path)
        return dict(cp.items(sect))
    except Exception as e:
        LOG.warn("Failed to load '%s': %s" % (conf_path, str(e)))

    return dict()


def outputs_result(result, root, restype="updates", keys=[]):
    """
    :param result: A list of result dicts :: [dict]
    :param root: Log root dir
    :param restype: Result type
    :param keys: CSV headers
    """
    if not keys:
        keys = DEFAULT_OUT_KEYS.get(restype, DEFAULT_OUT_KEYS["default"])

    result = sorted(result, key=operator.itemgetter(keys[0]))

    with open(logpath(root, restype + ".json"), 'w') as f:
        json.dump(dict(data=result, ), f)

    with open(logpath(root, restype + ".csv"), 'w') as f:
        if not keys:
            keys = DEFAULT_OUT_KEYS.get(restype, DEFAULT_OUT_KEYS["default"])

        f.write(','.join(keys) + '\n')
        for d in result:
            vals = [d.get(k, False) for k in keys]
            f.write(','.join(v for v in vals if v) + '\n')


_USAGE = """%prog [Options] COMMAND

Commands:
  l[ist]       List installed (default) or update (-L/--list-type updates)
               RPMs, or errata (-L/--list-type errata)
  d[ownload]   Download update RPMs

Examples:
  # Save installed rpms list, similar to 'yum list installed':
  %prog --disablerepo='*' --enablerepo='rhel-x86_64-server-6' \\
     --root=/var/lib/yum_makelistcache/root.d/aaa list

  # Save updates list, similar to 'yum check-update':
  %prog --disablerepo='*' --enablerepo='rhel-x86_64-server-6' \\
     --root=/var/lib/yum_makelistcache/root.d/aaa l -L updates

  # Save update RPMs, similar to 'yum update --downloadonly':
  %prog --disablerepo='*' --enablerepo='rhel-x86_64-server-6' \\
     --root=/var/lib/yum_makelistcache/root.d/aaa d
"""

_COMMANDS = dict(l="list", d="download")
_LIST_TYPES = (LIST_INSTALLED, LIST_UPDATES, LIST_ERRATA) \
            = ("installed", "updates", "errata")
_DEFAULTS = dict(root=os.curdir, log=False, dist="rhel",
                 list_type=LIST_INSTALLED,
                 enablerepo=[], disablerepo=[], conf=None, verbose=False)


def option_parser(usage=_USAGE, defaults=_DEFAULTS, cmds=_COMMANDS):
    """
    :param usage: Usage text
    :param defaults: Option value defaults
    :param cmds: Command list
    """
    p = optparse.OptionParser(usage)
    p.set_defaults(**defaults)

    p.add_option("-r", "--root", help="RPM DB root dir. By default, dir "
                 "in which the 'Packages' RPM DB exists or '../../../' "
                 "of that dir if 'Packages' exists under 'var/lib/rpm'.")
    p.add_option("", "--log", action="store_true",
                 help="Take run log ($logdir/%s.log) if given" % NAME)
    p.add_option("-d", "--dist", choices=("rhel", "fedora"),
                 help="Select distributions: fedora or rhel [%default]")

    p.add_option('', "--enablerepo", action="append", dest="enablerepos",
                 help="specify additional repoids to query, can be "
                      "specified multiple times")
    p.add_option('', "--disablerepo", action="append", dest="disablerepos",
                 help="specify repoids to disable, can be specified "
                      "multiple times")

    liog = optparse.OptionGroup(p, "'list' command options")
    liog.add_option("-L", "--list-type", choices=_LIST_TYPES,
                    help=("Select list type from %s [%%default]" %
                          (", ".join(_LIST_TYPES), )))
    p.add_option_group(liog)

    p.add_option("-C", "--conf", help="Specify .ini style config file path")
    p.add_option("-v", "--verbose", action="store_true", help="Verbose mode")

    return p


def main(argv=sys.argv, cmds=_COMMANDS):
    p = option_parser()
    (options, args) = p.parse_args(argv[1:])

    if not args or args[0] not in cmds.keys():
        LOG.error("You must specify command")
        p.print_help()
        sys.exit(3)

    LOG.setLevel(logging.DEBUG if options.verbose else logging.INFO)

    if options.conf:
        diff = load_conf(options.conf)
        for k, v in diff.iteritems():
            if k in ('enablerepos', 'disablerepos'):
                setattr(options, k, eval(v))

            elif getattr(options, k, False):
                setattr(options, k, v)

    options.root = os.path.abspath(options.root)  # Ensure abspath.

    if not setup_root(options.root):
        LOG.error("setup_root failed. Aborting...")
        sys.exit(2)

    if options.log:
        LOG.addHandler(logging.FileHandler(logpath(options.root,
                                                   NAME + ".log")))

    if args[0].startswith('l'):
        if options.list_type == LIST_ERRATA:
            res = yum_list_errata(options.root, options.enablerepos,
                                  options.disablerepos)
        else:
            res = yum_list(options.root, options.list_type,
                           options.enablerepos, options.disablerepos,
                           _RPM_KEYS)

        outputs_result(res, options.root, options.list_type)
    else:
        yum_download(options.root, options.enablerepos, options.disablerepos)


if __name__ == '__main__':
    main()

# vim:sw=4:ts=4:et:
