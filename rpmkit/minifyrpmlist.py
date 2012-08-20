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
from rpmkit.utils import concat, uniq

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


def find_groups_and_packages_map_0(gps, ps0):
    """
    :param gps: Group and Package pairs, [(group, [package])]
    :param ps0: Target packages list, [package]

    :return: [(group, found_packages_in_group, missing_packages_in_group)]
    """
    gps = [
        (g, [p for p in ps0 if p in ps], [p for p in ps if p not in ps0]) \
            for g, ps in gps
    ]

    # filter out groups having no packages in ps0 (gpp[1] => ps_found):
    return [gpp for gpp in gps if gpp[1]]


def cmp_groups(g1, g2):
    founds = len(g1[1]) - len(g2[1])
    if founds != 0:
        return founds
    else:
        return len(g2[2]) - len(g1[2])


def find_groups_and_packages_map(gps, ps0, optimize=True):
    """
    :param gps: Group and Package pairs, [(group, [package])]
    :param ps0: Target packages list, [package]
    :param optimize: Optimize groups map

    :return: [(group, found_packages_in_group, missing_packages_in_group)]
    """
    gps = find_groups_and_packages_map_0(gps, ps0)

    if not optimize:
        return gps

    # Find groups having max packages in ps0 one by one:
    gs = []
    ps_ref = ps0

    while True:
        if not gps:
            return gs

        cgs = sorted(gps, cmp=cmp_groups)

        g = cgs[0]
        gs.append(g)

        # rest of packages to search groups not in g:
        ps_ref = [p for p in ps_ref if p not in uniq(g[1])]
        gps = [(g, ps_f) for g, ps_f, _ps_m in cgs[1:]]

        gps = find_groups_and_packages_map_0(gps, ps_ref)


def score(ps_found, ps_missing):
    """
    see `find_groups_and_packages_map` also.
    """
    return len(ps_found) - len(ps_missing)


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
    """
    reqs = []  # packages in `packages` required by others.
    for p in packages:
        # find packages required by p, member of `packages` list, and not
        # member of prs:
        rs = uniq(concat((
            [r for r in rs if r in packages and r not in reqs] \
                for x, rs in requires if x == p
        )))
        if rs:
            reqs += rs
            logging.debug("Excluded as required by %s: %s" % (p, rs))

    return [p for p in packages if p not in uniq(reqs)]


_FORMAT_CHOICES = (_FORMAT_DEFAULT, _FORMAT_KS) = ("default", "ks")


def dump(groups, packages, output, limit=0, type=_FORMAT_DEFAULT):
    """
    :param groups: Group and member packages
    :param packages: Packages not in groups
    :param output: Output file object
    :param type: Format type
    """
    results = (
        (g, ps_found, ps_missing) for g, ps_found, ps_missing in
            groups if score(ps_found, ps_missing) > limit
    )
    if type == _FORMAT_DEFAULT:
        packages_in_groups = concat(ps_found for _g, ps_found, _ps in groups)
        print >> output, "# Package groups ----------------------------------"
        for g, ps_found, ps_missing in results:
            print >> output, "%s: ps_found=%s, ps_missing=%s, score=%d" % \
                (g, ps_found, ps_missing, score(ps_found, ps_missing))

        print >> output, "# Packages not in groups --------------------------"
        print >> output, "[%s, ...]" % \
            ", ".join(
                [p for p in packages if p not in packages_in_groups][:10]
            )
    else:
        ps_seen = concat(
            ps_found + ps_missing for _g, ps_found, ps_missing in groups
        )
        print >> output, "# kickstart config style packages list:"
        for g, ps_found, ps_missing in results:
            print >> output, '@' + g  # e.g. '@perl-runtime'
            print >> output, "# score = %d" % score(ps_found, ps_missing)
            print >> output, "# Packages of this group: %s" % ", ".join(ps_found[:10]) + "..."

            # Packages to excluded from this group explicitly:
            for p in ps_missing:
                print >> output, '-' + p

        for p in packages:
            if p not in ps_seen:
                print >> output, p


def option_parser():
    defaults = dict(
        comps=None,
        output=None,
        limit=0,
        repodir=None,
        dir=None,
        format=_FORMAT_DEFAULT,
        parse=False,
        verbose=False,
    )
    p = optparse.OptionParser("%prog [OPTION ...] RPMS_FILE")
    p.set_defaults(**defaults)

    p.add_option("-P", "--parse", action="store_true",
        help="Specify this if input is `rpm -qa` output and must be parsed."
    )
    p.add_option("-L", "--limit", help="Limit score to print [%default]")
    p.add_option("-r", "--repodir", help="Repo dir to refer package metadata")
    p.add_option("-d", "--dir", help="Dir where repodata cache was dumped")
    p.add_option(
        "-F", "--format", choices=_FORMAT_CHOICES,
        help="Output format type [%default]"
    )
    p.add_option("-o", "--output", help="Output filename [stdout]")
    p.add_option("-v", "--verbose", action="store_true", help="Verbose mode")

    return p


def main():
    p = option_parser()
    (options, args) = p.parse_args()

    logging.getLogger().setLevel(DEBUG if options.verbose else INFO)

    if not args:
        p.print_usage()
        sys.exit(1)

    if not options.repodir:
        options.repodir = raw_input(
            "Repository dir? e.g. '/contents/RHEL/6/3/x86_64/default/Server'"
        )

    if not options.dir:
        options.dir = RR.select_topdir()

    rpmsfile = args[0]

    packages = get_packages_from_file(rpmsfile, options.parse)
    logging.info("Found %d packages in %s" % (len(packages), rpmsfile))

    data = RR.load_dumped_repodata(options.repodir, options.dir)

    ps = minify_packages(data["requires"], packages)
    logging.info("Minified packages: %d -> %d" % (len(packages), len(ps)))

    output = open(options.output, 'w') if options.output else sys.stdout

    for p in ps:
        print >> output, p

    return  # disabled the following code for a while.

    gs = data["groups"]
    logging.info("Found %d groups in %s" % (len(gs), options.repodir))

    gps = find_groups_and_packages_map(gs, packages)
    logging.info("Found %d candidate groups" % len(gps))

    dump(gps, packages, output, options.limit, options.format)
    output.close()


if __name__ == '__main__':
    main()

# vim:sw=4:ts=4:et:
