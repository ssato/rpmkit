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

try:
    from jinja2_cli.render import render
    _JINJA2_CLI = True
except ImportError:
    def render(*args, **kwargs):
        pass

    _JINJA2_CLI = False

try:
    from tablib import Dataset, Databook
except ImportError:
    Dataset = Databook = None


_RPM_LIST_FILE = "packages.json"
_ERRATA_SUMMARY_FILE = "errata_summary.json"
_ERRATA_LIST_FILE = "errata.json"
_ERRATA_CVE_MAP_FILE = "errata_cve_map.json"
_UPDATES_FILE = "updates.json"
_XLS_FILE = "packages_and_errata_summary.xls"

_RPM_KEYS = ("name", "version", "release", "epoch", "arch", "buildhost")
_ERRATA_KEYS = ("advisory", "type", "severity")
_UPDATE_KEYS = ("name", "version", "release", "epoch", "arch", "advisories")

_TEMPLATE_PATHS = [os.curdir, "/usr/share/rpmkit/templates"]


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


def export_rpm_list(root, rpmkeys=_RPM_KEYS):
    """
    :param root: RPM DB top dir where ``subdir`` exists
    :param rpmkeys: RPM dict keys

    :return: The list of RPM package (NVREA) ::
             [{name, version, release, epoch, arch}]
    """
    return RU.list_installed_rpms(root, rpmkeys)


def dump_rpm_list(root, workdir, filename=_RPM_LIST_FILE):
    """
    :param root: RPM DB top dir
    :param workdir: Working dir to dump the result
    :param filename: Output file basename
    """
    rpms = export_rpm_list(root)
    logging.debug("%d installed rpms found in %s" % (len(rpms), root))

    json.dump(rpms, open(rpm_list_path(workdir, filename), 'w'))


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
    ...        u'version': u'7.19.7'}])
    >>> d = _mkedic(e, ps)
    """
    pkeys = ("name", "version", "release", "epoch", "arch")

    d = dict(zip(ekeys, errata))
    d["packages"] = [dict(zip(pkeys, itemgetter(*pkeys)(p))) for p in packages]

    return d


def dump_errata_summary(root, workdir, filename=_ERRATA_SUMMARY_FILE,
                        ekeys=_ERRATA_KEYS):
    """
    :param root: RPM DB top dir
    :param workdir: Working dir to dump the result
    :param filename: Output file basename
    """
    logfiles = (os.path.join(workdir, "errata_summary_output.log"),
                os.path.join(workdir, "errata_summary_error.log"))

    es = sorted((e for e in YS.list_errata_g(root, logfiles=logfiles)),
                key=itemgetter("advisory"))

    es = [_mkedic(e, ps) for e, ps in U.groupby_key(es, itemgetter(*ekeys))]
    json.dump(es, open(errata_summary_path(workdir, filename), 'w'))


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
    cve_ref_path = errata_cve_map_path(workdir)

    if os.path.exists(cve_ref_path):
        errata_cves_map = json.load(open(cve_ref_path))
    else:
        logging.info("Make up errata - cve - cvss map data from RHN...")
        errata_cves_map = mk_errata_map(offline)

        logging.info("Dumping errata - cve - cvss map data from RHN...")
        json.dump(errata_cves_map, open(cve_ref_path, 'w'))
        #assert bool(errata_cves_map), "errata_cache=" + errata_cache

    adv = errata["advisory"]

    ed = swapicall("errata.getDetails", offline, adv)[0]
    errata.update(ed)

    if adv.startswith("RHSA"):
        # FIXME: Errata - CVE map looks sometimes not enough.
        if use_map:
            errata["cves"] = errata_cves_map.get(adv, [])
        else:
            try:
                errata["cves"] = swapicall("errata.listCves", offline, adv)[0]
            except IndexError:
                logging.warn("Could not get relevant CVEs of errata: " + adv)
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
    es = json.load(open(errata_summary_path(workdir, ref_filename)))

    def _g(es):
        for ref_e in es:
            yield get_errata_details(ref_e, workdir, offline)

    errata = sorted((e for e in _g(es)), key=itemgetter("advisory"))
    json.dump(errata, open(errata_list_path(workdir), 'w'))


def _make_dataset(list_data, headers=None, title=None):
    """
    :param list_data: List of data
    :param headers: Dataset headers to be used as column headers
    :param headers: Dataset title to be used as worksheet's name
    """
    dataset = Dataset()

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


def dump_updates_list(workdir, rpmkeys=_MIN_RPM_KEYS):
    """
    :param workdir: Working dir to dump the result
    :param format: Output format: xls, xlsx or ods
    """
    errata = json.load(open(errata_summary_path(workdir)))
    updates = dict()
    p2k = itemgetter(*rpmkeys)

    for e in errata:
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

    # Make it valid JSON data. (It seems simple array isn't valid.)
    us = sorted(updates.values(), key=itemgetter("name"))
    data = dict(updates=us)

    json.dump(data, open(updates_file_path(workdir), 'w'))


_DETAILED_ERRATA_KEYS = ("advisory", "type", "severity", "synopsis",
                         "description", "issue_date", "last_modified_date",
                         "update_date", "url")  # TODO: CVEs


def _detailed_errata_list_g(workdir, edkeys=_DETAILED_ERRATA_KEYS):
    es = json.load(open(errata_list_path(workdir)))

    for e in es:
        x = dict(zip(edkeys, itemgetter(*edkeys)(e)))

        if x["severity"] is None:
            x["severity"] = "N/A"

        if x.get("cves", False):
            cves = ['"%(cve)s (%(score)s %(url)s)"' % c for c in x["cves"]]
            x["cves"] = ", ".join(cves)
        else:
            x["cves"] = "N/A"

        yield x


def _updates_list_g(workdir, ukeys=_UPDATE_KEYS):
    data = json.load(open(updates_file_path(workdir)))

    for u in data["updates"]:
        u["advisories"] = ", ".join(u["advisories"])
        yield u


def dump_datasets(workdir, details=False, rpmkeys=_RPM_KEYS,
                  ekeys=_ERRATA_KEYS, dekeys=_DETAILED_ERRATA_KEYS,
                  ukeys=_UPDATE_KEYS):
    """
    :param workdir: Working dir to dump the result
    """
    rpms = json.load(open(rpm_list_path(workdir)))
    errata = json.load(open(errata_summary_path(workdir)))
    updates = [u for u in _updates_list_g(workdir, ukeys)]

    datasets = [_make_dataset(rpms, rpmkeys, "Installed RPMs"),
                _make_dataset(errata, ekeys, "Errata"),
                _make_dataset(updates, ukeys, "Update RPMs")]

    if details:
        des = [x for x in _detailed_errata_list_g(workdir)]
        des_dataset = _make_dataset(des, dekeys, "Errata Details")

        book = Databook(datasets + [des_dataset])
    else:
        book = Databook(datasets)

    with open(dataset_file_path(workdir), 'wb') as out:
        out.write(book.xls)


def gen_depgraph(root, workdir, template_paths=_TEMPLATE_PATHS,
                 engine="twopi"):
    """
    Generate dependency graph with using graphviz.

    :param root: Root dir where 'var/lib/rpm' exists
    :param workdir: Working dir to dump the result
    :param template_paths: Template path list
    :param engine: Graphviz rendering engine to choose, e.g. neato
    """
    reqs_map = RU.make_requires_dict(root)
    ctx = dict(dependencies=[(r, ps) for r, ps in reqs_map.iteritems()])

    depgraph_s = render("rpm_dependencies.graphviz.j2", ctx,
                        template_paths, ask=True)
    src = os.path.join(workdir, "rpm_dependencies.graphviz")

    open(src, 'w').write(depgraph_s)

    output = src + ".svg"
    (outlog, errlog) = (os.path.join(workdir, "graphviz_out.log"),
                        os.path.join(workdir, "graphviz_err.log"))

    (out, err, rc) = YS.run("%s -Tsvg -o %s %s" % (engine, output, src))

    open(outlog, 'w').write(out)
    open(errlog, 'w').write(err)


def gen_html_report(root, workdir, template_paths=_TEMPLATE_PATHS):
    """
    Generate HTML report of RPMs.

    :param root: Root dir where 'var/lib/rpm' exists
    :param workdir: Working dir to dump the result
    """
    gen_depgraph(root, workdir, template_paths)

    jsdir = os.path.join(workdir, "js")
    if not os.path.exists(jsdir):
        os.makedirs(jsdir)

    js_tpaths = [os.path.join(t, "js") for t in template_paths]

    for f in ("graphviz-svg.js.j2", "jquery.js.j2",
              "rpm_dependencies.html.j2"):
        dst = os.path.join(workdir, f[:-3])
        s = render(f, {}, template_paths + js_tpaths, ask=True)
        open(dst, 'w').write(s)


def modmain(ppath, workdir=None, offline=False, errata_details=False,
            report=False, template_paths=_TEMPLATE_PATHS):
    """
    :param ppath: The path to 'Packages' RPM DB file
    :param workdir: Working dir to dump the result
    :param offline: True if get results only from local cache
    :param errata_details: True if detailed errata info is needed
    :param report: True if report to be generated
    """
    if not ppath:
        ppath = raw_input("Path to the RPM DB 'Packages' > ")

    ppath = os.path.normpath(ppath)
    root = YS.setup_root(ppath, force=True)

    if not workdir:
        workdir = root

    if not os.path.exists(workdir):
        logging.info("Creating working dir: " + workdir)
        os.makedirs(workdir)

    logging.info("Dump RPM list...")
    dump_rpm_list(root, workdir)

    logging.info("Dump Errata summaries...")
    dump_errata_summary(root, workdir)

    if errata_details:
        logging.info("Dump Errata details...")
        dump_errata_list(workdir, offline)

    logging.info("Dump update RPM list from errata data...")
    dump_updates_list(workdir)

    logging.info("Dump dataset file from RPMs and Errata data...")
    dump_datasets(workdir, errata_details)

    if report:
        logging.info("Dump depgraph and generating HTML reports...")
        gen_html_report(root, workdir, template_paths)


def mk_template_paths(tpaths_s, default=_TEMPLATE_PATHS, sep=':'):
    """
    :param tpaths_s: ':' separated template path list

    >>> default = _TEMPLATE_PATHS
    >>> default == mk_template_paths("")
    True
    >>> ["/a/b"] + default == mk_template_paths("/a/b")
    True
    >>> ["/a/b", "/c"] + default == mk_template_paths("/a/b:/c")
    True
    """
    tpaths = tpaths_s.split(sep)

    if tpaths:
        return tpaths + default
    else:
        return default  # Ignore given paths string.


def option_parser(template_paths=_TEMPLATE_PATHS):
    """
    :param defaults: Option value defaults
    :param usage: Usage text
    """
    defaults = dict(path=None, workdir=None, details=False, offline=False,
                    report=False, template_paths="", verbose=False)

    p = optparse.OptionParser("""%prog [Options...] RPMDB_PATH

    where RPMDB_PATH = the path to 'Packages' RPM DB file taken from
                       '/var/lib/rpm' on the target host""")

    p.set_defaults(**defaults)

    p.add_option("-w", "--workdir", help="Working dir [%default]")
    p.add_option("-d", "--details", action="store_true",
                 help="Get errata details also from RHN / Satellite")
    p.add_option("", "--offline", action="store_true", help="Offline mode")
    p.add_option("", "--report", action="store_true",
                 help="Generate summarized report in HTML format")
    p.add_option("-T", "--tpaths",
                 help="':' separated additional template search path "
                      "list [%s]" % ':'.join(template_paths))
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

    tpaths = mk_template_paths(options.tpaths)

    if options.report and not _JINJA2_CLI:
        sys.stderr.write("python-jinja2-cli is not installed so that "
                         "reporting function is disabled.")
        options.report = False

    modmain(ppath, options.workdir, options.offline, options.details,
            options.report, tpaths)


if __name__ == '__main__':
    main()

# vim:sw=4:ts=4:et:
