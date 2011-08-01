#! /usr/bin/python
#
# Sample python script utilizes swapi.py to:
#
#  * List updates for given RPM list
#  * List errata for given RPM list
#
# Copyright (C) 2011 Red Hat, Inc. 
# Red Hat Author(s): Satoru SATOH <ssato@redhat.com>
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
# Requirements: swapi, yum
#
# SEE ALSO: https://access.redhat.com/knowledge/docs/Red_Hat_Network/API_Documentation/
#
from __future__ import print_function
from itertools import chain, izip, izip_longest, groupby

import logging
import optparse
import os
import os.path
import pprint
import random
import sys
import swapi
import yum


try:
    import json
except ImportError:
    import simplejson as json



LOG_LEVELS = [logging.WARN, logging.INFO, logging.DEBUG]



def concat(xss):
    """
    @param  xss  list of lists or generators

    >>> concat([[]])
    []
    >>> concat((range(3), (i*2 for i in range(3))))
    [0, 1, 2, 0, 2, 4]
    """
    return list(chain(*list(xss)))


def normalize_arch(arch):
    """

    >>> normalize_arch("(none)")
    'noarch'
    >>> normalize_arch("x86_64")
    'x86_64'
    """
    if arch == "(none)":  # ex. 'gpg-pubkey'
        return "noarch"
    else:
        return arch


def normalize_epoch(epoch):
    """

    >>> normalize_epoch("(none)")  # rpmdb style
    0
    >>> normalize_epoch(" ")  # yum style
    0
    >>> normalize_epoch("0")
    0
    >>> normalize_epoch("1")
    1
    """
    if epoch is None:
        return 0
    else:
        if isinstance(epoch, str):
            epoch = epoch.strip()
            if epoch and epoch != "(none)":
                return int(epoch)
            else:
                return 0
        else:
            return epoch  # int?


def pkg2str(package):
    """
    Returns string representation of a package dict.
    """
    return "%(name)s-%(version)s-%(release)s.%(arch)s:%(epoch)s" % package


def pkgs2str(packages, with_name=False):
    """
    Returns string representation of [a package dict] (same name).
    """
    name = with_name and "name=%(name)s, " % packages[0]["name"] or ""
    evrs = ("(e=%(epoch)s, v=%(version)s, r=%(release)s)" % p for p in packages)

    return  name + ", ".join(evrs)


def pkg_cmp(p1, p2):
    """

    >>> p1 = dict(name="gpg-pubkey", version="069c8460", release="4d5067bf", arch="noarch", epoch=0)
    >>> p2 = dict(name="gpg-pubkey", version="00a4d52b", release="4cb9dd70", arch="noarch", epoch=0)
    >>> assert pkg_cmp(p1, p2) > 0

    >>> p3 = dict(name="kernel", version="2.6.38.8", release="32", arch="x86_64", epoch=0)
    >>> p4 = dict(name="kernel", version="2.6.38.8", release="35", arch="x86_64", epoch=0)
    >>> assert pkg_cmp(p3, p4) < 0

    >>> p5 = dict(name="rsync", version="2.6.8", release="3.1", arch="x86_64", epoch=0)
    >>> p6 = dict(name="rsync", version="3.0.6", release="4.el5", arch="x86_64", epoch=0)
    >>> assert pkg_cmp(p3, p4) < 0
    """
    p2evr = lambda p: (p["epoch"], p["version"], p["release"])

    assert p1["name"] == p2["name"], "Trying to compare different packages!"
    return yum.compareEVR(p2evr(p1), p2evr(p2))


def all_packages_in_channel(channel):
    args = "-A %s --group name channel.software.listAllPackages" % channel

    return swapi.mainloop(args.split())


def list_errata_for_packages(packages):
    pids = ",".join(str(p["id"]) for p in packages)

    logging.info("Try getting errata for packages (ids): " + pids)
    args = "--list-args %s packages.listProvidingErrata" % pids
    
    return swapi.mainloop(args.split())[0]


def all_packages_in_channels(channels):
    ret = dict()

    for channel in channels:
        logging.info("Try getting package list of channel %s from RHNS" % channel)
        d = all_packages_in_channel(channel)[0]

        logging.info("%d types of package found in channel %s" % (int(len(d.keys())), channel))
        ret.update(d)

    return ret


def packages_from_list_g(list_file, sep=",", comment="#",
        keys=("name", "version", "release", "arch", "epoch")):
    """
    Read lines from given list file and returns (yields) dict contains
    package's metadata.
    """
    for l in list_file.readlines():
        l = l.rstrip()

        if not l or l.startswith(comment):
            continue

        # TODO: Which is better? izip or izip_longest
        #p = dict(izip_longest(keys, l.split(sep)))
        p = dict(izip(keys, l.split(sep)))

        p["arch"] = normalize_arch(p["arch"])
        p["epoch"] = normalize_epoch(p["epoch"])

        logging.debug("installed package: " + pkg2str(p))

        yield p


def find_latest(packages):
    """Find the latest one from same packages with different versions.

    >>> gen_p = lambda r: dict(name="foo", version="0.1", release=str(r), arch="x86_64", epoch="(none)")
    >>> ps = [gen_p(r) for r in range(10)]
    >>> random.shuffle(ps)
    >>> p = find_latest(ps)
    >>> assert p["release"] == "9"
    """
    return sorted(packages, cmp=pkg_cmp)[-1]


def find_latests(packages):
    """Find the latests from given package list.
    """
    p2name = lambda p: p["name"]

    for ps in (list(g) for _k, g in groupby(packages, p2name)):
        pi = len(ps) > 1 and find_latest(ps) or ps[0]
        logging.debug("installed latest package: " + pkg2str(pi))

        yield pi


def find_updates_g(all_by_names, installed):
    """
    @params all_by_names  all packages :: dict([dict])
    @params installed  packages installed :: [dict]
    """
    is_newer = lambda p1, p2: pkg_cmp(p1, p2) > 0  # p1 is newer than p2.

    for pi in find_latests(installed):
        candidates = all_by_names.get(pi["name"], [])

        if candidates:
            cs = []
            for c in candidates:
                c["epoch"] = normalize_epoch(c["epoch"])
                cs.append(c)

            logging.debug("update candidates for %s: %s" % (pkg2str(pi), pkgs2str(cs)))
            ps = [p for p in cs if is_newer(p, pi)]

            if ps:
                logging.debug("updates for %s: %s" % (pkg2str(pi), pkgs2str(ps)))
                yield ps


def main(argv):
    chan_help = "Software channels separated with comma to find updates"

    p = optparse.OptionParser("%prog [OPTION ...] RPM_LIST_FILE")

    p.add_option("", "--channels", default=None, help=chan_help + " [MUST]")
    p.add_option("", "--errata", action="store_true", default=False,
        help="Output errata instead of update packages [%default]")
    p.add_option('-F', '--format', help="Output format (non-json)", default=False)
    p.add_option("-v", "--verbose", action="count", dest='verbosity', help="Verbose mode", default=0)

    (options, args) = p.parse_args(argv[1:])

    logging.getLogger().setLevel(LOG_LEVELS[options.verbosity])

    if len(args) == 0:
        p.print_usage()
        return 1

    if options.channels is None or not options.channels.strip():
        options.channels = raw_input(chan_help + "> ")

    channels = [c for c in options.channels.split(",") if c.strip()]

    input = args[0] == "-" and sys.stdin or open(args[0])

    ps_ref = all_packages_in_channels(channels)
    ps_installed = packages_from_list_g(input)

    updates = concat(list(find_updates_g(ps_ref, ps_installed)))

    if options.errata:
        es = list_errata_for_packages(updates)
        #pprint.pprint(es)
        errata = concat(es)

        if options.format:
            for e in errata:
                print(options.format % e)
        else:
            print(swapi.results_to_json_str(errata))

    else:
        if options.format:
            for p in updates:
                print(options.format % p)
        else:
            print(swapi.results_to_json_str(updates))

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))


# vim: set sw=4 ts=4 expandtab:
