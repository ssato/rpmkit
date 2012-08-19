#
# repodata.py - Parse repodata/*.xml.gz in yum repositories.
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
from rpmkit.memoize import memoize
from rpmkit.utils import concat, uniq

from itertools import repeat, izip
from logging import DEBUG, INFO
from operator import itemgetter

import xml.etree.cElementTree as ET
import cPickle as pickle

import gzip
import logging
import optparse
import os.path
import os
import re
import sys


REPODATA_XMLS = \
  (REPODATA_COMPS, REPODATA_FILELISTS, REPODATA_PRIMARY) = \
  ("comps", "filelists", "primary")

_SPECIAL_RE = re.compile(r"^(?:config|rpmlib|kernel|rtld)([^)]+)")


def _true(*args):
    return True


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


def _find_xml_file(topdir, rtype=REPODATA_COMPS):
    fs = [f for f in _find_xml_files_g(topdir, rtype)]
    assert fs, "No %s.xml[.gz] found under %s" % (rtype, topdir)

    return fs[0]


find_xml_file = memoize(_find_xml_file)


def _is_special(x):
    """
    'special' means that it's not file nor virtual package nor package name
    such like 'config(setup)', 'rpmlib(PayloadFilesHavePrefix)',
    'kernel(rhel5_net_netlink_ga)'.

    :param x: filename or file path or provides or something like rpmlib(...)

    >>> _is_special('config(samba)')
    True
    >>> _is_special('rpmlib(CompressedFileNames)')
    True
    >>> _is_special('rtld(GNU_HASH)')
    True
    """
    return _SPECIAL_RE.match(x) is not None


def _strip_x(x):
    """

    >>> _strip_x('libgstbase-0.10.so.0()(64bit)')
    'libgstbase-0.10.so.0'
    >>> _strip_x('libc.so.6(GLIBC_2.2.5)(64bit)')
    'libc.so.6'
    """
    return x[:x.find('(')] if '(' in x and x.endswith(')') else x


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


def get_package_requires_and_provides(xmlfile, include_specials=False):
    """
    Parse given primary.xml `xmlfile` and return a list of package, requires
    and provides tuples, [(package, [requires], [provides])].

    :param xmlfile: primary.xml file path
    :param include_specials: Do not ignore and include special objects,
        neighther file nor package

    :return: [(package, [requires], [provides])]
    """
    # We need to take care of namespaces in elementtree library.
    # SEE ALSO: http://effbot.org/zone/element-namespaces.htm
    ns0 = "http://linux.duke.edu/metadata/common"
    ns1 = "http://linux.duke.edu/metadata/rpm"

    pkk = "./{%s}package" % ns0  # [package]
    pnk = "./{%s}name" % ns0  # package name
    rqk = ".//{%s}requires/{%s}entry" % (ns1, ns1)  # [requires]
    prk = ".//{%s}provides/{%s}entry" % (ns1, ns1)  # [provides]

    pred = lambda y: include_specials or not _is_special(y.get("name"))
    name = lambda z: _strip_x(z.get("name"))

    return [
        (p.find(pnk).text,
         uniq([name(x) for x in p.findall(rqk) if pred(x)]),
         uniq([name(y) for y in p.findall(prk) if pred(y)]),
        ) for p in _tree_from_xml(xmlfile).findall(pkk)
    ]


def get_package_files(xmlfile, packages=[]):
    """
    Parse given filelist.xml `xmlfile` and return a list of package and files
    pairs, [(package, [files])].

    :param xmlfile: filelist.xml file path

    :return: [(package, file)]
    """
    ns = "http://linux.duke.edu/metadata/filelists"
    pk = "./{%s}package" % ns  # package
    fk = "./{%s}file" % ns  # file

    pred = (lambda p: p in packages) if packages else (lambda _: True)
    pfs = (
        (p.get("name"), uniq(x.text for x in p.findall(fk))) for p in
            _tree_from_xml(xmlfile).findall(pk)
    )
    return concat((izip(repeat(p), fs) for p, fs in pfs if fs and pred(p)))


def _find_package_from_filelists(x, filelists, packages, exact=True):
    """
    :param exact: Try exact match if True
    """
    pred = (lambda x, f: x == f) if exact else (lambda x, f: f.endswith(x))

    return uniq((p for p, f in filelists if pred(x, f) and p in packages))


def _find_package_from_provides(x, provides, packages):
    return uniq((p for p, pr in provides if x == pr and p in packages))


#find_package_from_filelists = memoize(_find_package_from_filelists)
#find_package_from_provides = memoize(_find_package_from_provides)
find_package_from_filelists = _find_package_from_filelists
find_package_from_provides = _find_package_from_provides


def _find_providing_packages(x, provides, filelists, packages):
    """
    :param x: filename or file path or provides or something like rpmlib(...)
    """
    if x.startswith("/"):  # file path
        ps = find_package_from_filelists(x, filelists, packages)
        assert ps, "No package provides " + x

        logging.debug("Packages provide %s (filelists): %s" % (x, ps))
        return ps
    else:
        # 1. Try exact match in packages:
        ps = [p for p in packages if x == p]
        if ps:
            logging.debug("It's a package (packages): %s" % x)
            return ps

        # 2. Try exact match in provides:
        ps = find_package_from_provides(x, provides, packages)
        if ps:
            logging.debug("Packages provide %s (provides): %s" % (x, ps))
            return ps

        # 3. Try fuzzy (! exact) match in filelists:
        ps = find_package_from_filelists(x, filelists, packages, False)

        # There are cases no package provides x. For example,
        # '/usr/sbin/sendmail' will be created by alternatives and link sources
        # are provided by sendmail ('/usr/sbin/sendmail.sendmail') and postfix
        # ('/usr/sbin/sendmail.postfix').
        if not ps:
            logging.debug("No package provides " + x)
            return [x]

        logging.debug(
            "Packages provide %s (filelists, fuzzy match): %s" % (x, ps)
        )
        return ps


#find_providing_packages = memoize(_find_providing_packages)
find_providing_packages = _find_providing_packages


def init_repodata(repodir, packages=[], resolve=False):
    """
    :param repodir: Repository dir holding repodata/
    :param packages: Reference list of packages, e.g. install rpm names
    :param resolv: Resolv object to package names if true
    """
    files = dict((t, find_xml_file(repodir, t)) for t in REPODATA_XMLS)

    groups = get_package_groups(files[REPODATA_COMPS])
    reqs_and_provs = get_package_requires_and_provides(files[REPODATA_PRIMARY])
    filelists = get_package_files(files[REPODATA_FILELISTS])

    if not packages:
        packages = uniq(p for p, _r, _p in reqs_and_provs)

    requires = concat(
        izip(repeat(p), rs) for p, rs in
            [itemgetter(0, 1)(t) for t in reqs_and_provs if t[0] in packages]
    )
    provides = concat(
        izip(repeat(p), prs) for p, prs in
            [itemgetter(0, 2)(t) for t in reqs_and_provs if t[0] in packages]
    )

    if resolve:
        requires = [
            (p, find_providing_packages(r, provides, filelists, packages)) \
                for p, r in requires
        ]

    return (groups, filelists, requires, provides)


def option_parser():
    defaults = dict(
        outdir="results",
        packages=None,
        verbose=False,
    )
    p = optparse.OptionParser("%prog [OPTION ...] REPODIR")
    p.set_defaults(**defaults)

    p.add_option("-p", "--packages", help="Specify the rpm list")
    p.add_option("-o", "--outdir", help="Output dir [%default]]")
    p.add_option("-v", "--verbose", action="store_true", help="Verbose mode")

    return p


def main():
    p = option_parser()
    (options, args) = p.parse_args()

    logging.getLogger().setLevel(DEBUG if options.verbose else INFO)

    if not args:
        p.print_usage()
        sys.exit(1)

    repodir = args[0]

    (groups, filelists, requires, provides) = \
        init_repodata(repodir, resolve=True)

    if not os.path.exists(options.outdir):
        os.makedirs(options.outdir)

    pickle.dump(groups, open(os.path.join(options.outdir, "groups.pkl"), 'w'))
    pickle.dump(filelists, open(os.path.join(options.outdir, "filelists.pkl"), 'w'))
    pickle.dump(requires, open(os.path.join(options.outdir, "requires.pkl"), 'w'))
    pickle.dump(provides, open(os.path.join(options.outdir, "provides.pkl"), 'w'))


if __name__ == "__main__":
    main()

# vim:sw=4:ts=4:et:
