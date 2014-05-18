#
# Copyright (C) 2012 Satoru SATOH <satoru.satoh @ gmail.com>
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

import rpmkit.environ as E
import rpmkit.shell as SH
import rpmkit.utils as U
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


class Test_00_functions(unittest.TestCase):

    def test_00__debug_mode(self):
        logging.getLogger().setLevel(logging.DEBUG)
        self.assertTrue(SH._debug_mode())

        logging.getLogger().setLevel(logging.INFO)
        self.assertFalse(SH._debug_mode())

    def test_10__terminate__not_terminated(self):
        p = subprocess.Popen("true", shell=True)
        p.wait()
        self.assertEquals(SH._terminate(p), 0)

    def test_11__terminate__terminated(self):
        p = subprocess.Popen("sleep 10", shell=True)
        p.poll()
        self.assertNotEquals(SH._terminate(p), 0)


class Test_10_Task(unittest.TestCase):

    def test_00___init__(self):
        (cmd, user, host, workdir, timeout) = \
            ("true", "foo", "localhost", "/tmp", 1)
        task = SH.Task(cmd, user, host, workdir, timeout)

        U.typecheck(task, SH.Task)

        self.assertEquals(task.cmd, cmd)
        self.assertEquals(task.user, user)
        self.assertEquals(task.host, host)
        self.assertEquals(task.workdir, workdir)
        self.assertEquals(task.timeout, timeout)

    def test_01___init__remote_host(self):
        (cmd, user, host, workdir, timeout) = \
            ("true", "foo", "www.example.com", "/tmp", 1)
        task = SH.Task(cmd, user, host, workdir, timeout)

        U.typecheck(task, SH.Task)

        self.assertNotEquals(task.cmd, cmd)
        self.assertEquals(task.user, user)
        self.assertEquals(task.host, host)
        self.assertNotEquals(task.workdir, workdir)
        self.assertEquals(task.timeout, timeout)

    def test_02___init__homedir(self):
        (cmd, user, host, workdir, timeout) = \
            ("true", E.get_username(), "localhost", "~/", 1)
        task = SH.Task(cmd, user, host, workdir, timeout)

        U.typecheck(task, SH.Task)

        self.assertEquals(task.cmd, cmd)
        self.assertEquals(task.user, user)
        self.assertEquals(task.host, host)
        self.assertNotEquals(task.workdir, workdir)
        self.assertEquals(task.workdir, os.path.expanduser(workdir))
        self.assertEquals(task.timeout, timeout)


class Test_20_do_task(unittest.TestCase):

    def test_00_do_task__no_errors(self):
        task = SH.Task("true", timeout=10)
        self.assertEquals(SH.do_task(task), 0)

    def test_01_do_task__no_errors_but_not_return_0_and_exception_raised(self):
        task = SH.Task("false", timeout=10)

        with self.assertRaises(SH.TaskError):
            SH.do_task(task)

    def test_02_do_task__no_errors_but_not_return_0(self):
        task = SH.Task("false", timeout=10)
        self.assertNotEquals(SH.do_task(task, stop_on_error=False), 0)

    def test_10_do_task__w_permission_denied_error(self):
        if os.getuid() == 0:
            print("Skip this test because you're root.")
            return

        # It seems that neighther 'subprocess.Popen("true",
        # cwd="/root").wait()' nor 'subprocess.Popen("cd /root && true",
        # shell=True).wait()' does not raise any exceptions these days:
        # task = SH.Task("true", workdir="/root", timeout=10)
        # task = SH.Task("cd /root && true", workdir="/root", timeout=10)

        task = SH.Task("touch /root/.bashrc", timeout=10)

        with self.assertRaises(SH.TaskError):
            SH.do_task(task, stop_on_error=True)

    def test_20_do_task__ignore_permission_denied_error(self):
        if os.getuid() == 0:
            print("Skip this test because you're root.")
            return

        task = SH.Task("touch /root/.bashrc", workdir="/root", timeout=10)
        self.assertNotEquals(SH.do_task(task, stop_on_error=False), 0)

    def test_30_do_task__timeout(self):
        task = SH.Task("sleep 10", timeout=1)

        with self.assertRaises(SH.TaskError):
            SH.do_task(task)

    def test_31_do_task__timeout__w_rc(self):
        task = SH.Task("sleep 10", timeout=1)

        self.assertNotEquals(SH.do_task(task, stop_on_error=False), 0)


class Test_30_run(unittest.TestCase):

    def test_00_run(self):
        self.assertEquals(SH.run("true", timeout=10), 0)

    def test_10_run__timeout(self):
        self.assertNotEquals(SH.run("sleep 10", timeout=2), 0)

    def test_20_run__w_permission_denied_error(self):
        if os.getuid() == 0:
            print("Skip this test because you're root.")
            return

        with self.assertRaises(SH.TaskError):
            SH.run("ls /root", stop_on_error=True)

    def test_30_run__ignore_permission_denied_error(self):
        if os.getuid() == 0:
            print("Skip this test because you're root.")
            return

        self.assertNotEquals(SH.run("ls /root", stop_on_error=False), 0)


PRUN_JOBS = 10


class Test_40_prun(unittest.TestCase):

    def test_00_prun(self):
        tasks = [SH.Task("true", timeout=10) for _ in range(PRUN_JOBS)]
        self.assertTrue(all(rc == 0 for rc in SH.prun(tasks)))


# vim:sw=4 ts=4 et:
