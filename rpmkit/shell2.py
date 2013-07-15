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
    """
    assert timeout is None or int(timeout) >= 0, \
        "Invalid timeout: " + str(timeout)


class Timeout(object):
    """

    >>> timeo = Timeout(10, 10)
    >>> timeo.exec_timeout() == 10
    True
    >>> timeo.set_exec_timeout(None)
    >>> timeo.exec_timeout() != 10
    True
    >>> timeo.exec_timeout() is None
    True
    """

    def __init__(self, exec_timeout=None, conn_timeout=None):
        _validate_timeout(exec_timeout)
        _validate_timeout(conn_timeout)

        self._exec_to = exec_timeout
        self._conn_to = conn_timeout

    def exec_timeout(self):
        return self._exec_to

    def conn_timeout(self):
        return self._conn_to

    def set_exec_timeout(self, val):
        _validate_timeout(val)
        self._exec_to = val

    def set_conn_timeout(self, val):
        _validate_timeout(val)
        self._conn_to = val

    def validate(self):
        _validate_timeout(self._exec_to)
        _validate_timeout(self._conn_to)


_TIMEOUT = Timeout(None, 10)


def run_async(cmd, user=None, host="localhost", workdir=os.curdir,
              timeout=_TIMEOUT, **kwargs):
    """
    Run command asyncronously.

    :param cmd: Command string
    :param user: User to run command
    :param host: Host to run command
    :param workdir: Working directory in which command runs
    :param timeout: Timeout object

    :return: greenlet instance
    """
    timeout.validate()

    if _is_local(host):
        if "~" in workdir:
            workdir = os.path.expanduser(workdir)
    else:
        if user is None:
            user = E.get_username()

        if timeout.conn_timeout() is None:
            toopt = ""
        else:
            toopt = "-o ConnectTimeout=%d" % timeout.conn_timeout()

        cmd = "ssh %s %s@%s 'cd %s && %s'" % (toopt, user, host, workdir, cmd)
        logging.debug("Remote host. Rewrote cmd to " + cmd)

        workdir = os.curdir

    return gevent.spawn(subprocess.Popen, cmd, cwd=workdir, shell=True)


def run(cmd, user=None, host="localhost", workdir=os.curdir,
        timeout=_TIMEOUT, stop_on_error=False, **kwargs):
    """
    Run command.

    :param cmd: Command string
    :param user: User to run command
    :param host: Host to run command
    :param workdir: Working directory in which command runs
    :param timeout: Timeout object
    :param stop_on_error: Stop and raise exception if any error occurs

    :return: True if job was sucessful else False or RuntimeError exception
        raised if stop_on_error is True
    """
    job = run_async(cmd, user, host, workdir, timeout)
    job.join(timeout.exec_timeout())

    if not job.successful():
        if stop_on_error:
            raise RuntimeError("Failed: " + cmd)

        logging.warn("Failed: " + cmd)
        return False

    return True


def prun_async(list_of_args):
    """
    Run commands in parallel asyncronously.

    :param list_of_args: List of arguments (:: [([arg], dict(kwarg=...))]) for
        each job will be passed to ``run_async`` function.

    :return: List of greenlet instance
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
