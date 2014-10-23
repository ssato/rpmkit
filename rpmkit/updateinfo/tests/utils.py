#
# Copyright (C) 2013 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato at redhat.com>
#
# This software is licensed to you under the GNU General Public License,
# version 3 (GPLv3). There is NO WARRANTY for this software, express or
# implied, including the implied warranties of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. You should have received a copy of GPLv3 along with this
# software; if not, see http://www.gnu.org/licenses/gpl.html
#
import rpmkit.updateinfo.utils as TT
import rpmkit.tests.common as C

import os
import os.path
import shutil
import unittest


class Test_00(unittest.TestCase):

    def test_10_local_timestamp(self):
        """TODO: How to test rpmkit.updateinfo.utils.local_timestamp ?
        """
        TT.local_timestamp()


class Test_20_check_rpmdb_root(unittest.TestCase):

    def setUp(self):
        self.workdir = C.setup_workdir()

        if TT.is_rhel_or_fedora():
            rpmdbdir = os.path.join(self.workdir, TT.RPMDB_SUBDIR)
            os.makedirs(rpmdbdir)

            for dbn in TT._RPM_DB_FILENAMES:
                shutil.copy(os.path.join('/', TT.RPMDB_SUBDIR, dbn), rpmdbdir)

    def tearDown(self):
        C.cleanup_workdir(self.workdir)

    def test_10_mkdtemp(self):
        self.assertTrue(os.path.exists(TT.mkdtemp(dir=self.workdir)))

    def test_20_check_rpmdb_root(self):
        self.assertTrue(TT.check_rpmdb_root(self.workdir))

# vim:sw=4:ts=4:et:
