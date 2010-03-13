#! /usr/bin/python
#
# rpm2json.py - Dump json data from binary rpm file
#
# Copyright (C) 2010 Satoru SATOH <satoru.satoh@gmail.com>
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
# SEE ALSO: http://docs.fedoraproject.org/drafts/rpm-guide-en/ch-rpm-programming-python.html
#

import optparse
import os
import rpm
import simplejson
import sys
import textwrap

try:
    import cjson
    def json_dumps(s):
        return cjson.encode(s)

except ImportError:
    def json_dumps(s):
        return simplejson.dumps(s, ensure_ascii=False)



def json_dumps_H(s):
    return simplejson.dumps(s, ensure_ascii=False, indent=2)


def rpmheader(rpmfile):
    """Read rpm header from a rpm file.

    @see http://docs.fedoraproject.org/drafts/rpm-guide-en/ch16s04.html
    """
    ts = rpm.TransactionSet()
    ts.setVSFlags(rpm._RPMVSF_NOSIGNATURES)
    fd = os.open(rpmfile, os.O_RDONLY)
    h = ts.hdrFromFdno(fd)
    os.close(fd)

    return h


def rpmtags():
    return [tag.replace('RPMTAG_','').lower() for tag in dir(rpm) if tag.startswith('RPMTAG_')]


def rpm_tag_values(rpmfile, tags):
    h = rpmheader(rpmfile)
    p = dict()

    for tag in tags:
        try:
            p[tag] = h[tag]
        except Exception, e:
            print str(e)

    return p


def show_all_tags():
    try:
        width = int(os.environ['COLUMNS'])
    except (KeyError, ValueError):
        width = 80

    width -= 2
    tags_text = "Tags: " + ", ".join(rpmtags())

    for l in textwrap.wrap(tags_text, width, subsequent_indent='  '):
        print l


def main():
    output = sys.stdout
    tags = ['name','version','release','arch','epoch','sourcerpm']

    p = optparse.OptionParser("""%prog [OPTION ...] RPM_0 [RPM_1 ...]

Examples:
  %prog Server/cups-1.3.7-11.el5.i386.rpm 
  %prog -T name,sourcerpm,rpmversion Server/*openjdk*.rpm
  %prog --show-tags"""
    )
    p.add_option('', '--show-tags', default=False, action='store_true',
        help='Show all possible rpm tags')
    p.add_option('-o', '--output', help='output filename [stdout]')
    p.add_option('-T', '--tags', default=",".join(tags),
        help='Comma separated rpm tag list to get. [%default]')
    p.add_option('-H', '--human-readable', default=False, action='store_true',
        help='Output formatted results.')
    (options, args) = p.parse_args()

    if options.show_tags:
        show_all_tags()
        sys.exit(0)

    if len(args) < 1:
        p.print_usage()
        sys.exit(1)

    if options.output:
        output = open(options.output, 'w')

    if options.tags:
        tags = options.tags.split(',')

    rpms = args
    rpmdata = []

    for r in rpms:
        vs = rpm_tag_values(r, tags)
        if vs:
            rpmdata.append(vs)

    if options.human_readable:
        x = json_dumps_H(rpmdata)
    else:
        x = json_dumps(rpmdata)

    print >> output, x


if __name__ == '__main__':
    main()


# vim: set sw=4 ts=4 expandtab:
