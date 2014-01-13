#
# build srpm in current dir or specified working dir from given rpm spec.
#
# Author: Satoru SATOH <ssato redhat.com>
# License: MIT
#
# Requirements: rpm-python, rpm-build
#
from logging import DEBUG, INFO

import os
import subprocess

try:
    import gevent

    from gevent import monkey
    monkey.patch_socket()

    def run(cmd_s, workdir=os, timeout=None, stop_on_error=True):
        """
        :param cmd_s: Command string to execute.
        :param workdir: Working dir to run command.
        :param timeout: Time out to wait for the completion of running command,
            or None
        :param stop_on_error: Raise subprocess.CalledProcessError exception if
            command execution was failed.

        :return: True if succeeded to run command or if ``stop_on_error`` is
            False.
        """
        job = gevent.spawn(subprocess.Popen, cmd_s, cwd=workdir, shell=True,
                           stdout=subprocess.PIPE)
        job.join(timeout)

        if job.successful():
            return True
        else:
            if stop_on_error:
                raise subprocess.CalledProcessError("Failed to run: " + cmd_s)

            return False

except ImportError:
    def run(cmd_s, workdir=os, timeout=None, stop_on_error=True):
        """
        :param cmd_s: Command string to execute.
        :param workdir: Working dir to run command.
        :param timeout: Time out to wait for the completion of running command,
            or None
        :param stop_on_error: Raise subprocess.CalledProcessError exception if
            command execution was failed.

        :return: True if succeeded to run command.
        """
        try:
            subprocess.check_call(cmd_s, cwd=workdir, shell=True,
                                  stdout=subprocess.PIPE)
        except subprocess.CalledProcessError:
            if stop_on_error:
                #raise subprocess.CalledProcessError("Failed to run: " + cmd_s)
                raise

            return False

        return True

import logging
import optparse
import os.path
import re
import rpm
import sys
import urllib2


def get_source0_url_from_rpmspec(rpmspec):
    """
    Parse given rpm spec and return (source0's url, source0).

    It may throw ValuError("can't parse specfile"), etc.

    :param rpmspec: Path to the RPM SPEC file
    :return: (URL_of_source0, source0_basename)
    """
    spec = rpm.spec(rpmspec)

    # looks rpmSourceFlags_e in <rpm/rpmspec.h>:
    is_source = lambda t: t[-1] == 1 << 0

    src0 = [s for s in spec.sources if is_source(s)][0][0]
    assert src0, "SOURCE0 should not be empty!"

    # 1. Try SOURCE0:
    if re.match(r"^(ftp|http|https)://", src0):
        logging.debug("URL=" + src0)
        url_src0 = (src0, os.path.basename(src0))
    else:
        # 2. Try URL + basename(src0):
        base_url = spec.sourceHeader["URL"]
        assert base_url, "URL should not be empty!"
        url_src0 = (os.path.join(base_url, src0), src0)

    logging.debug("URL=%s, src0=%s" % url_src0)
    return url_src0


def download(url, out, data=None, headers={}):
    """
    Download file from given URL and save as ``out``.

    :param url: URL of the file
    :param out: Output file path
    :param data: Data to send to when requesting the file
    :param headers: Extra headers to send to
    """
    req = urllib2.Request(url=url, data=data, headers=headers)
    f = urllib2.urlopen(req)

    with open(out, "wb") as o:
        o.write(f.read())


def download_src0(rpmspec, url, out):
    """
    :param rpmspec: Path to the RPM SPEC file
    :param url: URL candidate for the source0
    :param out: Output file path
    """
    try:
        download(url, out)

    except urllib2.HTTPError, e:
        logging.warn("Could not download source0 from: " + url)
        url = raw_input("Input the correct URL of source0 > ")

        download(url, out)


def do_buildsrpm(rpmspec, workdir, timeout=None):
    """
    Build the source rpm.

    :param rpmspec: Path to the RPM SPEC file
    :param workdir: Working dir to make RPM files
    :param timeout: Timeout in seconds to wait for the completion of build job.
        None means it will wait forever.
    """
    cs = ["rpmbuild", "--define \"_srcrpmdir %(workdir)s\"",
          "--define \"_sourcedir %(workdir)s\"",
          "--define \"_buildroot %(workdir)s\"",
          "-bs %(spec)s"]
    cmd = ' '.join(cs) % dict(workdir=workdir, spec=rpmspec)

    logging.info("Creating src.rpm from %s in %s" % (rpmspec, workdir))
    run(cmd, workdir=workdir, timeout=timeout, stop_on_error=True)


def main(argv=sys.argv):
    defaults = dict(verbose=False, workdir=None, timeout=None)

    p = optparse.OptionParser("%prog [Options...] RPM_SPEC")
    p.set_defaults(**defaults)

    p.add_option("-v", "--verbose", action="store_true", help="Verbose mode")
    p.add_option("-w", "--workdir", help="Working dir to search source0")
    p.add_option("-T", "--timeout",
                 help="Timeout in seconds or None (wait for the completion "
                      "of build forever")
    (options, args) = p.parse_args(argv[1:])

    if not args:
        p.print_usage()
        sys.exit(-1)

    logging.basicConfig(level=(DEBUG if options.verbose else INFO), )

    rpmspec = os.path.abspath(args[0])
    logging.info("rpm spec is " + rpmspec)

    if options.workdir is None:
        options.workdir = os.path.dirname(rpmspec)

    if options.timeout is not None:
        options.timeout = int(options.timeout)

    logging.info("Set workdir to " + options.workdir)

    (url, src0) = get_source0_url_from_rpmspec(rpmspec)
    s0 = os.path.join(options.workdir, src0)

    if not os.path.exists(options.workdir):
        logging.debug("Creating working dir: " + options.workdir)
        os.makedirs(options.workdir)

    if not os.path.exists(s0):
        download_src0(rpmspec, url, s0)

    do_buildsrpm(rpmspec, options.workdir, options.timeout)


if __name__ == '__main__':
    main(sys.argv)

# vim:sw=4:ts=4:et:
