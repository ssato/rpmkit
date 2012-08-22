#
# minifyrpms.py - Minify given rpm list
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
from rpmkit.identrpm import load_packages, parse_package_label
from rpmkit.utils import concat, uniq, uconcat

from itertools import izip, repeat
from logging import DEBUG, INFO
from operator import itemgetter

import rpmkit.repodata as RR
import logging
import optparse
import os
import os.path
import sys


def package_and_group_pairs(gps):
    """
    :param gps: Group and Package pairs, [(group, [package])
    """
    return concat(
        izip((p for p in ps), repeat(g)) for ps, g in
            ((ps, g) for g, ps in gps if ps)
    )


def find_missing_packages(group, ps, gps):
    """
    Find missing packages member of given package group `group` in given
    packages `ps`.

    :param group: Group ID or name
    :param ps: [package]
    :param gps: Group and Package pairs, [(group, [package])]
    """
    package_in_groups = concat((ps for g, ps in gps if g == group))
    return [p for p in package_in_groups if p not in ps]


def _id(x):
    return x


def get_packages_from_file(rpmlist, parse=True):
    """
    Get package names in given rpm list.

    :param rpmlist: Rpm list file, maybe output of `rpm -qa`
    :param parse: The list is package labels and must be parsed if True
    """
    l2n = lambda l: parse_package_label(l).get("name")
    f = l2n if parse else _id

    return [f(x) for x in load_packages(rpmlist)]


def minify_packages(requires, packages):
    """
    Minify package list `packages` by skipping packages required by others.

    :param requires: [(package, [required_package])]
    :param packages: Target package list to minify

    :return: (minified_packages, excluded_packages_as_required)
    """
    reqs = []  # packages in `packages` required by others.
    for p in packages:
        # find packages required by p, member of `packages` list, and not
        # member of prs:
        rs = uconcat((
            [r for r in rs if r in packages and r not in reqs] \
                for x, rs in requires if x == p
        ))
        if rs:
            reqs += rs
            #logging.debug("Excluded as required by %s: %s" % (p, rs))

    reqs = uniq(reqs)
    return ([p for p in packages if p not in reqs], reqs)


def cmp_groups(g1, g2):
    dfounds = len(g1[1]) - len(g2[1])
    dmissings = len(g2[2]) - len(g1[2])
    return dmissings if dfounds == 0 else dfounds


def key_group(g, weight=10):
    """
    :return: nfound - weight * nmissings
    """
    return len(g[1]) - weight * len(g[2])


def fmt_group(g):
    return "%s (%d/%d)" % (g[0], len(g[1]), len(g[2]))


def find_groups_0(gps, ps_ref, ps_req):
    """
    Find groups of which members are in `ps_ref`.

    :param gps: Group and package pairs, [(group, [package])]
    :param ps_ref: Packages to search groups for, [package]
    :param ps_req: Packages required by packages in ps_ref

    :return: [(group, found_packages_in_group, missing_packages_in_group)]
    """
    ps_all = ps_ref + ps_req
    gps = [
        (g,
         [x for x in ps_all if x in ps],  # packages found in ps.
         [y for y in ps if y not in ps_all]  # packages not found in 
        ) for g, ps in gps                   # both ps_ref and ps_req.
    ]

    # filter out groups having no packages in ps_ref (t[1] => ps_found)
    #return sorted((t for t in gps if t[1]), key=key_group, reverse=True)
    gs = [t for t in gps if t[1]]
    for g in gs:
        logging.debug("Groups having packages in list: " + fmt_group(g))

    return gs


def find_groups(gps, ps_ref, ps_req):
    """
    :param gps: Group and package pairs, [(group, [package])]
    :param ps_ref: Target packages to search for, [package]
    :param ps_req: Required packages by packages in ps_ref

    :return: [(group, found_packages_in_group, missing_packages_in_group)]
    """
    len0 = len(gps)
    gps = find_groups_0(gps, ps_ref, ps_req)
    logging.debug(
        "Initial candidate groups reduced from %d to %d" % (len0, len(gps))
    )

    # Find groups having max packages in ps_ref one by one:
    gs = []
    while True:
        if not gps:
            return gs

        candidates = sorted(gps, key=key_group, reverse=True)
        logging.debug(" *** Candidates *** ")
        for c in candidates:
            logging.debug(
                "Candidate group: %s, found=%d, missing=%d" % \
                    (c[0], len(c[1]), len(c[2]))
            )

        g = candidates[0]
        gs.append(g)
        logging.debug(
            "Candidate group: %s, found=%d, missing=%d" % \
                (g[0], len(g[1]), len(g[2]))
        )

        # filter out packages in this group `g` from `ps_ref` and `gps`:
        ps_ref = [p for p in ps_ref if p not in g[1]]
        gps = find_groups_0([t[:2] for t in candidates[1:]], ps_ref, ps_req)


FORMATS = (KS_FMT, JSON_FMT) = ("ks", "json")


def dump(groups, packages, ps_required, output, fmt=KS_FMT):
    """
    :param groups: Group and member packages
    :param packages: Packages not in groups
    :param ps_required: Excluded packages in originaly packages list
    :param output: Output file object
    """
    if fmt == KS_FMT:
        print >> output, "# package groups and packages"
        for g, ps_found, ps_missing in groups:
            print >> output, '@' + g  # e.g. '@perl-runtime'
            print >> output, "# found/missing = %d/%d" % \
                (len(ps_found), len(ps_missing))
            print >> output, "# Packages of this group: %s" % \
                ", ".join(sorted(ps_found)[:10]) + "..."

            # Packages to exclud from this group explicitly:
            for p in ps_missing:
                print >> output, '-' + p

        for p in packages:
            print >> output, p

        # Packages to exclude from the list as not needed because of
        # dependencies:
        print >> output, \
            "#\n# Excluded as installed when resolving dependencies:\n#"
        for p in ps_required:
            print >> output, "# " + p
    else:
        data = {}
        data["groups"] = [
            {"group": g, "found": ps_found, "missing": ps_missing} \
                for g, ps_found, ps_missing in groups
        ]
        data["packages"] = packages
        json.dump(data, output)


def option_parser():
    defaults = dict(
        parse=False,
        groups=False,
        datadir=None,
        output=None,
        fmt=KS_FMT,
        verbose=False,
    )
    p = optparse.OptionParser("%prog [OPTION ...] RPMS_FILE")
    p.set_defaults(**defaults)

    p.add_option("-P", "--parse", action="store_true",
        help="Specify this if input is `rpm -qa` output and must be parsed."
    )
    p.add_option("-G", "--groups", action="store_true",
        help="Use package groups data if True"
    )
    p.add_option("-d", "--datadir", help="Dir in which repodata cache was saved")
    p.add_option("-o", "--output", help="Output filename [stdout]")
    p.add_option("-f", "--fmt", choices=FORMATS,
        help="Output format [%default]"
    )
    p.add_option("-v", "--verbose", action="store_true", help="Verbose mode")

    return p


def main():
    p = option_parser()
    (options, args) = p.parse_args()

    logging.getLogger().setLevel(DEBUG if options.verbose else INFO)

    if not args:
        p.print_usage()
        sys.exit(1)

    if not options.datadir:
        options.datadir = raw_input("Specify repodata cache dir > ")

    rpmsfile = args[0]

    packages = get_packages_from_file(rpmsfile, options.parse)
    logging.info("Found %d packages in %s" % (len(packages), rpmsfile))

    data = RR.load_dumped_repodata(options.datadir)

    # 1. Minify packages list:
    (ps, ps_required) = minify_packages(data["requires"], packages)
    logging.info("Minified packages: %d -> %d" % (len(packages), len(ps)))

    if options.groups:
        gps = find_groups(data["groups"], ps, ps_required)
    else:
        gps = []

    output = open(options.output, 'w') if options.output else sys.stdout
    dump(gps, ps, ps_required, output, options.fmt)
    output.close()


if __name__ == '__main__':
    main()

# vim:sw=4:ts=4:et:
