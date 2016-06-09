#
# Copyright (C) 2016 Red Hat, Inc.
# Author: Satoru SATOH <ssato@redhat.com>
# License: MIT
#
"""
Design Doc:

- Utilize yum' cache, that is, it does not try fetching other.xml by itself.
- List changelog entries in JSON format outputs:

  - if RPM argument was given, show only changelog entries not in that version
  - if no arguments was given, show all RPM's changelog entries

- other.xml format:

<otherdata xmlns="http://linux.duke.edu/metadata/other" packages="17117">
<package pkgid="ea70be8751cf259b0686bcb29fb8703c" name="Deployment_Guide-as-IN" arch="noarch">
  <version epoch="0" ver="5.0.0" rel="19"/>
  <changelog author="Michael Hideo Smith mhideo@redhat.com 5.0.0-12" date="1166738400">
   - Resolves: #218359
   - Includes translations and content revisions.</changelog>
  <changelog author="Michael Hideo Smith mhideo@redhat.com 5.0.0-13" date="1167948000">
   - Resolves: #221247
   - Fix to broken rpm</changelog>
    ...
"""
from __future__ import print_function

import anyconfig
import datetime
import gzip
import logging
import operator
import optparse
import os.path
import sys

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


def _changelog_itr(elems):
    """
    :param elems: ET.Element objects represents changelog entries
    """
    for clog in elems:
        cinfo = clog.attrib
        cinfo["text"] = clog.text
        yield cinfo


def other_xml_itr(content):
    """
    :param content: the content of other.xml :: str
    """
    ns = "http://linux.duke.edu/metadata/other"
    root = ET.ElementTree(ET.fromstring(content)).getroot()
    for pkg in root.getchildren():
        pinfo = pkg.attrib
        LOG.debug("Found package: %s", str(pinfo))

        vinfo = pkg.find("{%s}version" % ns).attrib
        pinfo["version"] = vinfo["ver"]
        pinfo["release"] = vinfo["rel"]
        pinfo["epoch"] = vinfo["epoch"]

        pinfo["evr"] = operator.itemgetter("epoch", "version", "release")(pinfo)
        pinfo["changelogs"] = \
            list(_changelog_itr(pkg.findall("{%s}changelog" % ns)))

        yield pinfo


def get_changelogs_from_otherxml(filepath):
    """
    Try to fetch the content of given repo metadata xml from remote.

    :param filepath: Path to other.xml.gz
    """
    if filepath.endswith(".gz"):
        content = gzip.GzipFile(filename=filepath).read()
    else:
        content = open(filepath).read()

    return sorted(other_xml_itr(content),
                  key=operator.itemgetter("name", "evr", "arch"))


def option_parser():
    usage = """Usage: %prog [OPTION ...] OTHER_XML_GZ_PATH

    where OTHER_XML_GZ_PATH  Path to other.xml.gz
"""
    defaults = dict(output=None, verbose=False)

    psr = optparse.OptionParser(usage)
    psr.set_defaults(**defaults)
    psr.add_option("-v", "--verbose", action="store_true", help="Verbose mode")
    psr.add_option("-o", "--output", help="Output path")

    return psr


def main():
    psr = option_parser()
    (options, args) = psr.parse_args()

    if options.verbose:
        LOG.setLevel(logging.DEBUG)

    if not args:
        psr.print_help()
        sys.exit(1)

    LOG.info("Loading changelogs from: %s", args[0])
    res = get_changelogs_from_otherxml(args[0])

    LOG.info("changelogs of %d RPMs were found" % len(res))
    data = dict(date=datetime.datetime.now().strftime("%Y-%m-%d"), data=res)
    out = sys.stdout if options.output is None else options.output
    anyconfig.dump(data, out, ac_parser="json")


if __name__ == "__main__":
    main()

# vim:sw=4:ts=4:et:
