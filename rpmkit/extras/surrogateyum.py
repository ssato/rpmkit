#! /usr/bin/python -tt
# surrogateyum.py - Surrogate yum checks updates for other hosts
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
import shlex
import subprocess
import sys


_CURDIR = os.path.curdir
_TODAY = datetime.datetime.now().strftime("%Y%m%d")
_WORKDIR = os.path.join(_CURDIR, "surrogate-yum-root-" + _TODAY)

_DEFAULTS = dict(path=None, root=_WORKDIR, dist="rhel", force=False, verbose=False)

# It seems there are versions of python of which subprocess module lacks
# 'check_output' function:
try:
    subprocess.check_output
    def subproc_check_output(cmd):
        """
        :param cmd: Command string
        """
        logging.debug("cmd: " + cmd)
        return subprocess.check_output(cmd, shell=True)

except AttributeError:
    def subproc_check_output(cmd):
        logging.debug("cmd: " + cmd)
        return subprocess.Popen(cmd, shell=True,
                                stdout=subprocess.PIPE).communicate()[0]


def setup(path, root, force=False):
    """
    :param path: Path to the 'Packages' rpm database originally came from
                 /var/lib/rpm on the target host.
    :param root: The temporal root directry to put the rpm database.
    :param force: Force overwrite the rpmdb file previously copied.
    """
    assert root != "/"

    rpmdb_path = os.path.join(root, "var/lib/rpm")
    rpmdb_Packages_path = os.path.join(rpmdb_path, "Packages")

    if not os.path.exists(rpmdb_path):
        logging.debug("Creating rpmdb dir: " + rpmdb_path)
        os.makedirs(rpmdb_path)

    if os.path.exists(rpmdb_Packages_path) and not force:
        raise RuntimeError("RPM DB already exists: " + rpmdb_Packages_path)
    else:
        logging.debug("Copying RPM DB: %s -> %s/" % (path, rpmdb_path))
        shutil.copy2(path, rpmdb_Packages_path)


def _is_errata_line(line, dist):
    if dist == "fedora":
        reg = re.compile(r"^FEDORA-")
    else:  # RHEL:
        reg = re.compile(r"^RH[SBE]A-")

    return line and reg.match(line)


def surrogate_operation(root, operation):
    """
    Surrogates yum operation (command).

    :param root: Pivot root dir where var/lib/rpm/Packages of the target host
                 exists, e.g. /root/host_a/
    :param operation: Yum operation (command), e.g. 'list-sec'
    """
    c = "yum --installroot=%s %s" % (os.path.abspath(root), operation)
    return subproc_check_output(c)


def list_errata_g(root, dist):
    """
    A generator to return errata found in the output result of 'yum list-sec'
    one by one.

    :param root: Pivot root dir where var/lib/rpm/Packages of the target host
                 exists, e.g. /root/host_a/
    :param dist: Distribution name
    """
    result = surrogate_operation(root, "list-sec")
    if result:
        for line in result.splitlines():
            #logging.debug("line=" + line)
            if _is_errata_line(line, dist):
                yield line
    else:
        raise RuntimeError("Could not get the result. op=list-sec")


def list_updates_g(root, *args):
    """
    FIXME: Ugly and maybe yum-version-dependent implementation.

    A generator to return updates found in the output result of 'yum
    check-update' one by one.

    :param root: Pivot root dir where var/lib/rpm/Packages of the target host
                 exists, e.g. /root/host_a/
    """
    # NOTE: 'yum check-update' looks returns !0 exit code (e.g. 100) when there
    # are any updates found.
    result = surrogate_operation(root, "check-update || :")
    if result:
        # It seems that yum prints out an empty line before listing updates.
        in_list = False
        for line in result.splitlines():
            if line:
                if in_list:
                    yield line
            else:
                in_list = True
    else:
        raise RuntimeError("Could not get the result. op=list-sec")


def get_errata_deails(errata):
    """
    TBD

    :param errata: Errata advisory
    """
    return None


def option_parser(defaults=_DEFAULTS):
    p = optparse.OptionParser("%prog [OPTION ...] path_to_Packages_rpmdb")
    p.set_defaults(**defaults)

    p.add_option("-r", "--root", help="Output root dir [%default]")
    p.add_option("-d", "--dist", choices=("rhel", "fedora"),
                 help="Select distribution [%default]")
    p.add_option("-f", "--force", action="store_true",
                 help="Force overwrite rpmdb and outputs even if exists")
    p.add_option("-v", "--verbose", action="store_true", help="Verbose mode")

    return p


def main():
    p = option_parser()
    (options, args) = p.parse_args()

    logging.getLogger().setLevel(DEBUG if options.verbose else INFO)

    if not args:
        p.print_usage()
        sys.exit(-1)

    path = args[0]

    setup(path, options.root, options.force)
    es_g = list_errata_g(options.root, options.dist)

    for e in es_g:
        sys.stdout.write(str(e) + "\n")


if __name__ == '__main__':
    main()

# vim:sw=4:ts=4:et:
