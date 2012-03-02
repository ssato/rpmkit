#
# Copyright (C) 2011 Satoru SATOH <satoru.satoh @ gmail.com>
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
from __future__ import print_function

import rpmkit.shell as SH
import logging
import os
import os.path
import sys
import unittest


# see: http://goo.gl/7QRBR
# monkey patch to get nose working with subprocess...
def fileno_monkeypatch(self):
    return sys.__stdout__.fileno()

import StringIO
StringIO.StringIO.fileno = fileno_monkeypatch


logging.getLogger().setLevel(logging.DEBUG)


class Test_00_ThreadedCommand(unittest.TestCase):

    def test_run__00(self):
        self.assertEquals(SH.ThreadedCommand("true").run(), 0)

    def test_run__10_workdir(self):
        self.assertEquals(SH.ThreadedCommand("true", workdir="/tmp").run(), 0)

    def test_run__11_workdir__exceptions(self):
        if os.getuid() == 0:
            print("Skip this test because you're root.")
            return

        with self.assertRaises(OSError) as cm:
            SH.ThreadedCommand("true", workdir="/root").run(), 0

    def test_run__12_workdir__no_exceptions(self):
        if os.getuid() == 0:
            print("Skip this test because you're root.")
            return

        rc = SH.ThreadedCommand("true", workdir="/root", nofail=True).run()
        self.assertNotEquals(rc, 0, "rc=" + str(rc))

    def test_run__30_timeout(self):
        rc = SH.ThreadedCommand("sleep 10", timeout=1).run()
        self.assertNotEquals(rc, 0, "rc=" + str(rc))


class Test_10_run(unittest.TestCase):

    def test_run__00(self):
        self.assertEquals(SH.run("true"), 0)

    def test_run__10_stop_on_error(self):
        with self.assertRaises(RuntimeError) as cm:
            SH.run("false", stop_on_error=True)

    def test_run__11_stop_on_error_false(self):
        self.assertNotEquals(SH.run("false", stop_on_error=False), 0)


PRUN_JOBS = 5


class Test_20_prun(unittest.TestCase):

    def test_prun__00(self):
        n = PRUN_JOBS
        cs = [SH.ThreadedCommand("true") for _ in range(n)]
        self.assertEquals(SH.prun(cs), [0 for _ in range(n)])

    def test_prun__10_timeout(self):
        n = PRUN_JOBS
        cs = [SH.ThreadedCommand("sleep 10", timeout=1) for _ in range(n)]
        rcs = SH.prun(cs)
        self.assertNotEquals(rcs, [0 for _ in range(n)], "rcs=" + str(rcs))


# vim:sw=4 ts=4 et:
