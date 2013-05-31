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


def walk(visited, list_children, is_leaf=None, leaves=[], seens=[],
         topdown=True):
    """
    Like os.walk, walk tree from given ``visited`` and yields 3-tuple
    (visited_nodes, next_nodes_to_visit, leaf_nodes).

    :param visited: Path from root to the current node :: [node]
    :param list_children: Function to list next children nodes
    :param is_leaf: Function to check if the node is leaf
    :param leaves: List of known leaf nodes
    :param seens: List of seen nodes
    :param topdown: Yields result tuples before these children.
    """
    if is_leaf is None:
        is_leaf = lambda node: node in leaves or node in seens

    children = list_children(visited)
    immediate_leaves = [c for c in children if is_leaf(c)]
    next_nodes = [c for c in children if c not in immediate_leaves]

    if topdown:
        yield (visited, next_nodes, immediate_leaves)

    for node in next_nodes:
        visited.append(node)

        if node in seens:
            logging.info("Detect circular walking at " + node)
            continue

        seens = list(set(seens + visited + children))
        for x in walk(visited, list_children, is_leaf, leaves, seens, topdown):
            yield x

    if not topdown:
        yield (visited, next_nodes, immediate_leaves)


# vim:sw=4:ts=4:et:
