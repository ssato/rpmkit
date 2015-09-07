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
import rpmkit.yum_surrogate as TT
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

        def test_10_run_yum_cmd(self):
            for c in ("updateinfo list", "list installed"):
                TT.run_yum_cmd(self.workdir, c)

# vim:sw=4:ts=4:et:
