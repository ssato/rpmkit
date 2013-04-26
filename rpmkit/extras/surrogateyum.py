#
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
_WORKDIR = os.path.join(_CURDIR, "yumoffline-root-" + _TODAY)

_DEFAULTS = dict(path=None, root=_WORKDIR, dist="rhel", force=False, verbose=False)

try:
    subproc_check_output = subprocess.check_output
except NameError:
    def subproc_check_output(cmd):
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
        res = p.communicate()
        return res[0]


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


def list_errata(root, dist):
    c = "yum --installroot=%s list-sec" % os.path.abspath(root)
    logging.debug("cmd: " + c)
    result = subproc_check_output(shlex.split(c))
    return [l for l in result.splitlines() if _is_errata_line(l, dist)]


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
    p.add_option("-o", "--output", help="Output filename [stdout]")
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
    es = list_errata(options.root, options.dist)

    output = open(options.output, 'w') if options.output else sys.stdout
    for e in es:
        output.write(str(e) + "\n")


if __name__ == '__main__':
    main()

# vim:sw=4:ts=4:et:
