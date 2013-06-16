#
# Copyright (C) 2013 Red Hat, Inc.
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
import rpmkit.yum_surrogate as TT
import rpmkit.tests.common as C

import bsddb
import os
import os.path
import unittest


class Test_04_is_bsd_hashdb(unittest.TestCase):

    def setUp(self):
        self.workdir = C.setup_workdir()

    def tearDown(self):
        C.cleanup_workdir(self.workdir)

    def test_00_is_bsd_hashdb__True(self):
        path = os.path.join(self.workdir, "bsdhashdb")
        bsddb.hashopen(path)

        self.assertTrue(TT.is_bsd_hashdb(path))

    def test_10_is_bsd_hashdb__False(self):
        path = os.path.join(self.workdir, "bsdhashdb")
        open(path, 'w').write('\n')

        self.assertFalse(TT.is_bsd_hashdb(path))


class Test_05_find_Packages_rpmdb(unittest.TestCase):

    def setUp(self):
        self.workdir = C.setup_workdir()

    def tearDown(self):
        C.cleanup_workdir(self.workdir)

    def test_00_find_Packages_rpmdb__found(self):
        path = os.path.join(self.workdir, "var", "lib", "rpm", "Packages")
        os.makedirs(os.path.dirname(path))

        bsddb.hashopen(path)

        self.assertEquals(TT.find_Packages_rpmdb(self.workdir), path)


def setup_Packages(topdir):
    path = os.path.join(topdir, "var", "lib", "rpm", "Packages")
    os.makedirs(os.path.dirname(path))

    bsddb.hashopen(path)

    return path


class Test_06_setup_root(unittest.TestCase):

    def setUp(self):
        self.workdir = C.setup_workdir()

    def tearDown(self):
        #C.cleanup_workdir(self.workdir)
        pass

    def test_00_setup_root__exact_path(self):
        ppath = setup_Packages(self.workdir)
        self.assertEquals(TT.setup_root(ppath, refer_other_rpmdb=False),
                          os.path.abspath(self.workdir))

    def test_10_setup_root__find(self):
        ppath = setup_Packages(self.workdir)
        self.assertEquals(TT.setup_root(os.path.dirname(ppath),
                                        refer_other_rpmdb=False),
                          os.path.abspath(self.workdir))

        self.assertEquals(TT.setup_root(self.workdir, refer_other_rpmdb=False),
                          os.path.abspath(self.workdir))

    def test_20_setup_root__w_root(self):
        ppath = setup_Packages(self.workdir)
        root = os.path.join(self.workdir, "pivot_root")

        self.assertEquals(TT.setup_root(ppath, root, refer_other_rpmdb=False),
                          root)


# vim:sw=4:ts=4:et:
