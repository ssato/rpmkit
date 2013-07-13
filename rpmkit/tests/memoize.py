#
# Copyright (C) 2011 - 2013 Satoru SATOH <ssato at redhat.com>
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
from inspect import getdoc

import rpmkit.memoize as TT
import unittest


class Test_00_Memoize(unittest.TestCase):

    def test_00_simple_case(self):
        x = 0
        f = lambda _x: x

        f = TT.memoize(f)
        x = 1

        self.assertEquals(f(0), f(1))

    def test_10_doc_string_is_kept(self):
        def t():
            """Always returns True."""
            return True

        t2 = TT.memoize(t)
        self.assertEquals(getdoc(t), getdoc(t2))

    def test_20_not_callable_object_is_passed(self):
        self.assertRaises(AssertionError, TT.memoize, None)

# vim:sw=4:ts=4:et:
