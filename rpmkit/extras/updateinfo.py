#
# -*- coding: utf-8 -*-
#
# updateinfo.py - collect info of updates and errata applicable to the target
# system with referering its rpm database files and utilizing swapi and
# yum-surrogate.
#
# Copyright (C) 2013 Satoru SATOH <ssato@redhat.com>
# Copyright (C) 2013 Red Hat, Inc.
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
from rpmkit.globals import DEBUG, INFO, _
from operator import attrgetter, itemgetter

import rpmkit.globals as RG
import rpmkit.memoize as M
import rpmkit.rpmutils as RU
import rpmkit.utils as U
import rpmkit.swapi as SW
import rpmkit.yum_surrogate as YS

import datetime
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
_SUMMARY_FILE = "summary.json"
_XLS_FILE = "errata_summary.xls"

_RPM_KEYS = ("name", "version", "release", "epoch", "arch", "summary",
             "vendor", "buildhost")
_ERRATA_KEYS = ("advisory", "type", "severity")
_UPDATE_KEYS = ("name", "version", "release", "epoch", "arch", "advisories")
_BZ_KEYS = ("bug_id", "summary", "priority", "severity")


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
    d["package_names"] = ", ".join(p["name"] for p in packages)

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


_BZ_URL_FMT = "https://bugzilla.redhat.com/show_bug.cgi?id=%s"


def _update_bz(bz, fmt=_BZ_URL_FMT, heuristics=False):
    bz["id"] = bz["bug_id"]
    bz["url"] = fmt % bz["id"]
    bz["heuristics"] = 1 if heuristics else 0

    return bz


def get_bz_details(bzid, offline=False, bzkeys=_BZ_KEYS):
    """
    Get bugzilla info for given `bzid` w/ using swapi's virtual API.

    :param bzid: Bugzilla ID
    :param offline: True if get results only from local cache
    :param bzkeys: Bugzilla keys to get bugzilla info when details is True

    :return: A dict contains bugzilla ticket's info :: dict
    """
    return swapicall("swapi.bugzilla.getDetails", offline,
                     [bzid] + list(bzkeys))[0]


def get_bzs_from_errata_desc_g(errata_desc, offline=False, bzkeys=_BZ_KEYS,
                               bz_details=False, urlfmt=_BZ_URL_FMT):
    """
    Get list of bugzilla tickets' info from errata' description w/ using some
    heuristics.

    :param errata_details: Description of target errata
    :param offline: True if get results only from local cache
    :param bzkeys: Bugzilla keys to get bugzilla info when details is True
    :param bz_details: Get bugzilla detailed info if True
    """
    candidates = re.findall(r"(?:RH)*(?:BZ|bz)#(\d+)", errata_desc)
    for bzid in candidates:
        try:
            if bz_details:
                bz = get_bz_details(bzid, offline, bzkeys)
                if not bz:
                    logging.warn("Failed to get BZ info: " + bzid)
                    continue

                #print "*** bz=" + str(bz)
                yield _update_bz(bz, heuristics=True)
            else:
                yield dict(id=bzid, bug_id=bzid, url=urlfmt % bzid,
                           heuristics=1)

        except Exception as e:
            m = " Failed to get the bz info (bz#%s), exc=%s" % (bzid, e)
            logging.warn(m)


def get_errata_details(errata, workdir, offline=False, bzkeys=_BZ_KEYS,
                       bz_details=True, use_map=False):
    """
    Get errata details with using swapi (RHN hosted or satellite).

    :param errata: Basic errata info, {advisory, type, severity, ...}
    :param offline: True if get results only from local cache
    :param bzkeys: Bugzilla keys to get bugzilla info when details is True
    :param bz_details: Get bugzilla detailed info if True
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

    try:
        fmt = "https://bugzilla.redhat.com/show_bug.cgi?id=%s"
        bzs = swapicall("errata.bugzillaFixes", offline, adv)[0]  # :: dict

        # NOTE: 'errata.bugzillaFixes' may return [{}] if bugzilla tickets
        # relevant to errata was not found.
        if bzs:
            if bz_details:
                bzs = [_update_bz(get_bz_details(k, offline, bzkeys)) for k
                       in bzs.keys()]
            else:
                bzs = [dict(id=k, bug_id=k, summary=v[2:-2], url=fmt % k)
                       for k, v in bzs.iteritems()]
        else:
            m = "Failed to get bzs w/ RHN API relevant to " + adv
            logging.debug(m + ". So try to get them by some heuristics.")

            bzs = list(get_bzs_from_errata_desc_g(errata["description"],
                                                  offline, bzkeys, bz_details))

        errata["bzs"] = bzs

    except Exception as e:
        m = "Failed to get related bugzilla info %s, exc=%s" % (adv, e)
        logging.warn(m)
        errata["bzs"] = []

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


def dump_errata_list(workdir, offline=False, bzkeys=_BZ_KEYS, bz_details=True,
                     ref_filename=_ERRATA_SUMMARY_FILE,
                     filename=_ERRATA_LIST_FILE):
    """
    :param workdir: Working dir to dump the result
    :param offline: True if get results only from local cache
    :param bzkeys: Bugzilla keys to get bugzilla info when details is True
    :param bz_details: Get bugzilla detailed info if True
    :param ref_filename: Errata summary list as a reference
    :param filename: Output file basename
    """
    es = U.json_load(errata_summary_path(workdir, ref_filename))

    def _g(es):
        for ref_e in es:
            yield get_errata_details(ref_e, workdir, offline, bzkeys,
                                     bz_details)

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


def _make_cell_data(x, key, default="N/A"):
    if key == "cves":
        cves = x.get("cves", [])
        return ", ".join(_fmt_cvess(cves)) if cves else default

    elif key == "bzs":
        bzs = x.get("bzs", [])
        return ", ".join(_fmt_bzs(bzs)) if bzs else default

    else:
        v = x.get(key, default)
        return ", ".join(v) if isinstance(v, (list, tuple)) else v


def _make_dataset(list_data, headers=None, title=None):
    """
    :param list_data: List of data
    :param headers: Dataset headers to be used as column headers
    :param title: Dataset title to be used as worksheet's name
    """
    dataset = tablib.Dataset()

    # TODO: Check title as valid worksheet name, ex. len(title) <= 31. 
    # See also xlwt.Utils.valid_sheet_name.
    if title:
        dataset.title = title

    if headers:
        dataset.headers = headers

        for x in list_data:
            dataset.append([_make_cell_data(x, h) for h in headers])
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
                         "update_date", "url", "cves", "bzs"]


def _fmt_cvess(cves):
    """
    :param cves: List of CVE dict {cve, score, url, metrics} or str "cve".
    :return: List of CVE strings
    """
    try:
        fmt = '%(cve)s (score=%(score)s, metrics=%(metrics)s, url=%(url)s)'
        cves = [fmt % c for c in cves]
    except KeyError:
        pass

    return cves


def _fmt_bzs(bzs):
    """
    :param cves: List of CVE dict {cve, score, url, metrics} or str "cve".
    :return: List of CVE strings
    """
    def _fmt(bz):
        if "summary" in bz:
            return "bz#%(id)s: %(summary)s (%(url)s"
        else:
            return "bz#%(id)s (%(url)s"

    try:
        bzs = [_fmt(bz) % bz for bz in bzs]
    except KeyError:
        logging.warn("BZ Key error: " + str(bzs))
        pass

    return bzs


def _detailed_errata_list_g(workdir):
    es = U.json_load(errata_list_path(workdir))
    default = "N/A"

    for e in es:
        if e["severity"] is None:
            e["severity"] = default

        yield e


def _updates_list_g(workdir, ukeys=_UPDATE_KEYS):
    data = U.json_load(updates_file_path(workdir))

    for u in data["updates"]:
        u["advisories"] = ", ".join(u["advisories"])
        yield u


_ERRATA_TYPES_MAP = dict(SA="RHSA", BA="RHBA", EA="RHEA")


def classify_errata(errata):
    """Classify errata by its type, RH(SA|BA|EA).

    :param errata: An errata dict

    >>> assert classify_errata(dict(advisory="RHSA-2012:1236")) == "RHSA"
    >>> assert classify_errata(dict(advisory="RHBA-2012:1224")) == "RHBA"
    >>> assert classify_errata(dict(advisory="RHEA-2012:0226")) == "RHEA"
    """
    return _ERRATA_TYPES_MAP[errata["advisory"][2:4]]


def _make_summary_dataset(workdir, rpms, errata, updates,
                          filename=_SUMMARY_FILE):
    """
    :param rpms: List of RPM info.
    :param errata: List of Errata info.
    :param updates: List of update RPM info.
    """
    rhsa = [e for e in errata if classify_errata(e) == "RHSA"]
    rhsa_cri = [e for e in rhsa if e.get("severity") == "Critical"]
    rhsa_imp = [e for e in rhsa if e.get("severity") == "Important"]
    rhba = [e for e in errata if classify_errata(e) == "RHBA"]
    rhea = [e for e in errata if classify_errata(e) == "RHEA"]
    rpmnames_need_updates = U.uniq(u["name"] for u in updates)
    rpmnames = U.uniq(r["name"] for r in rpms)

    U.json_dump(dict(rhsa=rhsa, rhsa_cri=rhsa_cri, rhsa_imp=rhsa_imp,
                     rhba=rhba, rhea=rhea,
                     rpmnames_need_updates=rpmnames_need_updates),
                os.path.join(workdir, filename))

    ds = [(_("# of Security Errata (critical)"), len(rhsa_cri), "", ""),
          (_("# of Security Errata (important)"), len(rhsa_imp), "", ""),
          (_("# of Security Errata (all)"), len(rhsa), "", ""),
          (_("# of Bug Errata"), len(rhba), "", ""),
          (_("# of Enhancement Errata"), len(rhea), "-", ""),
          (_("# of Installed RPMs"), len(rpms), "", ""),
          (_("# of RPMs (names) need to be updated"),
           len(rpmnames_need_updates), "", ""),
          (_("The rate of RPMs (names) need any updates / RPMs (names) [%]"),
           100 * len(rpmnames_need_updates) / len(rpmnames), "", "")]

    dataset = tablib.Dataset()
    dataset.title = _("Summary")
    dataset.headers = (_("item"), _("value"), _("rating"), _("comments"))

    for d in ds:
        dataset.append(d)

    return dataset


def _date_from_errata_issue_data(date_s):
    """
    NOTE: Errata issue_date and update_date format: month/day/year,
        e.g. 12/16/10.

    >>> _date_from_errata_issue_data("12/16/10")
    (2010, 12, 16)
    """
    (m, d, y) = date_s.split('/')
    return (int("20" + y), int(m), int(d))


def _is_newer_errata(errata, since=None):
    """
    NOTE: issue_date format: month/day/year, e.g. 12/16/10

    >>> e = dict(advisory="RHBA-2010:0993", issue_date="12/16/10")
    >>> _is_newer_errata(e, None)
    True
    >>> _is_newer_errata(e, "2010-11-01")
    True
    >>> _is_newer_errata(e, "2010-12-16")
    False
    >>> _is_newer_errata(e, "2010-12-31")
    False
    """
    if since is None:
        return True  # Unknown

    (y, m, d) = since.split('-')
    (y, m, d) = (int(y), int(m), int(d))
    #logging.debug("Try to check the errata is newer than "
    #              "y=%d, m=%d, d=%d" % (y, m, d))

    # Set to dummy and old enough date if failed to get issue_date.
    issue_date = errata.get("issue_date", "1900-01-01")
    (e_y, e_m, e_d) = _date_from_errata_issue_data(issue_date)
    #logging.debug("Issue date of the errata: y=%d, m=%d, d=%d" % (e_y, e_m,
    #                                                              e_d))

    if e_y < y:
        return False
    elif e_y > y:
        return True
    else:
        if e_m < m:
            return False
        elif e_m > m:
            return True
        else:
            if e_m < m or (e_m == m and e_d <= d):
                return False

    return True


def cve_socre_gt(cve, score=4.0, default=False):
    """
    :param cve: A dict contains CVE and CVSS info.
    :param score: Lowest score to select CVEs (float). It's Set to 4.0 (PCIDSS
        limit) by default:

        * NVD Vulnerability Severity Ratings: http://nvd.nist.gov/cvss.cfm
        * PCIDSS: https://www.pcisecuritystandards.org

    :param default: Default value if failed to get CVSS score to compare with
        given score

    :return: True if given CVE's socre is greater or equal to given score.
    """
    try:
        return float(cve["score"]) >= score
    except Exception as e:
        logging.warn("Failed to compare CVE's score: %s, score=%.1f" % \
            (str(cve), score))

    return default


_CVE_SECERRATA_KEYS = ["advisory", "severity", "cves", "synopsis",
                       "issue_date", "url"]


def make_cve_sec_errata_dataset(workdir, csekeys=_CVE_SECERRATA_KEYS,
                                cvss_score=4.0):
    """
    """
    es = U.json_load(errata_list_path(workdir))
    cses = [e for e in es if e.get("cves", False) and
            any(cve_socre_gt(cve, cvss_score) for cve in e["cves"])]
    cseds_title = _("Sec. Errata CVSS >= %.1f") % cvss_score
    cseds = _make_dataset(cses, csekeys, cseds_title)


def dump_datasets(workdir, details=False, rpmkeys=_RPM_KEYS,
                  ekeys=_ERRATA_KEYS, dekeys=_DETAILED_ERRATA_KEYS,
                  ukeys=_UPDATE_KEYS, start_date=None,
                  csekeys=_CVE_SECERRATA_KEYS, cvss_score=4.0):
    """
    :param workdir: Working dir to dump the result
    :param start_date: Add an optional worksheet to list only errata newer
        than the date ``start_date``. Along with this, detailed errata info
        will be gotten if this date was not None and a valid date strings.
    """
    rpms = U.json_load(rpm_list_path(workdir))
    errata = U.json_load(errata_summary_path(workdir))
    updates = [u for u in _updates_list_g(workdir, ukeys)]

    datasets = [_make_summary_dataset(workdir, rpms, errata, updates),
                _make_dataset(rpms, rpmkeys, _("Installed RPMs")),
                _make_dataset(errata, ekeys + ("package_names", ),
                              _("Errata")),
                _make_dataset(updates, ukeys, _("Update RPMs"))]

    if details or start_date is not None:
        extra_ds = []

        es = [x for x in _detailed_errata_list_g(workdir)]
        eds = _make_dataset(es, dekeys, _("Errata Details"))

        cses = [e for e in es if e.get("cves", False) and
                any(cve_socre_gt(cve, cvss_score) for cve in e["cves"])]
        cseds_title = _("Sec. Errata CVSS >= %.1f") % cvss_score
        cseds = _make_dataset(cses, csekeys, cseds_title)

        extra_ds = [eds, cseds]

        if start_date is None:
            book = tablib.Databook(datasets + extra_ds)
        else:
            es = [e for e in es if _is_newer_errata(e, start_date)]
            eds2 = _make_dataset(es, dekeys,
                                 _("Errata Details (%s ~)") % start_date)

            cses = [e for e in es if e.get("cves", []) and
                    any(cve_socre_gt(cve, cvss_score) for cve in e["cves"])]
            cseds = _make_dataset(cses, csekeys, cseds_title)

            es_diff = [e["advisory"] for e in es]
            errata = [e for e in errata if e["advisory"] in es_diff]
            es2 = _make_dataset(errata, ekeys + ("package_names", ),
                                _("Errata (%s ~)") % start_date)

            extra_ds = [es2, eds2, cseds]
            book = tablib.Databook(extra_ds + datasets)
    else:
        book = tablib.Databook(datasets)

    with open(dataset_file_path(workdir), 'wb') as out:
        out.write(book.xls)


_WARN_DETAILS_NOT_AVAIL = """\
Detailed errata and packages information of the detected distribution %s
is not supported. So it will disabled this feature."""


def modmain(ppath, workdir=None, offline=False, details=False, dist=None,
            repos=[], force=False, rpmkeys=_RPM_KEYS, bzkeys=_BZ_KEYS,
            bz_details=True, start_date=None, verbose=False,
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
    :param bzkeys: Bugzilla keys to get bugzilla info when details is True
    :param bz_details: Get bugzilla detailed info if True
    :param start_date: Add an optional worksheet to list only errata newer
        than the date ``start_date``
    :param verbose: Verbose mode
    """
    logging.getLogger().setLevel(DEBUG if verbose else INFO)

    if not ppath:
        ppath = raw_input(_("Path to the RPM DB 'Packages' > "))

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
            dump_errata_list(workdir, offline, bzkeys, bz_details)

            logging.info("Update package list...")
            dump_detailed_packages_list(workdir, offline, repos)
        else:
            logging.warn(warn_details_msg % dist)

    logging.info("Dump update RPM list from errata data...")
    dump_updates_list(workdir)

    logging.info("Dump dataset file from RPMs and Errata data...")
    dump_datasets(workdir, details, start_date=start_date)


def option_parser():
    """
    Option parser.
    """
    defaults = dict(path=None, workdir=None, details=False, offline=False,
                    dist=None, repos="", force=False, verbose=False,
                    bzkeys=None, bz_details=False, start_date=None)

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

    p.add_option("", "--bzkeys",
                 help="Comma separated bugzilla keys. "
                      "Choices are " + ','.join(_BZ_KEYS))
    p.add_option("", "--bz-details", action="store_true",
                 help="Get detailed bugzilla info relevant to each errata "
                      "if True. You should run 'bugzilla login' in advance."
                      "(bugzilla command is in python-bugzilla RPMs)")
    p.add_option("", "--since",
                 help="Specified the date in YYYY-MM-DD format to generate "
                      "the worksheet to list only errata issued since given "
                      "date; ex. '--since 2013-06-10'")

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

    if options.bzkeys:
        options.bzkeys = options.bzkeys.split(',')

    repos = options.repos.split(',')

    modmain(ppath, options.workdir, options.offline, options.details,
            options.dist, repos, options.force, bzkeys=options.bzkeys,
            bz_details=options.bz_details, start_date=options.since,
            verbose=options.verbose)


if __name__ == '__main__':
    main()

# vim:sw=4:ts=4:et:
