#
# Copyright (C) 2014 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato@redhat.com>
# License: GPLv3+
#
import rpmkit.identrpm as RI
import rpmkit.swapi as RS
import logging
import multiprocessing
import os.path
import os
import sys
import urlgrabber


RPMDB_SUBDIR = "var/lib/rpm"


def fetch_rpm_path_g(label):
    """
    :param label: RPM package label
    """
    pkgs = RI.identify(label, True)
    for p in pkgs:
        if 'path' not in p:
            pd = RS.call("packages.getDetails", [pkg['id']])
            p.update(pd)

        yield p


def fetch_rpm_infos(label):
    """
    :param label: RPM package label
    """
    ps = sorted(fetch_rpm_path_g(label), key=itemgetter('epoch'), reverse=True)

    m0 = "Candidate RPMs: %(name)s-%(version)s.%(release)s.%(arch)s" % ps[0]
    logging.info(m0 + "epochs=%s" % ', '.join(str(p['epoch']) for p in ps))

    return ps


def download_rpms(label, outdir, latest=False):
    """
    :param label: RPM package label
    :param outdir: Where to save RPM[s]
    :param latest: Download the latest RPM if True else oldest RPM will be
        downloaded.
    """
    ps = fetch_rpm_infos(label)
    pkg = ps[0]  # Select the head of the list

    urls = RS.call("packages.getPackageUrl", [pkg["id"]], ["--no-cache"])
    logging.info("RPM URLs: " + ', '.join(urls))

    url = urls[0]  # Likewise
    return urlgrabber.urlgrab(url, os.path.join(outdir, os.path.basename(url)))


def option_parser():
    defaults = dict(verbose=False, input=None, sw_options=[])

    p = optparse.OptionParser(usage)
    p.set_defaults(**defaults)
    p.add_option("-i", "--input",
                 help="Packages list file (output of 'rpm -qa')")
    p.add_option("", "--sw-options", action="append",
                 help="Options passed to swapi, can be specified multiple"
                      "times.")
    p.add_option("-v", "--verbose", action="store_true", help="Verbose mode")
    return p


def main(cmd_map=_ARGS_CMD_MAP):
    p = option_parser()
    (options, args) = p.parse_args()

    RU.init_log(DEBUG if options.verbose else INFO)

    if not args:
        p.print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()

# vim:sw=4:ts=4:et:
