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
    class Test_10_Base(unittest.TestCase):

        def setUp(self):
            self.workdir = C.setup_workdir()

            rpmdbdir = os.path.join(self.workdir, RUU.RPMDB_SUBDIR)
            os.makedirs(rpmdbdir)

            for dbn in RUU._RPM_DB_FILENAMES:
                shutil.copy(os.path.join('/', RUU.RPMDB_SUBDIR, dbn), rpmdbdir)

            self.base = TT.Base(self.workdir)

        def tearDown(self):
            C.cleanup_workdir(self.workdir)

        def test_10_create(self):
            self.assertTrue(isinstance(self.base.base, TT.yum.YumBase))
            self.assertEquals(self.base.base.repos.listEnabled(), [])

        def test_20_list_packages(self):
            pkgs = self.base.list_packages()

            for narrow in TT._PKG_NARROWS:
                self.assertTrue(isinstance(pkgs[narrow], list))

            self.assertNotEquals(pkgs["installed"], [])

        def test_40_list_errata(self):
            es = self.base.list_errata()
            self.assertTrue(isinstance(es, list))

        def test_50_list_updates(self):
            pkgs = self.base.list_updates()
            self.assertTrue(isinstance(pkgs, list))

# vim:sw=4:ts=4:et:
