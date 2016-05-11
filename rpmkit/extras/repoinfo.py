#
# Copyright (C) 2016 Red Hat, Inc.
# Author: Satoru SATOH <ssato@redhat.com>
# License: MIT
#
"""
package size in primary.xml:

  <package type="rpm">
    <name>tftp-server</name>
    ...
    <size package="49428" installed="61007" archive="62600"/>
    ...
  </package>

-> repo size ~ sum (//package/size/@package)
"""
from __future__ import print_function

import datetime
import gzip
import itertools
import logging
import operator
import optparse
import os.path
import string
import sys
import tempfile

try:
    # First, try lxml which is compatible with elementtree and looks faster a
    # lot. See also: http://getpython3.com/diveintopython3/xml.html
    from lxml2 import etree as ET
except ImportError:
    try:
        import xml.etree.ElementTree as ET
    except ImportError:
        import elementtree.ElementTree as ET


LOG = logging.getLogger(__name__)
_REPO_XML_NS = "http://linux.duke.edu/metadata/common"  # see primary.xml


def _ns(*items):
    """
    :return: ET's expression with namespace prefix
    """
    return '/'.join("{%s}%s" % (_REPO_XML_NS, item) for item in items)


def pkgdata_from_primary_xml_itr(filepath):
    """
    :param filepath: Path to primary.xml[.gz]
    """
    content = gzip.GzipFile(filename=filepath).read()
    root = ET.ElementTree(ET.fromstring(content)).getroot()

    for pkg in root.findall(_ns("package")):
        try:
            yield dict(name=pkg.find(_ns("name")).text,
                       evr=pkg.find(_ns("version")).attrib,
                       arch=pkg.find(_ns("arch")).text,
                       size=pkg.find(_ns("size")).attrib)
        except:
            LOG.warn("Skipped: ", pkg.find(_ns("name")).text)
            pass


_SUMMARY = """
# of RPMs (names): %d
# of unique RPMs: %d
Total size of RPMs: %d [GB]
"""


def anaylize_and_show_results(filepath, summary=_SUMMARY):
    """
    :param filepath: Path to primary.xml[.gz]
    """
    pkgs = list(pkgdata_from_primary_xml_itr(filepath))
    unit = 1024 * 1024 * 1024  # (byte) -> kbyte -> MByte -> GByte

    uns = set(p["name"] for p in pkgs)
    ups = set((p["name"], p["arch"], tuple(p["evr"].values())) for p in pkgs)
    ssize = sum(int(p["size"]["package"]) for p in pkgs) / unit

    print(_SUMMARY % (len(uns), len(ups), ssize))


def option_parser():
    usage = """Usage: %prog [OPTION ...] PATH

    where PATH   Path to primary.xml.gz
"""
    psr = optparse.OptionParser(usage)
    psr.set_defaults(verbose=False)
    psr.add_option("-v", "--verbose", action="store_true", help="Verbose mode")

    return psr


def main():
    psr = option_parser()
    (options, args) = psr.parse_args()

    if options.verbose:
        LOG.setLevel(logging.DEBUG)

    if not args:
        psr.print_help()
        sys.exit(1)

    anaylize_and_show_results(args[0])


if __name__ == "__main__":
    main()

# vim:sw=4:ts=4:et:
