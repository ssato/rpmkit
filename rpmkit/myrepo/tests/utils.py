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
import rpmkit.myrepo.utils as U

import unittest


class Test_00(unittest.TestCase):

    def test_00_typecheck(self):
        U.typecheck("aaa", str)
        U.typecheck(1, int)
        U.typecheck({}, dict)

        class A(object):
            pass

        U.typecheck(A(), A)

        with self.assertRaises(TypeError) as cm:
            U.typecheck(A(), str)

    def test_10_compile_template(self):
        pass

    def test_20_is_local(self):
        self.assertTrue(U.is_local("localhost"))
        self.assertTrue(U.is_local("localhost.localdomain"))

        self.assertFalse(U.is_local("repo-server.example.com"))
        self.assertFalse(U.is_local("127.0.0.1"))  # special case


# vim:sw=4 ts=4 et:
