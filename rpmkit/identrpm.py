#
# Identify given RPMs with using RHN API.
#
# Copyright (C) 2011, 2012 Red Hat, Inc.
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
import rpmkit.swapi as SW
import rpmkit.rpmutils as RU

import commands
import logging
import optparse
import os
import pprint
import re
import shlex
import sys


def parse_package_label(label):
    """
    Return NVR[A] (name, version, release[, arch]) dict of package constructed
    from given label (output of 'rpm -qa') containing version and other
    information.

    >>> eq = SW.dict_equals
    >>> d_ref = {
    ...     'arch': 'noarch', 'label': 'autoconf-2.59-12.noarch',
    ...     'name': 'autoconf', 'version': '2.59', 'release': '12',
    ... }
    >>> d = parse_package_label('autoconf-2.59-12.noarch')
    >>> assert eq(d, d_ref), "exp. %s vs. %s" % (str(d_ref), str(d))
    >>> d_ref = {
    ...     'arch': 'i386', 'label': 'MySQL-python-1.2.1-1.i386',
    ...     'name': 'MySQL-python', 'version': '1.2.1', 'release': '1',
    ... }
    >>> d = parse_package_label('MySQL-python-1.2.1-1.i386')
    >>> assert eq(d, d_ref), "exp. %s vs. %s" % (str(d_ref), str(d))
    >>> d_ref = {
    ...     'label': 'cdparanoia-alpha9.8-27.2', 'name': 'cdparanoia',
    ...     'version': 'alpha9.8', 'release': '27.2'
    ... }
    >>> d = parse_package_label('cdparanoia-alpha9.8-27.2')
    >>> assert eq(d, d_ref), "exp. %s vs. %s" % (str(d_ref), str(d))
    >>> d_ref = {
    ...     'arch': 'i386', 'label': 'ash-0.3.8-20.el4_7.1-i386',
    ...     'name': 'ash', 'version': '0.3.8', 'release': '20.el4_7.1'
    ... }
    >>> d = parse_package_label('ash-0.3.8-20.el4_7.1-i386')
    >>> assert eq(d, d_ref), "exp. %s vs. %s" % (str(d_ref), str(d))

    # FIXME: It seems there are some other special cases such $version and
    # $release cannot be parsed correctly:

        parse_package_label('amanda-2.4.4p1.0.3E')  ==> Fail
    """
    pkg = {'label': label}

    arch_re = re.compile(
        r"(?:.|-)+(?P<arch>i[356]86|x86_64|ppc|ia64|s390|s390x|noarch)"
    )
    m = arch_re.match(label)
    if m:
        arch = m.groupdict().get('arch')
        pkg['arch'] = arch
        label = label[:label.rfind(arch) - 1]
        #logging.debug("modified label=%s, arch=%s" % (label, arch))

    # Version string is consist of [0-9.]+ as usual, however there are some
    # special cases of which version strings are consist of [a-zA-Z]+[0-9.]+
    # such like cdparanoia, rarpd and kinput2.
    pkg_re = re.compile(r'(?P<name>\S+)-(?P<version>[^-]+)-(?P<release>\S+)')

    m = pkg_re.match(label)
    if m:
        pkg.update(m.groupdict())
    else:
        pkg_re_2 = re.compile(r'(?P<name>\S+)-(?P<version>[0-9]+)')
        m = pkg_re_2.match(label)
        if m:
            pkg.update(m.groupdict())

    return pkg


def complement_package_metadata(pkg):
    """Get missing package metadata and returns a dict.

    :param pkg:  dict(name, version, release, ...)
    """
    try:
        cfmt = "-A \"{name},{version},{release},\'\',{arch}\" " + \
            "packages.findByNvrea"
        m = " Try getting w/ packages.findByNvrea, arch="

        c = cfmt.format(**pkg)
        logging.info(m + pkg["arch"])

        cs = shlex.split(c)
        logging.debug(" args passed to swapi.main(): " + str(cs))

        (r, _opts) = SW.main(cs)

        if not r:
            pkg["arch"] = "noarch"  # override it.
            logging.info(m + "noarch")
            c = cfmt.format(**pkg)

            cs = shlex.split(c)
            logging.debug(" args passed to swapi.main(): " + str(cs))

            (r, _opts) = SW.main(cs)

        logging.debug("q=" + cmd + ", r=" + str(r))

        r[0]["epoch"] = RU.normalize_epoch(r[0]["epoch"])

        if not r[0].get("arch", False):
            r[0]["arch"] = r[0]["arch_label"]

        return r[0]

    except Exception, e:
        try:
            fmt = "-A \"name:{name} AND version:{version} AND " + \
                "release:{release}\" packages.search.advanced"
            cmd = fmt.format(**pkg)

            logging.info(" Try getting w/ packages.search.advanced")

            cs = shlex.split(cmd)
            logging.debug(" args passed to swapi.main(): " + str(cs))

            (r, _opts) = SW.main(cs)
            logging.debug("q=" + cmd + ", r=" + str(r))

            r[0]["epoch"] = RU.normalize_epoch(r[0]["epoch"])

            if not r[0].get("arch", False):
                r[0]["arch"] = r[0]["arch_label"]

            return r[0]

        except Exception, e:
            print str(e)

            logging.error("Failed to query: "
                          "nvr=({name}, {version}, {release})".format(**pkg))
            r = pkg
            r["epoch"] = 0
            r["arch"] = "?"

            return r


def load_packages(pf):
    """Load package info list from given file.

    :param pf: Packages list file.
    """
    return [l.rstrip() for l in open(pf).readlines()
            if l and not l.startswith("#")]


def init_log(verbose):
    """Initialize logging module
    """
    level = logging.WARN  # default

    if verbose > 0:
        level = logging.INFO

        if verbose > 1:
            level = logging.DEBUG

    logging.basicConfig(level=level)


def main(argv=sys.argv):
    default_format = "{name},{version},{release},{arch},{epoch}"
    defaults = {
        "verbose": 0,
        "arch": "x86_64",
        "format": None,
    }

    p = optparse.OptionParser("""%prog [Options...] [RPM_0 [RPM_1 ...]]

where RPM_N = <name>-<version>-<release>[-<arch>]

Examples:

$ identrpm --format "{name},{version},{release},{arch},{epoch}" \
>   autoconf-2.59-12.noarch
autoconf,2.59,12,noarch,0

$ identrpm --format "{name}: {summary}" autoconf-2.59-12
autoconf: A GNU tool for automatically configuring source code.
    """)
    p.set_defaults(**defaults)

    p.add_option("-v", "--verbose", action="count", help="Verbose mode")
    p.add_option("-D", "--debug", action="store_const", dest="verbose",
                 const=2, help="Debug mode")
    p.add_option("-i", "--input",
                 help="Packages list file (output of 'rpm -qa')")
    p.add_option("-A", "--arch", help="Architecture of package[s] [%default]")
    p.add_option("-F", "--format",
                 help="Output format, e.g %s" % default_format)

    (options, packages) = p.parse_args(argv[1:])

    init_log(options.verbose)

    if options.input:
        packages = load_packages(options.input)
    else:
        if not packages:
            p.print_usage()
            sys.exit(1)

    for plabel in packages:
        p = parse_package_label(plabel)

        logging.info(" Guessd p=" + str(p))

        if not p.get("arch"):
            p["arch"] = options.arch

        logging.debug(" p=" + str(p))
        p = complement_package_metadata(p)

        if p is None:
            print "Not found: " + plabel
        else:
            if options.format:
                print options.format.format(**p)
            else:
                pprint.pprint(p)


if __name__ == '__main__':
    main(sys.argv)


# vim:sw=4:ts=4:et:
