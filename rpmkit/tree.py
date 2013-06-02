#
# Copyright (C) 2013 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato@redhat.com>
#
# License: MIT
#
from itertools import izip

import logging
import os
import sys


## The followings are very experimental...
sys.setrecursionlimit(1000)


class Node(object):

    def __init__(self, name, children=[]):
        self._name = name
        self._children = children

    def name(self):
        return self._name

    def list_children(self):
        return self._children

    def add_child(self, cnode):
        if cnode not in self.list_children():
            self._children.append(cnode)

    def __eq__(self, other):
        return self._name == other.name()

    def __repr__(self):
        return "Node(%s)" % self.name()


def walk(visited, list_children, is_leaf=None, leaves=[], seens=[],
         topdown=True, aggressive=False):
    """
    Like os.walk, walk tree from given ``visited`` and yields list of visited
    nodes list from root to leaves.

    :param visited: Path from root to the current node :: [node]
    :param list_children: Function to list next children nodes
    :param is_leaf: Function to check if the node is leaf :: node -> bool
    :param leaves: List of known leaf nodes
    :param seens: List of seen nodes
    :param topdown: Yields result tuples before walking children.
    :param aggressive: Cut branches aggressively, that is, seen nodes in
        siblings and these children are also considered as virtual leaves.
    """
    if is_leaf is None:
        is_leaf = lambda node: not list_children(node)

    children = list_children(visited[-1])

    immediate_leaves = [c for c in children if is_leaf(c)]
    next_nodes = [c for c in children if c not in immediate_leaves]

    if topdown:
        for leaf in immediate_leaves:
            yield visited + [leaf]

    for node in next_nodes:
        if node in seens or node in visited:
            logging.debug("Detect circular walking: " + node)
            continue

        visited.append(node)

        if aggressive:
            seens = list(set(seens + visited + children))
        else:
            seens = list(set(seens + visited))

        for x in walk(visited, list_children, is_leaf, leaves, seens,
                      topdown):
            yield x

    if not topdown:
        for leaf in immediate_leaves:
            yield visited + [leaf]


def make_tree_from_path(paths, leaves=[], acyclic=True):
    """
    Make hierarchical tree of dicts from path in the paths list made
    by the above 'walk' function.

    :param paths: List of paths of which root (path[0]) is same
    :return: dict(name: [, children: <node>])
    """
    nodes = dict()

    if leaves:
        for leaf in leaves:
            if leaf not in nodes:
                nodes[leaf] = dict(name=leaf)

    assert paths != [[]], "Empty list of list was given!"

    # sort paths by its legth
    paths = sorted(paths, key=len, reverse=True)

    for path in paths:
        rpath = list(reversed(path))
        assert rpath

        # This node is a leaf:
        head = rpath[0]
        if nodes.get(head, None) is None:
            nodes[head] = dict(name=head)

        for node, child in izip(rpath[1:], rpath):
            x = nodes.get(node, None)
            c = nodes[child]  # This node should be created before.

            if x is None:
                nodes[node] = dict(name=node, children=[c])
                continue

            logging.debug("The node was created in another path: " + node)
            cs = x.get("children", [])
            if cs:
                logging.debug("The node has another children: " + node)
                if c not in cs:
                    nodes[node]["children"].append(c)
            else:
                logging.debug("The node was a leaf: " + node)
                nodes[node]["children"] = [c]

    return nodes[paths[0][0]]


# vim:sw=4:ts=4:et:
