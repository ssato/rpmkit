#
# Copyright (C) 2014 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato at redhat.com>
#
# This software is licensed to you under the GNU General Public License,
# version 3 (GPLv3). There is NO WARRANTY for this software, express or
# implied, including the implied warranties of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. You should have received a copy of GPLv3 along with this
# software; if not, see http://www.gnu.org/licenses/gpl.html
#
import rpmkit.updateinfo.yumbase as TT
import rpmkit.updateinfo.utils as RUU
import rpmkit.tests.common as C

import os.path
import os
import shutil
import unittest


if RUU.is_rhel_or_fedora():
    class Test_10_effectful_functions(unittest.TestCase):

        def setUp(self):
            self.workdir = C.setup_workdir()

            rpmdbdir = os.path.join(self.workdir, RUU.RPMDB_SUBDIR)
            os.makedirs(rpmdbdir)

            for dbn in RUU._RPM_DB_FILENAMES:
                shutil.copy(os.path.join('/', RUU.RPMDB_SUBDIR, dbn), rpmdbdir)

        def tearDown(self):
            C.cleanup_workdir(self.workdir)

        def test_10_create(self):
            base = TT.create(self.workdir)
            self.assertTrue(isinstance(base, TT.yum.YumBase))
            self.assertEquals(base.repos.listEnabled(), [])

        def test_20_list_packages(self):
            pkgs = TT.list_packages('/')

            for narrow in TT._PKG_NARROWS:
                self.assertTrue(isinstance(pkgs[narrow], list))

            self.assertNotEquals(pkgs["installed"], [])

        def test_40_list_errata(self):
            es = TT.list_errata(self.workdir)
            self.assertTrue(isinstance(es, list))

        def test_50_list_updates(self):
            pkgs = TT.list_updates('/')
            self.assertTrue(isinstance(pkgs, list))

# vim:sw=4:ts=4:et:
