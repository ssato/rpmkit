#
# Identify given RPMs list with using RHN package search APIs.
#
# Copyright (C) 2011 - 2014 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato@redhat.com>
# License: GPLv3+
#
"""Identify given RPMs list.
"""
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


LOG = logging.getLogger('rpmkit.identrpm')

_ARCHS = ('i[356]86', 'x86_64', 'ppc', 'ia64', 's390', 's390x', 'armv7hl',
          'noarch')
_ARCH_REG = re.compile(r"(?:.|-)+(?P<arch>" + '|'.join(_ARCHS) + r")$")

# NOTE: Version string consists of [0-9.]+ as usual, however it seems that
# there are some special cases of which version strings are consist of
# [a-zA-Z]+[0-9.]+ such like cdparanoia ('cdparanoia-alpha9.8-27.2'), rarpd and
# kinput2 in older version of RHEL, RHL or Fedora.
_NV_REG_BASE = r"^(?P<name>[^.]+)-(?P<version>[^-]+)"
_NV_REG = re.compile(_NV_REG_BASE + r'$')
_NVR_REG = re.compile(_NV_REG_BASE + r"-(?P<release>[^-]+)$")


def pkg_eq(pkg0, pkg1):
    """
    Compare a couple of dict contains RPM basic information (N, V, R, A, E).

    :param pkg0: A dict contains RPM basic information
    :param pkg1: Another dict contains RPM basic information

    >>> p0 = dict(name='aaa', version='0.0.1', release='1', arch='i686')
    >>> p1 = p0.copy()
    >>> p2 = p1.copy(); p2['epoch'] = 2
    >>> pkg_eq(p0, p1)
    True
    >>> pkg_eq(p0, p2)
    False
    """
    return all(pkg0.get(k) == pkg1.get(k) for k in
               ('name', 'version', 'release', 'arch', 'epoch'))


def parse_rpm_label(label, epoch=0, arch_reg=_ARCH_REG, nvr_reg=_NVR_REG):
    """
    Parse given maybe-rpm-label string ``label`` and return a dict contains
    RPM's basic information such as NVR[A] (name, version, release[, arch]) to
    identify the RPM.

    :param label: Maybe RPM's label, '%{n}-%{v}-%{r}.%{arch} ....' in the RPM
        list gotten by running 'rpm -qa' or the list file found in sosreport
        archives typically.
    :param epoch: Default epoch value
    :param arch_reg: Regex pattern of possible RPM build target archs
    :param nvr_reg: Regex pattern of RPM's name, version and release
    :param nv_reg: Regex pattern of RPM's name and version

    :return: A dict contains RPM's basic information or None (parse error)

    Possible format of RPM labels may be:

    * "%(name)s-%(version)s-%(release)s.%(arch)s": 'rpm -qa', sosreport.
    * "%(name)s-%(version)s-%(release)s-%(arch)s": 'rpm -qa' ? (old style)
    * "%(epoch)s:%(name)s-%(version)s-%(release)s.%(arch)s": yum ?
    * "%(name)s-%(epoch)s:%(version)s-%(release)s.%(arch)s": yum ?
    * "%(name)s-%(version)s-%(release)s"
    * "%(name)s-%(version)s": I don't think there is a way to distinguish
      between this and the above.
    * "%(name)s.%(arch)s": Likewise.

    See also :method:`yum.rpmsack.RPMDBPackageSack._match_repattern`

    NOTE: It seems there are some other special cases such $version and
    $release cannot be parsed correctly:

        parse_rpm_label('amanda-2.4.4p1.0.3E') ==> None (Failure)

    >>> refs = [dict(name='autoconf', version='2.59', release='12',
    ...              arch='noarch', epoch=0, label='autoconf-2.59-12.noarch'),
    ...         dict(name='MySQL-python', version='1.2.1', release='1',
    ...              arch='i386', epoch=0, label='MySQL-python-1.2.1-1.i386'),
    ...         dict(name='ash', version='0.3.8', release='20.el4_7.1',
    ...              arch='x86_64', epoch=0,
    ...              label='ash-0.3.8-20.el4_7.1-x86_64'),
    ...         dict(name='cdparanoia', version='alpha9.8', release='27.2',
    ...              epoch=0, label='cdparanoia-alpha9.8-27.2'),
    ...         dict(name='MySQL-python', version='1.2.1', release='1',
    ...              arch='i386', epoch=3,
    ...              label='3:MySQL-python-1.2.1-1.i386'),
    ...         dict(name='MySQL-python', version='1.2.1', release='1',
    ...              arch='i386', epoch=3,
    ...              label='MySQL-python-3:1.2.1-1.i386'),
    ...         dict(name='MySQL-python', version='1.2.1', release='1',
    ...              epoch=0, label='MySQL-python-1.2.1-1'),
    ... # This is not supported.
    ... #       dict(name='MySQL-python', version='1.2.1', epoch=0,
    ... #            label='MySQL-python-1.2.1'),
    ... # This is also no supported.
    ... #       dict(name='MySQL-python', arch='x86_64', epoch=0,
    ... #            label='MySQL-python.x86_64'),
    ...        ]
    >>> for r in refs:
    ...     x = parse_rpm_label(r['label'])
    ...     assert x is not None
    ...     assert pkg_eq(x, r), "%s, label=%s" % (x, r['label'])
    >>>
    """
    # ``label`` must not contain any white space chars.
    assert re.match(r"^\S+$", label), "Invalid RPM label: " + label

    pkg = {'label': label}

    # 1. Try to find arch and strip it from this label string.
    m = re.match(arch_reg, label)
    if m:
        arch = m.groupdict().get('arch')
        pkg['arch'] = arch
        label = label[:label.rfind(arch) - 1]

    # 2. Try to find epoch.
    if ':' in label:
        (maybe_epoch, label) = label.split(':')

        if '-' in maybe_epoch:
            (name, epoch) = maybe_epoch.rsplit('-', 1)
            (version, release) = label.rsplit('-', 1)

            try:
                pkg['epoch'] = int(epoch)
            except ValueError:
                LOG.error("Failed to parse epoch '%s'; name=%s, version=%s, "
                          "release=%s" % (epoch, name, version, release))
                return None

            pkg['name'] = name
            pkg['version'] = version
            pkg['release'] = release

            return pkg
        else:
            try:
                pkg['epoch'] = int(maybe_epoch)
            except ValueError:
                LOG.error("Failed to parse epoch '%s'; label=%s" %
                          (maybe_epoch, label))
                return None
    else:
        pkg['epoch'] = epoch

    m = nvr_reg.match(label)
    if m:
        pkg.update(m.groupdict())
        return pkg

    LOG.error("Failed to parse NVR string: label=%s, epoch=%d" %
              (label, pkg['epoch']))
    return None


def complement_rpm_metadata(pkg):
    """
    Get missing package metadata and return a dict.

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
        p = parse_rpm_label(plabel)

        logging.info(" Guessd p=" + str(p))

        if not p.get("arch"):
            p["arch"] = options.arch

        logging.debug(" p=" + str(p))
        p = complement_rpm_metadata(p)

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
