#
# Copyright (C) 2012 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato at redhat.com>
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
import rpmkit.utils as TT
import functools
import operator
import unittest


def plus(xs):
    for x in xs:
        assert isinstance(x, (int, float)), "not add-able object: " + str(x)

    return functools.reduce(operator.add, xs)


class Test_00(unittest.TestCase):

    def test_00_typecheck(self):
        TT.typecheck("aaa", str)
        TT.typecheck(1, int)
        TT.typecheck({}, dict)

        class A(object):
            pass

        TT.typecheck(A(), A)

        with self.assertRaises(TypeError) as cm:
            TT.typecheck(A(), str)

    def test_20_is_local(self):
        self.assertTrue(TT.is_local("localhost"))
        self.assertTrue(TT.is_local("localhost.localdomain"))

        self.assertFalse(TT.is_local("repo-server.example.com"))
        self.assertFalse(TT.is_local("127.0.0.1"))  # special case

    def test_90_pcall(self):
        res = TT.pcall(plus, [(1, 2), (2, 3, 4)], 2)
        self.assertEquals(res, [3, 9])

# vim:sw=4 ts=4 et:
