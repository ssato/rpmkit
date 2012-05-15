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


def _id():
    return random.randint(0, 100000)


class Test_10_Packages(unittest.TestCase):

    def test__init__(self):
        x = P.Package(_id(), "foo", "0.0.1", "1", "0", "x86_64")
        self.assertTrue(bool(x))


class Test_20_Errata(unittest.TestCase):

    def test__init__(self):
        x = P.Errata(_id(), "RHSA-2012:0546", "RHSA-2012:0546-1",
            "Critical: php security update", "2012-05-07")
        self.assertTrue(bool(x))


class Test_30_CVE(unittest.TestCase):

    def test__init__(self):
        x = P.CVE(_id(), "CVE-2012-1823")
        self.assertTrue(bool(x))


class Test_10_PackageDetails(unittest.TestCase):

    def test__init__(self):
        #x = P.PackageDetails(_id(), ...)
        #self.assertTrue(bool(x))
        pass


class Test_10_PackageFile(unittest.TestCase):

    def test__init__(self):
        x = P.PackageFile(_id(), "/bin/bash")
        self.assertTrue(bool(x))


class Test_40_PackageRequires(unittest.TestCase):

    def test__init__(self):
        #x = P.PackageRequires(_id(), ...)
        #self.assertTrue(bool(x))
        pass


class Test_40_PackageProvides(unittest.TestCase):

    def test__init__(self):
        x = P.PackageProvides(_id(), "webserver") 
        self.assertTrue(bool(x))


class Test_40_PackageErrata(unittest.TestCase):

    def test__init__(self):
        x = P.PackageErrata(_id(), _id()) 
        self.assertTrue(bool(x))


# vim:sw=4:ts=4:et:
