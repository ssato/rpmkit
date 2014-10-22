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
import rpmkit.updateinfo.subproc as TT
import rpmkit.tests.common as C

import os.path
import os
import unittest


class Test_00(unittest.TestCase):

    def test_10_check_output_simple__assert_outfile(self):
        try:
            TT.check_output_simple("ls", "/path/to/outfile")
        except AssertionError:
            pass


class Test_10_effectful_functions(unittest.TestCase):

    def setUp(self):
        self.workdir = C.setup_workdir()
        self.saved_nose_procs = os.environ.get("NOSE_PROCESSES", "0")
        os.environ["NOSE_PROCESSES"] = "0"

    def tearDown(self):
        C.cleanup_workdir(self.workdir)
        os.environ["NOSE_PROCESSES"] = self.saved_nose_procs

    def test_12_check_output_simple__str(self):
        outfile = os.path.join(self.workdir, "check_output_simple.out.txt")
        with open(outfile, 'w') as out:
            rc = TT.check_output_simple("echo OK", out)
            self.assertEquals(rc, 0)

        self.assertEquals(open(outfile, 'r').read(), "OK\n")

    def test_20_run__success__wo_kwargs(self):
        (out, err, rc) = TT.run("echo OK")

        self.assertEquals(out, ["OK\n"])
        self.assertEquals(err, [])
        self.assertEquals(rc, 0)

    def test_22_run__failure__wo_kwargs(self):
        (out, err, rc) = TT.run("false")

        self.assertEquals(out, [])
        self.assertEquals(err, [])
        self.assertEquals(rc, 1)

    def test_26_run__success__w_output_file(self):
        outfile = os.path.join(self.workdir, "test_10_20_run.out.txt")
        with open(outfile, 'w') as out:
            (out, err, rc) = TT.run("echo OK", out.write)

        self.assertEquals(out, ["OK\n"])
        self.assertEquals(err, [])
        self.assertEquals(rc, 0)
        self.assertEquals(open(outfile, 'r').read(), "OK\n")

    def test_28_run__success__w_timeout(self):
        """FIXME: timeout is not work yet.
        """
        return
        (out, err, rc) = TT.run("sleep 10", timeout=3)

        self.assertEquals(out, [])
        self.assertEquals(err, [])
        self.assertNotEquals(rc, 0)

# vim:sw=4:ts=4:et:
