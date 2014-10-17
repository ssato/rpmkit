#
# Copyright (C) 2014 Red Hat, Inc.
# Author: Satoru SATOH <ssato@redhat.com>
# License: GPLv3+
#
from __future__ import print_function
from gi.repository import Libosinfo as osinfo
from logging import DEBUG, INFO

import rpmkit.swapi
import rpmkit.rpmutils
import rpmkit.utils

import anyconfig
import collections
import datetime
import exceptions
import itertools
import logging
import optparse
import os.path
import re
import sys
import tempfile


_TODAY = datetime.datetime.now().strftime("%Y-%m-%d")
_ES_FMT = "%(advisory)s,%(synopsis)s,%(issue_date)s"


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

    >>> get_distro_release_date("rhel", 5, 4)
    '2009-09-02'
    """
    db = init_osinfo()
    osi = db.get_os(get_osid(distro, version, release))
    return osi.get_param_value("release-date")


def errata_get_details(errata, swopts=[]):
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


def errata_get_relevant_package_list(errata, swopts=[]):
    """
    :param errata: A dict contains basic errata info
    :param swopts: A list of extra options for swapi
    """
    adv = errata.get("advisory", errata.get("advisory_name", None))
    assert adv is not None, "Not a dict?: {}".format(errata)

    logging.info("Try to fetch packages relevant to {}".format(adv))
    errata["packages"] = rpmkit.swapi.call("errata.listPackages", adv, swopts)
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
        es = [errata_get_details(e) for e in es]

    if list_pkgs:
        logging.info("Try to fetch errata packages info from RHNS...")
        es = [errata_get_relevant_package_list(e) for e in es]

    return es


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
    ...               version=5, releases=(11, -1), arch="i386"), d)
    True
    >>> d = parse_distro("rhel-5.4..11")
    >>> dicts_eq(dict(os="rhel",  # doctest: +NORMALIZE_WHITESPACE
    ...               version=5, releases=(4, 11), arch="x86_64"), d)
    True
    >>> d = parse_distro("rhel-5.4..11-i386")
    >>> dicts_eq(dict(os="rhel",  # doctest: +NORMALIZE_WHITESPACE
    ...               version=5, releases=(4, 11), arch="i386"), d)
    True
    >>> d = parse_distro("rhel-6.5")
    >>> dicts_eq(dict(os="rhel",  # doctest: +NORMALIZE_WHITESPACE
    ...               version=6, releases=(5, -1), arch="x86_64"), d)
    True
    >>> d = parse_distro("rhel-6.2..5-i386")
    >>> dicts_eq(dict(os="rhel",  # doctest: +NORMALIZE_WHITESPACE
    ...               version=6, releases=(2, 5), arch="i386"), d)
    True
    >>> d = parse_distro("rhel-6")
    >>> dicts_eq(dict(os="rhel",  # doctest: +NORMALIZE_WHITESPACE
    ...               version=6, releases=(0, -1), arch="x86_64"), d)
    True
    >>> d = parse_distro("fedora-20")
    >>> dicts_eq(dict(os="fedora", # doctest: +NORMALIZE_WHITESPACE
    ...               version=20, releases=None, arch="x86_64"), d)
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

        if d["os"] == "rhel":
            rel = 0 if d["release"] is None else int(d["release"])
            rel_2 = -1 if d["release_2"] is None else int(d["release_2"])
            if rel_2 != -1 and rel_2 <= rel:
                rel_2 = -1

            d["releases"] = (rel, rel_2)

        if d["arch"] is None:
            d["arch"] = arch

        return d
    except Exception as e:
        raise DistroParseError("Not a distro? : {}:\n{}".format(distro, e))


def guess_rhns_channels_by_distro(distro):
    """
    :param distro: A dict represents OS distribution
    """
    if distro["os"] == "rhel":
        if distro["version"] == 4:
            return ["rhel-x86_64-as-4"]
        elif distro["version"] == 5:
            return ["rhel-x86_64-server-5"]
        elif distro["version"] == 6:
            return ["rhel-x86_64-server-6"]  # "rhel-x86_64-server-optional-6"]
        else:
            return []  # Not supported.

    return []


def list_errata_from_rhns(distro_s, channels=[], arch="x86_64", swopts=[]):
    """
    :param distro: A string represents distribution (of releases optionally),
        ex. 'rhel-6.5-x86_64', 'fedora-20', 'rhel-5.4..11-i386'
    :param channels: List of software channels in RHNS (RHN, RH Satellite),
        ex. ['rhel-x86_64-server-5']
    :param arch: Default architecture
    :param swopts: A list of extra options for swapi
    """
    distro = parse_distro(distro_s, arch)
    if not channels:
        channels = guess_rhns_channels_by_distro(distro)
        assert channels, "Failed to guess channels for {}".format(distro_s)

    period = [get_distro_release_date(distro["os"], distro["version"],
                                      distro["releases"][0]), ]
    if distro["releases"][1] != -1:
        end = get_distro_release_date(distro["os"], distro["version"],
                                      distro["releases"][1])
        period.append(end)

    f = get_errata_list_from_rhns
    es = itertools.chain(*(f(c, period, list_pkgs=True, swopts=swopts) for c
                           in channels))
    return rpmkit.utils.unique(es)


def list_errata_packages(errata, swopts=[]):
    """
    :param errata: A list of dicts contain errata info including relevant
        packages (a dict of packages' info including path)
    :param swopts: A list of extra options for swapi
    """
    ps = itertools.chain(*((p for p in e["packages"]) for e in errata))
    return rpmkit.utils.unique(ps)


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
                    all_versions=False, swopts=[], verbose=False)

    p = optparse.OptionParser(usage)
    p.set_defaults(**defaults)

    p.add_option("-d", "--download", action="store_true",
                 help="Download errata packages (Not implemented yet)")
    p.add_option("-w", "--workdir", help="Working dir to save results")
    p.add_option("-c", "--channel", action="append", dest="channels",
                 help="List of software channels in RHNS. These will be "
                      "guessed automatically if not given")
    p.add_option("-a", "--arch", help="Specify arch [%default]")
    p.add_option("-A", "--all-versions", action="store_true",
                 help="Collect all versions of packages [no; latest ones only]")
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

    distro = args[0]
    es = list_errata_from_rhns(distro, options.channels, options.arch,
                               options.swopts)
    pkgs = list_errata_packages(es, options.swopts)
    latest_pkgs = rpmkit.rpmutils.find_latests(pkgs)

    if options.workdir:
        if os.path.exists(options.workdir):
            assert os.path.isdir(options.workdir), \
                "Not a dir: " + options.workdir
        else:
            os.makedirs(options.workdir)
            logging.info("Created: " + options.workdir)
    else:
        options.workdir = tempfile.mkdtemp(dir="/tmp",
                                           prefix="errata_for_releases-")
        logging.info("Created: " + options.workdir)

    metadata = dict(generator="rpmkit.extras.listerrata_for_releases",
                    version="0.1", last_updated=_TODAY,
                    os=distro, arch=options.arch,
                    channels=(options.channels or 'auto'),
                    nerrata=len(es), npackages=len(pkgs),
                    nupdates=len(latest_pkgs))

    anyconfig.dump(dict(metadata=metadata, data=es),
                   os.path.join(options.workdir, "errata.json"))
    anyconfig.dump(dict(metadata=metadata, data=pkgs),
                   os.path.join(options.workdir, "packages.json"))
    anyconfig.dump(dict(metadata=metadata, data=pkgs),
                   os.path.join(options.workdir, "update_packages.json"))

    with open(os.path.join(options.workdir, "updates.txt"), 'w') as f:
        for u in latest_pkgs:
            f.write(u["path"] + '\n')


if __name__ == "__main__":
    main()

# vim:sw=4:ts=4:et:
