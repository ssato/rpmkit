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
from rpmkit.memoize import memoize
from rpmkit.utils import concat, uniq

from collections import deque
from itertools import groupby
from operator import itemgetter, attrgetter
from yum.rpmsack import RPMDBPackageSack

import rpmkit.tree as RT

import logging
import os
import random
import re
import sys
import rpm
import yum


RPM_BASIC_KEYS = ("name", "version", "release", "epoch", "arch")


def rpm_header_from_rpmfile(rpmfile):
    """
    Read rpm.hdr from rpmfile.
    """
    return rpm.TransactionSet().hdrFromFdno(open(rpmfile, "rb"))


def _is_noarch(srpm):
    """
    Detect if given srpm is for noarch (arch-independent) package.
    """
    return rpm_header_from_rpmfile(srpm)["arch"] == "noarch"


is_noarch = memoize(_is_noarch)


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


def yum_list_installed(root=None):
    """
    :param root: RPM DB root dir
    :return: List of yum.rpmsack.RPMInstalledPackage objects
    """
    if root is None:
        root = "/var/lib/rpm"

    sack = RPMDBPackageSack(root, cachedir=os.path.join(root, "cache"),
                            persistdir=root)

    return sack.returnPackages()  # NOTE: 'gpg-pubkey' is not in this list.


def list_installed_rpms(root=None, keys=RPM_BASIC_KEYS, yum=False):
    """
    :param root: RPM DB root dir
    :param keys: RPM Package dict keys
    :param yum: Use yum instead of querying rpm db directly
    :return: List of RPM dict of given keys
    """
    if yum:
        p2d = lambda p: dict(zip(keys, attrgetter(*keys)(p)))

        return sorted((p2d(p) for p in yum_list_installed(root)),
                      key=itemgetter(*keys))
    else:
        if root:
            rpm.addMacro("_dbpath", root)

        ts = rpm.TransactionSet()
        mi = ts.dbMatch()

        if root:
            rpm.delMacro("_dbpath")

        ps = [h2nvrea(h, keys) for h in mi]
        del mi, ts

        return sorted(ps, key=itemgetter(*keys))


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
    return yum.compareEVR(p2evr(p1), p2evr(p2))


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
    for name, g in groupby(sort_by_names(xs), itemgetter("name")):
        yield (name, list(g))


def find_latests(packages):
    """Find the latest packages from given packages.

    It's similar to find_latest() but given packages may have different names.
    """
    return [find_latest(ps) for _n, ps in group_by_names_g(packages)]


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


def find_updates_g(all_packages, packages):
    """Find all updates relevant to given (installed) packages.

    :param all_packages: all packages including latest updates
    :param packages: (installed) packages

    Both types are same [dict(name, version, release, epoch, arch)].
    """
    def is_newer(p1, p2):
        return pcmp(p1, p2) > 0  # p1 is newer than p2.

    ref_packages = list_to_dict_keyed_by_names(all_packages)

    for p in find_latests(packages):  # filter out older ones.
        candidates = ref_packages.get(p["name"], [])

        if candidates:
            cs = [normalize(c) for c in candidates]
            logging.debug(
                " update candidates for %s: %s" % (p2s(p), ps2s(cs))
            )

            updates = [c for c in cs if is_newer(c, p)]

            if updates:
                logging.debug(
                    " updates for %s: %s" % (p2s(p), ps2s(updates))
                )
                yield sorted(updates)


def _make_requires_dict(root=None, reversed=False):
    """
    Returns RPM dependency relations map.

    :param root: RPM Database root dir or None (use /var/lib/rpm).
    :param reversed: Returns a dict such
        {required_RPM: [RPM_requires]} instead of a dict such
        {RPM: [RPM_required]} if True.

    :return: Requirements relation map, {p: [required]} or {required: [p]}

    NOTEs:
     * X.required_packages returns RPMs required to install it (X instance).
       e.g. gc (X) requires libgcc

       where X = yum.rpmsack.RPMInstalledPackage

     * X.requiring_packages returns RPMs requiring it (X instance).
       e.g. libgcc (X) is required by gc

     * yum.rpmsack.RPMInstalledPackage goes away in DNF so that
       I have to find similar function in DNF.

       (see also: http://fedoraproject.org/wiki/Features/DNF)
    """
    def list_reqs(p):
        fn = "requiring_packages" if reversed else "required_packages"
        return sorted(x.name for x in getattr(p, fn)())

    return dict((p.name, list_reqs(p)) for p in yum_list_installed(root))


make_requires_dict = memoize(_make_requires_dict)


def make_reversed_requires_dict(root):
    """
    :param root: root dir of RPM Database
    :return: {name_required: [name_requires]}
    """
    return make_requires_dict(root, True)


## The followings are experimental...
sys.setrecursionlimit(1000)


def _get_leaves(root=None):
    """
    Get leaves which no other RPMs require.

    :param root: root dir of RPM Database
    :return: List of RPM names which is not required by any other RPMs
    """
    rreqs = make_requires_dict(root, True)  # required -> [p]
    return [r for r, ps in rreqs.iteritems() if not ps]


get_leaves = memoize(_get_leaves)


def walk_dependency_graph_0(root_name, rreqs, leaves, seens=[], topdown=False):
    """
    Walk RPM dependency tree from given root RPM name recursively and yields a
    all paths to leaves.

    :param root_name: Root RPM name
    :param rreqs: Dependency map, {required: [requires]}.
    :param leaves: RPMs not required by other RPMs.
    :param seens: Seen RPM names to avoid walking circular depdendency trees.
    :param topdown: Yields tuples before these children.
    """
    list_children = lambda node: rreqs.get(node, [])

    return [p for p in RT.walk([root_name], list_children, leaves=leaves) if p]


def walk_dependency_graph(root=None):
    """
    :param root: root dir of RPM Database
    :return: List of path of dependency graph
    """
    reqs = make_requires_dict(root)  # p -> [required]
    rreqs = make_requires_dict(root, True)  # required -> [p]

    # NOTE: roots require no other RPMs
    roots = [p for p, rs in reqs.iteritems() if not rs]
    leaves = get_leaves(root)

    pss = [walk_dependency_graph_0(rn, rreqs, leaves) for rn in roots]
    return [ps for ps in pss if ps]  # Remove empty lists


def make_dependency_graph(root=None):
    """
    :param root: root dir of RPM Database
    :return: List of path of dependency graph
    """
    maxlen = lambda paths: max(len(p) for p in paths)

    pss = sorted(walk_dependency_graph(root), key=maxlen)
    leaves = get_leaves(root)

    trees = [RT.make_tree_from_path(ps, leaves=leaves) for ps in pss]

    return trees


# vim:sw=4:ts=4:et:
