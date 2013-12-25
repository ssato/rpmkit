#
# comp2json.py - Parse repodata/comps.xml* in yum repositories and dump
# JSON data files.
#
# Copyright (C) 2013 Red Hat, Inc.
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
from logging import DEBUG, INFO

import rpmkit.yum_surrogate as YS
import rpmkit.utils as RU
import xml.etree.cElementTree as ET
import gzip
import logging
import optparse
import os.path
import os
import sys
import tempfile


def _tree_from_xml(xmlfile):
    return ET.parse(gzip.open(xmlfile) if xmlfile.endswith(".gz") else open(xmlfile))


def _find_xml_files_g(topdir="/var/cache/yum", rtype="comps"):
    """
    Find {comps,filelists,primary}.xml under `topdir` and yield its path.
    """
    for root, dirs, files in os.walk(topdir):
        for f in files:
            if rtype in f and (f.endswith(".xml.gz") or f.endswith(".xml")):
                yield os.path.join(root, f)


def find_xml_file(topdir, rtype="comps"):
    fs = [f for f in _find_xml_files_g(topdir, "comps")]
    assert fs, "No %s.xml[.gz] found under %s" % (rtype, topdir)

    return fs[0]


def yum_makecache(root, repos):
    """
    :param root: Root dir where var/cache/yum/ exists or should be created.
    :return: (outs, err, rc)
    """
    root = os.path.abspath(root)
    logfiles = [os.path.join(root, "yum_makecache.log"),
                os.path.join(root, "yum_makecache.error.log")]

    opt = ["--disablerepo='*'"] + ["--enablerepo='%s'" % r for r in repos]

    cachedir = os.path.join(root, "var/cache/yum")
    if not os.path.exists(cachedir):
        os.makedirs(cachedir)

    return YS.surrogate_operation(root, ' '.join(opt) + " makecache", logfiles)


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
    p2d = lambda p: dict(name=p.text, **p.attrib)

    gps = ((g.find(kk).text, [p2d(p) for p in g.findall(pk)]) for g
           in _tree_from_xml(xmlfile).findall(gk))

    # filter out groups having no packages as such group is useless:
    return [dict(group_id=g, packages=ps) for g, ps in gps if ps]


def dump_package_groups(xmlfile, outdir, outfile="comps.json"):
    """
    :param xmlfile: comps xml file path
    :param outdir: Output directory
    """
    outpath = os.path.join(outdir, outfile)
    data = get_package_groups(xmlfile)

    outdir = os.path.dirname(outpath)
    if not os.path.exists(outdir):
        os.makedirs(outdir)

    RU.json_dump(data, outpath)


def option_parser():
    defaults = dict(outdir=None, verbose=False, repos=[])
    p = optparse.OptionParser("%prog [OPTION ...] YUM_REPO_CACHE_METADATADIR")
    p.set_defaults(**defaults)

    p.add_option("-O", "--outdir", help="Output dir [dynamically created]")
    p.add_option("-r", "--repos", action="append",
                 help="Comma separated yum repos to fetch errata info, "
                      "e.g. 'rhel-x86_64-server-6'. Please note that any "
                      "other repos are disabled if this option was set.")
    p.add_option("-v", "--verbose", action="store_true", help="Verbose mode")

    return p


def main():
    p = option_parser()
    (options, args) = p.parse_args()

    logging.getLogger().setLevel(DEBUG if options.verbose else INFO)

    if not args:
        p.print_usage()
        sys.exit(1)

    if not options.outdir:
        options.outdir = tempfile.mkdtemp(dir="/tmp", prefix="compsxml2json-")
        logging.info("Created a dir to save results: " + options.outdir)

    xmlfile = None
    for d in args:
        try:
            xmlfile = find_xml_file(d)
            logging.info("comps.xml* was found under: " + d)
            break
        except AssertionError:
            continue

    if xmlfile is None:
        # FIXME: Try other (args[1:]) dirs also.
        (outs, errs, rc) = yum_makecache(args[0], options.repos)

        if rc != 0:
            logging.error("comps.xml was not found under: " + ', '.join(args))
            sys.exit(1)

        xmlfile = find_xml_file(args[0])

    dump_package_groups(xmlfile, options.outdir)


if __name__ == "__main__":
    main()

# vim:sw=4:ts=4:et:
