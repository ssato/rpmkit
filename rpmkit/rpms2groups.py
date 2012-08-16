#
# rpms2groups.py - Refer package groups in comps file and reconstruct list of
# rpms and rpm groups.
#
# Copyright (C) 2012 Satoru SATOH <satoru.satoh@gmail.com>
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
from itertools import repeat

import xml.etree.ElementTree as ET
import gzip
import optparse
import os
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

    pk = "./packagelist/packagereq/[@type='default']"
    kk = "./id" if byid else "./name"

    return (
        (g.find(kk).text, [p.text for p in g0.findall(pk)]) for g in
            tree.findall("./group")
    )


def package_and_group_pairs(gps):
    """
    :param gps: Group and Package pairs, [(group, [package])
    """
    return concat(
        zip((p for p in ps), repeat(g)) for ps, g in
            ((ps, g) for g, ps in gps if ps)
    )


def find_groups(name, pgs):
    """
    Find groups for package `name`

    :param name: Package name
    :param pgs: [(package_name, package_group)]
    """
    return [g for p, g in pgs if p == name]


def find_missing_packages(group, ps, gps):
    """
    Find missing packages member of given package group `group` in given
    packages `ps`.

    :param group: Group ID or name
    :param ps: [package]
    :param gps: Group and Package pairs, [(group, [package])
    """
    package_in_groups = concat((ps for g, ps in gps if g == group))
    return [p for p in package_in_groups if p not in ps]


def main():
    output = sys.stdout
    tags = ['name','version','release','arch','epoch','sourcerpm']

    p = optparse.OptionParser("""%prog [OPTION ...] RPM_0 [RPM_1 ...]

Examples:
  %prog Server/cups-1.3.7-11.el5.i386.rpm 
  %prog -T name,sourcerpm,rpmversion Server/*openjdk*.rpm
  %prog --show-tags"""
    )
    p.add_option('', '--show-tags', default=False, action='store_true',
        help='Show all possible rpm tags')
    p.add_option('-o', '--output', help='output filename [stdout]')
    p.add_option('-T', '--tags', default=",".join(tags),
        help='Comma separated rpm tag list to get or \"almost\" to get almost data dump (except for \"headerimmutable\"). [%default]')
    p.add_option('', "--blacklist", default="headerimmutable",
        help="Comma separated tags list not to get data [%default]")
    p.add_option('-H', '--human-readable', default=False, action='store_true',
        help='Output formatted results.')
    (options, args) = p.parse_args()

    if options.show_tags:
        show_all_tags()
        sys.exit(0)

    if len(args) < 1:
        p.print_usage()
        sys.exit(1)

    if options.output:
        output = open(options.output, 'w')

    if options.blacklist:
        blacklist = options.blacklist.split(",")
    else:
        blacklist = []

    if options.tags:
        if options.tags == "almost":
            tags = [t for t in rpmtags() if t not in blacklist]
        else:
            tags = options.tags.split(',')

    rpms = args
    rpmdata = []

    for r in rpms:
        vs = rpm_tag_values(r, tags)
        if vs:
            rpmdata.append(vs)

    x = json_dumps(rpmdata, options.human_readable)

    print >> output, x


if __name__ == '__main__':
    main()

# vim:sw=4:ts=4:et:
