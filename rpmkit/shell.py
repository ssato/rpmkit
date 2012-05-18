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


def _cleanup_process(pid):
    """
    Cleanups to avoid creating zonbie.
    """
    try:
        (_pid, _rc) = os.waitpid(pid, os.WNOHANG)
    except OSError:
        pass


def _terminate(proc):
    """
    Force terminating the given proc :: subprocess.Popen

    :return:  status code of proc
    """
    U.typecheck(proc, subprocess.Popen)

    rc = proc.poll()
    if rc is not None:  # It's finished already.
        return rc

    proc.terminate()
    time.sleep(1)
    rc = proc.poll()

    if rc is not None:
        return rc

    proc.kill()
    _cleanup_process(proc.pid)

    return -1


def init(loglevel=logging.INFO):
    multiprocessing.log_to_stderr()
    multiprocessing.get_logger().setLevel(loglevel)
    results = multiprocessing.Queue()
    return results


class TaskError(Exception):

    def __init__(self, rc=-1):
        self._rc = rc

    def __str__(self):
        return "rc=" + str(self._rc)


class Task(object):

    def __init__(self, cmd, user=None, host="localhost", workdir=os.curdir,
            timeout=MAX_TIMEOUT):
        """
        :param cmd: Command string
        :param user: User to run command
        :param host: Host to run command
        :param workdir: Working directory in which command runs
        :param timeout: Time out in seconds
        """
        assert _is_valid_timeout(timeout), "Invalid timeout: " + str(timeout)

        self.user = E.get_username() if user is None else user
        self.host = host
        self.timeout = timeout

        if U.is_local(host):
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
        self.proc = None
        self.returncode = None

    def __str__(self):
        return self.cmd_str

    def finished(self):
        return not self.rc() is None

    def rc(self):
        return self.returncode


def do_task(task, stop_on_error=True):
    """
    :param task: Task object
    :param stop_on_error: Stop task when any error occurs if True
    """
    stdin = open(os.devnull, "r")
    stdout = sys.stdout if _debug_mode() else open(os.devnull, "w")

    try:
        logging.info("Run: " + str(task))
        task.proc = subprocess.Popen(
            task.cmd,
            bufsize=4096,
            shell=True,
            cwd=task.workdir,
            stdin=stdin,
            stdout=stdout,
            stderr=sys.stderr,
        )
    except Exception as e:
        if stop_on_error:
            raise

        logging.warn(str(e))
        return -1

    if task.timeout is not None:
        timer = threading.Timer(task.timeout, _terminate, [task.proc])
        timer.start()

    task.returncode = task.proc.wait()  # may block forever.

    if task.timeout is not None:
        timer.cancel()

    sys.stdout.flush()
    sys.stderr.flush()

    if task.rc() != 0 and stop_on_error:
        raise TaskError(task.rc())

    return task.rc()


def run(cmd, user=None, host="localhost", workdir=os.curdir, timeout=None,
        stop_on_error=False):
    """
    :param stop_on_error: Do not catch exceptions of errors if true
    """
    task = Task(cmd, user, host, workdir, timeout)
    proc = multiprocessing.Process(target=do_task, args=(task, stop_on_error))

    proc.start()
    proc.join(timeout)

    if proc.is_alive():
        proc.terminate()
        proc.join()

        _cleanup_process(proc.pid)

    return task.rc()


def prun(tasks):
    """
    :param tasks: Task objects
    """
    def pool_initializer():
        logging.info("Starting: " + multiprocessing.current_process().name)

    pool = multiprocessing.Pool(initializer=pool_initializer)
    results = pool.map(do_task, tasks)
    pool.close()
    pool.join()

    return results


if __name__ == '__main__':
    results = init()


# vim:sw=4:ts=4:et:
