#
# List multiple versions of RPMs by versions.
#
# Copyright (C) 2012 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato@redhat.com>
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
from rpmkit.utils import groupby_key

from itertools import izip_longest as izip
from operator import itemgetter

import rpmkit.rpmutils as U

import glob
import logging
import optparse
import os.path
import rpm
import sys


_RPM_KEYS = ["name", "version", "release", "epoch", "arch"]

# may be changed depends on 'num-deltas' in createrepo
_KEEP_LIMIT = 1


def _path2rpm(filepath, keys=_RPM_KEYS):
    """
    :param filepath: RPM file path
    :param keys: keys for RPM dict object
    """
    h = rpm.TransactionSet().hdrFromFdno(open(filepath, "rb"))
    return dict(izip(["path"] + keys, [filepath] + [h[k] for k in keys]))


def rpms_group_by_names_g(rpmdir, newers=False):
    """List RPMs in given dir grouped by name.

    :param rpmdir: Dir in which RPM files are
    """
    ps_g = (_path2rpm(f) for f in glob.glob(os.path.join(rpmdir, "*.rpm")))
    for name, ps in groupby_key(ps_g, itemgetter("name")):
        yield sorted(ps, cmp=U.pcmp, reverse=(not newers))


def format(ps, sep="\n  "):
    return "# " + ps[0]["name"] + ":" + sep + sep.join(p["path"] for p in ps)


def init_log(level):
    lvl = [logging.DEBUG, logging.INFO, logging.WARN][level]
    logging.basicConfig(format="[%(levelname)s] %(message)s", level=lvl)


def option_parser():
    p = optparse.OptionParser("%prog [OPTION ...] RPMS_DIR")

    p.set_defaults(verbose=1, newers=False, limit=_KEEP_LIMIT)
    p.add_option(
        "-n", "--newers", action="store_true",
        help="It list older RPMs for GC by default. This option inverts"
             " this behavior and it will list *newer* RPMs instead."
    )
    p.add_option(
        "-l", "--limit", type="int",
        help="Number of RPMs to filter *out* [%default]"
    )
    p.add_option("-D", "--debug", action="store_const", const=0,
        dest="verbose", help="Debug mode"
    )
    p.add_option("-q", "--quiet", action="store_const", const=2,
        dest="verbose", help="Quiet mode"
    )
    return p


def main(argv=sys.argv):
    p = option_parser()
    (options, args) = p.parse_args(argv[1:])

    if not args:
        p.print_help()
        sys.exit(0)

    init_log(options.verbose)

    rpmsdir = args[0]

    for ps in rpms_group_by_names_g(rpmsdir, options.newers):
        if ps and len(ps) > 1:
            print format(ps[:len(ps) - options.limit])


if __name__ == '__main__':
    main(sys.argv)

# vim:sw=4:ts=4:et:
