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


_CONNECT_TIMEOUT = 10    # 10 [sec]


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
    >>> _validate_timeout(-1)
    AssertionError: Invalid timeout: -1
    """
    assert timeout is None or int(timeout) >= 0, \
        "Invalid timeout: " + str(timeout)


def run_async(cmd, user=None, host="localhost", workdir=os.curdir,
              timeout=None, connect_timeout=_CONNECT_TIMEOUT,
              stop_on_error=False, **kwargs):
    """
    Run command.

    :param cmd: Command string
    :param user: User to run command
    :param host: Host to run command
    :param workdir: Working directory in which command runs
    :param timeout: Command execution timeout in seconds
    :param connect_timeout: Connect timeout in seconds
    :param stop_on_error: Do not catch exceptions of errors if true

    :return: greenlet instance
    """
    _validate_timeout(timeout)
    _validate_timeout(connect_timeout)

    if _is_local(host):
        if "~" in workdir:
            workdir = os.path.expanduser(workdir)
    else:
        if user is None:
            user = E.get_username()

        if connect_timeout is None:
            toopt = ""
        else:
            toopt = "-o ConnectTimeout=%d" % connect_timeout

        cmd = "ssh %s %s@%s 'cd %s && %s'" % (toopt, user, host, workdir, cmd)
        logging.debug("Remote host. Rewrote cmd to " + cmd)

        workdir = os.curdir

    return gevent.spawn(subprocess.Popen, cmd, cwd=workdir, shell=True)


def run(cmd, user=None, host="localhost", workdir=os.curdir,
        timeout=None, connect_timeout=_CONNECT_TIMEOUT,
        stop_on_error=False, **kwargs):
    """
    Run command.

    :param cmd: Command string
    :param user: User to run command
    :param host: Host to run command
    :param workdir: Working directory in which command runs
    :param timeout: Command execution timeout in seconds
    :param connect_timeout: Connect timeout in seconds
    :param stop_on_error: Do not catch exceptions of errors if true

    :return: True if job was sucessful else False
    """
    job = run_async(cmd, user, host, workdir, timeout, connect_timeout,
                    stop_on_error, **kwargs)
    job.join(timeout)

    return job.successful()  # TODO: ... or job.exception


def prun_async(list_of_args):
    """
    Run commands. 

    :param list_of_args: List of arguments (:: [([arg], dict(kwarg=...))]) for
        each job will be passed to ``run_async`` function.

    :return: List of greenlet instance
    """
    return [run_async(*args, **kwargs) for args, kwargs in list_of_args]


def prun(list_of_args):
    """
    Run commands. 

    :param list_of_args: List of arguments (:: [([arg], dict(kwarg=...))]) for
        each job will be passed to ``run_async`` function.

    :return: List of status of each job :: [bool]
    """
    return [run(*args, **kwargs) for args, kwargs in list_of_args]


# vim:sw=4:ts=4:et:
