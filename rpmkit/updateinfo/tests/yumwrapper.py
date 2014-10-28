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
import rpmkit.updateinfo.yumwrapper as TT
import rpmkit.updateinfo.utils as RUU
import rpmkit.tests.common as C

import os.path
import os
import shutil
import unittest


if RUU.is_rhel_or_fedora():
    class Test_10_Base__no_enabled_repos(unittest.TestCase):

        def setUp(self):
            self.workdir = C.setup_workdir()

            rpmdbdir = os.path.join(self.workdir, RUU.RPMDB_SUBDIR)
            os.makedirs(rpmdbdir)

            for dbn in RUU._RPM_DB_FILENAMES:
                shutil.copy(os.path.join('/', RUU.RPMDB_SUBDIR, dbn), rpmdbdir)

            self.base = TT.Base(self.workdir)

        def tearDown(self):
            C.cleanup_workdir(self.workdir)

        def test_10_run(self):
            for c in ("list-sec", "list installed"):
                (out, err, rc) = self.base.run(c)
                self.assertTrue(out)
                self.assertFalse(err)
                self.assertFalse(rc in (1, 2))

        def test_20_list_errata__no_errata(self):
            xs = self.base.list_errata()
            self.assertEquals(xs, [])

        def test_30_list_updates__no_updates(self):
            xs = self.base.list_updates()
            self.assertEquals(xs, [])

        def test_40_download_updates__no_updates(self):
            self.assertTrue(self.base.download_updates())

# vim:sw=4:ts=4:et:
