#! /usr/bin/python -tt
# yum_surrogate.py - Surrogate yum execution for other hosts have no or
# insufficient access to any yum repositories provide updates
#
# Copyright (C) 2013 Satoru SATOH <ssato@redhat.com>
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
from logging import DEBUG, INFO

import datetime
import logging
import optparse
import os
import os.path
import re
import shutil
import subprocess
import sys

try:
    import json
except ImportError:
    import simplejson as json


_CURDIR = os.path.curdir
_TODAY = datetime.datetime.now().strftime("%Y%m%d")
_WORKDIR = os.path.join(_CURDIR, "surrogate-yum-root-" + _TODAY)

_DEFAULTS = dict(path=None, root=_WORKDIR, dist="auto", format=False,
                 copy=False, force=False, verbose=False,
                 other_db=False)
_ARGV_SEP = "--"

_RPM_DB_FILENAMES = ["Basenames", "Name", "Providename", "Requirename"]

_USAGE = "%prog [Options...] " + _ARGV_SEP + """ yum_command_and_options...

Notes:
  The host surrogates yum run must have access to all of the yum repositories
  provide updates which the target host needs. And by necessity, the host runs
  this tool must be same architecutre as the target host, and runs same OS
  version as the one the target runs.

Examples:
  # Run %prog on host accessible to any repos, for the host named
  # rhel-6-client-2 which don't have access to any repos provide updates:

  # a. list repos:
  %prog -p ./rhel-6-client-2/Packages -r rhel-6-client-2/ -- repolist

  # a'. same as the above except for the path of rpmdb:
  %prog -p ./rhel-6-client-2/var/lib/rpm/Packages -- repolist

  # b. list updates applicable to rhel-6-client-2:
  %prog -vf -p ./rhel-6-client-2/Packages -r rhel-6-client-2/ -- check-update

  # c. list errata applicable to rhel-6-client-2:
  %prog -p ./rhel-6-client-2/Packages -r rhel-6-client-2/ -- list-sec

  # d. download update rpms applicable to rhel-6-client-2:
  # (NOTE: '-y' option for 'update' is must as yum cannot interact with you.)
  %prog -p ./rhel-6-client-2/Packages -r rhel-6-client-2/ \\
    -O -- update -y --downloadonly --downloaddir=./rhel-6-client-2/updates/\
"""


def run(cmd):
    """
    :param cmd: Command string
    :return: (output :: str ,err_output :: str, exitcode :: Int)
    """
    logging.debug("Run command: " + cmd)
    p = subprocess.Popen(cmd, shell=True, stderr=subprocess.PIPE,
                         stdout=subprocess.PIPE)
    (out, err) = p.communicate()
    return (out, err, p.returncode)


def copyfile(src, dst, force, copy=False):
    src = os.path.abspath(src)
    dst = os.path.abspath(dst)

    assert src != dst, "Copying source and destination are same file!"

    if os.path.exists(dst):
        if force:
            os.remove(dst)
        else:
            logging.info("Already exists and skip copying: " + dst)
            return

    if copy:
        logging.debug("Copying: %s -> %s" % (src, dst))
        shutil.copy2(src, dst)
    else:
        logging.debug("Create a symlink: %s -> %s" % (src, dst))
        os.symlink(src, dst)


def setup_data(path, root, force=False, copy=False, refer_other_rpmdb=True,
               rpmdb_filenames=_RPM_DB_FILENAMES):
    """
    :param path: Path to the 'Packages' rpm database originally came from
                 /var/lib/rpm on the target host.
    :param root: The temporal root directry to put the rpm database.
    :param force: Force overwrite the rpmdb file previously copied.
    :param copy: Copy RPM db files instead of symlinks
    :param refer_other_rpmdb: True If other rpm dabase files are refered.
    """
    assert root != "/"

    rpmdb_dir = os.path.join(root, "var/lib/rpm")
    rpmdb_Packages_path = os.path.join(rpmdb_dir, "Packages")

    assert os.path.exists(path)

    if not os.path.exists(rpmdb_dir):
        logging.debug("Creating rpmdb dir: " + rpmdb_dir)
        os.makedirs(rpmdb_dir)

    copyfile(path, rpmdb_Packages_path, force, copy)

    if refer_other_rpmdb:
        srcdir = os.path.dirname(path)

        if not rpmdb_files_exist(path, rpmdb_filenames):
            RuntimeError("Some RPM Database files not exist in " + srcdir)

        for f in rpmdb_filenames:
            src = os.path.join(srcdir, f)
            dst = os.path.join(rpmdb_dir, f)

            if not os.path.exists(src):
                logging.warn("File not exists. Skipped: " + src)
                continue

            copyfile(src, dst, force, copy)


def detect_dist():
    if os.path.exists("/etc/fedora-release"):
        return "fedora"
    elif os.path.exists("/etc/redhat-release"):
        return "rhel"
    else:
        return "uknown"


def rpmdb_files_exist(path, rpmdb_filenames=_RPM_DB_FILENAMES):
    """
    :param path: Path to 'Packages' rpm database file where other files might
                 exists.
    """
    dbdir = os.path.dirname(path)
    return all(os.path.exists(os.path.join(dbdir, f)) for f in rpmdb_filenames)


def surrogate_operation(root, operation):
    """
    Surrogates yum operation (command).

    :param root: Pivot root dir where var/lib/rpm/Packages of the target host
                 exists, e.g. /root/host_a/
    :param operation: Yum operation (command), e.g. 'list-sec'
    """
    root = os.path.abspath(root)
    cs = ["yum", ("" if root == "/" else "--installroot=" + root), operation]

    return run(' '.join(cs))


def _is_errata_line(line, dist):
    if dist == "fedora":
        reg = re.compile(r"^FEDORA-")
    else:  # RHEL:
        reg = re.compile(r"^RH[SBE]A-")

    return line and reg.match(line)


def failure(cmd, result):
    raise RuntimeError("Could not get the result. op=" + cmd +
                       ", out=%s, err=%s, rc=%d" % result)


_RPM_ARCHS = ("i386", "i586", "i686", "x86_64", "ppc", "ia64", "s390",
              "s390x", "noarch")


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

    return dict(advisory=advisory, type=etype, severity=severity,  # errata
                name=name, epoch=epoch, version=version,  # RPM package
                release=release, arch=arch)


def list_errata_g(root, dist=None):
    """
    A generator to return errata found in the output result of 'yum list-sec'
    one by one.

    :param root: Pivot root dir where var/lib/rpm/Packages of the target host
                 exists, e.g. /root/host_a/
    :param dist: Distribution name or None
    """
    if not dist:
        dist = detect_dist()

    result = surrogate_operation(root, "list-sec")
    if result[-1] == 0:
        for line in result[0].splitlines():
            if _is_errata_line(line, dist):
                yield parse_errata_line(line)
            else:
                logging.debug("Not errata line: " + line)
    else:
        failure("list-sec", result)


def parse_update_line(line):
    """

    >>> s = "bind-libs.x86_64  32:9.8.2-0.17.rc1.el6_4.4  rhel-x86_64-server-6"
    >>> p = parse_update_line(s)
    >>> assert p["name"] == "bind-libs"
    >>> assert p["arch"] == "x86_64"
    >>> assert p["epoch"] == "32"
    >>> assert p["version"] == "9.8.2"
    >>> assert p["release"] == "0.17.rc1.el6_4.4"

    >>> s = "perl-HTTP-Tiny.noarch   0.017-242.fc18   updates"
    >>> p = parse_update_line(s)
    >>> assert p["name"] == "perl-HTTP-Tiny"
    >>> assert p["arch"] == "noarch"
    >>> assert p["epoch"] == "0"
    >>> assert p["version"] == "0.017"
    >>> assert p["release"] == "242.fc18"
    """
    preg = re.compile(r"^(?P<name>[A-Za-z0-9][^.]+)[.](?P<arch>\w+) +" +
                      r"(?:(?P<epoch>\d+):)?(?P<version>[^-]+)-" +
                      r"(?P<release>\S+) +(?P<repo>\S+)$")

    m = preg.match(line)
    if m:
        p = m.groupdict()
        if p["epoch"] is None:
            p["epoch"] = "0"

        return p
    else:
        return dict()


def list_updates_g(root, *args):
    """
    FIXME: Ugly and maybe yum-version-dependent implementation.

    A generator to return updates found in the output result of 'yum
    check-update' one by one.

    :param root: Pivot root dir where var/lib/rpm/Packages of the target host
                 exists, e.g. /root/host_a/
    """
    # NOTE: 'yum check-update' looks returning non-zero exit code (e.g. 100)
    # when there are any updates found.
    result = surrogate_operation(root, "check-update")
    if result[0]:
        # It seems that yum prints out an empty line before listing updates.
        in_list = False
        for line in result[0].splitlines():
            if line:
                if in_list:
                    yield parse_update_line(line)
            else:
                in_list = True
    else:
        failure("check-update", result)


def run_yum_cmd(root, yum_args, *args):
    result = surrogate_operation(root, yum_args)
    if result[-1] == 0:
        print result[0]
    else:
        # FIXME: Ugly code based on heuristics.
        if "check-update" in yum_args or "--downloadonly" in yum_args:
            print result[0]
        else:
            failure(yum_args, result)


_FORMATABLE_COMMANDS = {"check-update": list_updates_g,
                        "list-sec": list_errata_g, }


def option_parser(defaults=_DEFAULTS, usage=_USAGE,
                  fmt_cmds=_FORMATABLE_COMMANDS):
    """
    :param defaults: Option value defaults
    :param usage: Usage text
    :param fmt_cmds: Commands supports format option
    """
    p = optparse.OptionParser(usage)
    p.set_defaults(**defaults)

    p.add_option("-p", "--path",
                 help="Path to the RPM DB file '/var/lib/rpm/Packages' "
                      "originally taken from the target host")
    p.add_option("-r", "--root", help="RPM DB root dir [%default]")
    p.add_option("-d", "--dist", choices=("rhel", "fedora", "auto"),
                 help="Select distributions: fedora, rhel or auto [%default]")
    p.add_option("-F", "--format", action="store_true",
                 help="Parse results and output in JSON format for some "
                      "commands: " + ", ".join(fmt_cmds.keys()))
    p.add_option("-c", "--copy", action="store_true",
                 help="Copy RPM DB files instead of symlinks")
    p.add_option("-f", "--force", action="store_true",
                 help="Force overwrite RPM DB files even if exists already")
    p.add_option("-O", "--other-db", action="store_true",
                 help="Refer RPM DB files other than 'Packages' also. "
                      "You must specify this if you want to perform some "
                      "yum sub commands like 'install', 'update' requires "
                      "other RPM DB files")
    p.add_option("-v", "--verbose", action="store_true", help="Verbose mode")

    return p


def split_yum_args(argv, sep=_ARGV_SEP):
    """
    Split list of command arguments w/o argv[0] into options for this script
    itself and yum command to surrogate run.

    :param argv: Command line arguments :: [str]
    :param sep: splitter

    >>> argv = ["-p", "./rhel-6-client-2/rpmdb/Packages", "-r",
    ...         "rhel-6-client-2/", "-v", "--", "list-sec"]
    >>> (self_argv, yum_argv) = split_yum_args(argv)
    >>> self_argv  # doctest: +NORMALIZE_WHITESPACE
    ['-p', './rhel-6-client-2/rpmdb/Packages', '-r',
     'rhel-6-client-2/', '-v']
    >>> yum_argv
    ['list-sec']

    >>> argv = ["-p", "./rhel-6-client-2/rpmdb/Packages", "-h"]
    >>> (self_argv, yum_argv) = split_yum_args(argv)
    >>> self_argv
    ['-p', './rhel-6-client-2/rpmdb/Packages', '-h']
    >>> yum_argv
    []
    """
    sep_idx = argv.index(sep) if sep in argv else len(argv)
    return (argv[:sep_idx], argv[sep_idx+1:])


def main(argv=sys.argv, fmtble_cmds=_FORMATABLE_COMMANDS):
    p = option_parser()

    (self_argv, yum_argv) = split_yum_args(argv[1:])
    (options, args) = p.parse_args(self_argv)

    if not yum_argv:
        logging.error("No yum command and options specified after '--'")
        p.print_help()
        sys.exit(-1)

    logging.getLogger().setLevel(DEBUG if options.verbose else INFO)

    if options.dist == "auto":
        options.dist = detect_dist()

    if not options.path:
        options.path = raw_input("Path to the rpm db to surrogate > ")

    if options.path.endswith("var/lib/rpm/Packages"):
        options.root = options.path.replace("var/lib/rpm/Packages", "")
        logging.debug("Set root to: " + options.root)
    else:
        setup_data(options.path, options.root, options.force,
                   options.copy, options.other_db)

    if options.format:
        f = None
        for c in fmtble_cmds.keys():
            if c in yum_argv:
                f = fmtble_cmds[c]
                logging.debug("cmd=%s, fun=%s" % (c, f))
                break

        if f is None:
            run_yum_cmd(options.root, ' '.join(yum_argv))
        else:
            json.dump([x for x in f(options.root, options.dist)],
                      sys.stdout, indent=2)
            print
    else:
        run_yum_cmd(options.root, ' '.join(yum_argv))


if __name__ == '__main__':
    main()

# vim:sw=4:ts=4:et:
