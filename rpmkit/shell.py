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
import rpmkit.Bunch as B
import rpmkit.environ as E
import rpmkit.utils as U

import logging
import multiprocessing
import os
import os.path
import subprocess
import sys
import tempfile
import threading
import time


MIN_TIMEOUT = 5  # [sec]
MAX_TIMEOUT = 60 * 5  # 300 [sec] = 5 [min]


def _debug_mode():
    return logging.getLogger().level < logging.INFO  # logging.DEBUG


def _is_valid_timeout(timeout):
    """
    >>> _is_valid_timeout(None)
    True
    >>> _is_valid_timeout(0)
    True
    >>> _is_valid_timeout(10)
    True
    >>> _is_valid_timeout(-1)
    False
    >>> _is_valid_timeout("10")
    False
    """
    if timeout is None:
        return True
    else:
        return isinstance(timeout, int) and timeout >= 0


def _flush_out(f, dst=sys.stdout):
    f.seek(0)
    out = f.read()
    if out:
        print >> dst, out


def _terminate(proc):
    """
    Force terminating the given proc :: subprocess.Popen

    :return:  status code of proc
    """
    U.typecheck(proc, subprocess.Popen)

    if proc.returncode is not None:  # It's finished already.
        return proc.returncode

    # First, try sending SIGTERM to stop it.
    proc.terminate()
    rc = proc.poll()

    if rc is None:
        proc.kill()  # Second, try sending SIGKILL to kill it.
    else:
        return rc

    # Avoid creating zonbie.
    try:
        (_pid, _rc) = os.waitpid(proc.pid, os.WNOHANG)
    except OSError:
        pass

    return -1


def worker(task):
    """
    :param task: Task object
    """
    stdin = open(os.devnull, "r")
    stdout = tempfile.TemporaryFile()
    stderr = tempfile.TemporaryFile()

    try:
        task.proc = subprocess.Popen(
            task.cmd,
            bufsize=4096,
            shell=True,
            cwd=task.workdir,
            stdin=None,
            stdout=stdout,
            stderr=stderr,
        )
    except Exception, e:
        if task.nofail:
            logging.warn(str(e))
            task.result = -1
            return task.result
        else:
            raise

    timer = threading.Timer(task.timeout, _terminate, [task.proc])
    timer.start()

    task.result = task.proc.wait()  # may block forever.

    timer.cancel()

    if _debug_mode():
        _flush_out(stdout)
    _flush_out(stderr, sys.stderr)

    sys.stdout.flush()
    sys.stderr.flush()

    return task.result


class Task(B.Bunch):

    def __init__(self, cmd, user=None, host="localhost", workdir=os.curdir,
            timeout=MAX_TIMEOUT, nofail=False):
        """
        :param cmd: Command string
        :param user: User to run command
        :param host: Host to run command
        :param workdir: Working directory in which command runs
        :param timeout: Time out in seconds
        :param nofail: Capture exceptions and never fails
        """
        assert _is_valid_timeout(timeout), "Invalid timeout: " + str(timeout)

        self.user = E.get_username() if user is None else user
        self.host = host
        self.timeout = timeout
        self.nofail = nofail

        if U.is_local(host):
            #logging.debug("host %s is local" % host)
            if "~" in workdir:
                workdir = os.path.expanduser(workdir)
        else:
            cmd = "ssh -o ConnectTimeout=%d %s@%s 'cd %s && %s'" % \
                (MIN_TIMEOUT, user, host, workdir, cmd)
            logging.debug("Remote host. Rewrote cmd to " + cmd)
            workdir = os.curdir

        self.cmd = cmd
        self.workdir = workdir
        self.cmd_str = "%s [%s]" % (cmd, workdir)
        self.thread = None
        self.proc = None
        self.result = None

    def description(self):
        return self.cmd_str

    def __str__(self):
        return self.cmd_str

    def finished(self):
        return not self.result is None

    def returncode(self):
        return self.result


class ThreadedCommand(object):
    """
    Based on the idea found at
    http://stackoverflow.com/questions/1191374/subprocess-with-timeout
    """

    def __init__(self, task, *args, **kwargs):
        """
        :param task: Task object or cmd
        """
        if not isinstance(task, Task):
            task = Task(task, *args, **kwargs)

        self.task = task

    def __str__(self):
        return self.task.description()

    def timeout(self):
        return self.task.timeout

    def run_async(self):
        """
        FIXME: Avoid deadlock in subprocesses. See also http://goo.gl/xpYeE
        """
        logging.info("Run: " + self.task.description())

        self.thread = threading.Thread(
            name=self.task.description()[:20],
            target=worker,
            args=(self.task, ),
        )
        self.thread.start()

        logging.debug("Finished: " + self.task.description())

    def get_result(self):
        if self.thread is None:
            logging.warn(
                "Thread does not exist. Did you call %s.run_async() ?" % \
                    self.__class__.__name__
            )
            return -1

        # it may block.
        self.thread.join()

        # NOTE: It seems there is a case that thread is not alive but process
        # spawned from that thread is still alive.
        if not self.task.finished():
            self.task.result = _terminate(self.task.proc)

        if self.thread.isAlive():
            self.thread.join()

        return self.task.result

    def run(self):
        self.run_async()
        return self.get_result()


def run(cmd, user=None, host="localhost", workdir=os.curdir, timeout=None,
        stop_on_error=False):
    """
    :param stop_on_error: Whether to raise exception if any errors occurred.
    """
    task = Task(cmd, user, host, workdir, timeout)
    rc = ThreadedCommand(task).run()

    if rc != 0:
        emsg = "Failed: %s, rc=%d" % (str(task), rc)

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
        (c for c in cs if c.timeout() is not None), key=lambda c: c.timeout()
    )
    cs_wo_t = [c for c in cs if c.timeout() is None]

    for c in reversed(cs_w_t):
        c.run_async()

    for c in cs_wo_t:
        c.run_async()

    # no timeouts suggests these should finish jobs immedicately.
    rcs = [c.get_result() for c in cs_wo_t]

    rcs += [c.get_result() for c in cs_w_t]

    return rcs


# vim:sw=4 ts=4 et:
