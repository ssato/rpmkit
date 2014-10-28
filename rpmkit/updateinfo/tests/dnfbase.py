#
# Copyright (C) 2014 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato at redhat.com>
# License: GPLv3+
#
import rpmkit.updateinfo.dnfbase as TT
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

        def test_20_list_installed(self):
            pkgs = self.base.list_installed()
            self.assertTrue(isinstance(pkgs, list))
            self.assertTrue(bool(pkgs))

        def test_30_list_updates(self):
            pkgs = self.base.list_updates()
            self.assertTrue(isinstance(pkgs, list))

        def test_40_list_errata(self):
            pass

# vim:sw=4:ts=4:et:
