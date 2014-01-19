#
# Copyright (C) 2014 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato@redhat.com>
# License: GPLv3+
#
import rpmkit.identrpm as RI
import rpmkit.swapi as RS
import itertools
import logging
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


def fetch_rpm_paths(label):
    """
    :param label: RPM package label
    """
    ps = sorted(fetch_rpm_path_g(label), key=itemgetter('epoch'), reverse=True)

    m0 = "Candidate RPMs: %(name)s-%(version)s.%(release)s.%(arch)s" % ps[0]
    logging.info(m0 + "epochs=%s" % ', '.join(str(p['epoch']) for p in ps))


def download_rpm(label, outdir):
    """
    :param label: RPM package label
    """
    pkgs = RI.identify(label, True)
    for p in pkgs:
        logging.info("Candidate RPM info: n=%(name)s, v=%(version)s, "
                     "r=%(release)s, " "arch=%(arch)s, epoch=%(epoch)d, "
                     "id=%(id)d" % p)

    pkg = pkgs[0]  # Select the head of the list
    urls = RS.call("packages.getPackageUrl", [pkg["id"]], ["--no-cache"])
    logging.info("RPM URLs: " + ', '.join(urls))

    url = urls[0]  # Likewise
    x = urlgrabber.urlgrab(url, os.path.join(outdir, os.path.basename(url)))

# vim:sw=4:ts=4:et:
