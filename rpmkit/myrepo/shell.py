#
# Copyright (C) 2011 Red Hat, Inc.
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


WAIT_TYPE = (WAIT_FOREVER, WAIT_MIN, WAIT_MAX) = (None, "min", "max")
MIN_TIMEOUT = 5  # [sec]


class ThreadedCommand(object):
    """
    Based on the idea found at
    http://stackoverflow.com/questions/1191374/subprocess-with-timeout
    """

    def __init__(self, cmd, user=None, host="localhost", workdir=os.curdir,
            stop_on_failure=True, timeout=None):
        self.host = host
        self.stop_on_failure = stop_on_failure
        self.user = E.get_username() if user is None else user
        self.timeout = timeout

        if U.is_local(host):
            if "~" in workdir:
                workdir = os.path.expanduser(workdir)
        else:
            cmd = "ssh -o ConnectTimeout=%d %s@%s 'cd %s && %s'" % \
                (MIN_TIMEOUT, user, host, workdir, cmd)
            workdir = os.curdir

        self.cmd = cmd
        self.workdir = workdir
        self.cmd_str = "%s [%s]" % (self.cmd, self.workdir)

        self.process = None
        self.thread = None
        self.result = None

    def run_async(self):
        def func():
            if logging.getLogger().level < logging.INFO:  # logging.DEBUG
                stdout = sys.stdout
            else:
                stdout = open("/dev/null", "w")

            #logging.info("Run: %s" % cmd_str_shorten)
            logging.info("Run: " + self.cmd_str)

            self.process = subprocess.Popen(self.cmd,
                                            bufsize=4096,
                                            shell=True,
                                            cwd=self.workdir,
                                            stdout=stdout,
                                            stderr=sys.stderr
            )
            self.result = self.process.wait()

            logging.debug("Finished: %s" % self.cmd_str)

        self.thread = threading.Thread(target=func)
        self.thread.start()

    def get_result(self):
        if self.thread is None:
            logging.warn(
                "Thread does not exist. Did you call %s.run_async() ?" % \
                    self.__class__.__name__
            )
            return None

        # it will block.
        self.thread.join(self.timeout)

        if self.thread.is_alive():
            logging.warn("Terminating: %s" % self.cmd_str)
            try:
                self.process.terminate()
            except OSError:  # the process exited already.
                pass

            self.thread.join()

        rc = self.result

        if rc != 0:
            emsg = "Failed: %s, rc=%d" % (self.cmd, rc)

            if self.stop_on_failure:
                raise RuntimeError(emsg)
            else:
                logging.warn(emsg)

        return rc

    def run(self):
        self.run_async()
        return self.get_result()


def run(cmd_str, user=None, host="localhost", workdir=os.curdir,
        stop_on_failure=True, timeout=None):
    cmd = ThreadedCommand(cmd_str, user, host, workdir, stop_on_failure, timeout)
    return cmd.run()


def prun_and_get_results(cmds, wait=WAIT_FOREVER):
    """
    @cmds  [ThreadedCommand]
    @wait  Int  Timewait value in seconds.
    """
    def is_valid_timeout(timeout):
        return timeout is None or isinstance(timeout, int) and timeout > 0

    for c in cmds:
        c.run_async()

    if wait != WAIT_FOREVER:
        ts = [c.timeout for c in cmds if is_valid_timeout(c.timeout)]

        if ts:
            if wait == WAIT_MAX:
                timeout = max(ts)
            elif wait == WAIT_MIN:
                timeout = min(ts)
            else:
                if not is_valid_timeout(wait):
                    RuntimeError(
                        "Invalid 'wait' value was passed to get_results: " + \
                            str(wait)
                    )
                else:
                    timeout = wait

            time.sleep(timeout)

    return [c.get_result() for c in cmds]


# vim:sw=4 ts=4 et:
