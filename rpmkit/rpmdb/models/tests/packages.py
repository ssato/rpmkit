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
import rpmkit.rpmdb.models.packages as P
import random
import unittest


class Test_10_Packages(unittest.TestCase):

    def test__init__(self):
        _id = random.randint(0, 100000)
        p = P.Package(_id, "foo", "0.0.1", "1", "0", "x86_64")
        self.assertTrue(bool(p))


# vim:sw=4:ts=4:et:
