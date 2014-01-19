#
# Copyright (C) 2014 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato@redhat.com>
# License: GPLv3+
#
import rpmkit.identrpm as RI
import rpmkit.swapi as RS
import logging
import os.path
import os
import sys
import urlgrabber


RPMDB_SUBDIR = "var/lib/rpm"


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

    return

    url = urls[0]  # Likewise
    x = urlgrabber.urlgrab(url, os.path.join(outdir, os.path.basename(url)))

# vim:sw=4:ts=4:et:
