#! /usr/bin/python
#
# Identify given RPMs with using RHN API.
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
# Requirements: spacecmd
#
import rpmkit.swapi as SW

import commands
import logging
import optparse
import os
import re
import shlex
import sys



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


def parse_package_label(label):
    """
    Return NVR[A] (name, version, release[, arch]) dict of package constructed
    from given label (output of 'rpm -qa') containing version and other
    information.

    >>> parse_package_label('MySQL-python-1.2.1-1.i386')
    {'arch': 'i386', 'label': 'MySQL-python-1.2.1-1.i386', 'name': 'MySQL-python', 'release': '1.2.1', 'version': '11'}
    >>> parse_package_label('cdparanoia-alpha9.8-27.2')
    {'label': 'cdparanoia-alpha9.8-27.2', 'name': 'cdparanoia', 'release': 'alpha9.8', 'version': '27.2'}
    >>> parse_package_label('ash-0.3.8-20.el4_7.1-i386')
    {'arch': 'i386', 'label': 'ash-0.3.8-20.el4_7.1-i386', 'name': 'ash', 'release': '0.3.8', 'version': '20.el4_7.1'}

    ## FIXME: It seems there are some other special cases such $version and
    ## $release cannot be parsed correctly:
    ##
    ##   parse_package_label('amanda-2.4.4p1.0.3E')  ==> Fail
    """
    pkg = {'label':label}

    arch_re = re.compile(r'(?:.|-)+(?P<arch>i[356]86|x86_64|ppc|ia64|s390|s390x|noarch)')
    m = arch_re.match(label)
    if m:
        arch = m.groupdict().get('arch')
        pkg['arch'] = arch
        label = label.strip(arch)[:-1]

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


def add_missing_infos(pkg, arch="x86_64"):
    """Get missing package metadata and returns a dict.

    :param pkg:  dict(name, version, release, ...)
    """
    pkg.update(arch=arch)

    try:
        c = "-A \"{name},{version},{release},\'\',{arch}\" packages.findByNvrea".format(**pkg)
        (r, _opts) = SW.mainloop(shlex.split(c))
        
        if not r:
            c = "-A \"{name},{version},{release},\'\',noarch\" packages.findByNvrea".format(**pkg)
            (r, _opts) = SW.mainloop(shlex.split(c))
 
        logging.debug("q=" + cmd + ", r=" + str(r))

        r[0]["epoch"] = normalize_epoch(r[0]["epoch"])

        if not r[0].get("arch", False):
            r[0]["arch"] = r[0]["arch_label"]

        return r[0]

    except Exception, e:
        try:
            fmt = '-A "name:{name} AND version:{version} AND release:{release}" packages.search.advanced'
            cmd = fmt.format(**pkg)

            (r, _opts) = SW.mainloop(shlex.split(cmd))
            logging.debug("q=" + cmd + ", r=" + str(r))

            r[0]["epoch"] = normalize_epoch(r[0]["epoch"])

            if not r[0].get("arch", False):
                r[0]["arch"] = r[0]["arch_label"]

            return r[0]

        except Exception, e:
            #raise RuntimeError(str(e))
            logging.error("failed to query: nvr=({name}, {version}, {release})".format(**pkg))
            r = pkg
            r["epoch"] = 0
            r["arch"] = "?"

            return r


def load_packages(pf):
    """Load package info list from given file.

    :param pf: Packages list file.
    """
    return [l.rstrip() for l in open(pf).readlines() if l and not l.startswith("#")]


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
    format = "{name},{version},{release},{arch},{epoch}"

    p = optparse.OptionParser("%prog [Options...] [RPM_0 [RPM_1 ...]]")

    p.add_option("-v", "--verbose", help="Verbose mode", default=0, action="count")
    p.add_option("-i", "--input", help="Packages list file (output of 'rpm -qa')")
    p.add_option("-A", "--arch", help="Architecture of package[s] [%default]", default="x86_64")
    p.add_option("-F", "--format", help="Output format [%default]", default=format)

    (options, packages) = p.parse_args(argv[1:])

    init_log(options.verbose)

    if options.input:
        packages = load_packages(options.input)
    else:
        if not packages:
            p.print_usage()
            sys.exit(1)

    for pl in packages:
        p = parse_package_label(pl)

        logging.debug("pkg=" + str(p))
        p = add_missing_infos(p, options.arch)

        if p is None:
            print "Not found: " + pl
        else:
            print options.format.format(**p)


if __name__ == '__main__':
    main(sys.argv)

# vim: sw=4 ts=4 et:
