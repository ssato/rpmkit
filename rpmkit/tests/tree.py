#
# Copyright (C) 2013 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato at redhat.com>
#
# License: MIT
#
import rpmkit.tree as TT
import unittest

list_children = lambda node: node.list_children()


class Test_00_pure_functions(unittest.TestCase):

    def test_00_walk__a_node(self):
        tree = TT.Node("foo")

        ret = [t for t in TT.walk([tree], list_children)]
        self.assertEquals(ret, [])

    def test_01_walk__nodes(self):
        tree = TT.Node("foo", [TT.Node("bar"),
                               TT.Node("baz", [TT.Node("aaa")])])

        ret = [t for t in TT.walk([tree], list_children)]

        self.assertEquals([n.name() for n in ret[0]], ["foo", "bar"])
        self.assertEquals([n.name() for n in ret[1]], ["foo", "baz", "aaa"])

    def test_10_make_hierarchical_nested_dicts_from_paths(self):
        paths = [['kbd-misc', 'kbd', 'dracut', 'dracut-kernel'],
                 ['kbd-misc', 'kbd', 'dracut', 'kexec-tools']]
        ref = dict(name="kbd-misc",
                   children=[
                       dict(name="kbd",
                            children=[
                                dict(name="dracut",
                                     children=[
                                         dict(name="dracut-kernel"),
                                         dict(name="kexec-tools")])])])

        result = TT.make_hierarchical_nested_dicts_from_paths(paths)

        self.assertEquals(result, ref)


# vim:sw=4 ts=4 et:
