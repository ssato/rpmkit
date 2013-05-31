#
# Copyright (C) 2013 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato@redhat.com>
#
# License: MIT
#
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
         topdown=True):
    """
    Like os.walk, walk tree from given ``visited`` and yields list of visited
    nodes list from root to leaves.

    :param visited: Path from root to the current node :: [node]
    :param list_children: Function to list next children nodes
    :param is_leaf: Function to check if the node is leaf :: node -> bool
    :param leaves: List of known leaf nodes
    :param seens: List of seen nodes
    :param topdown: Yields result tuples before walking children.
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
        visited.append(node)

        if node in seens:
            logging.info("Detect circular walking")
            continue

        seens = list(set(seens + visited + children))
        for x in walk(visited, list_children, is_leaf, leaves, seens,
                      topdown):
            yield x

    if not topdown:
        for leaf in immediate_leaves:
            yield visited + [leaf]


# vim:sw=4:ts=4:et:
