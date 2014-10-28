#
# -*- coding: utf-8 -*-
#
# CLI for rpmkit.updateinfo
#
# Copyright (C) 2013 Satoru SATOH <ssato@redhat.com>
# Copyright (C) 2013, 2014 Red Hat, Inc.
#
# License: GPLv3+
#
from rpmkit.globals import _

import rpmkit.updateinfo.yumwrapper
import rpmkit.updateinfo.utils
import rpmkit.memoize
import rpmkit.utils as U
import rpmkit.swapi

import logging
import optparse
import os
import os.path
import tablib


LOG = logging.getLogger("rpmkit.updateinfo.cli")

_RPM_LIST_FILE = "packages.json"
_ERRATA_LIST_FILE = "errata.json"
_UPDATES_LIST_FILE = "updates.json"

_RPM_KEYS = ("name", "version", "release", "epoch", "arch", "summary",
             "vendor", "buildhost")
_ERRATA_KEYS = ("advisory", "type", "severity")
_UPDATE_KEYS = ("name", "version", "release", "epoch", "arch", "advisories")
_BZ_KEYS = ("bug_id", "summary", "priority", "severity")

BACKENDS = dict(yumwrapper=rpmkit.updateinfo.yumwrapper,
                yum=rpmkit.updateinfo.yumbase,
                dnf=rpmkit.updateinfo.dnfbase)


def rpm_list_path(workdir, filename=_RPM_LIST_FILE):
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


def errata_cve_map_path(workdir):
    """
    :param workdir: Working dir to dump the result
    """
    return os.path.join(workdir, "errata_cve_map.json")


def dataset_file_path(workdir):
    """
    :param workdir: Working dir to dump the result
    :param filename: Output file basename
    """
    return os.path.join(workdir, "errata_summary.xls")


def updates_file_path(workdir, filename=_UPDATES_LIST_FILE):
    """
    :param workdir: Working dir to dump the result
    """
    return os.path.join(workdir, filename)


def mk_cve_vs_cvss_map():
    """
    Make up CVE vs. CVSS map w/ using swapi's virtual APIs.

    :return: A list of CVE details :: {cve: {cve, url, score, metrics}, }
    """
    return dict((c["cve"], c) for c in
                rpmkit.swapi.call("swapi.cve.getAll") if c)


@rpmkit.memoize.memoize
def get_cve_details(cve, cve_cvss_map={}):
    """
    :param cve: CVE ID, ex. CVE-2014-3660
    :param cve_cvss_map: A dict :: {cve: cve_and_cvss_data}

    :return: A dict represents CVE and its CVSS metrics
    """
    dcve = cve_cvss_map.get(cve)
    if dcve:
        return dcve

    dcve = rpmkit.swapi.call("swapi.cve.getCvss", [cve])
    if dcve:
        dcve = dcve[0]  # :: dict
    else:
        LOG.warn("Could not get CVSS metrics of %s", cve)
        dcve = dict(cve=cve, )

    return dcve


def add_cvss_for_errata(errata, cve_cvss_map={}):
    """
    Complement CVSS data for CVE relevant to errata

    :param errata: Basic errata info, {advisory, type, severity, ...}
    :param cve_cvss_map: A dict :: {cve: cve_and_cvss_data}
    """
    adv = errata["advisory"]
    cves = errata.get("cves", [])

    if not adv.startswith("RHSA") or not cves:
        return errata

    errata["cves"] = [get_cve_details(cve, cve_cvss_map) for cve in cves]

    return errata


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


_DETAILED_ERRATA_KEYS = ["advisory", "type", "severity", "synopsis",
                         "description", "issue_date", "update_date",
                         "url", "cves", "bzs"]


def _fmt_cve(cve):
    if 'score' in cve:
        return '%(cve)s (score=%(score)s, metrics=%(metrics)s, url=%(url)s)'
    else:
        return '%(cve)s (CVSS=N/A)'


def _fmt_cvess(cves):
    """
    :param cves: List of CVE dict {cve, score, url, metrics} or str "cve".
    :return: List of CVE strings
    """
    try:
        cves = [_fmt_cve(c) % c for c in cves]
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
        LOG.warn("BZ Key error: " + str(bzs))
        pass

    return bzs


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


def _make_summary_dataset(workdir, rpms, errata, updates):
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
                os.path.join(workdir, "summary.json"))

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
    # LOG.debug("Try to check the errata is newer than "
    #              "y=%d, m=%d, d=%d" % (y, m, d))

    # Set to dummy and old enough date if failed to get issue_date.
    issue_date = errata.get("issue_date", "1900-01-01")
    (e_y, e_m, e_d) = _date_from_errata_issue_data(issue_date)
    # LOG.debug("Issue date of the errata: y=%d, m=%d, d=%d" % (e_y, e_m,
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
    except Exception:
        LOG.warn("Failed to compare CVE's score: %s, score=%.1f",
                 str(cve), score)

    return default


_CVE_SECERRATA_KEYS = ["advisory", "severity", "cves", "synopsis",
                       "issue_date", "url"]


def dump_datasets(workdir, rpms, errata, updates, rpmkeys=_RPM_KEYS,
                  ekeys=_ERRATA_KEYS, dekeys=_DETAILED_ERRATA_KEYS,
                  ukeys=_UPDATE_KEYS, start_date=None,
                  csekeys=_CVE_SECERRATA_KEYS, cvss_score=4.0):
    """
    :param workdir: Working dir to dump the result
    :param start_date: Add an optional worksheet to list only errata newer
        than the date ``start_date``. Along with this, detailed errata info
        will be gotten if this date was not None and a valid date strings.
    """
    datasets = [_make_summary_dataset(workdir, rpms, errata, updates),
                _make_dataset(rpms, rpmkeys, _("Installed RPMs")),
                _make_dataset(errata, ekeys + ("package_names", ),
                              _("Errata")),
                _make_dataset(updates, ukeys, _("Update RPMs"))]

    extra_ds = []

    eds = _make_dataset(errata, dekeys, _("Errata Details"))

    cses = [e for e in errata if e.get("cves", False) and
            any(cve_socre_gt(cve, cvss_score) for cve in e["cves"])]
    cseds_title = _("Sec. Errata CVSS >= %.1f") % cvss_score
    cseds = _make_dataset(cses, csekeys, cseds_title)

    extra_ds = [eds, cseds]

    if start_date is None:
        book = tablib.Databook(datasets + extra_ds)
    else:
        es = [e for e in errata if _is_newer_errata(e, start_date)]
        eds2 = _make_dataset(es, dekeys,
                             _("Errata Details (%s ~)") % start_date)

        cses = [e for e in es if e.get("cves", []) and
                any(cve_socre_gt(cve, cvss_score) for cve in e["cves"])]
        cseds = _make_dataset(cses, csekeys, cseds_title)

        es_diff = [e["advisory"] for e in es]
        errata = [e for e in es if e["advisory"] in es_diff]
        es2 = _make_dataset(errata, ekeys + ("package_names", ),
                            _("Errata (%s ~)") % start_date)

        extra_ds = [es2, eds2, cseds]
        book = tablib.Databook(extra_ds + datasets)

    with open(dataset_file_path(workdir), 'wb') as out:
        out.write(book.xls)


def modmain(root, workdir=None, repos=[], backend="yumwrapper", verbose=False,
            **kwargs):
    """
    :param root: Root dir of RPM db, ex. / (/var/lib/rpm)
    :param repos: List of yum repos to get updateinfo data (errata and updtes)
    :param backend: Backend module to use to get updates and errata
    :param verbose: Verbose mode
    """
    global LOG
    LOG.setLevel(logging.DEBUG if verbose else logging.INFO)

    if rpmkit.updateinfo.utils.check_rpmdb_root(root, True):
        raise RuntimeError("Not a root of RPM DB: %s" % root)

    if workdir is None:
        LOG.info("Set workdir to root: %s", root)
        workdir = root
    else:
        if not os.path.exists(workdir):
            LOG.info("Creating working dir: %s", workdir)
            os.makedirs(workdir)

    base = rpmkit.updateinfo.yumwrapper.Base(root, repos, workdir=workdir)

    LOG.info("Dump Installed RPMs list loaded from: %s", base.root)
    ips = base.list_installed(mark_extras=True)
    LOG.info("%d Installed RPMs found", len(ips))
    U.json_dump(dict(data=ips, ), rpm_list_path(base.workdir))

    LOG.info("Dump Errata list...")
    cvemap = mk_cve_vs_cvss_map()
    es = [add_cvss_for_errata(e, cvemap) for e in base.list_errata()]
    LOG.info("%d Errata found for installed rpms", len(es))
    U.json_dump(dict(data=es, ), errata_list_path(base.workdir))

    LOG.info("Dump Update RPMs list...")
    us = base.list_updates()
    LOG.info("%d Update RPMs found for installed rpms", len(es))
    U.json_dump(dict(data=us, ), updates_file_path(base.workdir))

    LOG.info("Dump dataset file from RPMs and Errata data...")
    dump_datasets(workdir, ips, es, us)


def option_parser():
    defaults = dict(path=None, workdir=None, repos=[], backend="yumwrapper",
                    verbose=False)

    p = optparse.OptionParser("""%prog [Options...] RPMDB_ROOT

    where RPMDB_ROOT = RPM DB root having var/lib/rpm from the target host""")

    p.set_defaults(**defaults)

    p.add_option("-w", "--workdir", help="Working dir [%default]")
    p.add_option("", "--repo", dest="repos",
                 help="Comma separated yum repos to fetch errata info, "
                      "e.g. 'rhel-x86_64-server-6'. Please note that any "
                      "other repos are disabled if this option was set.")
    p.add_option("-B", "--backend", choices=BACKENDS.keys(),
                 help="Specify backend to get updates and errata. Choices: "
                      "%s [%%default]" % ', '.join(BACKENDS.keys()))
    p.add_option("-v", "--verbose", action="store_true", help="Verbose mode")

    return p


def main():
    p = option_parser()
    (options, args) = p.parse_args()

    root = args[0] if args else raw_input("Root of RPM DB files > ")
    assert os.path.exists(root), "Not found RPM DB Root: %s" % root

    modmain(root, options.workdir, repos=options.repos,
            verbose=options.verbose)


if __name__ == '__main__':
    main()

# vim:sw=4:ts=4:et:
