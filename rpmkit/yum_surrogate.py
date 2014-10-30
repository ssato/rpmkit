#
# yum_surrogate.py - Surrogate yum execution for other hosts have no or
# insufficient access to any yum repositories provide updates
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
from logging import DEBUG, INFO

import rpmkit.updateinfo.utils as RUU
import rpmkit.updateinfo.yumwrapper as RUY

import logging
import optparse
import sys

try:
    import json
except ImportError:
    import simplejson as json


def failure(cmd, outs, errs, rc):
    raise RuntimeError("Could not get the result: "
                       "\nop='%s', rc=%d,\nout=%s\n"
                       "err=%s" % (cmd, rc, ''.join(outs), ''.join(errs)))


def run_yum_cmd(root, yum_args, *args):
    (outs, errs, rc) = RUY._run(["yum", "--installroot", root, yum_args])

    if rc == 0:
        print ''.join(outs)
    else:
        # FIXME: Ugly code based on heuristics.
        if "check-update" in yum_args or "--downloadonly" in yum_args:
            print ''.join(outs)
        else:
            failure(yum_args, outs, errs, rc)


_ARGV_SEP = "--"

_USAGE = "%prog [Options...] RPMDB_ROOT" + _ARGV_SEP + """ yum_args...

  where RPMDB_PATH = the root of RPM DB files taken from '/var/lib/rpm' on the
                     target host
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
  %prog ./rhel-6-client-2 -- repolist

  # a'. same as the above except for the path of rpmdb:
  %prog ./rhel-6-client-2  -- repolist

  # b. list updates applicable to rhel-6-client-2:
  %prog -vf ./rhel-6-client-2 -- check-update

  # c. list errata applicable to rhel-6-client-2:
  %prog ./rhel-6-client-2 -- list-sec

  # d. download update rpms applicable to rhel-6-client-2:
  # (NOTE: '-y' option for 'update' is must as yum cannot interact with you.)
  %prog ./rhel-6-client-2 -O -- update -y \\
    --downloadonly --downloaddir=./rhel-6-client-2/updates/\
"""


def list_errata_g(root, *args):
    base = RUY.Base(root)
    for e in base.list_errata_g(args):
        yield e


def list_updates_g(root, *args):
    base = RUY.Base(root)
    for u in base.list_updates_g(args):
        yield u


_FORMATABLE_COMMANDS = {"check-update": list_updates_g,
                        "list-sec": list_errata_g}


def option_parser(usage=_USAGE, fmt_cmds=_FORMATABLE_COMMANDS):
    """
    :param defaults: Option value defaults
    :param usage: Usage text
    :param fmt_cmds: Commands supports format option
    """
    defaults = dict(path=None, root=None, format=False, verbose=False)

    p = optparse.OptionParser(usage)
    p.set_defaults(**defaults)

    p.add_option("-r", "--root", help="RPM DB root dir. By default, dir "
                 "in which the 'Packages' RPM DB exists or '../../../' "
                 "of that dir if 'Packages' exists under 'var/lib/rpm'.")
    p.add_option("-F", "--format", action="store_true",
                 help="Parse results and output in JSON format for some "
                      "commands: " + ", ".join(fmt_cmds.keys()))
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
        root = args[0]
    else:
        root = raw_input("Path to the RPM DB root > ")

    if not RUU.check_rpmdb_root(root, False):
        logging.error("Not a root of RPM DB ?: %s" % root)
        sys.exit(-1)

    if options.format:
        f = None
        for c in fmtble_cmds.keys():
            if c in yum_argv:
                f = fmtble_cmds[c]
                logging.debug("cmd=%s, fun=%s" % (c, f))
                break

        if f is None:
            run_yum_cmd(root, ' '.join(yum_argv))
        else:
            res = [x for x in f(root, *yum_argv)]
            json.dump(res, sys.stdout, indent=2)
            print
    else:
        run_yum_cmd(root, ' '.join(yum_argv))

    # sys.stdout.flush()
    # sys.stderr.flush()


if __name__ == '__main__':
    main()

# vim:sw=4:ts=4:et:
