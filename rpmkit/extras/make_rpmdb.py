#
# Copyright (C) 2014 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato@redhat.com>
# License: GPLv3+
#
"""
Make up RPM database files from a RPMs list such like `rpm -qa` outputs,
installed-rpms file in sosreport outputs, etc.
"""
from logging import DEBUG, INFO

import rpmkit.identrpm as RI
import rpmkit.rpmutils as RR
import rpmkit.swapi as RS
import rpmkit.utils as RU
import logging
import multiprocessing
import operator
import optparse
import os.path
import os
import rpm
import sys
import urlgrabber


def read_rpm_header(ts, rpm_path):
    """
    :param ts: An initialized instance of rpm.TransactionSet
    :param rpm_path: RPM's file path
    """
    with open(rpm_path, 'rb') as f:
        return ts.hdrFromFdno(f)


rpmtsCallback_fd = None


# @see http://bit.ly/1jkc2iW
def runCallback(reason, amount, total, key, client_data):
    global rpmtsCallback_fd

    sargs = [str(a) for a in (reason, amount, total, key, client_data)]

    if reason == rpm.RPMCALLBACK_INST_OPEN_FILE:
        logging.debug("Opening file: " + str(sargs))
        rpmtsCallback_fd = os.open(key, os.O_RDONLY)

        return rpmtsCallback_fd

    elif reason == rpm.RPMCALLBACK_INST_START:
        logging.debug("Closing file: " + str(sargs))

        if rpmtsCallback_fd:
            os.close(rpmtsCallback_fd)


def install_rpms(rpms, dbdir):
    """
    :param rpms: A list of RPM info dicts contain 'path' info
    :param dbdir: RPM DB topdir; RPM DB files will be created in
        ``dbdir``/var/lib/rpm.
    """
    if not dbdir.startswith(os.path.sep):  # Relative path.
        dbdir = os.path.abspath(dbdir)

    ts = RR.rpm_transactionset(dbdir, readonly=False)

    # Corresponding to combination of rpm options:
    #   --noscripts --justdb --notriggers
    ts.setFlags(rpm.RPMTRANS_FLAG_NOSCRIPTS | rpm.RPMTRANS_FLAG_JUSTDB |
                rpm.RPMTRANS_FLAG_NOTRIGGERS)

    # Corresponding to combination of rpm options: --force
    ts.setProbFilter(rpm.RPMPROB_FILTER_REPLACEPKG |
                     rpm.RPMPROB_FILTER_REPLACENEWFILES |
                     rpm.RPMPROB_FILTER_REPLACEOLDFILES |
                     rpm.RPMPROB_FILTER_OLDPACKAGE |
                     rpm.RPMPROB_FILTER_FORCERELOCATE)

    # Avoid check signature checks:
    ts.setVSFlags(rpm._RPMVSF_NOSIGNATURES)

    for rpm_path in rpms:
        h = read_rpm_header(ts, rpm_path)
        logging.debug("Add: %s-%s-%s" % (h['name'], h['version'],
                                         h['release']))

        ts.addInstall(h, rpm_path, 'i')

    unresolved_deps = ts.check()
    if unresolved_deps:
        logging.error("Unresolved deps: " + str(unresolved_deps))
        return

    # pylint: disable=E1101
    ts.order()
    # pylint: enable=E1101

    ts.run(runCallback, 1)


def download_rpms(pkg, outdir):
    """
    TBD.

    :param pkg: A dict contains RPM basic information other than url
    :param outdir: Where to save RPM[s]
    """
    url = RS.call("packages.getPackageUrl", [pkg["id"]], ["--no-cache"])[0]
    logging.info("RPM URL: " + ', '.join(url))

    return urlgrabber.urlgrab(url, os.path.join(outdir, os.path.basename(url)))


def make_rpmdb(rpmlist_path, rpmsdir=os.curdir, root=os.curdir, options=[],
               dryrun=False):
    """
    """
    if not rpmsdir.startswith(os.path.sep):  # relative path.
        rpmsdir = os.path.abspath(rpmsdir)

    labels = RI.load_packages(rpmlist_path)
    (pss, failed) = RI.identify_rpms(labels, details=True, newer=False,
                                     options=options)

    # Pick up oldest from each ps if len(ps) > 1.
    rpm_paths = [os.path.join(rpmsdir, ps[0]['path']) for ps in pss if ps]

    logging.warn("%d RPMs not resolved: %s" % (len(failed), ', '.join(failed)))

    if dryrun:
        logging.info("Just print out commands may do same things: ")

        for p in rpm_paths:
            print("rpm --force --nodeps --justdb --root %s %s" % (root, p))
    else:
        install_rpms(rpm_paths, root)


def option_parser():
    defaults = dict(verbose=False, sw_options=[], rpmsdir=os.curdir,
                    root=os.curdir, dryrun=False)

    p = optparse.OptionParser("Usage: %prog [Options] RPMS_LIST")
    p.set_defaults(**defaults)

    p.add_option("", "--dryrun", action="store_true",
                 help="Do not install RPMs and make RPM database files "
                      "actually and print out commands have same effects")
    p.add_option("", "--rpmsdir", help="Top dir RPMs are [%default]")
    p.add_option("", "--root",
                 help="Root dir of RPM DBs will be created [%default]")
    p.add_option("", "--sw-options", action="append",
                 help="Options passed to swapi, can be specified multiple"
                      "times.")
    p.add_option("-v", "--verbose", action="store_true", help="Verbose mode")
    return p


def main():
    p = option_parser()
    (options, args) = p.parse_args()

    RU.init_log(DEBUG if options.verbose else INFO)

    if not args:
        p.print_usage()
        sys.exit(1)

    rpmlist_path = args[0]

    if not dryrun and not os.path.exists(os.path.join(options.rpmsdir,
                                                     'redhat')):
       print("RPMs dir does not look exist under: " + options.rpmsdir)
       sys.exit(1)

    make_rpmdb(rpmlist_path, options.rpmsdir, options.root, options.sw_options,
               options.dryrun)


if __name__ == "__main__":
    main()

# vim:sw=4:ts=4:et:
