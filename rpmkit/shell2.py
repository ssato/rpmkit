#
# Copyright (C) 2011 - 2013 Red Hat, Inc.
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

import gevent
import logging
import os
import os.path
import signal
import subprocess


def _is_local(fqdn_or_hostname):
    """
    >>> _is_local("localhost")
    True
    >>> _is_local("localhost.localdomain")
    True
    >>> _is_local("repo-server.example.com")
    False
    >>> _is_local("127.0.0.1")  # special case:
    False
    """
    return fqdn_or_hostname.startswith("localhost")


def _validate_timeout(timeout):
    """
    Validate timeout value.

    >>> _validate_timeout(10)
    >>> _validate_timeout(0)
    >>> _validate_timeout(None)
    >>> try:
    ...     _validate_timeout(-1)
    ... except AssertionError:
    ...     pass

    :param timeout: Time value :: Int or None
    """
    assert timeout is None or int(timeout) >= 0, \
        "Invalid timeout: " + str(timeout)


def _validate_timeouts(*timeouts):
    """
    A variant of the above function to validate multiple timeout values.

    :param timeouts: List of timeout values :: [Int | None]
    """
    for to in timeouts:
        _validate_timeout(to)


# Connection timeout and Timeout to wait completion of runnign command in
# seconds. None or -1 means that it will wait forever.
_RUN_TO = None
_CONN_TO = 10


# FIXME: A class wrapping gevent.Greenlet to join/kill/timeout subprocess
# processes, must be implemented.
class CommandRunner(gevent.Greenlet):

    pass


def run_async(cmd, user=None, host="localhost", workdir=os.curdir,
              timeout=_RUN_TO, conn_timeout=_CONN_TO, **kwargs):
    """
    Run command ``cmd`` asyncronously.

    :param cmd: Command string
    :param user: Run command as this user
    :param host: Host on which command runs
    :param workdir: Working directory in which command runs
    :param timeout: Command execution timeout in seconds or None
    :param conn_timeout: Connection timeout in seconds or None

    :return: greenlet instance
    """
    _validate_timeouts(timeout, conn_timeout)

    if _is_local(host):
        if "~" in workdir:
            workdir = os.path.expanduser(workdir)
    else:
        if user is None:
            user = E.get_username()

        if conn_timeout is None:
            toopt = ""
        else:
            toopt = '' "-o ConnectTimeout=%d" % conn_timeout

        cmd = "ssh %s %s@%s 'cd %s && %s'" % (toopt, user, host, workdir, cmd)
        logging.debug("Remote host. Rewrote cmd to " + cmd)

        workdir = os.curdir

    gevent.signal(signal.SIGQUIT, gevent.shutdown)

    return gevent.spawn(subprocess.Popen, cmd, cwd=workdir, shell=True)


def run(cmd, user=None, host="localhost", workdir=os.curdir, timeout=_RUN_TO,
        conn_timeout=_CONN_TO, stop_on_error=False, **kwargs):
    """
    Run command ``cmd``.

    :param cmd: Command string
    :param user: User to run command
    :param host: Host to run command
    :param workdir: Working directory in which command runs
    :param timeout: Command execution timeout in seconds or None
    :param conn_timeout: Connection timeout in seconds or None
    :param stop_on_error: Stop and raise exception if any error occurs

    :return: True if job was sucessful else False or RuntimeError exception
        raised if stop_on_error is True
    """
    job = run_async(cmd, user, host, workdir, timeout, conn_timeout)
    timer = gevent.Timeout.start_new(timeout)

    try:
        #job.join(timeout=timer)
        job.join()  # It will block!

        if job.successful():
            return True

        reason = "unknown"

        if stop_on_error:
            gevent.shutdown()
            raise RuntimeError(m)

    # FIXME: This does not work and Timeout exception never be raised for
    # subprocess's process actually.
    except gevent.Timeout:
        reason = "timeout"

    except KeyboardInterrupt as e:
        reason = "interrupted"
        job.kill()

    gevent.shutdown()
    logging.warn("Failed (%s): %s" % (reason, cmd))
    return False


def prun_async(list_of_args):
    """
    Run commands in parallel asyncronously.

    :param list_of_args: List of arguments (:: [([arg], dict(kwarg=...))]) for
        each job will be passed to ``run_async`` function.

    :return: List of greenlet instances
    """
    return [run_async(*args, **kwargs) for args, kwargs in list_of_args]


def prun(list_of_args):
    """
    Run commands in parallel.

    :param list_of_args: List of arguments (:: [([arg], dict(kwarg=...))]) for
        each job will be passed to ``run_async`` function.

    :return: List of status of each job :: [bool]
    """
    return [run(*args, **kwargs) for args, kwargs in list_of_args]

# vim:sw=4:ts=4:et:
