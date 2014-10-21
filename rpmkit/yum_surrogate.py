#
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

import rpmkit.yum_makelistcache
import Queue as Q
import bsddb
import logging
import optparse
import os
import os.path
import re
import shutil
import subprocess
import sys
import threading

try:
    import json
except ImportError:
    import simplejson as json


_RPMDB_SUBDIR = "var/lib/rpm"

_DEFAULTS = dict(path=None, root=None, dist="auto", format=False,
                 logdir=None, copy=False, force=False, verbose=False,
                 other_db=False)
_ARGV_SEP = "--"

_RPM_DB_FILENAMES = ["Basenames", "Name", "Providename", "Requirename"]

_USAGE = "%prog [Options...] RPMDB_PATH" + _ARGV_SEP + """ yum_args...

  where RPMDB_PATH = the path to 'Packages' RPM DB file taken from
                     '/var/lib/rpm' on the target host
        yum_args = yum command, options and other args to run

Notes:
  The host surrogates yum run must have access to all of the yum repositories
  provide updates which the target host needs. And by necessity, the host runs
  this tool must be same architecutre as the target host, and runs same OS
  version as the one the target runs.

Examples:
  # Run %prog on host accessible to any repos, for the host named
  # rhel-6-client-2 which doesn't have access to any repos provide updates:

  # a. list repos:
  %prog ./rhel-6-client-2/Packages -- repolist

  # a'. same as the above except for the path of rpmdb:
  %prog ./rhel-6-client-2/var/lib/rpm/Packages -- repolist

  # b. list updates applicable to rhel-6-client-2:
  %prog -vf ./rhel-6-client-2/Packages -- check-update

  # c. list errata applicable to rhel-6-client-2:
  %prog ./rhel-6-client-2/Packages -- list-sec

  # d. download update rpms applicable to rhel-6-client-2:
  # (NOTE: '-y' option for 'update' is must as yum cannot interact with you.)
  %prog ./rhel-6-client-2/Packages -O -- update -y \\
    --downloadonly --downloaddir=./rhel-6-client-2/updates/\
"""


def enqueue_output(outfd, queue):
    """
    :param outfd: Output FD to read results
    :param queue: Queue to enqueue results read from ``outfd``
    """
    for line in iter(outfd.readline, b''):
        queue.put(line)


def _id(x):
    return x


def run(cmd, ofunc=_id, efunc=_id, timeout=None):
    """
    Run commands without blocking I/O. See also http://bit.ly/VoKhdS.

    :param cmd: Command string
    :param ofunc: Function to process output line by line :: str => line -> ...
    :param efunc: Function to process error line by line :: str => line -> ...
    :param timeout: Timeout to wait execution of ``cmd`` in seconds or None
        (wait forever)

    :return: (output :: [str] ,err_output :: [str], exitcode :: Int)
    """
    logging.debug("Run command: " + cmd)
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, bufsize=1, close_fds=True)
    outq = Q.Queue()
    errq = Q.Queue()

    oets = [threading.Thread(target=enqueue_output, args=(p.stdout, outq)),
            threading.Thread(target=enqueue_output, args=(p.stderr, errq))]

    for t in oets:
        t.setDaemon(True)
        t.start()

    if timeout is not None:
        threading.Thread(target=p.kill)

    outs = errs = []

    while True:
        try:
            oline = outq.get_nowait()
        except Q.Empty:
            # TODO: Too verbose.
            # logging.debug("No output from stdout of #%d yet" % p.pid)
            pass
        else:
            ofunc(oline)
            outs.append(oline)

        try:
            eline = errq.get_nowait()
        except Q.Empty:
            # TODO: Too verbose.
            # logging.debug("No output from stderr of #%d yet" % p.pid)
            pass
        else:
            efunc(eline)
            errs.append(eline)

        if p.poll() is not None:
            break

    for t in oets:
        t.join()

    return (outs, errs, -1 if p.returncode is None else p.returncode)


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


def setup_data(ppath, root, force=False, copy=False, refer_other_rpmdb=True,
               rpmdb_filenames=_RPM_DB_FILENAMES, subdir=_RPMDB_SUBDIR):
    """
    :param ppath: Path to the 'Packages' rpm database originally came from
                 /var/lib/rpm on the target host, not under ``subdir``.
    :param root: The temporal root directry to put the rpm database.
    :param force: Force overwrite the rpmdb file previously copied.
    :param copy: Copy RPM db files instead of symlinks
    :param refer_other_rpmdb: True If other rpm dabase files are refered.
    """
    assert root != "/"

    rpmdb_dir = os.path.join(root, subdir)
    new_ppath = os.path.join(rpmdb_dir, "Packages")

    assert os.path.exists(ppath)

    if not os.path.exists(rpmdb_dir):
        logging.debug("Creating rpmdb dir: " + rpmdb_dir)
        os.makedirs(rpmdb_dir)

    if ppath == new_ppath:
        logging.warn("Copying destination is same as source: " + ppath)
    else:
        copyfile(ppath, new_ppath, force, copy)

    if refer_other_rpmdb:
        srcdir = os.path.dirname(ppath)

        if not rpmdb_files_exist(ppath, rpmdb_filenames):
            RuntimeError("Some RPM Database files not exist in " + srcdir)

        for f in rpmdb_filenames:
            src = os.path.join(srcdir, f)
            dst = os.path.join(rpmdb_dir, f)

            if not os.path.exists(src):
                logging.warn("File not exists. Skipped: " + src)
                continue

            if src == dst:
                logging.warn("Copying destination is same as source: " + src)
            else:
                copyfile(src, dst, force, copy)


def find_Packages_rpmdb(topdir):
    """
    Find the path to 'Packages' rpm database file under ``topdir``.

    :param topdir: top dir to start finding the rpm database file
    :return: Path of 'Packages' rpm database file :: str
    """
    pname = "Packages"

    dirs = [t[0] for t in os.walk(topdir) if pname in t[-1]]
    candidates = sorted(os.path.join(d, pname) for d in dirs)

    if not candidates:
        m = "RPM database file '%s' not found under %s" % (pname, topdir)
        raise RuntimeError(m)

    p = candidates[0]

    if not rpmkit.yum_makelistcache._is_bsd_hashdb(p):
        raise RuntimeError("Found but it was not BSD DB file: " + p)

    return p


def setup_root(ppath, root=None, force=False, copy=False,
               refer_other_rpmdb=True, subdir=_RPMDB_SUBDIR,
               find=True):
    """
    :param ppath: The path to RPM DB 'Packages' of the target host, may not be
        under ``subdir``.
    :param root: The temporal root directry to put the rpm database.
    :param force: Force overwrite the rpmdb file previously copied.
    :param copy: Copy RPM db files instead of symlinks
    :param refer_other_rpmdb: True If other rpm dabase files are refered.
    :param find: Find RPM DB 'Packages' under ``ppath``.

    :return: Root path
    """
    if find and not ppath.endswith("Packages"):
        m = "Adjust ppath from " + ppath
        ppath = find_Packages_rpmdb(ppath)
        logging.debug(m + " to " + ppath)

    ppath = os.path.normpath(ppath)
    prelpath = os.path.join(subdir, "Packages")

    if root:
        root = os.path.normpath(root)
        if root != os.path.dirname(ppath.replace(prelpath, "")):
            setup_data(ppath, root, force, copy, refer_other_rpmdb)
    else:
        if ppath.endswith(prelpath):
            root = ppath.replace(prelpath, "")
        else:
            root = os.path.dirname(ppath)
            assert root != '/'

            setup_data(ppath, root, force, copy, refer_other_rpmdb)

    return os.path.abspath(root)


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


def surrogate_operation(root, operation, logfiles=None):
    """
    Surrogates yum operation (command).

    :param root: Pivot root dir where var/lib/rpm/Packages of the target host
        exists, e.g. /root/host_a/
    :param operation: Yum operation (command), e.g. 'list-sec'
    :param logfiles: Pair of output and error log files,
        e.g. ('./tmp/out.log', '/tmp/err.log')
    """
    root = os.path.abspath(root)
    cs = ["yum", "" if root == "/" else "--installroot=" + root, operation]

    cmd = ' '.join(cs)

    if logfiles and len(logfiles) == 2:
        (outlog, errlog) = logfiles

        with open(outlog, 'w') as olog, open(errlog, 'w') as elog:
            (outs, errs, rc) = run(cmd, olog.write, elog.write)
    else:
        (outs, errs, rc) = run(cmd)

    return (outs, errs, rc)


def failure(cmd, result):
    (outs, errs, rc) = result

    raise RuntimeError("Could not get the result: "
                       "\nop='%s', rc=%d,\nout=%s\n"
                       "err=%s" % (cmd, rc, ''.join(outs), ''.join(errs)))


def run_yum_cmd(root, yum_args, logfiles, *args):
    res = (outs, errs, rc) = surrogate_operation(root, yum_args, logfiles)

    if rc == 0:
        print ''.join(outs)
    else:
        # FIXME: Ugly code based on heuristics.
        if "check-update" in yum_args or "--downloadonly" in yum_args:
            print ''.join(outs)
        else:
            failure(yum_args, res)


_FORMATABLE_COMMANDS = {"check-update": rpmkit.yum_makelistcache.yum_list,
                        "list-sec": rpmkit.yum_makelistcache.parse_errata_line}


def option_parser(defaults=_DEFAULTS, usage=_USAGE,
                  fmt_cmds=_FORMATABLE_COMMANDS):
    """
    :param defaults: Option value defaults
    :param usage: Usage text
    :param fmt_cmds: Commands supports format option
    """
    p = optparse.OptionParser(usage)
    p.set_defaults(**defaults)

    p.add_option("-r", "--root", help="RPM DB root dir. By default, dir "
                 "in which the 'Packages' RPM DB exists or '../../../' "
                 "of that dir if 'Packages' exists under 'var/lib/rpm'.")
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
    p.add_option("-L", "--logdir", help="Path to log dir")
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

    if args:
        ppath = args[0]
    else:
        ppath = raw_input("Path to the 'Packages' RPM DB file > ")

    if options.dist == "auto":
        options.dist = detect_dist()

    root = setup_root(ppath, options.root, options.force, options.copy,
                      options.other_db)

    if options.logdir:
        if not os.path.exists(options.logdir):
            logging.info("Create log dir: " + options.logdir)
            os.makedirs(options.logdir)

        logfiles = (os.path.join(options.logdir, "output.log"),
                    os.path.join(options.logdir, "error.log"))
    else:
        logfiles = None

    if options.format:
        f = None
        for c in fmtble_cmds.keys():
            if c in yum_argv:
                f = fmtble_cmds[c]
                logging.debug("cmd=%s, fun=%s" % (c, f))
                break

        if f is None:
            run_yum_cmd(root, ' '.join(yum_argv), logfiles=logfiles)
        else:
            res = [x for x in f(root, options.dist, logfiles=logfiles)]
            json.dump(res, sys.stdout, indent=2)
            print
    else:
        run_yum_cmd(root, ' '.join(yum_argv), logfiles=logfiles)

    # sys.stdout.flush()
    # sys.stderr.flush()


if __name__ == '__main__':
    main()

# vim:sw=4:ts=4:et:
