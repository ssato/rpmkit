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
import rpmkit.environ as E

import os
import os.path
import sys
import unittest


# FIXME: Most of current tests just checks type-safety.
class Test_00(unittest.TestCase):

    def __result_is_str_and_not_empty(self, f):
        x = f()
        self.assertTrue(isinstance(x, str))
        self.assertNotEquals(x, "")

    def test_00_list_archs(self):
        self.assertTrue(isinstance(E.list_archs(), list))
        self.assertEquals(E.list_archs("i386"), ["i386"])
        self.assertEquals(E.list_archs("i686"), ["i386"])
        self.assertEquals(E.list_archs("x86_64"), ["x86_64", "i386"])

    def test_10_list_dists(self):
        self.assertTrue(isinstance(E.list_dists(), list))

    def test_20_is_git_available(self):
        self.assertTrue(isinstance(E.is_git_available(), bool))

    def test_30_hostname(self):
        self.__result_is_str_and_not_empty(E.hostname)

    def test_40_get_username(self):
        self.__result_is_str_and_not_empty(E.get_username)

    def test_50_get_email(self):
        self.__result_is_str_and_not_empty(E.get_email)

    def test_60_get_fullname(self):
        self.__result_is_str_and_not_empty(E.get_fullname)

    def test_70_get_distribution(self):
        x = E.get_distribution()
        self.assertTrue(isinstance(x, tuple))
        self.assertEquals(len(x), 2)


# vim:sw=4 ts=4 et:
