#
# Create updateinfo.xml w/ using some RHN APIs.
#
# Copyright (C) 2013 Satoru SATOH <ssato redhat.com>
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
import rpmkit.swapi as RS

import codecs
import gzip
import logging
import optparse
import os
import os.path
import re
import sys


UPDATEINFO_XML = """<?xml version="1.0" encoding="UTF-8"?>
<updates>%s</updates>"""

# Examples:
#
# <update from="security@redhat.com" status="final" type="bugfix" version="4">
#   <id>RHBA-2010:0836</id>
#   <title>NetworkManager bug fix and enhancement update</title>
#   <issued date="2010-11-10 00:00:00"/>
#   <updated date="2010-11-10 00:00:00"/>
#   <rights>Copyright 2010 Red Hat Inc</rights>
#   <summary>Updated NetworkManager packages that fix a bug and add various
#     enhancements are now available for Red Hat Enterprise Linux 6.
#   </summary>
#   <description>...</description>
#   <solution>...</solution>
#   <references>
#     <reference href="https://rhn.redhat.com/errata/RHBA-2010-0836.html"
#                type="self" title="RHBA-2010:0836"/>
#     <reference href="https://bugzilla.redhat.com/bugzilla/show_bug.cgi?id=638598"
#                id="638598" type="bugzilla" title="Enable Networking and ..."/>
#   </references>
#   <pkglist>
#     <collection short="rhel-x86_64-server-6">
#       <name>Red Hat Enterprise Linux Server (v. 6 for 64-bit x86_64)</name>
#       <package name="NetworkManager-glib" version="0.8.1" release="5.el6_0.1" epoch="1" arch="i686" src="NetworkManager-0.8.1-5.el6_0.1.src.rpm">
#         <filename>NetworkManager-glib-0.8.1-5.el6_0.1.i686.rpm</filename>
#         <sum type="sha256">4f9a37a475a7ef0cdeea963d30c84298a99cb8640a5a7bb9ee22d39c0f870177</sum>
#       </package>
#       <package name="NetworkManager" version="0.8.1" release="5.el6_0.1" epoch="1" arch="x86_64" src="NetworkManager-0.8.1-5.el6_0.1.src.rpm">
#         <filename>NetworkManager-0.8.1-5.el6_0.1.x86_64.rpm</filename>
#         <sum type="sha256">5cf5374cecd88b4ac3eabc20babfc0e25ee049f21dc8ead5e1aa128112f7c0c3</sum>
#       </package>
#       <package name="NetworkManager-glib" version="0.8.1" release="5.el6_0.1" epoch="1" arch="x86_64" src="NetworkManager-0.8.1-5.el6_0.1.src.rpm">
#         <filename>NetworkManager-glib-0.8.1-5.el6_0.1.x86_64.rpm</filename>
#         <sum type="sha256">8a4d9e10521857662926f31bce305e4a3f452cd35f6c7cee2d4f38fe6e55f54b</sum>
#       </package>
#       <package name="NetworkManager-gnome" version="0.8.1" release="5.el6_0.1" epoch="1" arch="x86_64" src="NetworkManager-0.8.1-5.el6_0.1.src.rpm">
#         <filename>NetworkManager-gnome-0.8.1-5.el6_0.1.x86_64.rpm</filename>
#         <sum type="sha256">444c6a4078ec0f6ef41f7890e87cdc21b752209738b72698c4a03120e7ad900a</sum>
#       </package>
#     </collection>
#   </pkglist>
# </update>
#
# SEE ALSO: java/code/src/com/redhat/rhn/taskomatic/task/repomd/UpdateInfoWriter.java in spacewalk,
#   https://git.fedorahosted.org/cgit/spacewalk.git/tree/java/code/src/com/redhat/rhn/taskomatic/task/repomd/UpdateInfoWriter.java
# 
UPDATEINFO_XML_UPDATE = """\
<update from="%(from)s" status="%(status)s" type="%(type)s" version="%(version)s">
  <id>%(advisory_name)s</id>
  <title>%(synopsis)s</title>
  <issued date="%(issue_date)s"/>
  <updated date="%(update_date)s"/>
  <rights>Copyright 2001 - 2014 Red Hat Inc</rights>
  <summary>%(synopsis)s</summary>
  <description>%(description)s</description>
  <solution>%(solution)s</solution>
  <references>%(references)s</references>
  <pkglist>
    <collection short="%(channel_label)s">
      <name>%(channel_name)s</name>
      %(packages)s
    </collection>
  </pkglist>
</update>
"""

# epoch: unsigned int >= 0 (0 means None)
UPDATEINFO_XML_PACKAGE = """\
<package name="%(name)s" version="%(version)s" release="%(release)s" epoch="%(epoch)s" arch="%(arch)s" src="%(sourcerpm)s">
  <filename>%(file)s</filename>
  <sum type="%(checksum_type)s">%(checksum)s</sum>
</package>
"""


class StrictTypeError(TypeError):
    pass


def swapicall(cmd):
    """
    swapi (SpaceWalk API library) main() wrapper.

    :param cmd: command args :: [str]
    """
    return RS.main(cmd)[0]


# TODO: Which is better ?  _advisory_type_to_errata_type or _advisory_to_errata_type
def _advisory_type_to_errata_type(atype):
    """
    :param atype: Advisory type = (Security | Bug Fix | Product Enhancement)
        Advisory

    >>> _advisory_type_to_errata_type("Bug Fix Advisory")
    'bugfix'
    >>> _advisory_type_to_errata_type("Product Enhancement Advisory")
    'enhancement'
    >>> _advisory_type_to_errata_type("Security Advisory")
    'security'
    """
    assert atype.endswith(" Advisory"), "Wrong advisory_type: " + str(atype)
    return ''.join(atype.split()[:-1]).lower()


_ADV_ERRATA_MAP = dict(S="security", B="bugfix", E="enhancement")


def _advisory_to_errata_type(advisory, aemap=_ADV_ERRATA_MAP):
    """
    :param advisory: Advisory name, e.g. RHEA-2011:0141
    """
    try:
        return aemap[re.match(r"^RH(S|B|E)A-\d{4}:\d{4}$",
                              advisory).groups()[0]]
    except Exception as e:
        logging.error("exc=" + str(e))
        raise StrictTypeError("Wrong advisory name: " + str(advisory))


def dict_to_attrs(d):
    """
    >>> dict(a=1, b="ccc", d="Hello, world!")
    'a="1" b="ccc" d="Hello, world!"'
    """
    return ' '.join("%s=%s" % (k, str(v)) for k, v in d.iteritems())


def get_references_g(advisory, cves=[], references=[]):
    """
    :param advisory: Advisory name, e.g. RHEA-2011:0141
    :param cves: List of relevant CVEs which is only available in RHSAs
    :param references:  List of other type references such like 
        'http://www.redhat.com/security/updates/classification/#important' in
        RHSAs.
    """
    url = "https://rhn.redhat.com/errata/%s.html" % advisory.replace(':', '-')
    yield dict(href=url, type="self", title=advisory)

    bzs = swapicall(["-A", advisory, "errata.bugzillaFixes"])[0]
    for bzid, bztitle in bzs.iteritems():
        url = "https://bugzilla.redhat.com/bugzilla/show_bug.cgi?id=%s" % bzid
        yield dict(href=url, type="bugzilla", title=bztitle)

    for cve in cves:
        url = "https://www.redhat.com/security/data/cve/%s.html" % cve
        yield dict(href=url, id=cve, type="cve", title=cve)

    for ref in references:
        yield dict(href=ref, type="other")


def make_references_g(advisory, cves=[], references=[]):
    for d in get_references_g(advisory, cves, references):
        yield "<references %s />" % dict_to_attrs(d)


def make_relevant_packages_g(advisory, tmpl=UPDATEINFO_XML_PACKAGE):
    """
    :param advisory: Advisory name, e.g. RHEA-2011:0141
    """
    for p in swapicall(["-A", advisory, "errata.listPackages"]):
        p["sourcerpm"] = "Not_resolved (TODO)"
        p["arch"] = p["arch_label"]

        yield tmpl % p


def list_errata_g(channel):
    """
    :param channel: Software channel label, e.g. rhel-x86_64-as-4.
    :yield: A dict of errata information needed to make up udpateinfo

    channel.software.listErrata ::
        (channel :: str) -> { advisory_name, e.g. RHSA-2007:0107, 
                              advisory_type, e.g. Security Advisory, 
                              issue_date, e.g. 2007-03-13 13:00:00,
                              advisory, e.g. RHSA-2007:0107, 
                              last_modified_date, e.g. 2007-03-15 00:06:52, 
                              synopsis, e.g. "Important: gnupg security update", 
                              date, e.g. "2007-03-13 13:00:00", 
                              update_date, e.g. "2007-03-14 13:00:00", 
                              id, e.g. 1393, 
                              advisory_synopsis, ...}
    """
    for errata in swapicall(["-A", channel, "channel.software.listErrata"]):
        if not isinstance(errata, dict) or not errata.get("advisory", False):
            logging.warn("Wrong data: " + str(errata))

        advisory = errata["advisory"]
        logging.info("Got errata: " + advisory)

        errata["from"] = "security@redhat.com"
        errata["status"] = "final"
        errata["type"] = _advisory_to_errata_type(advisory)

        # TODO: Maybe 'release' in results of errata.getDetails is this.
        errata["version"] = "1"

        # TODO: Get channel's name.
        errata["channel_label"] = errata["channel_name"] = channel

        ed = swapicall(["-A", advisory, "errata.getDetails"])[0]
        for k in ("synopsis", "description", "solution"):
            errata[k] = ed[k]

        if advisory.startswith("RHSA"):
            errata["cves"] = swapicall(["-A", advisory, "errata.listCves"])

        yield errata


def make_errata_xml_fragment_g(channel, tmpl=UPDATEINFO_XML_UPDATE):
    """
    :param channel: Software channel label, e.g. rhel-x86_64-as-4.
    """
    for errata in list_errata_g(channel):
        refs_g = make_references_g(errata["advisory"], errata.get("cves", []),
                                   errata.get("references", []))
        pkgs_g = make_relevant_packages_g(errata["advisory"])

        errata["references"] = ''.join(refs_g)
        errata["packages"] = ''.join(pkgs_g)

        yield tmpl % errata


def make_updateinfo_xml(channel, outdir, outname="updateinfo.xml"):
    """
    """
    if not os.path.exists(outdir):
        logging.info("Create output dir: " + outdir)
        os.makedirs(outdir)

    outpath = os.path.join(outdir, outname)

    if outname.endswith(".gz"):
        (opener, opener_args) = (gzip.open, (outpath, "wb"))
    else:
        (opener, opener_args) = (codecs.open, (outpath, 'w', "utf-8"))

    logging.info("Retrieving and write data to "
                 "updateinfo.xml for " + channel)
    with opener(*opener_args) as out:
        for xml_fragment in make_errata_xml_fragment_g(channel):
            out.write(xml_fragment)


def init_log(level):
    lvl = [logging.DEBUG, logging.INFO, logging.WARN][level]
    logging.basicConfig(format="[%(levelname)s] %(message)s", level=lvl)


def option_parser():
    p = optparse.OptionParser("%prog [OPTION ...] SW_CHANNEL_LABEL")

    defaults = dict(outdir=None, outname="updateinfo.xml", verbose=1)
    p.set_defaults(**defaults)

    p.add_option("-O", "--outdir", help="Specify output dir [%default]")
    p.add_option("-o", "--outname", help="Specify output filename [%default]")
    p.add_option("-v", "--verbose", action="store_const", const=0,
                 dest="verbose", help="Verbose mode")
    p.add_option("-q", "--quiet", action="store_const", const=2,
                 dest="verbose", help="Quiet mode")
    return p


def main(argv=sys.argv):
    p = option_parser()
    (options, args) = p.parse_args(argv[1:])

    if not args:
        p.print_help()
        print >> sys.stderr, \
            "\nNo channel was specified!\n" + \
            "Try `swapi channel.listSoftwareChannels` to get sw channels"
        sys.exit(0)

    init_log(options.verbose)

    channel = args[0]

    if not options.outdir:
        options.outdir = os.path.join("/tmp", channel)
        logging.info("Set outdir to: " + options.outdir)

    make_updateinfo_xml(channel, options.outdir, options.outname)


if __name__ == '__main__':
    main(sys.argv)

# vim:sw=4:ts=4:et:
