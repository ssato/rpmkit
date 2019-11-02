#
# Copyright (C) 2011 - 2013 Red Hat, Inc.
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
from operator import itemgetter

import rpmkit.utils as RU
import rpmkit.memoize as RM
import itertools
import logging
import operator
import os
import re
import rpm


RPM_BASIC_KEYS = ("name", "version", "release", "epoch", "arch")
RPMDB_SUBDIR = "var/lib/rpm"


def ucat(xss):
    return RU.uniq(RU.concat(xss))


def rpm_header_from_rpmfile(rpmfile):
    """
    Read rpm.hdr from rpmfile.
    """
    with open(rpmfile, "rb") as f:
        return rpm.TransactionSet().hdrFromFdno(f)

    return None


def _is_noarch(srpm):
    """
    Detect if given srpm is for noarch (arch-independent) package.
    """
    h = rpm_header_from_rpmfile(srpm)
    if h is None:
        return False  # TODO: What should be returned?

    return h["arch"] == "noarch"


is_noarch = RM.memoize(_is_noarch)


def normalize_arch(arch):
    """
    Normalize given package's arch.

    NOTE: $arch maybe '(none)', 'gpg-pubkey' for example.

    >>> normalize_arch("(none)")
    'noarch'
    >>> normalize_arch("x86_64")
    'x86_64'
    """
    return "noarch" if arch == "(none)" else arch


def normalize_epoch(epoch):
    """Normalize given package's epoch.

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

    if isinstance(epoch, str):
        return int(epoch) if re.match(r".*(\d+).*", epoch) else 0
    else:
        assert isinstance(epoch, int), \
            "epoch is not an int object: " + repr(epoch)
        return epoch  # int?


def normalize(p):
    """
    :param p: dict(name, version, release, epoch, arch)
    """
    try:
        p["arch"] = normalize_arch(p.get("arch", p.get("arch_label", False)))
        p["epoch"] = normalize_epoch(p["epoch"])
    except KeyError:
        raise KeyError("p=" + str(p))

    return p


def h2nvrea(h, keys=RPM_BASIC_KEYS):
    """
    :param h: RPM DB header object
    :param keys: RPM Package dict keys
    """
    return dict(zip(keys, [h[k] for k in keys]))


def rpm_transactionset(root='/', readonly=True):
    """
    Return rpm.TransactionSet object.

    :param root: RPM DB root dir
    :param readonly: Return read-only transaction set to pure query purpose

    :return: An instance of rpm.TransactionSet
    """
    if not root.startswith('/'):
        root = os.path.abspath(root)

    ts = rpm.TransactionSet(root)

    if readonly:
        # see also: rpmUtils/transaction.py:initReadOnlyTransaction()
        ts.setVSFlags((rpm._RPMVSF_NOSIGNATURES | rpm._RPMVSF_NODIGESTS))

    return ts


def _list_installed_rpms(root='/', keys=RPM_BASIC_KEYS, yum=False):
    """
    Return a list of installed RPMs.

    :param root: RPM DB root dir
    :param keys: RPM Package dict keys
    :param yum: Use yum instead of querying rpm db directly

    :return: List of RPM dict of given keys
    """
    if yum:
        p2d = lambda p: dict(zip(keys, operator.attrgetter(*keys)(p)))

        return sorted((p2d(p) for p in yum_list_installed(root)),
                      key=itemgetter(*keys))
    else:
        ts = rpm_transactionset(root)
        mi = ts.dbMatch()

        ps = [h2nvrea(h, keys) for h in mi]
        del mi, ts

        return sorted(ps, key=itemgetter(*keys))


list_installed_rpms = RM.memoize(_list_installed_rpms)


def guess_rhel_version(root, maybe_rhel_4=False):
    """
    Guess RHEL major version from RPM database based on
    rpmkit.rpms2sqldb.PackageMetadata.guess_rhel_version.

    - RHEL 3 => rpm.RPMTAG_RPMVERSION = '4.2.x' where x = 1,2,3
        or '4.2' or '4.3.3' (comps-*3AS-xxx) or '4.1.1' (comps*-3[aA][Ss])
    - RHEL 4 => rpm.RPMTAG_RPMVERSION = '4.3.3'
    - RHEL 5 => rpm.RPMTAG_RPMVERSION = '4.4.2' or '4.4.2.3'
    - RHEL 6 (beta) => rpm.RPMTAG_RPMVERSION = '4.7.0-rc1'

    :param root: RPM DB root dir
    :param maybe_rhel_4:
    """
    ps = yum_list_installed(root)
    assert ps, "No packages found for the root: " + root

    is_rhel_4 = False

    if maybe_rhel_4:
        for p in ps:
            if p.name in ("comps", "comps-extras"):
                if p.version.startswith('4'):
                    is_rhel_4 = True
                    break

    rpmver = ps[0].rpmversion
    irpmver = int(''.join(rpmver.split('.')[:4])[:4])

    # Handle special cases at first:
    if is_rhel_4:
        osver = 4
    elif (irpmver >= 421 and irpmver <= 423) or irpmver == 42:
        osver = 3
    elif irpmver in (433, 432, 431):
        osver = 4
    elif irpmver == 442:
        osver = 5
    elif irpmver >= 470 and irpmver < 4110:  # 471, 472, 480, etc.
        osver = 6
    elif irpmver >= 4110:  # 4111, etc.
        osver = 7
    else:
        osver = 0

    return osver


def _get_rpmver(root):
    ts = rpm_transactionset(root, True)
    rpmver = [h for h in ts.dbMatch()][0][rpm.RPMTAG_RPMVERSION]
    del ts

    return rpmver


def guess_rhel_version_simple(root):
    """
    Guess RHEL major version from RPM database. It's similar to the above
    :function:`guess_rhel_version` but does not process RHEL 3 cases.

    - RHEL 4 => rpm.RPMTAG_RPMVERSION = '4.3.3'
    - RHEL 5 => rpm.RPMTAG_RPMVERSION = '4.4.2' or '4.4.2.3'
    - RHEL 6 => rpm.RPMTAG_RPMVERSION >= '4.7.0-rc1'
    - RHEL 7 => rpm.RPMTAG_RPMVERSION >= '4.11.1'

    :param root: RPM DB root dir
    :param maybe_rhel_4:
    """
    rpmver = _get_rpmver(root)
    irpmver = int(''.join(rpmver.split('.')[:4])[:4])

    if irpmver in (433, 432, 431):
        osver = 4
    elif irpmver == 442:
        osver = 5
    elif irpmver >= 470 and irpmver < 4110:
        osver = 6
    elif irpmver >= 4110:
        osver = 7
    else:
        osver = 0

    return osver

def _compare_evr(evr1, evr2):
    """Stolen from yum (rpmUtils.miscutils.compareEVR) (yum: GPLv2+).

    :param evr1: A tuple of (Epoch, Version, Release)
    :param evr2: Likewise
    :return:
        1 if evr1 is newer than evr2, 0 if these are same version and -1 if
        evr2 is newer than evr1.
    """
    epoch1 = '0' if evr1[0] is None else str(evr1[0])
    epoch2 = '0' if evr2[0] is None else str(evr2[0])

    return rpm.labelCompare((epoch1, str(evr1[1]), str(evr1[2])),
                             (epoch2, str(evr2[1]), str(evr2[2])))


def pcmp(p1, p2):
    """Compare packages by NVRAEs.

    :param p1, p2: dict(name, version, release, epoch, arch)

    TODO: Make it fallback to rpm.versionCompare if yum is not available?

    >>> p1 = dict(name="gpg-pubkey", version="00a4d52b", release="4cb9dd70",
    ...           arch="noarch", epoch=0,
    ... )
    >>> p2 = dict(name="gpg-pubkey", version="069c8460", release="4d5067bf",
    ...           arch="noarch", epoch=0,
    ... )
    >>> pcmp(p1, p1) == 0
    True
    >>> pcmp(p1, p2) < 0
    True

    >>> p3 = dict(name="kernel", version="2.6.38.8", release="32",
    ...           arch="x86_64", epoch=0,
    ... )
    >>> p4 = dict(name="kernel", version="2.6.38.8", release="35",
    ...           arch="x86_64", epoch=0,
    ... )
    >>> pcmp(p3, p4) < 0
    True

    >>> p5 = dict(name="rsync", version="2.6.8", release="3.1",
    ...           arch="x86_64", epoch=0,
    ... )
    >>> p6 = dict(name="rsync", version="3.0.6", release="4.el5",
    ...           arch="x86_64", epoch=0,
    ... )
    >>> pcmp(p3, p4) < 0
    True
    """
    p2evr = itemgetter("epoch", "version", "release")
    assert p1["name"] == p2["name"], "Trying to compare different packages!"
    return _compare_evr(p2evr(p1), p2evr(p2))


def find_latest(packages):
    """Find the latest one from given packages have same name but with
    different versions.
    """
    assert packages, "Empty list was given!"
    return sorted(packages, cmp=pcmp)[-1]


def sort_by_names(xs):
    """
    :param xs: [dict(name, ...)]
    """
    return sorted(xs, key=itemgetter("name"))


def group_by_names_g(xs):
    """

    >>> xs = [
    ...   {"name": "a", "val": 1}, {"name": "b", "val": 2},
    ...   {"name": "c", "val": 3},
    ...   {"name": "a", "val": 4}, {"name": "b", "val": 5}
    ... ]
    >>> zs = [
    ...   ('a', [{'name': 'a', 'val': 1}, {'name': 'a', 'val': 4}]),
    ...   ('b', [{'name': 'b', 'val': 2}, {'name': 'b', 'val': 5}]),
    ...   ('c', [{'name': 'c', 'val': 3}])
    ... ]
    >>> [(n, ys) for n, ys in group_by_names_g(xs)] == zs
    True
    """
    for name, g in itertools.groupby(sort_by_names(xs), itemgetter("name")):
        yield (name, list(g))


def group_by_keys_g(xs, keys):
    """

    >>> xs = [
    ...   {"name": "a", "arch": "x86_64", "val": 1},
    ...   {"name": "b", "arch": "x86_64", "val": 2},
    ...   {"name": "a", "arch": "i686", "val": 4},
    ...   {"name": "b", "arch": "x86_64", "val": 5},
    ...   {"name": "b", "arch": "i686", "val": 2},
    ... ]
    >>> zs = [
    ...   (('a', 'i686'), [{'arch': 'i686', 'name': 'a', 'val': 4}]),
    ...   (('a', 'x86_64'), [{'arch': 'x86_64', 'name': 'a', 'val': 1}]),
    ...   (('b', 'i686'), [{'arch': 'i686', 'name': 'b', 'val': 2}]),
    ...   (('b', 'x86_64'),
    ...    [{'arch': 'x86_64', 'name': 'b', 'val': 2},
    ...     {'arch': 'x86_64', 'name': 'b', 'val': 5}])
    ... ]
    >>> [(n, ys) for n, ys in group_by_keys_g(xs, ("name", "arch"))] == zs
    True
    """
    _sort = lambda xs: sorted(xs, key=itemgetter(*keys))
    for keys, g in itertools.groupby(_sort(xs), itemgetter(*keys)):
        yield (keys, list(g))


def find_latests(packages, keys=("name", )):
    """Find the latest packages from given packages.

    It's similar to find_latest() but given packages may have different names.
    """
    return [find_latest(ps) for _n, ps in group_by_keys_g(packages, keys)]


def p2s(package):
    """Returns string representation of a package dict.

    :param package: (normalized) dict(name, version, release, arch)

    >>> p1 = dict(name="gpg-pubkey", version="069c8460", release="4d5067bf",
    ...           arch="noarch", epoch=0,
    ... )
    >>> p2s(p1)
    'gpg-pubkey-069c8460-4d5067bf.noarch:0'
    """
    return "%(name)s-%(version)s-%(release)s.%(arch)s:%(epoch)s" % package


def ps2s(packages, with_name=False):
    """Constructs and returns a string reprensents packages of which names
    are same but EVRs (versions and/or revisions, ...) are not same.

    >>> p1 = dict(name="gpg-pubkey", version="069c8460", release="4d5067bf",
    ...           arch="noarch", epoch=0,
    ... )
    >>> p2 = dict(name="gpg-pubkey", version="00a4d52b", release="4cb9dd70",
    ...           arch="noarch", epoch=0,
    ... )
    >>> r1 = ps2s([p1, p2])
    >>> r1
    '(e=0, v=069c8460, r=4d5067bf), (e=0, v=00a4d52b, r=4cb9dd70)'
    >>> ps2s([p1, p2], True) == "name=gpg-pubkey, " + r1
    True
    """
    name = "name=%s, " % packages[0]["name"]
    evrs = ", ".join(
        "(e=%(epoch)s, v=%(version)s, r=%(release)s)" % p for p in packages
    )

    return name + evrs if with_name else evrs


def list_to_dict_keyed_by_names(xs):
    """
    :param xs: [dict(name, ...)]
    """
    return dict((name, ys) for name, ys in group_by_names_g(xs))


def guess_os_version_from_rpmfile(rpmfile):
    """
    Guess RHEL major version from rpm file.

    - RHEL 3 => rpm.RPMTAG_RPMVERSION = '4.2.x' where x = 1,2,3
        or '4.2' or '4.3.3' (comps-*3AS-xxx) or '4.1.1' (comps*-3[aA][Ss])
    - RHEL 4 => rpm.RPMTAG_RPMVERSION = '4.3.3'
    - RHEL 5 => rpm.RPMTAG_RPMVERSION = '4.4.2' or '4.4.2.3'
    - RHEL 6 (beta) => rpm.RPMTAG_RPMVERSION = '4.7.0-rc1'

    :param rpmfile: Path to the RPM file
    """
    header = rpm_header_from_rpmfile(rpmfile)

    rpmver = header[rpm.RPMTAG_RPMVERSION]
    (name, version) = (header[rpm.RPMTAG_NAME], header[rpm.RPMTAG_VERSION])

    irpmver = int(''.join(rpmver.split('.')[:3])[:3])

    # Handle special cases at first:
    if name in ('comps', 'comps-extras') and version in ('3AS', '3as'):
        osver = 3
    elif name in ('comps', 'comps-extras') and version == '4AS':
        osver = 4
    elif name == 'rpmdb-redhat' and version == '3':
        osver = 3
    elif (irpmver >= 421 and irpmver <= 423) or irpmver == 42:
        osver = 3
    elif irpmver == 433 or irpmver == 432 or irpmver == 431:
        osver = 4
    elif irpmver == 442:
        osver = 5
    elif irpmver == 470:
        osver = 6
    elif irpmver >= 411:
        osver = 7
    else:
        osver = 0

    return osver

# vim:sw=4:ts=4:et:
