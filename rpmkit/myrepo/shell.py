#
# Copyright (C) 2011, 2012 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato@redhat.com>
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
import rpmkit.myrepo.environ as E
import rpmkit.myrepo.utils as U

import logging
import os
import os.path
import subprocess
import sys
import threading
import time


MIN_TIMEOUT = 5  # [sec]


def is_valid_timeout(timeout):
    """
    >>> is_valid_timeout(None)
    True
    >>> is_valid_timeout(0)
    True
    >>> is_valid_timeout(10)
    True
    >>> is_valid_timeout(-1)
    False
    >>> is_valid_timeout("10")
    False
    """
    if timeout is None:
        return True
    else:
        return isinstance(timeout, int) and timeout >= 0


class ThreadedCommand(object):
    """
    Based on the idea found at
    http://stackoverflow.com/questions/1191374/subprocess-with-timeout
    """

    def __init__(self, cmd, user=None, host="localhost", workdir=os.curdir,
            timeout=None):
        """
        :param cmd: Command string
        :param user: User to run command
        :param host: Host to run command
        :param workdir: Working directory in which command runs
        :param timeout: Time out in seconds
        """
        assert is_valid_timeout(timeout), "Invalid timeout: " + str(timeout)

        self.cmd = cmd
        self.user = E.get_username() if user is None else user
        self.host = host
        self.timeout = timeout

        if U.is_local(host):
            if "~" in workdir:
                workdir = os.path.expanduser(workdir)
        else:
            cmd = "ssh -o ConnectTimeout=%d %s@%s 'cd %s && %s'" % \
                (MIN_TIMEOUT, user, host, workdir, cmd)
            workdir = os.curdir

        self.workdir = workdir
        self.cmd_str = "%s [%s]" % (self.cmd, self.workdir)
        self.thread = None
        self.proc = None
        self.result = None

    def __str__(self):
        return self.cmd_str

    def run_async(self):
        def func():
            if logging.getLogger().level < logging.INFO:  # logging.DEBUG
                stdout = sys.stdout
            else:
                stdout = open(getattr(os, "devnull", "/dev/null"), "w")

            logging.info("Run: " + self.cmd_str)
            self.proc = subprocess.Popen(
                self.cmd,
                bufsize=4096,
                shell=True,
                cwd=self.workdir,
                stdin=open("/dev/null", "r"),
                stdout=stdout,
                stderr=sys.stderr,
            )
            self.result = self.proc.wait()
            logging.debug("Finished: %s" % self.cmd_str)

        self.thread = threading.Thread(target=func)
        self.thread.start()

    def terminate(self):
        if self.proc and self.result is None:
            logging.warn("Terminating: " + self.cmd_str)
            self.proc.terminate()

            rc = self.proc.poll()
            if rc is None:
                self.proc.kill()

            # avoid creating zonbie.
            try:
                (_pid, _rc) = os.waitpid(self.proc.pid, os.WNOHANG)
            except OSError:
                pass

            self.result = -1

    def get_result(self):
        if self.thread is None:
            logging.warn(
                "Thread does not exist. Did you call %s.run_async() ?" % \
                    self.__class__.__name__
            )
            return -1

        # it may block.
        self.thread.join(self.timeout)

        # NOTE: It seems there is a case that thread is not alive but process
        # spawned from that thread is still alive.
        self.terminate()

        if self.thread.isAlive():
            self.thread.join()

        return self.result

    def run(self):
        self.run_async()
        return self.get_result()


def run(cmd, user=None, host="localhost", workdir=os.curdir, timeout=None,
        stop_on_error=False):
    """
    :param stop_on_error: Whether to raise exception if any errors occurred.
    """
    c = ThreadedCommand(cmd, user, host, workdir, timeout)
    rc = c.run()

    if rc != 0:
        emsg = "Failed: %s, rc=%d" % (str(c), rc)

        if stop_on_error:
            raise RuntimeError(emsg)
        else:
            logging.warn(emsg)

    return rc


def prun(cs):
    """
    :param cs: A list of ThreadedCommand objects
    """
    cs_w_t = sorted(
        (c for c in cs if c.timeout is not None), key=lambda c: c.timeout
    )
    cs_wo_t = [c for c in cs if c.timeout is None]

    for c in reversed(cs_w_t):
        c.run_async()

    for c in cs_wo_t:
        c.run_async()

    # no timeouts suggests these should finish jobs immedicately.
    rcs = [c.get_result() for c in cs_wo_t]

    rcs += [c.get_result() for c in cs_w_t]

    return rcs


# vim:sw=4 ts=4 et:
