#
# updateinfo.py - collect info of updates and errata applicable to the target
# system with referering its rpm database files and utilizing swapi and
# yum-surrogate.
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
from operator import attrgetter, itemgetter

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
import tablib


_RPM_LIST_FILE = "packages.json"
_ERRATA_SUMMARY_FILE = "errata_summary.json"
_ERRATA_LIST_FILE = "errata.json"
_ERRATA_CVE_MAP_FILE = "errata_cve_map.json"
_UPDATES_FILE = "updates.json"
_XLS_FILE = "packages_and_errata_summary.xls"

_RPM_KEYS = ("name", "version", "release", "epoch", "arch", "summary",
             "vendor", "buildhost")
_ERRATA_KEYS = ("advisory", "type", "severity")
_UPDATE_KEYS = ("name", "version", "release", "epoch", "arch", "advisories")


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


def dataset_file_path(workdir, filename=_XLS_FILE):
    """
    :param workdir: Working dir to dump the result
    :param filename: Output file basename
    """
    return os.path.join(workdir, filename)


def updates_file_path(workdir, filename=_UPDATES_FILE):
    """
    :param workdir: Working dir to dump the result
    :param filename: Output file basename
    """
    return os.path.join(workdir, filename)


def dump_rpm_list(root, workdir, filename=_RPM_LIST_FILE, rpmkeys=_RPM_KEYS):
    """
    :param root: RPM DB top dir
    :param workdir: Working dir to dump the result
    :param filename: Output file basename
    :param rpmkeys: RPM keys to get info of package
    """
    logging.debug("Get rpms for the root: " + root)
    rpms = RU.list_installed_rpms(root, yum=True, keys=rpmkeys)
    logging.debug("%d installed rpms found in %s" % (len(rpms), root))

    U.json_dump(rpms, rpm_list_path(workdir, filename))


def _mkedic(errata, packages, ekeys=_ERRATA_KEYS):
    """
    >>> e = (u'RHSA-2013:0771', u'Security', u'Moderate')
    >>> ps = [  # doctest: +NORMALIZE_WHITESPACE
    ...       {u'advisory': u'RHSA-2013:0771',
    ...        u'arch': u'x86_64', u'epoch': u'0', u'name': u'curl',
    ...        u'release': u'36.el6_4', u'severity': u'Moderate',
    ...        u'type': u'Security', u'version': u'7.19.7'},
    ...       {u'advisory': u'RHSA-2013:0771', u'arch': u'x86_64',
    ...        u'epoch': u'0', u'name': u'libcurl', u'release': u'36.el6_4',
    ...        u'severity': u'Moderate', u'type': u'Security',
    ...        u'version': u'7.19.7'}]
    >>> d = _mkedic(e, ps)
    """
    pkeys = ("name", "version", "release", "epoch", "arch")

    d = dict(zip(ekeys, errata))
    d["packages"] = [dict(zip(pkeys, itemgetter(*pkeys)(p))) for p in packages]

    return d


def fetch_and_dump_errata_summary(root, workdir, dist=None, repos=[],
                                  filename=_ERRATA_SUMMARY_FILE,
                                  ekeys=_ERRATA_KEYS):
    """
    :param root: RPM DB top dir
    :param workdir: Working dir to dump the result
    :param dist: Specify target distribution explicitly
    :param repos: List of yum repos to fetch errata info
    :param filename: Output file basename
    """
    logfiles = (os.path.join(workdir, "errata_summary_output.log"),
                os.path.join(workdir, "errata_summary_error.log"))

    if repos:
        repos_s = ' '.join("--enablerepo='%s'" % r for r in repos)
        opts = "--disablerepo='*' " + repos_s
    else:
        opts = ""

    es = sorted((e for e in YS.list_errata_g(root, dist, logfiles, opts)),
                key=itemgetter("advisory"))

    es = [_mkedic(e, ps) for e, ps in U.groupby_key(es, itemgetter(*ekeys))]
    U.json_dump(es, errata_summary_path(workdir, filename))


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
                    "The CVE %s not found in master data " % c +
                    "downloaded from access.redhat.com"
                )
                cve = swapicall("swapi.cve.getCvss", offline, c)[0]

            errata_cves_map[e["advisory"]].append(cve)

    return errata_cves_map


def get_errata_details(errata, workdir, offline=False, use_map=False):
    """
    Get errata details with using swapi (RHN hosted or satellite).

    :param errata: Basic errata info, {advisory, type, severity, ...}
    :param offline: True if get results only from local cache
    """
    if use_map:
        cve_ref_path = errata_cve_map_path(workdir)

        if os.path.exists(cve_ref_path):
            errata_cves_map = U.json_load(cve_ref_path)
        else:
            logging.info("Make up errata - cve - cvss map data from RHN...")
            errata_cves_map = mk_errata_map(offline)

            logging.info("Dumping errata - cve - cvss map data from RHN...")
            U.json_dump(errata_cves_map, cve_ref_path)
            #assert bool(errata_cves_map), "errata_cache=" + errata_cache

    adv = errata["advisory"]

    ed = swapicall("errata.getDetails", offline, adv)[0]
    errata.update(ed)

    if adv.startswith("RHSA"):
        # FIXME: Errata - CVE map looks sometimes incomplete.
        if use_map:
            errata["cves"] = errata_cves_map.get(adv, [])
        else:
            try:
                cves = swapicall("errata.listCves", offline, adv)
                dcves = []
                if cves:
                    for cve in cves:
                        dcve = swapicall("swapi.cve.getCvss", offline, cve)[0]
                        if dcve:
                            dcves.append(dcve)
                        else:
                            logging.warn("Couldn't get details of " + cve)

                errata["cves"] = dcves if dcves else cves

            except IndexError:
                logging.warn("Could not get relevant CVEs: " + adv)
                errata["cves"] = []

    errata["url"] = errata_url(adv)

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
    es = U.json_load(errata_summary_path(workdir, ref_filename))

    def _g(es):
        for ref_e in es:
            yield get_errata_details(ref_e, workdir, offline)

    errata = sorted((e for e in _g(es)), key=itemgetter("advisory"))
    U.json_dump(errata, errata_list_path(workdir))


def dump_detailed_packages_list(workdir, offline=False, chans=[],
                                ref_filename=_RPM_LIST_FILE):
    """
    FIXME: How to distinguish between RH and non-RH RPMs.

    :param workdir: Working dir to dump the result
    :param offline: True if get results only from local cache
    :param chans: List of channels (yum repos) to fetch pkg info
    :param ref_filename: Package summary list as a reference
    """
    ps = U.json_load(rpm_list_path(workdir, ref_filename))
    ref_ps = []

    for chan in chans:
        try:
            ref = swapicall("channel.software.listLatestPackages",
                            offline, chan)
            for p in ref:
                if p not in ref_ps:
                    ref_ps.append(p)
        except:
            pass

    names = U.uniq(p["name"] for p in ref_ps)
    new_ps = []

    for p in ps:
        if p["name"] in names:
            p["originally_from"] = "RH"
        else:
            p["originally_from"] = "Uknown"

        new_ps.append(p)

    # Backup original:
    os.rename(rpm_list_path(workdir), rpm_list_path(workdir) + ".save")

    U.json_dump(new_ps, rpm_list_path(workdir))


def _make_dataset(list_data, headers=None, title=None):
    """
    :param list_data: List of data
    :param headers: Dataset headers to be used as column headers
    :param headers: Dataset title to be used as worksheet's name
    """
    dataset = tablib.Dataset()

    if title:
        dataset.title = title

    if headers:
        dataset.headers = headers

        for x in list_data:
            dataset.append([x.get(h) for h in headers])
    else:
        for x in list_data:
            dataset.append(x.values())

    return dataset


_MIN_RPM_KEYS = ("name", "version", "release", "epoch", "arch")


def errata_to_updates_list(errata_list, rpmkeys=_MIN_RPM_KEYS):
    """
    Make a list of package updates from errata list.

    :param errata_list: Errata list
    """
    updates = dict()
    p2k = itemgetter(*rpmkeys)

    for e in errata_list:
        adv = e["advisory"]

        for p in e["packages"]:
            x_seen = updates.get(p2k(p), None)

            if x_seen is None:
                x = p
                x["advisories"] = [adv]
                updates[p2k(p)] = x
            else:
                if adv not in x_seen:
                    x_seen["advisories"].append(adv)

    return sorted(updates.values(), key=itemgetter("name"))


def dump_updates_list(workdir, rpmkeys=_MIN_RPM_KEYS):
    """
    :param workdir: Working dir to dump the result
    :param format: Output format: xls, xlsx or ods
    """
    es = U.json_load(errata_summary_path(workdir))
    us = errata_to_updates_list(es, rpmkeys)

    # Make it valid JSON data. (It seems simple array isn't valid.)
    data = dict(updates=us)

    U.json_dump(data, updates_file_path(workdir))


_DETAILED_ERRATA_KEYS = ["advisory", "type", "severity", "synopsis",
                         "description", "issue_date", "last_modified_date",
                         "update_date", "url", "cves"]


def _fmt_cvess(cves):
    """
    :param cves: List of CVE dict {cve, score, url, metrics} or str "cve".
    :return: List of CVE strings
    """
    try:
        fmt = '"%(cve)s (score=%(score)s, metrics=%(metrics)s, url=%(url)s)"'
        cves = [fmt % c for c in cves]
    except KeyError:
        pass

    return cves


def _detailed_errata_list_g(workdir):
    es = U.json_load(errata_list_path(workdir))

    for e in es:
        if e["severity"] is None:
            e["severity"] = "N/A"

        if e.get("cves", False):
            e["cves"] = ", ".join(_fmt_cvess(e["cves"]))
        else:
            e["cves"] = "N/A"

        yield e


def _updates_list_g(workdir, ukeys=_UPDATE_KEYS):
    data = U.json_load(updates_file_path(workdir))

    for u in data["updates"]:
        u["advisories"] = ", ".join(u["advisories"])
        yield u


def dump_datasets(workdir, details=False, rpmkeys=_RPM_KEYS,
                  ekeys=_ERRATA_KEYS, dekeys=_DETAILED_ERRATA_KEYS,
                  ukeys=_UPDATE_KEYS):
    """
    :param workdir: Working dir to dump the result
    """
    rpms = U.json_load(rpm_list_path(workdir))
    errata = U.json_load(errata_summary_path(workdir))
    updates = [u for u in _updates_list_g(workdir, ukeys)]

    datasets = [_make_dataset(rpms, rpmkeys, "Installed RPMs"),
                _make_dataset(errata, ekeys, "Errata"),
                _make_dataset(updates, ukeys, "Update RPMs")]

    if details:
        des = [x for x in _detailed_errata_list_g(workdir)]
        des_dataset = _make_dataset(des, dekeys, "Errata Details")

        book = tablib.Databook(datasets + [des_dataset])
    else:
        book = tablib.Databook(datasets)

    with open(dataset_file_path(workdir), 'wb') as out:
        out.write(book.xls)


_WARN_DETAILS_NOT_AVAIL = """\
Detailed errata and packages information of the detected distribution %s
is not supported. So it will disabled this feature."""


def modmain(ppath, workdir=None, offline=False, details=False, dist=None,
            repos=[], force=False, rpmkeys=_RPM_KEYS, verbose=False,
            warn_details_msg=_WARN_DETAILS_NOT_AVAIL):
    """
    :param ppath: The path to 'Packages' RPM DB file
    :param workdir: Working dir to dump the result
    :param offline: True if get results only from local cache
    :param details: True if detailed errata and packages info is needed
    :param dist: Specify target distribution explicitly
    :param repos: Specify yum repos to fetch errata and updates info
    :param force: Force overwrite the rpmdb file previously copied
    :param rpmkeys: RPM keys to get info of package
    """
    logging.getLogger().setLevel(DEBUG if verbose else INFO)

    if not ppath:
        ppath = raw_input("Path to the RPM DB 'Packages' > ")

    if workdir:
        if not os.path.exists(workdir):
            logging.info("Creating working dir: " + workdir)
            os.makedirs(workdir)

        root = YS.setup_root(ppath, workdir, force=force)
    else:
        root = YS.setup_root(ppath, force=force)
        workdir = root

    logging.info("Dump RPM list...")
    dump_rpm_list(root, workdir, rpmkeys=rpmkeys)

    logging.info("Dump Errata summaries...")
    fetch_and_dump_errata_summary(root, workdir, dist, repos)

    if details:
        if not dist:
            dist = YS.detect_dist()

        if dist == "rhel":
            logging.info("Dump Errata details...")
            dump_errata_list(workdir, offline)

            logging.info("Update package list...")
            dump_detailed_packages_list(workdir, offline, repos)
        else:
            logging.warn(warn_details_msg % dist)

    logging.info("Dump update RPM list from errata data...")
    dump_updates_list(workdir)

    logging.info("Dump dataset file from RPMs and Errata data...")
    dump_datasets(workdir, details)


def option_parser():
    """
    Option parser.
    """
    defaults = dict(path=None, workdir=None, details=False, offline=False,
                    dist=None, repos="", force=False, verbose=False)

    p = optparse.OptionParser("""%prog [Options...] RPMDB_PATH

    where RPMDB_PATH = the path to 'Packages' RPM DB file taken from
                       '/var/lib/rpm' on the target host""")

    p.set_defaults(**defaults)

    p.add_option("-w", "--workdir", help="Working dir [%default]")
    p.add_option("", "--details", action="store_true",
                 help="Get errata details also from RHN / Satellite")
    p.add_option("", "--offline", action="store_true",
                 help="Run swapi on offline mode")
    p.add_option("", "--dist", help="Specify distribution")
    p.add_option("", "--repos",
                 help="Comma separated yum repos to fetch errata info, "
                      "e.g. 'rhel-x86_64-server-6'. Please note that any "
                      "other repos are disabled if this option was set.")
    p.add_option("-f", "--force", action="store_true",
                 help="Force overwrite RPM DB files even if exists already")
    p.add_option("-v", "--verbose", action="store_true", help="Verbose mode")

    return p


def main():
    p = option_parser()
    (options, args) = p.parse_args()

    logging.getLogger().setLevel(DEBUG if options.verbose else INFO)

    if args:
        ppath = args[0]
    else:
        ppath = raw_input("Path to the 'Packages' RPM DB file > ")

    assert os.path.exists(ppath), "RPM DB file looks not exist"

    repos = options.repos.split(',')

    modmain(ppath, options.workdir, options.offline, options.details,
            options.dist, repos, options.force)


if __name__ == '__main__':
    main()

# vim:sw=4:ts=4:et:
