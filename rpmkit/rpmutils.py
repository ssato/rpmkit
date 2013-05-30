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


def list_installed_rpms(rpmdb_dir=None, keys=RPM_BASIC_KEYS):
    """
    :param rpmdb_dir:
    :param keys: RPM Package dict keys
    :return: List of RPM dict of given keys
    """
    if rpmdb_dir:
        rpm.addMacro("_dbpath", rpmdb_dir)

    ts = rpm.TransactionSet()
    mi = ts.dbMatch()

    if rpmdb_dir:
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


def make_requires_dict(root):
    """
    Based on yumQuiet.getDeps() in repo-graph in yum-utils licensed and
    distributed under GPLv2+.

    :param root: root dir of RPM Database
    :return: Requirement relation map, {package: [required_package]}
    """
    requires = dict()
    providers = dict()
    skip = []

    def _find_reqs(name, cachedb, requires):
        return [x for x in cachedb.keys() if x != name]

    sack = RPMDBPackageSack(root, cachedir=os.path.join(root, "cache"),
                            persistdir=root)

    for p in sack.returnPackages():
        cachedb = dict()

        reqs = p.returnPrco("requires")

        # It seems there is no such cases but just in case.
        if not reqs:
            requires[p.name] = []
            continue

        for rs in reqs:
            reqname = rs[0]

            # Special cases: rpmlib* or self dependency
            if reqname.startswith("rpmlib") or reqname == p.name:
                continue

            prov = providers.get(reqname, None)

            if prov is None:
                provs = sack.searchProvides(reqname)
                if provs:
                    prov = provs[0].name
                    providers[reqname] = prov
                else:
                    logging.warn("Nothing provides " + reqname)
                    continue

            if prov == p.name:
                cachedb[prov] = None
            else:
                if prov in cachedb or prov in skip:
                    continue
                else:
                    cachedb[prov] = None

            requires[p.name] = _find_reqs(p.name, cachedb, requires)

    return requires


def make_reversed_requires_dict(root):
    """
    :param root: root dir of RPM Database
    :return: {name_required: [name_requires]}
    """
    reqs_map = make_requires_dict(root)  # {req: [reqd]}
    rreqs = dict()  # {reqd : [req]}

    for p, rs in reqs_map.iteritems():
        for r in rs:
            if r == p:
                continue  # skip self.

            rreqs[r] = sorted(set(rreqs.get(r, []) + [p]))

    return rreqs


## The followings are very experimental...
sys.setrecursionlimit(1000)


def pp_nodes(ns, limit=None):
    """
    Pretty print list of nodes.

    :param ns: List of nodes
    :param limit: Limit items to print
    :return: Pretty printed list string
    """
    if limit is None:
        limit = len(ns) + 1

    return ", ".join(n.name for n in ns[:limit])


class Node(object):

    def __init__(self, name, children=[], is_root=False):
        """
        :param name: Name :: str
        :param children: Child nodes :: [Node]
        :param is_root: Is this node root ?
        """
        self.name = name
        self._is_root = is_root

        self.children = set(children)
        self.childnames = set(c.name for c in children)
        self._has_children = bool(self.childnames)

    def get_children(self):
        return self.children

    def get_child_names(self):
        return self.childnames

    def has_children(self):
        return self._has_children

    def add_child(self, cnode, seens=[]):
        """
        :param cnode: Child node to add
        :type Node:
        :param seens: List of seen node names
        :type [str]:
        """
        if not seens:
            seens = [self.name] + list(self.get_child_names())

        if cnode.name in seens:
            return  # Avoid circular references

        self.children.add(cnode)
        self.childnames.add(cnode.name)

        if not self.has_children():
            self._has_children = True

    def add_children(self, diff):
        """
        :param diff: Node list
        :type [Node]:
        """
        for c in diff:
            self.add_child(c)

    def is_root(self):
        return self._is_root

    def is_leaf(self):
        return not self.has_children()

    def make_not_root(self):
        self._is_root = False

    def __str__(self):
        return repr(self)

    def __repr__(self):
        return "Node {'%s', children=[%s]}" % \
               (self.name, pp_nodes(list(self.children)))

    def __cmp__(self, other):
        return cmp(self.name, other.name)

    def __eq__(self, other):
        return self.name == other.name


def resolv_deps(root, rreqs, acc=[]):
    pass  # for r in rreqs.get(root)


def make_depgraph(root, reversed=False):
    """
    Make a dependency graph of installed RPMs.

    :param root: RPM DB top dir
    :return: List of root nodes.
    """
    pass


def make_depgraph_2(root, reversed=False):
    """
    Make a dependency graph of installed RPMs.

    :param root: RPM DB top dir
    :param reversed: Try to make reversed dependency graph (very experimental).
    :return: List of root nodes.
    """
    f = make_reversed_requires_dict if reversed else make_requires_dict
    reqs_map = f(root)  # {reqs: [reqd]} or {reqd: [reqs]} (reversed)

    nodes = dict()  # {name: Node n}

    for x, ys in reqs_map.iteritems():
        node = nodes.get(x, None)

        if node:
            logging.debug("Already created as child node: " + x)

            cs_ref = node.get_child_names()
            cs = set(ys)

            if cs.issubset(cs_ref):
                continue

            for c in cs:
                if c not in cs_ref:
                    logging.debug("Create child node not seen yet: " + c)
                    cnode = nodes[c] = Node(c, [], False)
                    node.add_child(cnode)
        else:
            logging.debug("Create root node: name=" + x)
            node = nodes[x] = Node(x, [], True)

            for y in ys:
                cnode = nodes.get(y, None)

                if cnode is None:
                    logging.debug("Create child node: " + y)
                    cnode = nodes[y] = Node(y, [], False)
                else:
                    cnode.make_not_root()

                node.add_child(cnode)

    return sorted(nodes.values(), key=attrgetter("name"))


def find_all_paths(graph, start, end, path=[]):
    path = path + [start]
    if start == end:
        return [path]
    if not graph.has_key(start):
        return []
    paths = []
    for node in graph[start]:
        if node not in path:
            newpaths = find_all_paths(graph, node, end, path)
            for newpath in newpaths:
                paths.append(newpath)
    return paths


def traverse_node_g(node, rank=0):
    """
    Yields list of nodes traversing children of given node.

    :param node: Node object
    """
    to_traverse = deque()
    nodes_list = []
    last_rank = cur_rank = rank

    to_traverse.append((cur_rank, node))

    while to_traverse:
        logging.debug("to_traverse=" + str(to_traverse))
        (cur_rank, cur_node) = to_traverse.popleft()

        while last_rank and last_rank >= cur_rank:
            nodes_list.pop()
            logging.debug("nodes_list=" + str(nodes_list) +
                          ", ranks: last=%d, cur=%d" % (last_rank, cur_rank))
            last_rank -= 1

        nodes_list.append(cur_node.name)
        logging.debug("(nodes_list to yield: " + str(nodes_list))
        yield nodes_list

        to_traverse.extendleft(((cur_rank + 1, c) for c in
                               cur_node.get_children()))
        last_rank = cur_rank


# vim:sw=4:ts=4:et:
