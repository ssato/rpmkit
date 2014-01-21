#
# Identify given RPMs list with using RHN package search APIs.
#
# Copyright (C) 2011 - 2014 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato@redhat.com>
# License: GPLv3+
#
"""Identify given RPMs list.
"""
from __future__ import print_function

import rpmkit.rpmutils as RR
import rpmkit.swapi as SW
import rpmkit.utils as RU

import anyconfig
import commands
import datetime
import logging
import multiprocessing
import operator
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


def uniq(xs, sort=False):
    """
    :param xs: Iterable object :: list, tuple, generator, etc.
    :param sort: Result will be sorted if True

    >>> uniq((1, 3, 0, 5, -1))
    [0, 1, 3, 5, -1]
    >>> uniq((1, 3, 0, 5, -1), True)
    [-1, 0, 1, 3, 5]
    """
    return (sorted if sort else list)(set(xs))


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
        logging.info("Succeed to parse %(label)s: n=%(name)s, v=%(version)s, "
                     "r=%(release)s" % pkg)
        return pkg

    LOG.error("Failed to parse NVR string: label=%s, epoch=%d" %
              (label, pkg['epoch']))
    return None


def find_rpm_by_nvrea(pkg, options=[]):
    """
    :param pkg: A dict contains RPM basic information such as name, version,
        release, ...
    :param options: List of option strings passed to
        :function:`rpmkti.swapi.call`, e.g. ['--verbose', '--server ...']

    :return: List of another pkg dicts

    see also: http://red.ht/1jgCNCh
    """
    epoch = ' ' if pkg['epoch'] == 0 else pkg['epoch']
    api_args = [pkg['name'], pkg['version'], pkg['release'], epoch,
                pkg['arch']]
    try:
        return SW.call('packages.findByNvrea', api_args, options)
    except RuntimeError, IndexError:
        return []


def find_rpm_by_search(pkg, options=[]):
    """
    :param pkg: A dict contains RPM basic information such as name, version,
        release, ...
    :param options: List of option strings passed to
        :function:`rpmkti.swapi.call`, e.g. ['--verbose', '--server ...']

    :return: List of another pkg dicts

    see also: http://red.ht/1dIs967
    """
    epoch = ' ' if pkg['epoch'] == 0 else pkg['epoch']
    arg_fmt = "name:%(name)s AND version:%(version)s AND release:%(release)s"

    if pkg.get('epoch', 0) != 0:
        arg_fmt += " AND epoch:%(epoch)d"

    if pkg.get('arch', False):
        arg_fmt += " AND arch:%(arch)s"

    try:
        return SW.call('packages.search.advanced', [arg_fmt % pkg], options)
    except RuntimeError, IndexError:
        return []


def complement_rpm_metadata(pkg, options=[]):
    """
    Get missing package metadata and return a dict.

    :param pkg: A dict contains RPM basic information such as name, version,
        release, ...
    :param options: List of option strings passed to
        :function:`rpmkti.swapi.call`, e.g. ['--verbose', '--server ...']

    :return: Updated dict
    """
    def _normalize(p):
        if 'arch_label' in p and 'arch' not in p:
            p['arch'] = p['arch_label']
        p['epoch'] = RR.normalize_epoch(p['epoch'])

        return p

    logging.info("Try fetching w/ the API, packages.findByNvrea: " + str(pkg))
    if pkg.get('arch', False):
        ps = find_rpm_by_nvrea(pkg, options)
        if ps:
            return [_normalize(p) for p in ps]

    logging.info("Try fetching w/ the API, packages.search.advanced: "
                 "%s" % str(pkg))
    ps = find_rpm_by_search(pkg, options)

    if ps:
        return [_normalize(p) for p in ps]

    return []


def identify(label, details=False, options=[]):
    """
    :param label: Maybe RPM's label, '%{n}-%{v}-%{r}.%{arch} ....' in the RPM
        list gotten by running 'rpm -qa' or the list file found in sosreport
        archives typically.
    :param details: Try to get extra information other than NVREA if True.
    :param options: List of option strings passed to
        :function:`rpmkti.swapi.call`, e.g. ['--verbose', '--server ...']

    :return: List of pkg dicts. Each dict contains RPM basic info such as name,
        version, release, arch and epoch.
    """
    p = parse_rpm_label(label)
    logging.info(" Guessd p=" + str(p))

    if not p:
        logging.error("Failed to parse given RPM label: " + label)
        return []

    keys = ('name', 'version', 'release', 'epoch', 'arch')
    if not details and all(k in p for k in keys):
        return [p]  # We've got enough information of this RPM.

    return complement_rpm_metadata(p)


def identify_(ldo):
    """
    :param ldo: A tuple of (label, details, options) or
        (label, kwargs) (kwargs = dict(details=, options=, ) passed to
        :function:`identify`.
    :return: List of pkg dicts. Each dict contains RPM basic info such as name,
        version, release, arch and epoch.
    """
    lldo = len(ldo)
    assert lldo > 0, "Null tuple passed: ldo=" + str(ldo)

    if lldo < 2:
        return identify(ldo[0])
    elif lldo < 3:
        if isinstance(lldo[1], dict):
            return identify(ldo[0], **ldo[1])
        else:
            return identify(ldo[0], ldo[1])
    else:
        return identify(ldo[0], ldo[1], ldo[2])


_NCPUS = multiprocessing.cpu_count()


def identify_rpms(labels, details=False, newer=True, options=[],
                  nprocs=_NCPUS):
    """
    :param labels: List RPM labels
    :param details: Get extra information other than RPM's N, V, R, E, A if
        True or get them from RHN / RH Satellite if not available
    :param newer: Sort by epochs; older is prior to newers
    :param options: List of option strings passed to
        :function:`rpmkti.swapi.call`, e.g. ['--verbose', '--server ...']
    :param nprocs: Number of parallelized processes to identify each lables

    :return: List of list of RPM info dicts :: [[p]]
    """
    if nprocs > 1:
        pool = multiprocessing.Pool(processes=nprocs)
        pss = pool.map(identify_, ((l, details, options) for l in labels))
    else:
        pss = [identify(label, details, options) for label in labels]

    if newer:
        return [sorted(ps, key=operator.itemgetter("epoch"), reverse=True)
                for ps in pss]
    else:
        return [sorted(ps, key=operator.itemgetter("epoch")) for ps in pss]


def load_packages_g(pf):
    """
    Load package info list from given file, generator version.

    :param pf: Packages list file.
    """
    for l in open(pf).readlines():
        if l.startswith('#'):
            continue

        l = l.rstrip()

        if not l:
            continue

        yield l.split(' ')[0] if ' ' in l else l


def load_packages(pf):
    """Load package info list from given file.

    :param pf: Packages list file.
    """
    return uniq(load_packages_g(pf))


def init_log(verbose):
    """Initialize logging module
    """
    level = logging.WARN  # default

    if verbose > 0:
        level = logging.INFO

        if verbose > 1:
            level = logging.DEBUG

    logging.basicConfig(level=level)


def process_datetime_g(ps):
    """
    Returned results w/ swapi.call may contain datetime.datetime object but
    datetime.datetime objects cannot be serialized in JSON format and need to
    be converted into other object such as str instance.
    """
    for p in ps:
        for k in p.keys():
            if isinstance(p[k], datetime.datetime):
                p[k] = p[k].strftime("%Y-%m-%dT%H:%M:%S")

        yield p


def print_outputs(ps, format=None, output=None):
    if format:
        out = open(output, 'w') if output else sys.stdout
        for p in ps:
            print(format.format(**p), file=out)
    else:
        if output:
            anyconfig.dump(sorted(process_datetime_g(ps),
                                  key=operator.itemgetter("name")),
                           output)
        else:
            for p in ps:
                print(pprint.pformat(p), sys.stdout)


def main(argv=sys.argv):
    default_format = "{name},{version},{release},{arch},{epoch}"
    defaults = dict(verbose=0, format=None, details=False, sw_options=[],
                    input=None, output=None, latest=False, all=False)

    p = optparse.OptionParser("""%prog [Options...] [RPM_0 [RPM_1 ...]]

where RPM_N = <name>-<version>-<release>[-<arch>]

Examples:

$ identrpm --format "{name},{version},{release},{arch},{epoch}" \
>   autoconf-2.59-12.noarch
autoconf,2.59,12,noarch,0

$ identrpm --details --format "{name}: {summary}" autoconf-2.59-12
autoconf: A GNU tool for automatically configuring source code.
    """)
    p.set_defaults(**defaults)

    p.add_option("-i", "--input",
                 help="Packages list file path (output of 'rpm -qa')")
    p.add_option("-o", "--output",
                 help="Output file path [stdout]. It must be ends w/ .json, "
                      "yaml, etc.")
    p.add_option("-F", "--format",
                 help="Output format, e.g %s" % default_format)
    p.add_option("", "--details", action="store_true",
                 help="Get extra information other than RPM's N, V, R, E, A")
    p.add_option("", "--latest", action="store_true",
                 help="Output only the latest RPMs instead of oldest RPMs")
    p.add_option("", "--all", action="store_true", help="Output all RPMs")
    p.add_option("", "--sw-options", action="append",
                 help="Options passed to swapi, can be specified multiple"
                      "times.")
    p.add_option("-v", "--verbose", action="count", help="Verbose mode")
    p.add_option("-D", "--debug", action="store_const", dest="verbose",
                 const=2, help="Debug mode")

    (options, packages) = p.parse_args(argv[1:])

    init_log(options.verbose)

    if options.input:
        packages = load_packages(options.input)
    else:
        if not packages:
            p.print_usage()
            sys.exit(1)

    pss = identify_rpms(packages, options.details, options.latest,
                        options.sw_options)
    if options.all:
        print_outputs(RU.concat(pss), options.format, options.output)
    else:
        print_outputs([ps[0] for ps in pss if ps], options.format,
                      options.output)

if __name__ == '__main__':
    main(sys.argv)

# vim:sw=4:ts=4:et:
