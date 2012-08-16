#
# repodata.py - Parse repodata/*.xml.gz in rpm repositories.
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
from rpmkit.utils import concat, unique

import xml.etree.cElementTree as ET
import gzip
import os


REPODATA_XMLS = \
  (REPODATA_COMPS, REPODATA_FILELISTS, REPODATA_PRIMARY) = \
  ("comps", "filelists", "primary")


def _tree_from_xml(xmlfile):
    return ET.parse(
        gzip.open(xmlfile) if xmlfile.endswith(".gz") else open(xmlfile)
    )


def _find_xml_files_g(topdir="/var/cache/yum", rtype=REPODATA_COMPS):
    """
    Find {comps,filelists,primary}.xml under `topdir` and yield its path.
    """
    for root, dirs, files in os.walk(topdir):
        for f in files:
            if rtype in f and (f.endswith(".xml.gz") or f.endswith(".xml")):
                yield os.path.join(root, f)


def find_xml_file(topdir, rtype=REPODATA_COMPS):
    fs = [f for f in _find_xml_files_g(topdir, rtype)]
    assert fs, "No %s.xml[.gz] found under %s" % (rtype, topdir)

    return fs[0]


def get_package_groups(xmlfile, byid=True):
    """
    Parse given comps file (`xmlfile`) and return a list of package group and
    packages pairs.

    :param xmlfile: comps xml file path
    :param byid: Identify package groups by ID or name

    :return: [(group_id_or_name, [package_names])]
    """
    gk = "./group"
    kk = "./id" if byid else "./name"
    pk = "./packagelist/packagereq/[@type='default']"
    gps = (
        (g.find(kk).text, [p.text for p in g.findall(pk)]) for g in
            _tree_from_xml(xmlfile).findall(gk)
    )

    # filter out groups having no packages as such group is useless:
    return [(g, ps) for g, ps in gps if ps]


def get_package_requires_and_provides(xmlfile):
    """
    Parse given primary.xml `xmlfile` and return a list of package, requires
    and provides tuples, [(package, [requires], [provides])].

    :param xmlfile: primary.xml file path

    :return: [(package, [requires], [provides])]
    """
    # We need to take care of namespaces in elementtree library.
    # SEE ALSO: http://effbot.org/zone/element-namespaces.htm
    ns0 = "http://linux.duke.edu/metadata/common"
    ns1 = "http://linux.duke.edu/metadata/rpm"

    pnk = "./{%s}name" % ns0  # package name
    rqk = ".//{%s}requires/{%s}entry/[@name]" % (ns1, ns1)  # [requires]
    prk = ".//{%s}provides/{%s}entry/[@name]" % (ns1, ns1)  # [provides]
    pkk = ".//{%s}package" % ns0  # [package]

    return [
        (p.find(pnk).text,
         unique(x.get("name") for x in p.findall(rqk)),
         unique(x.get("name") for x in p.findall(prk)),
        ) for p in _tree_from_xml(xmlfile).findall(pkk)
    ]


def get_package_files(xmlfile):
    """
    Parse given filelist.xml `xmlfile` and return a list of package and files
    pairs, [(package, [files])].

    :param xmlfile: filelist.xml file path

    :return: [(package, [file])]
    """
    ns = "http://linux.duke.edu/metadata/filelists"

    pk = "./{%s}package" % ns  # package
    fk = "./{%s}file" % ns  # file

    return [
        (p.get("name"), [x.text for x in p.findall(fk)]) for p in
            _tree_from_xml(xmlfile).findall(pk)
    ]


def main():
    pass


if __name__ == '__main__':
    main()

# vim:sw=4:ts=4:et:
