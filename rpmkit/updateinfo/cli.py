#
# -*- coding: utf-8 -*-
#
# CLI for rpmkit.updateinfo
#
# Copyright (C) 2013 Satoru SATOH <ssato@redhat.com>
# Copyright (C) 2013, 2014 Red Hat, Inc.
#
# License: GPLv3+
#
import rpmkit.updateinfo.main as RUM
import rpmkit.updateinfo.multihosts as RUMS
import datetime
import logging
import optparse
import os.path


_TODAY = datetime.datetime.now().strftime("%F")
_DEFAULTS = dict(path=None, workdir="/tmp/rk-updateinfo-{}".format(_TODAY),
                 repos=[], multiproc=False, id=None,
                 score=RUM.DEFAULT_CVSS_SCORE, keywords=RUM.ERRATA_KEYWORDS,
                 rpms=RUM.CORE_RPMS, period='', refdir=None,
                 backend=RUM.DEFAULT_BACKEND, verbose=False)
_USAGE = """\
%prog [Options...] ROOT

    where ROOT = RPM DB root having var/lib/rpm from the target host or
                 top dir to hold RPM DB roots of some hosts
                 [multihosts mode]"""


def option_parser(defaults=_DEFAULTS, usage=_USAGE, backends=RUM.BACKENDS):
    p = optparse.OptionParser(usage)
    p.set_defaults(**defaults)

    p.add_option("-w", "--workdir", help="Working dir [%default]")
    p.add_option("-r", "--repo", dest="repos", action="append",
                 help="Yum repo to fetch errata info, e.g. "
                      "'rhel-x86_64-server-6'. It can be given multiple times "
                      "to specify multiple yum repos. Note: Any other repos "
                      "are disabled if this option was set.")
    p.add_option("-I", "--id", help="Data ID [None]")
    p.add_option("-M", "--multiproc", action="store_true",
                 help="Specify this option if you want to analyze data "
                      "in parallel (disabled currently)")
    p.add_option("-B", "--backend", choices=backends.keys(),
                 help="Specify backend to get updates and errata. Choices: "
                      "%s [%%default]" % ', '.join(backends.keys()))
    p.add_option("-S", "--score", type="float",
                 help="CVSS base metrics score to filter 'important' "
                      "security errata [%default]. "
                      "Specify -1 if you want to disable this.")
    p.add_option("-k", "--keyword", dest="keywords", action="append",
                 help="Keyword to select more 'important' bug errata. "
                      "You can specify this multiple times. "
                      "[%s]" % ', '.join(defaults["keywords"]))
    p.add_option('', "--rpm", dest="rpms", action="append",
                 help="RPM names to filter errata relevant to given RPMs")
    p.add_option('', "--period",
                 help="Period to filter errata in format of "
                      "YYYY[-MM[-DD]][,YYYY[-MM[-DD]]], "
                      "ex. '2014-10-01,2014-12-31', '2014-01-01'. "
                      "If end date is omitted, Today will be used instead")
    p.add_option("-R", "--refdir",
                 help="Output 'delta' result compared to the data in this dir")
    p.add_option("-v", "--verbose", action="store_true", help="Verbose mode")

    return p


def main():
    p = option_parser()
    (options, args) = p.parse_args()

    RUM.LOG.setLevel(logging.DEBUG if options.verbose else logging.INFO)

    root = args[0] if args else raw_input("Host[s] data dir (root) > ")
    assert os.path.exists(root), "Not found RPM DB Root: %s" % root

    period = options.period.split(',') if options.period else ()

    if os.path.exists(os.path.join(root, "var/lib/rpm")):
        RUM.main(root, options.workdir, options.repos, options.id,
                 options.score, options.keywords, options.rpms, period,
                 options.refdir)
    else:
        # multihosts mode.
        #
        # TODO: multiproc mode is disabled and options.multiproc is not passed
        # to RUMS.main until the issue of yum that its thread locks conflict w/
        # multiprocessing module is fixed.
        RUMS.main(root, options.workdir, options.repos, options.score,
                  options.keywords, options.rpms, period, options.refdir,
                  False)


if __name__ == '__main__':
    main()

# vim:sw=4:ts=4:et:
