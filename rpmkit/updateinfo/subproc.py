#
# Copyright (C) 2014 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato@redhat.com>
#
# This software is licensed to you under the GNU General Public License,
# version 3 (GPLv3). There is NO WARRANTY for this software, express or
# implied, including the implied warranties of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. You should have received a copy of GPLv3 along with this
# software; if not, see http://www.gnu.org/licenses/gpl.html
#
import Queue
import logging
import os.path
import os
import subprocess
import threading


def is_string(s, str_types=(str, unicode)):
    """
    >>> is_string("abc def")
    True
    >>> is_string(u"abc")
    True
    >>> is_string(1)
    False
    >>> is_string({})
    False
    >>> is_string([])
    False
    """
    return isinstance(s, str_types)


def check_output_simple(cmd, outfile, **kwargs):
    """
    :param cmd: Command string[s]
    :param outfile: Output file object
    :param kwargs: Extra arguments passed to subprocess.Popen
    """
    assert isinstance(outfile, file), "Not a file object: %s" % str(outfile)

    if is_string(cmd):
        cmd = cmd.split()

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, **kwargs)

    while True:
        out = proc.stdout.readline(1)

        if out == '':
            while True:  # It may be blocked forever.
                if proc.poll() is not None:
                    break

        outfile.write(out)
        outfile.flush()

        if proc.poll() is not None:
            break

    return proc.returncode


def enqueue_output(outfd, queue):
    """
    :param outfd: Output FD to read results
    :param queue: Queue to enqueue results read from ``outfd``
    """
    for line in iter(outfd.readline, b''):
        queue.put(line)


def _id(x):
    return x


def run(cmd, ofunc=_id, efunc=_id, timeout=None, **kwargs):
    """
    Run commands without blocking I/O. See also http://bit.ly/VoKhdS.

    :param cmd: Command string[s]
    :param ofunc: Function to process output line by line
        ex. sys.stdout.write :: str => line -> IO (), etc.
    :param efunc: Function to process error line by line
        ex. sys.stderr.write :: str => line -> IO (), etc.
    :param timeout: Timeout to wait for the finish of execution of ``cmd`` in
        seconds or None to wait it forever
    :param kwargs: Extra arguments passed to subprocess.Popen

    :return: (output :: [str] ,err_output :: [str], exitcode :: Int)
    """
    if is_string(cmd):
        cmd = cmd.split()

    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         bufsize=1, close_fds=True)
    outq = Queue.Queue()
    errq = Queue.Queue()

    oets = [threading.Thread(target=enqueue_output, args=(p.stdout, outq)),
            threading.Thread(target=enqueue_output, args=(p.stderr, errq))]

    for t in oets:
        t.setDaemon(True)
        t.start()

    if timeout is not None:
        threading.Thread(target=p.kill)

    outs = []
    errs = []

    while True:
        try:
            oline = outq.get_nowait()
        except Queue.Empty:
            # TODO: How to get info. The following is useful but too verbose.
            # logging.debug("No output from stdout of #%d yet" % p.pid)
            pass
        else:
            ofunc(oline)
            outs.append(oline)

        try:
            eline = errq.get_nowait()
        except Queue.Empty:
            pass
        else:
            efunc(eline)
            errs.append(eline)

        if p.poll() is not None:
            break

    for t in oets:
        t.join()

    return (outs, errs, -1 if p.returncode is None else p.returncode)

# vim:sw=4:ts=4:et:
