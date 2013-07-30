#
# Copyright (C) 2012, 2013 Satoru SATOH <satoru.satoh @ gmail.com>
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
import rpmkit.shell2 as TT

import logging
import os
import os.path
import subprocess
import sys
import unittest


# see: http://goo.gl/7QRBR
# monkey patch to get nose working with subprocess...
def fileno_monkeypatch(self):
    return sys.__stdout__.fileno()

import StringIO
StringIO.StringIO.fileno = fileno_monkeypatch


class Test_10_run(unittest.TestCase):

    def test_00_run_async__simplest_case(self):
        job = TT.run_async("true")

        self.assertTrue(isinstance(job, TT.gevent.greenlet.Greenlet))

        job.join()
        self.assertTrue(job.successful())

    def test_01_run_async__simplest_case(self):
        job = TT.run_async("false")

        self.assertTrue(isinstance(job, TT.gevent.greenlet.Greenlet))

        job.join()
        self.assertTrue(job.successful())

    def test_10_run__simplest_case(self):
        self.assertTrue(TT.run("true"))
        self.assertTrue(TT.run("false"))

    def test_20_run__if_timeout(self):
        """FIXME: Timeout function for gevent.Greenlet/subprocess combination
        must be implemented.
        """
        return

        self.assertFalse(TT.run("sleep 10", timeout=1))

    def test_30_run__if_interrupted(self):
        """TODO: Implement test cases of keyboard interruption."""

        def emit_KeybordInterrupt():
            raise KeyboardInterrupt("Fake Ctrl-C !")

        job = TT.run_async("sleep 5")
        TT.gevent.spawn(emit_KeybordInterrupt).join()

        self.assertFalse(job.join())


class Test_20_prun(unittest.TestCase):

    def test_00_prun_async__simplest_case(self):
        pass

    def test_01_run_async__simplest_case(self):
        pass

    def test_10_run__simplest_case(self):
        rcs = TT.prun([(("true", ), dict(shell=True, cwd=os.curdir))])
        for rc in rcs:
            self.assertTrue(rc)

# vim:sw=4 ts=4 et:
