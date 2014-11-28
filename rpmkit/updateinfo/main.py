#
# -*- coding: utf-8 -*-
#
# main module of rpmkit.updateinfo
#
# Copyright (C) 2013 Satoru SATOH <ssato@redhat.com>
# Copyright (C) 2013, 2014 Red Hat, Inc.
#
# License: GPLv3+
#
from rpmkit.globals import _

import rpmkit.updateinfo.yumwrapper
import rpmkit.updateinfo.yumbase
import rpmkit.updateinfo.dnfbase
import rpmkit.updateinfo.utils
import rpmkit.memoize
import rpmkit.utils as U
import rpmkit.swapi

import datetime
import logging
import operator
import os
import os.path
import tablib


LOG = logging.getLogger("rpmkit.updateinfo")
TIMESTAMP = datetime.datetime.now().strftime("%F %T")

_RPM_LIST_FILE = "packages.json"
_ERRATA_LIST_FILE = "errata.json"
_UPDATES_LIST_FILE = "updates.json"

_RPM_KEYS = ("name", "version", "release", "epoch", "arch", "summary",
             "vendor", "buildhost")
_ERRATA_KEYS = ("advisory", "type", "severity")
_UPDATE_KEYS = ("name", "version", "release", "epoch", "arch")
_BZ_KEYS = ("bug_id", "summary", "priority", "severity")

BACKENDS = dict(yumwrapper=rpmkit.updateinfo.yumwrapper.Base,
                yumbase=rpmkit.updateinfo.yumbase.Base,
                dnfbase=rpmkit.updateinfo.dnfbase.Base)
DEFAULT_BACKEND = BACKENDS["yumbase"]

RHBA_KEYWORDS = ["crash", "panic", "hang", "SEGV", "segmentation fault"]


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


def updates_file_path(workdir, filename=_UPDATES_LIST_FILE):
    """
    :param workdir: Working dir to dump the result
    """
    return os.path.join(workdir, filename)


def dataset_file_path(workdir):
    """
    :param workdir: Working dir to dump the result
    :param filename: Output file basename
    """
    return os.path.join(workdir, "errata_summary.xls")


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
    :param cve: A dict represents CVE :: {id:, url:, ...}
    :param cve_cvss_map: A dict :: {cve: cve_and_cvss_data}

    :return: A dict represents CVE and its CVSS metrics
    """
    cveid = cve.get("id", cve.get("cve"))
    dcve = cve_cvss_map.get(cveid)
    if dcve:
        cve.update(**dcve)
        return cve

    dcve = rpmkit.swapi.call("swapi.cve.getCvss", [cveid])
    if dcve:
        dcve = dcve[0]  # :: dict
        dcve["nvd_url"] = dcve["url"]
        dcve["url"] = cve["url"]
    else:
        LOG.warn("Could not get CVSS metrics of %s", cveid)
        dcve = dict(cve=cveid, )

    cve.update(**dcve)
    return cve


def add_cvss_for_errata(errata, cve_cvss_map={}):
    """
    Complement CVSS data for CVE relevant to errata

    :param errata: Basic errata info, {advisory, type, severity, ...}
    :param cve_cvss_map: A dict :: {cve: cve_and_cvss_data}
    """
    cves = errata.get("cves", [])
    if not cves:
        return errata

    errata["cves"] = [get_cve_details(cve, cve_cvss_map) for cve in cves]
    return errata


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
    except Exception as e:
        raise RuntimeError("Wrong CVEs: %s, exc=%s" % (str(cves), str(e)))

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


def _make_cell_data(x, key, default="N/A"):
    if key == "cves":
        cves = x.get("cves", [])
        try:
            return ", ".join(_fmt_cvess(cves)) if cves else default
        except Exception as e:
            raise RuntimeError("Wrong CVEs: %s, exc=%s" % (str(cves), str(e)))

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

_ERRATA_TYPES_MAP = dict(SA="RHSA", BA="RHBA", EA="RHEA")


def classify_errata(errata):
    """Classify errata by its type, RH(SA|BA|EA).

    :param errata: An errata dict

    >>> assert classify_errata(dict(advisory="RHSA-2012:1236")) == "RHSA"
    >>> assert classify_errata(dict(advisory="RHBA-2012:1224")) == "RHBA"
    >>> assert classify_errata(dict(advisory="RHEA-2012:0226")) == "RHEA"
    """
    return _ERRATA_TYPES_MAP[errata["advisory"][2:4]]


def _make_summary_dataset(workdir, rpms, errata, updates, imp_rhsas=[],
                          imp_rhbas=[], score=4.0):
    """
    :param rpms: List of RPM info.
    :param errata: List of Errata info.
    :param updates: List of update RPM info.
    """
    rhsa = [e for e in errata if classify_errata(e) == "RHSA"]
    rhsa_cri = [e for e in rhsa if e.get("severity") == "Critical"]
    rhsa_imp = [e for e in rhsa if e.get("severity") == "Important"]
    rhsa_cri_or_imp = [e for e in rhsa
                       if e.get("severity") in ("Important", "Critical")]
    rhba = [e for e in errata if classify_errata(e) == "RHBA"]
    rhea = [e for e in errata if classify_errata(e) == "RHEA"]
    rpmnames_need_updates = U.uniq(u["name"] for u in updates)
    rpmnames = U.uniq(r["name"] for r in rpms)

    U.json_dump(dict(rhsa=rhsa, rhsa_cri=rhsa_cri, rhsa_imp=rhsa_imp,
                     rhba=rhba, rhea=rhea,
                     important_rhsa=imp_rhsas, important_rhba=imp_rhbas,
                     rpmnames_need_updates=rpmnames_need_updates),
                os.path.join(workdir, "summary.json"))

    ds = [(_("# of Security Errata (critical)"), len(rhsa_cri), "", ""),
          (_("# of Security Errata (important)"), len(rhsa_imp), "", ""),
          (_("# of Security Errata (critical or important)"),
           len(rhsa_cri_or_imp), "", ""),
          (_("# of Security Errata (all)"), len(rhsa), "", ""),
          (_("# of Bug Errata"), len(rhba), "", ""),
          (_("# of Enhancement Errata"), len(rhea), "-", ""),
          (_("# of Installed RPMs"), len(rpms), "", ""),
          (_("# of RPMs (names) need to be updated"),
           len(rpmnames_need_updates), "", ""),
          (_("# of 'Important' Security Errata (CVSS Score >= %.1f)" % score),
           len(imp_rhsas), "", ""),
          (_("# of 'Important' Bug Errata (keyword)"), len(imp_rhbas), "", ""),
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

    :errata: A dict {advisory:, issue_date:, } represents an errata
    :since: Limit date in the formats, YY/MM/DD or YY-MM-DD

    >>> e = dict(advisory="RHBA-2010:0993", issue_date="12/16/10")
    >>> _is_newer_errata(e, None)
    True
    >>> _is_newer_errata(e, "2010-11-01")
    True
    >>> _is_newer_errata(e, "2010/11/01")
    True
    >>> _is_newer_errata(e, "2010-12-16")
    False
    >>> _is_newer_errata(e, "2010-12-31")
    False
    """
    if since is None:
        return True  # Unknown

    (y, m, d) = since.split('-' if '-' in since else '/')
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
                  csekeys=_CVE_SECERRATA_KEYS, cvss_score=4.0,
                  keywords=RHBA_KEYWORDS):
    """
    :param workdir: Working dir to dump the result
    :param start_date: Add an optional worksheet to list only errata newer
        than the date ``start_date``. Along with this, detailed errata info
        will be gotten if this date was not None and a valid date strings.
    """
    datasets = [_make_dataset(rpms, rpmkeys, _("Installed RPMs")),
                _make_dataset(errata, ekeys + ("package_names", ),
                              _("Errata")),
                _make_dataset(updates, ukeys, _("Update RPMs"))]

    eds = _make_dataset(errata, dekeys, _("Errata Details"))

    cseds_title = _("RHSAs - CVSS >= %.1f") % cvss_score
    cses = [e for e in errata if e.get("severity") and e.get("cves", False) and
            any(cve_socre_gt(cve, cvss_score) for cve in e["cves"])]
    cseds = _make_dataset(cses, csekeys, cseds_title)

    ciseds_title = _("Critical or Important RHSAs")
    cises = [e for e in errata
             if e.get("severity") in ("Critical", "Important")]
    cisekeys = ["advisory", "severity", "synopsis", "issue_date", "url"]
    ciseds = _make_dataset(cises, cisekeys, ciseds_title)

    ibeds_title = _("RHBAs selected by keywords")
    ibes = [e for e in errata if any(kw in e["description"] for kw
                                     in keywords)]
    ibeds_keys = ("advisory", "synopsis", "url")
    ibeds = _make_dataset(ibes, ibeds_keys, ibeds_title)

    summary_ds = _make_summary_dataset(workdir, rpms, errata, updates,
                                       cses, ibes)

    special_ds = [summary_ds, cseds, ciseds, ibeds, eds]

    if start_date is not None:
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

        special_ds = [es2, eds2, cseds]

    book = tablib.Databook(special_ds + datasets)

    with open(dataset_file_path(workdir), 'wb') as out:
        out.write(book.xls)


def compute_delta(refdir, errata, updates):
    """
    :param refdir: Dir has reference data files: packages.json, errata.json
        and updates.json
    :param errata: A list of errata
    :param updates: A list of update packages
    """
    emsg = "Reference %s not found: %s"
    assert os.path.exists(refdir), emsg % ("data dir", refdir)

    ref_es_file = os.path.join(refdir, "errata.json")
    ref_us_file = os.path.join(refdir, "updates.json")
    assert os.path.exists(ref_es_file), emsg % ("errata file", ref_es_file)
    assert os.path.exists(ref_us_file), emsg % ("updates file", ref_us_file)

    ref_es_data = U.json_load(ref_es_file)
    ref_us_data = U.json_load(ref_us_file)
    LOG.info("Loaded reference errata and updates file")

    nevra_keys = ("name", "epoch", "version", "release", "arch")
    ref_eadvs = U.uniq(e["advisory"] for e in ref_es_data["data"])
    ref_nevras = U.uniq([p[k] for k in nevra_keys] for p in
                        ref_us_data["data"])

    return ([e for e in errata if e["advisory"] in ref_eadvs],
            [u for u in updates if [u[k] for k in nevra_keys]
             in ref_nevras])


def get_backend(backend, fallback=rpmkit.updateinfo.yumbase.Base,
                backends=BACKENDS):
    LOG.info("Try backend: %s", backend)
    return backends.get(backend, fallback)


def main(root, workdir=None, repos=[], backend=DEFAULT_BACKEND,
         keywords=RHBA_KEYWORDS, refdir=None, backends=BACKENDS, **kwargs):
    """
    :param root: Root dir of RPM db, ex. / (/var/lib/rpm)
    :param workdir: Working dir to save results
    :param repos: List of yum repos to get updateinfo data (errata and updtes)
    :param backend: Backend module to use to get updates and errata
    :param keywords: Keyword list to filter 'important' RHBAs
    :param refdir: A dir holding reference data previously generated to
        compute delta (updates since that data)
    :param backends: Backend list
    """
    if not rpmkit.updateinfo.utils.check_rpmdb_root(root, True):
        raise RuntimeError("Not a root of RPM DB: %s" % root)

    if workdir is None:
        LOG.info("Set workdir to root: %s", root)
        workdir = root
    else:
        if not os.path.exists(workdir):
            LOG.info("Creating working dir: %s", workdir)
            os.makedirs(workdir)

    base = get_backend(backend)(root, repos, workdir=workdir)
    LOG.info("root=%s, workdir=%s, repos=%s", root, workdir, ','.join(repos))

    LOG.info("Dump metadata first...")
    U.json_dump(dict(root=root, repos=repos, backend=str(backend),
                     keywords=keywords, refdir=refdir,
                     generated=TIMESTAMP),
                os.path.join(workdir, "metadata.json"))

    LOG.info("Dump Installed RPMs list loaded from: %s", base.root)
    ips = sorted(base.list_installed(),
                 key=operator.itemgetter("name", "epoch", "version",
                                         "release"))
    LOG.info("%d Installed RPMs found", len(ips))
    U.json_dump(dict(data=ips, ), rpm_list_path(base.workdir))

    LOG.info("Dump Errata list...")
    es = [add_cvss_for_errata(e, mk_cve_vs_cvss_map()) for e
          in base.list_errata()]
    LOG.info("%d Errata found for installed rpms", len(es))
    U.json_dump(dict(data=es, ), errata_list_path(base.workdir))

    LOG.info("Dump Update RPMs list...")
    us = base.list_updates()
    LOG.info("%d Update RPMs found for installed rpms", len(us))
    U.json_dump(dict(data=us, ), updates_file_path(base.workdir))

    if refdir:
        LOG.info("Computing delta errata and updates for data in %s", refdir)
        (es, us) = compute_delta(refdir, es, us)

        LOG.info("%d Delta Errata found for installed rpms", len(es))
        U.json_dump(dict(data=es, ), errata_list_path(base.workdir,
                                                      "errata_delta.json"))

        LOG.info("%d Delta Update RPMs found for installed rpms", len(us))
        U.json_dump(dict(data=us, ), updates_file_path(base.workdir,
                                                       "updates_delta.json"))

    es = sorted(es, cmp=rpmkit.updateinfo.utils.cmp_errata)
    us = sorted(us, key=operator.itemgetter("name", "epoch", "version",
                                            "release"))

    LOG.info("Dump dataset file from RPMs and Errata data...")
    dump_datasets(workdir, ips, es, us)

# vim:sw=4:ts=4:et:
