#
# rpms2groups.py - Refer package groups in comps file and reconstruct list of
# rpms and rpm groups from packages list.
#
# Copyright (C) 2012 Satoru SATOH <ssato@redhat.com>
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
# SEE ALSO: http://docs.fedoraproject.org/drafts/rpm-guide-en/ch-rpm-programming-python.html
#

"""
Note: Format of comps xml files

<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE comps PUBLIC "-//Red Hat, Inc.//DTD Comps info//EN" "comps.dtd">
<comps>
  <group>
     <id>admin-tools</id>
     <name>Administration Tools</name>
     ...
     <packagelist>
       <packagereq type="default">authconfig-gtk</packagereq>
       ...
       <packagereq type="optional">apper</packagereq>
       ...
       <packagereq type="optional">yumex</packagereq>
     </packagelist>
   </group>
  ...
</comps>
"""

from rpmkit.utils import concat
from rpmkit.identrpm import load_packages, parse_package_label

from itertools import izip, repeat
from logging import DEBUG, INFO

import xml.etree.ElementTree as ET
import gzip
import logging
import optparse
import os
import os.path
import rpm
import sys


def groups_from_comps(cpath, byid=True):
    """
    Parse given comps file (`cpath`) and returns package groups.

    :param cpath: comps file path
    :param byid: Identify package group by ID

    :return: ((group_id_or_name, [package_names])) (generator)
    """
    comps = gzip.open(cpath) if cpath.endswith(".gz") else open(cpath)
    tree = ET.parse(comps)

    kk = "./id" if byid else "./name"
    pk = "./packagelist/packagereq/[@type='default']"
    gps = (
        (g.find(kk).text, [p.text for p in g.findall(pk)]) for g in
            tree.findall("./group")
    )

    # filter out groups having no packages:
    return [(g, ps) for g, ps in gps if ps]


def package_and_group_pairs(gps):
    """
    :param gps: Group and Package pairs, [(group, [package])
    """
    return concat(
        izip((p for p in ps), repeat(g)) for ps, g in
            ((ps, g) for g, ps in gps if ps)
    )


def find_missing_packages(group, ps, gps):
    """
    Find missing packages member of given package group `group` in given
    packages `ps`.

    :param group: Group ID or name
    :param ps: [package]
    :param gps: Group and Package pairs, [(group, [package])]
    """
    package_in_groups = concat((ps for g, ps in gps if g == group))
    return [p for p in package_in_groups if p not in ps]


def find_groups_and_packages_map(gps, ps0):
    """
    :param gps: Group and Package pairs, [(group, [package])]
    :param ps0: Target packages list, [package]

    :return: [(group, found_packages_in_group, missing_packages_in_group)]
    """
    gps2 = (
        (g, [p for p in ps0 if p in ps], [p for p in ps if p not in ps0]) \
            for g, ps in gps
    )

    # filter out groups having no packages found in ps0:
    return [(g, fps, mps) for g, fps, mps in gps2 if fps]


def score(group, ps_found, ps_missing):
    """
    see `find_groups_and_packages_map` also.
    """
    return len(ps_found) - len(ps_missing)


def _id(x):
    return x


def get_packages_from_file(rpmlist, parse=True):
    """
    Get package names in given rpm list.

    :param rpmlist: Rpm list file, maybe output of `rpm -qa`
    :param parse: The list is package labels and must be parsed if True
    """
    l2n = lambda l: parse_package_label(l).get("name")
    f = l2n if parse else _id

    return [f(x) for x in load_packages(rpmlist)]


def find_comps_g(topdir="/var/cache/yum"):
    """
    Find comps.xml under `topdir` and yield its path.
    """
    for root, dirs, files in os.walk(topdir):
        for f in files:
            if "comps" in f and "xml" in f:
                yield os.path.join(root, f)


def option_parser():
    defaults = dict(
        comps=None,
        output=None,
        parse=False,
        verbose=False,
    )
    p = optparse.OptionParser("%prog [OPTION ...] RPMS_FILE")
    p.set_defaults(**defaults)

    p.add_option("-C", "--comps",
        help="Comps file path to get package groups. "
            "If not given, searched from /var/cache/yum/"
    )
    p.add_option("-P", "--parse",
        help="Specify this if input is `rpm -qa` output and must be parsed."
    )
    p.add_option("-o", "--output", help="output filename [stdout]")
    p.add_option("-v", "--verbose", action="store_true", help="Verbose mode")

    return p


def main():
    p = option_parser()
    (options, args) = p.parse_args()

    logging.getLogger().setLevel(DEBUG if options.verbose else INFO)

    if not args:
        p.print_usage()
        sys.exit(1)

    if not options.comps:
        options.comps = [f for f in find_comps_g()][0]  # Use the first one.

    packages = get_packages_from_file(args[0], options.parse)
    gps = find_groups_and_packages_map(groups_from_comps(options.comps), packages)

    output = open(options.output, 'w') if options.output else sys.stdout

    for g, ps_found, ps_missing in gps:
        #if not ps_found:
        #    continue

        print >> output, "%s: ps_found=%s, ps_missing=%s, score=%d" % \
            (g, ps_found, ps_missing, score(g, ps_found, ps_missing))

    output.close()


if __name__ == '__main__':
    main()

# vim:sw=4:ts=4:et:
