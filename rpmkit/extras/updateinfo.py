#! /usr/bin/python -tt
# updateinfo.py - collect info of update and errata applicable to given rpm db
# with utilizing swapi and yum-surrogate.
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
from operator import itemgetter

import rpmkit.memoize as M
import rpmkit.rpmutils as RU
import rpmkit.utils as U
import rpmkit.swapi as SW
import rpmkit.yum_surrogate as YS

import logging
import optparse
import os
import os.path
import re
import sys

try:
    import json
except ImportError:
    import simplejson as json


_DEFAULTS = dict(path=None, root=_WORKDIR, dist="auto", format=False,
                 copy=False, force=False, verbose=False,
                 other_db=False)

_RPMDB_SUBDIR = "var/lib/rpm"

_RPM_LIST_FILE = "packages.json"
_ERRATA_SUMMARY_FILE = "errata_summary.json"
_ERRATA_LIST_FILE = "errata.json"
_ERRATA_CVE_MAP_FILE = "errata_cve_map.json"


def rpm_list_path(workdir, filename=_RPM_LIST_FILE):
    """
    :param workdir: Working dir to dump the result
    :param filename: Output file basename
    """
    return os.path.join(workdir, filename)


def errata_summary_path(workdir, filename=_ERRATA_SUMMARY_FILE):
    """
    :param workdir: Working dir to dump the result
    :param filename: Output file basename
    """
    return os.path.join(workdir, filename)


def errata_list_path(workdir, filename=_ERRATA_LIST_FILE):
    """
    :param workdir: Working dir to dump the result
    :param filename: Output file basename
    """
    return os.path.join(workdir, filename)


def errata_cve_map_path(workdir, filename=_ERRATA_CVE_MAP_FILE):
    """
    :param workdir: Working dir to dump the result
    :param filename: Output file basename
    """
    return os.path.join(workdir, filename)


def export_rpm_list(datadir, subdir=_RPMDB_SUBDIR):
    """
    :param datadir: RPM DB top dir where ``subdir`` exists
    :param subdir: sub dir of ``datadir`` in which RPM DB files exist

    :return: The list of RPM package (NVREA) ::
             [{name, version, release, epoch, arch}]
    """
    f = os.paht.join(datadir, subdir, "Packages")
    assert os.path.exists(f), "RPM DB file looks not exist under " + datadir

    return RU.rpm_list(datadir)


def dump_rpm_list(rpm_list, workdir, filename=_RPM_LIST_FILE):
    """
    :param rpm_list: The list of RPM package (NVREA) retuned from
        export_rpm_list() :: [{name, version, release, epoch, arch}]
    :param workdir: Working dir to dump the result
    :param filename: Output file basename
    """
    json.dump(rpm_list, open(rpm_list_path(workdir, filename), 'w')


def get_errata_list_g(ppath):
    """
    Get errata applicable to given RPM db ``ppath`` (Packages) with
    yum-surrogate's help: yum-surrogate -p ``ppath`` -r ``root`` -F -- list-sec

    :param ppath: The path to RPM DB 'Packages' of target host or system group
    :return: [{errata_advisory, errata_type, errata_severity_or_None,
               rpm_name, rpm_epoch, rpm_version, rpm_release, rpm_arch}]
    """
    defaults = YU._DEFAULTS
    defaults["path"] = ppath
    defaults["format"] = True

    yum_argv = ["list-sec"]

    p = YU.option_parser(defaults)
    (options, _args) = p.parse_args([])

    if options.path.endswith("/var/lib/rpm/Packages"):
        options.root = options.path.replace("/var/lib/rpm/Packages", "")
    else:
        options.root = os.path.dirname(options.path)
        YU.setup_data(options.path, options.root, options.force,
                      options.copy, options.other_db)

    for e in YU.list_errata_g(options.root):
        yield e


_ERRATA_KEYS = ("advisory", "type", "severity")


def _mkedic(errata, packages, ekeys=_ERRATA_KEYS):
    """
    >>> e = (u'RHSA-2013:0771', u'Security', u'Moderate')
    >>> ps = [{u'advisory': u'RHSA-2013:0771',  # doctest: +NORMALIZE_WHITESPACE
    ...        u'arch': u'x86_64', u'epoch': u'0', u'name': u'curl',
    ...        u'release': u'36.el6_4', u'severity': u'Moderate',
    ...        u'type': u'Security', u'version': u'7.19.7'},
    ...       {u'advisory': u'RHSA-2013:0771', u'arch': u'x86_64',
    ...        u'epoch': u'0', u'name': u'libcurl', u'release': u'36.el6_4',
    ...        u'severity': u'Moderate', u'type': u'Security',
    ...        u'version': u'7.19.7'}])
    >>> d = _mkedic(e, ps)
    """
    pkeys = ("name", "version", "release", "epoch", "arch")

    d = dict(zip(ekeys, errata))
    d["packages"] = [dict(zip(pkeys, itemgetter(pkeys)(p))) for p in packages]

    return d


def dump_errata_summary(ppath, workdir, filename=_ERRATA_SUMMARY_FILE,
                        ekeys=_ERRATA_KEYS):
    """
    :param ppath: The path to RPM DB 'Packages' of target host or system group
    :param workdir: Working dir to dump the result
    :param filename: Output file basename
    """
    es = sorted((e for e in get_errata_list_g(ppath)),
                key=itemgetter("advisory"))

    es = [_mkedic(e, ps) for e, ps in U.groupby_key(es, itemgetter(*ekeys))]
    json.dump(es, open(errata_summary_path(workdir, filename), 'w')


def _swapicall(api, offline=False, args=[]):
    """
    :param api: RHN or swapi's virtual API string
    :type api: str
    :param offline: True if run swapi on offline mode
    :type offline: True | False :: bool
    :param args: arguments for swapi
    :type args: [str]
    """
    opts = ["--verbose", "--cacheonly"] if offline else ["--verbose"]
    return SW.call(api, args, opts)


swapicall = M.memoize(_swapicall)


def errata_url(errata):
    """
    :param errata: Errata Advisory name
    :type errata: str

    >>> errata_url("RHSA-2011:1073")
    'http://rhn.redhat.com/errata/RHSA-2011-1073.html'
    >>> errata_url("RHSA-2007:0967-2")
    'http://rhn.redhat.com/errata/RHSA-2007-0967.html'
    """
    if errata[-2] == "-":  # degenerate advisory names
        errata = errata[:-2]

    return "http://rhn.redhat.com/errata/%s.html" % errata.replace(':', '-')


def mk_errata_map(offline):
    """
    Make up errata vs. CVEs and CVSSes map with using swapi's virtual APIs.

    :param offline: True if run swapi on offline mode
    :type offline: True | False :: bool
    """
    # cves :: {cve: {cve, url, score, metrics}, }
    cves_map = dict((c["cve"], c) for c in
                    swapicall("swapi.cve.getAll", offline) if c)

    # [{advisory: errata_advisory, cves: [cve], }]
    es = swapicall("swapi.errata.getAll", offline)

    # {advisory: [cve]} where cve = {cve:, url:, socre:, metrics:}
    errata_cves_map = dict()

    for e in es:
        errata_cves_map[e["advisory"]] = []

        for c in e["cves"]:
            cve = cves_map.get(c)

            if not cve:
                logging.warn(
                    "The CVE %s not found in master data " % c + \
                    "downloaded from access.redhat.com"
                )
                cve = swapicall("swapi.cve.getCvss", offline, c)[0]

            errata_cves_map[e["advisory"]].append(cve)

    return errata_cves_map


def get_errata_details(errata, workdir, offline=False):
    """
    Get errata details with using swapi (RHN hosted or satellite).

    :param errata: Basic errata info, {advisory, type, severity, ...}
    :param offline: True if get results only from local cache
    """
    cve_ref_path = errata_cve_map_path(workdir)

    if os.path.exists(cve_ref_path):
        errata_cves_map = json.load(open(cve_ref_path))
    else:
        logging.info("Make up errata - cve - cvss map data from RHN...")
        errata_cves_map = mk_errata_map(offline)

        logging.info("Dumping errata - cve - cvss map data from RHN...")
        json.dump(errata_cves_map, open(cve_ref_path, 'w'))
        #assert bool(errata_cves_map), "errata_cache=" + errata_cache

    ed = swapicall("errata.getDetails", offline, e["advisory"])[0]
    errata.update(ed)

    errata["cves"] = errata_cves_map.get(e["advisory"], [])
    errata["url"] = errata_url(e["advisory"])

    return errata


def dump_errata_list(workdir, offline=False,
                     ref_filename=_ERRATA_SUMMARY_FILE,
                     filename=_ERRATA_LIST_FILE):
    """
    :param workdir: Working dir to dump the result
    :param offline: True if get results only from local cache
    :param ref_filename: Errata summary list as a reference
    :param filename: Output file basename
    """
    es = json.load(open(errata_summary_path(workdir, ref_filename)))

    def _g(es):
        for ref_e in es:
            yield get_errata_details(ref_e, workdir, offline)

    return [e for e in _g(es)]


# vim:sw=4:ts=4:et:
