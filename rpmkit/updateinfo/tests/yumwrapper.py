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


class Test_00(unittest.TestCase):

    def test_10_logdir(self):
        self.assertEquals(TT.logdir("/a/b/c"), "/a/b/c/var/log")


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

        def test_10_run_command(self):
            opts = ["--disablerepo='*'"]
            for c in ("list-sec", "list installed"):
                (out, err, rc) = TT.run_command(self.workdir, c, opts)
                self.assertTrue(out)
                self.assertFalse(err)
                self.assertFalse(rc in (1, 2))

        def test_20_list_errata__no_errata(self):
            xs = TT.list_errata(self.workdir, [], ['*'])
            self.assertEquals(xs, [])

        def test_30_list_updates__no_updates(self):
            xs = TT.list_updates(self.workdir, [], ['*'])
            self.assertEquals(xs, [])

        def test_40_download_updates__no_updates(self):
            self.assertTrue(TT.download_updates(self.workdir, [], ['*']))

# vim:sw=4:ts=4:et:
