#
# Copyright (C) 2014, 2015 Red Hat, Inc.
# Author: Satoru SATOH <ssato@redhat.com>
# License: GPLv3+
#
from __future__ import print_function

try:
    import gi
    gi.require_version('Libosinfo', '1.0')
    from gi.repository import Libosinfo as osinfo
except ImportError:
    osinfo = None

from logging import DEBUG, INFO

import anyconfig
import collections
import datetime
import exceptions
import gzip
import itertools
import logging
import operator
import optparse
import os.path
import re
import requests
import sys
import tempfile

try:
    import cStringIO as StringIO
except ImportError:
    import StringIO

try:
    # First, try lxml which is compatible with elementtree and looks faster a
    # lot. See also: http://getpython3.com/diveintopython3/xml.html
    from lxml2 import etree as ET
except ImportError:
    try:
        import xml.etree.ElementTree as ET
    except ImportError:
        import elementtree.ElementTree as ET

try:
    import yum
    _YUMVARS = yum.YumBase().conf.yumvar
except ImportError:
    _YUMVARS = dict(releasever=None, basearch="x86_64")

import rpmkit.swapi
import rpmkit.rpmutils
import rpmkit.utils


_TODAY = datetime.datetime.now().strftime("%Y-%m-%d")
_ES_FMT = "%(advisory)s,%(synopsis)s,%(issue_date)s"
LOG = logging.getLogger(__name__)


def prev_date(date_s):
    """
    >>> prev_date("2014-07-31")
    '2014-07-30'
    >>> prev_date("2014-07-01")
    '2014-06-30'
    """
    day = [int(d) for d in date_s.split('-')]
    prev = datetime.datetime(*day) - datetime.timedelta(1)
    return prev.strftime("%Y-%m-%d")


def init_osinfo(path=None):
    """
    Initialize libosinfo db.

    :param path: libosinfo distro data
    :return: an osinfo.Db instance
    """
    if osinfo is None:
        return None

    loader = osinfo.Loader()
    if path is None:
        loader.process_default_path()
    else:
        loader.process_path(path)

    return loader.get_db()


def get_osid(distro, version, release=0):
    """
    see /usr/share/libosinfo/db/oses/{fedora,rhel}.xml in libosinfo.

    TODO: utilize libosinfo api;
        osinfo-query --fields=short-id,release-date os distro=rhel
    """
    if distro == "rhel":
        osid = "http://redhat.com/rhel/{}.{}".format(version, release)
    elif distro == "fedora":
        osid = "http://fedoraproject.org/fedora/{}".format(version)
    else:
        # FIXME: Utilize libosinfo's API. See also the src of osinfo-query,
        # http://bit.ly/1wd2Emr
        return None

    return osid


def get_distro_release_date(distro, version, release=0):
    """
    see also: https://access.redhat.com/articles/3078 (rhel)

    >>> try:
    ...     get_distro_release_date("rhel", 5, 4) == '2009-09-02'
    ... except RuntimeError as exc:
    ...     True
    True
    """
    db = init_osinfo()
    if db is None:
        raise RuntimeError("Libosinfo initialization failed")

    osi = db.get_os(get_osid(distro, version, release))

    if osi is None:
        raise RuntimeError("Not found: distro={}, version={}, "
                           "release={}".format(distro, version, release))

    return osi.get_param_value("release-date")


def errata_add_details(errata, swopts=[]):
    """
    :param errata: A dict contains basic errata info
    :param swopts: A list of extra options for swapi
    """
    assert "advisory" in errata, "Not an errata dict?: " + str(errata)

    logging.info("Try to fetch details of {advisory}".format(errata))
    details = rpmkit.swapi.call("errata.getDetails", errata["advisory"],
                                swopts)
    errata.update(details)
    return errata


def errata_add_relevant_package_list(errata, ref_packages, swopts=[]):
    """
    :param errata: A dict contains basic errata info
    :param swopts: A list of extra options for swapi
    """
    adv = errata.get("advisory", errata.get("advisory_name", None))
    assert adv is not None, "Not a dict?: {}".format(errata)

    logging.debug("Try to fetch packages relevant to {}".format(adv))
    ps = rpmkit.swapi.call("errata.listPackages", adv, swopts)
    ref_pids = [p["id"] for p in ref_packages]

    errata["packages"] = [p for p in ps if p["id"] in ref_pids]
    return errata


def get_errata_list_from_rhns(channel, period, details=False, list_pkgs=False,
                              swopts=[]):
    """
    :param channel: List of software channels in RHNS (RHN, RH Satellite),
        ex. 'rhel-x86_64-server-5'
    :param period: Range of date to get errata list within,
        ex. ["2014-01-01"], ["2009-01-31", "2010-02-01"]
    :param details: Get each errata detailed info additionally if True
    :param list_pkgs: Get package info relevant to each errata additionally
        if True
    :param swopts: A list of extra options for swapi
    """
    logging.info("Try to fetch errata info from RHNS...")
    es = rpmkit.swapi.call("channel.software.listErrata", [channel] + period,
                           swopts)
    logging.info("Got {} errata in {} ({})".format(len(es), channel,
                                                   '..'.join(period)))
    if details:
        logging.info("Try to fetch errata details from RHNS...")
        es = [errata_add_details(e) for e in es]

    if list_pkgs:
        logging.info("Try to fetch errata packages info from RHNS...")
        rps = rpmkit.swapi.call("channel.software.listAllPackages",
                                [channel], swopts)
        es = [errata_add_relevant_package_list(e, rps, swopts) for e in es]

    return es


def expand_baseurl_in_repofile(baseurl, relver=None, yumvars=_YUMVARS):
    """
    Expand yum variables in baseurl string from yum .repo files.
    """
    relver = yumvars.get("releasever", relver)
    if not relver:
        relver = "7Server"  # FIXME
    basearch = yumvars.get("basearch", "x86_64")

    return re.sub(r"\$basearch", basearch,
                  re.sub(r"\$releasever", relver, baseurl))


def updateinfo_xml_itr(updateinfo):
    """
    :param updateinfo: the content of updateinfo.xml :: str
    """
    root = ET.ElementTree(ET.fromstring(updateinfo)).getroot()
    for upd in root.findall("update"):
        uinfo = upd.attrib
        for k in "id title severity rights summary description".split():
            elem = upd.find(k)
            if elem is not None:
                uinfo[k] = elem.text

        for k in "issued updated".split():
            uinfo[k] = upd.find(k).attrib["date"]
        uinfo["refs"] = [r.attrib for r in upd.findall(".//reference")]
        uinfo["packages"] = [dict(filename=p.find("filename").text, **p.attrib)
                             for p in upd.findall(".//package")]
        yield uinfo


def get_errata_list_from_updateinfo_by_repofile(rid, basearch="x86_64"):
    """
    Try to fetch the content of given repo metadata xml from remote.

    :param rid: ID of the repo from RH CDN, ex. rhel-7-server-rpms
    """
    timeout = 60 * 5
    try:
        repos = anyconfig.load("/etc/yum.repos.d/*.repo", ac_parser="ini")
        repo = repos.get(rid, None)
        if repo is None:
            LOG.error("Failed to get repo info: %r", rid)
            return None

        rparams = dict(timeout=timeout)
        if "sslclientcert" in repo and "sslclientkey" in repo:
            rparams["cert"] = (repo["sslclientcert"], repo["sslclientkey"])

        if "sslcacert" in repo:
            rparams["verify"] = repo["sslcacert"]

        try:
            m = re.match(r"Red Hat Enterprise Linux (\d+) .*", repo["name"])
            relver = "%dServer" % int(m.groups()[0]) if m else "7Server"
        except (AttributeError, IndexError):
            relver = None

        baseurl = expand_baseurl_in_repofile(repo["baseurl"], relver)
        repomd_xml_url = os.path.join(baseurl, "repodata/repomd.xml")

        LOG.info("Try to fetch repomd.xml: %s", repomd_xml_url)
        resp = requests.get(repomd_xml_url, **rparams)
        if not resp.ok:
            LOG.error("Failed to get repomd.xml from %s", baseurl)
            return None

        LOG.debug("Try to parse repomd.xml...")
        root = ET.ElementTree(ET.fromstring(resp.text)).getroot()

        ns = "http://linux.duke.edu/metadata/repo"
        es = root.findall(".//{%s}location" % ns)
        us = [e.attrib["href"] for e in es if "updateinfo.xml"
              in e.attrib["href"]]
        if not us:
            LOG.error("Failed to find the url %s", repomd_xml_url)
            return None

        upd_url = os.path.join(baseurl, us[0])

        LOG.debug("Try to fetch updateinfo.xml: %s", upd_url)
        resp = requests.get(upd_url, **rparams)

        if not resp.ok:
            LOG.error("Failed to get updateinfo.xml from %s", upd_url)
            return None

        updgz = resp.content
        uinfo = gzip.GzipFile(fileobj=StringIO.StringIO(updgz)).read()
        return sorted(updateinfo_xml_itr(uinfo),
                      key=operator.itemgetter("issued"))
    except Exception as exc:
        raise RuntimeError("Failed: exc=%r" % exc)


def get_errata_list_from_updateinfo(repo, period=None, list_pkgs=False,
                                    **opts):
    """
    Very dirty hack!

    :param repo: ID of the repo from RH CDN, ex. rhel-7-server-rpms
    :param period: Range of date to get errata list within,
        ex. ["2014-01-01"], ["2009-01-31", "2010-02-01"]
    :param list_pkgs:
        Get package info relevant to each errata additionally if True
    :param opts: Optional keyword arguments such as baseurl

    .. todo::
       baseurl should be detected from yum .repo files
    """
    repomd_url = os.path.join(opts["baseurl"], repo, "repodata/repomd.xml")
    repomd = rpmkit.swapi.urlread(repomd_url)  # IOError, etc. may be raised.
    root = ET.ElementTree(ET.fromstring(repomd)).getroot()
    es = root.findall(".//{http://linux.duke.edu/metadata/repo}location")
    us = [e.attrib["href"] for e in es if "updateinfo.xml" in e.attrib["href"]]
    if not us:
        raise RuntimeError("Failed to find the url of updateinfo.xml from %s" %
                           repomd_url)
    upd_url = os.path.join(opts["baseurl"], repo, us[0])
    updgz = rpmkit.swapi.urlread(upd_url)  # raises ...
    updateinfo = gzip.GzipFile(fileobj=StringIO.StringIO(updgz)).read()
    return sorted(updateinfo_xml_itr(updateinfo),
                  key=operator.itemgetter("issued"))


def dicts_eq(lhs, rhs, strict=False):
    """
    >>> dicts_eq({}, {})
    True
    >>> dicts_eq(dict(a=1, ), {})
    False
    >>> dicts_eq(dict(a=1, ), dict(a=1, b=2))
    True
    >>> dicts_eq(dict(a=1, ), dict(a=2, ))
    False
    >>> dicts_eq(dict(a=1, ), dict(a=1, b=2), strict=True)
    False
    >>> dicts_eq({}, None)  # doctest: +ELLIPSIS
    Traceback (most recent call last):
    AssertionError: ...
    """
    for d in (lhs, rhs):
        assert isinstance(d, collections.Mapping), "Not a dict: " + str(d)

    if strict and sorted(lhs.keys()) != sorted(rhs.keys()):
        return False

    for k in lhs.keys():
        if k not in rhs:
            return False
        if rhs[k] != lhs[k]:
            return False

    return True


class DistroParseError(exceptions.ValueError):
    pass


def parse_distro(distro, arch="x86_64"):
    """
    :param distro: A string represents distribution,
        ex. 'rhel-6.5-x86_64', 'fedora-20'
    :param arch: Default architecture

    >>> d = parse_distro("rhel-5.11-i386")
    >>> dicts_eq(dict(os="rhel",  # doctest: +NORMALIZE_WHITESPACE
    ...               version=5, release=11, releases=(11, -1),
    ...               label="rhel-5.11-i386", arch="i386"), d)
    True
    >>> d = parse_distro("rhel-5.4..11")
    >>> dicts_eq(dict(os="rhel",  # doctest: +NORMALIZE_WHITESPACE
    ...               version=5, release=4, releases=(4, 11),
    ...               label="rhel-5.4-x86_64", arch="x86_64"), d)
    True
    >>> d = parse_distro("rhel-5.4..11-i386")
    >>> dicts_eq(dict(os="rhel",  # doctest: +NORMALIZE_WHITESPACE
    ...               version=5, release=4, releases=(4, 11),
    ...               label="rhel-5.4-i386", arch="i386"), d)
    True
    >>> d = parse_distro("rhel-6.5")
    >>> dicts_eq(dict(os="rhel",  # doctest: +NORMALIZE_WHITESPACE
    ...               version=6, release=5, releases=(5, -1),
    ...               label="rhel-6.5-x86_64", arch="x86_64"), d)
    True
    >>> d = parse_distro("rhel-6.2..5-i386")
    >>> dicts_eq(dict(os="rhel",  # doctest: +NORMALIZE_WHITESPACE
    ...               version=6, release=2, releases=(2, 5),
    ...               label="rhel-6.2-i386", arch="i386"), d)
    True
    >>> d = parse_distro("rhel-6")
    >>> dicts_eq(dict(os="rhel",  # doctest: +NORMALIZE_WHITESPACE
    ...               version=6, release=0, releases=(0, -1),
    ...               label="rhel-6.0-x86_64", arch="x86_64"), d)
    True
    >>> d = parse_distro("fedora-20")
    >>> dicts_eq(dict(os="fedora", # doctest: +NORMALIZE_WHITESPACE
    ...               version=20, release=None, releases=None,
    ...               label="fedora-20-x86_64", arch="x86_64"), d)
    True
    >>> d = parse_distro("foo-20.1")  # doctest: +ELLIPSIS
    Traceback (most recent call last):
    DistroParseError: ...
    """
    try:
        d = re.match(r"^(?P<os>fedora|rhel)-(?P<version>\d+)"
                     "(?:\.(?P<release>\d+)(?:\.\.(?P<release_2>\d+))?)?"
                     "(?:-(?P<arch>.+))?$",
                     distro).groupdict()

        # Some special cases.
        d["version"] = int(d["version"])
        d["releases"] = None

        if d["arch"] is None:
            d["arch"] = arch

        if d["os"] == "rhel":
            rel = 0 if d["release"] is None else int(d["release"])
            rel_2 = -1 if d["release_2"] is None else int(d["release_2"])
            if rel_2 != -1 and rel_2 <= rel:
                rel_2 = -1

            d["release"] = rel
            d["releases"] = (rel, rel_2)

        if d["release"] is None:
            label = "{os}-{version}-{arch}".format(**d)
        else:
            label = "{os}-{version}.{release}-{arch}".format(**d)

        d["label"] = label
        return d
    except Exception as e:
        raise DistroParseError("Not a distro? : {}:\n{}".format(distro, e))


def distro_guess_checksum_type(distro):
    """
    Guess distro's yum repo checksum type.

    :param distro: A dict represents OS distribution
    """
    if distro["os"] == "rhel" and distro["version"] < 6:
        return "md5"
    else:
        return "sha256"


def distro_resolve_release_dates(distro):
    """
    :param distro: A dict represents OS distribution
    """
    period = [get_distro_release_date(distro["os"], distro["version"],
                                      distro["release"]), ]
    logging.info("{} released={}".format(distro["label"], period[0]))

    if distro["releases"][1] != -1:
        end = get_distro_release_date(distro["os"], distro["version"],
                                      distro["releases"][1])
        logging.info("{}-{}.{}-{} released={}".format(distro["os"],
                                                      distro["version"],
                                                      distro["releases"][1],
                                                      distro["arch"],
                                                      end))
        period.append(prev_date(end))
        logging.info("period: {}..{}".format(*period))

    return period


def guess_rhns_channels_by_distro(distro):
    """
    :param distro: A dict represents OS distribution
    """
    if distro["os"] == "rhel":
        if distro["version"] == 4:
            return ["rhel-{arch}-as-4".format(**distro)]
        elif distro["version"] == 5:
            return ["rhel-{arch}-server-5".format(**distro)]
        elif distro["version"] == 6:
            # "rhel-x86_64-server-optional-6"]
            return ["rhel-{arch}-server-6".format(**distro)]
        else:
            return []  # Not supported.

    return []


def distro_new_by_rhns(distro_s, arch="x86_64", channels=[]):
    """
    :param distro_s: A string represents distribution,
        ex. 'rhel-6.5-x86_64', 'fedora-20'
    :param arch: Default architecture
    :param channels: List of software channels in RHNS (RHN, RH Satellite),
        ex. ['rhel-x86_64-server-5']
    """
    distro = parse_distro(distro_s, arch)

    if not channels:
        channels = guess_rhns_channels_by_distro(distro)
        assert channels, "No channels found for {label}".format(distro)

    distro["channels"] = channels
    distro["checksum_type"] = distro_guess_checksum_type(distro)
    distro["period"] = distro_resolve_release_dates(distro)

    return distro


def distro_new(distro_s, arch="x86_64"):
    """
    :param distro_s: A string represents distribution,
        ex. 'rhel-6.5-x86_64', 'fedora-20'
    :param arch: Default architecture
    """
    distro = parse_distro(distro_s, arch)
    distro["period"] = distro_resolve_release_dates(distro)
    distro["repoid"] = "rhel-%(version)d-server-rpms" % distro
    distro["channels"] = [distro["repoid"]]
    distro["checksum_type"] = "sha256"
    return distro


def list_errata_from_rhns(distro, swopts=[]):
    """
    :param distro: A dict represents OS distribution.
    :param swopts: A list of extra options for swapi
    """
    f = get_errata_list_from_rhns
    es = itertools.chain(*(f(c, distro["period"], list_pkgs=True,
                             swopts=swopts) for c in distro["channels"]))
    return rpmkit.utils.unique(es)


def list_errata_packages(errata, swopts=[]):
    """
    :param errata: A list of dicts contain errata info including relevant
        packages (a dict of packages' info including path)
    :param swopts: A list of extra options for swapi
    """
    ps = itertools.chain(*((p for p in e["packages"]) for e in errata))
    return rpmkit.utils.unique(ps)


def gen_mkiso_script(distro, metadata, prefix='/'):
    """
    Generate a script to make update iso image.

    :param distro: A dict represents OS distribution.
    """
    tmpl = """#! /bin/bash
set -e

cd ${{0%/*}}/

name={label}-updates
isodir=${{name}}
checksum_type={checksum_type}

# prefix must be an absolute path.
prefix=${{1:-{prefix}}}

if test ! -d ${{prefix}}/redhat; then
    echo "[Error] ${prefix} does not look appropriate path holidng rpms."
    exit 1
fi

test -d $isodir || mkdir -p $isodir/rpms
cp -f errata.csv $isodir/
cat << EOF > $isodir/metadata.txt
channels={channels}
num_of_errata={nerrata}
num_of_update_rpms={nupdates}
EOF
(
cd $isodir/rpms
for f in $(cat ../../updates.txt); do ln -s $prefix/$f ./; done
createrepo --simple-md-filenames --no-database --checksum=${{checksum_type}} .
cat << EOF > ../${{name}}.repo
[${{name}}]
name=${{name}}
baseurl=file:///mnt/rpms
metadata_expire=-1
enabled=0
gpgcheck=0
EOF
)
mkisofs -f -J -r -R -V "$label" -o "$name".iso $isodir/
"""
    d = distro.copy()

    d["prefix"] = prefix
    d["today"] = _TODAY
    d["channels"] = metadata["channels"]
    d["nerrata"] = metadata["nerrata"]
    d["nupdates"] = metadata["nupdates"]

    return tmpl.format(**d)


def output_results(errata, packages, updates, distro, workdir):
    """
    """
    metadata = dict(generator="rpmkit.extras.listerrata_for_releases",
                    version="0.1", last_updated=_TODAY,
                    channels=', '.join(distro["channels"]),
                    nerrata=len(errata), npackages=len(packages),
                    nupdates=len(updates))
    metadata.update(distro)

    anyconfig.dump(dict(metadata=metadata, data=errata),
                   os.path.join(workdir, "errata.json"))
    anyconfig.dump(dict(metadata=metadata, data=packages),
                   os.path.join(workdir, "packages.json"))
    anyconfig.dump(dict(metadata=metadata, data=updates),
                   os.path.join(workdir, "updates.json"))

    with open(os.path.join(workdir, "updates.txt"), 'w') as f:
        for u in updates:
            f.write(u.get("path", u.get("filename", "N/A")) + '\n')

    with open(os.path.join(workdir, "errata.csv"), 'w') as f:
        f.write("advisory,synopsis,issue_date,url\n")
        for e in errata:
            adv = e.get("advisory", e.get("id"))
            adv_s = adv.replace(':', '-')
            url = "https://rhn.redhat.com/errata/{}.html".format(adv_s)

            f.write("{},{},{},{}\n".format(adv,
                                           e.get("synopsis", e.get("title")),
                                           e.get("issue_date",
                                                 e.get("issued")), url))

    fn = os.path.join(workdir, "geniso.sh")
    with open(fn, 'w') as f:
        f.write(gen_mkiso_script(distro, metadata))
    os.chmod(fn, 0o755)


def option_parser():
    usage = """Usage: %prog [OPTION]... DISTRO

    where DISTRO = OS distribution name including release[s] such as rhel-6.5,
                   rhel-5.11-x86_64, rhel-7, fedora-20, rhel-6.2..5,
                   rhel-5.4..5-x86_64.

                   '..' in release versions is used to specify the period of
                   releases; rhel-6.2..5 means "from rhel-6.2 to rhel-6.5" and
                   "rhel-5.4..5-x86_64" means "from rhel-5.4-x86_64 to
                   rhel-5.5-x86_64"."""
    defaults = dict(download=False, workdir=None, channels=[], arch="x86_64",
                    all_versions=False, swopts=[], rhns=False,
                    verbose=False)

    p = optparse.OptionParser(usage)
    p.set_defaults(**defaults)

    p.add_option("-R", "--rhns", action="store_true",
                 help="Use classic RHN / Satellite API to fetch info")
    p.add_option("-d", "--download", action="store_true",
                 help="Download errata packages (Not implemented yet)")
    p.add_option("-w", "--workdir", help="Working dir to save results")
    p.add_option("-c", "--channel", action="append", dest="channels",
                 help="List of software channels in RHNS. These will be "
                      "guessed automatically if not given")
    p.add_option("-a", "--arch", help="Specify arch [%default]")
    p.add_option("-A", "--all-versions", action="store_true",
                 help="Collect all versions of packages [no; latests only]")
    p.add_option("", "--swopt", action="append", dest="swopts",
                 help="A list of swapi options, ex. --swopt='--verbose'")
    p.add_option("-v", "--verbose", action="store_true", help="Verbose mode")

    return p


def main():
    p = option_parser()
    (options, args) = p.parse_args()

    rpmkit.utils.init_log(DEBUG if options.verbose else INFO)

    if not args:
        p.print_help()
        sys.exit(1)

    if options.rhns:
        distro = distro_new_by_rhns(args[0], options.arch, options.channels)
        errata = list_errata_from_rhns(distro, options.swopts)
        packages = list_errata_packages(errata, options.swopts)
        updates = rpmkit.rpmutils.find_latests(packages, ("name", "arch_label"))
    else:
        distro = distro_new(args[0], options.arch)
        # basearch = distro["arch"]  # TBD.
        errata = get_errata_list_from_updateinfo_by_repofile(distro["repoid"])
        packages = list_errata_packages(errata)
        updates = rpmkit.rpmutils.find_latests(packages, ("name", "arch"))

    if options.workdir:
        workdir = options.workdir
        if os.path.exists(workdir):
            assert os.path.isdir(workdir), "Not a dir: {}".format(workdir)
        else:
            os.makedirs(workdir)
            logging.info("Created: {}".format(workdir))
    else:
        workdir = tempfile.mkdtemp(dir="/tmp", prefix="errata_for_releases-")
        logging.info("Created: {}".format(workdir))

    output_results(errata, packages, updates, distro, workdir)


if __name__ == "__main__":
    main()

# vim:sw=4:ts=4:et:
