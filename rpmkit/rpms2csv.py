#
# Author: Satoru SATOH <ssato@redhat.com>
# License: MIT
#
import rpmkit.rpm2json as RJ

import glob
import operator
import optparse
import os
import os.path
import rpm
import sys


RPM_TAGS = ['name', 'version', 'release', 'arch', 'epoch', 'summary']


def rpmfile2metadata(rpmfile, tags=RPM_TAGS):
    return RJ.rpm_tag_values(rpmfile, tags)


def rpms_g(rpmsdir, func=rpmfile2metadata):
    """
    :param subdir:
    """
    for f in glob.glob(os.path.join(rpmsdir, "*.rpm")):
        yield func(f)


def main(args):
    output = sys.stdout

    defaults = dict(
        output=output,
        rpmsdir=os.curdir,
        tags=",".join(RPM_TAGS),
    )

    p = optparse.OptionParser("%prog [OPTION ...] OUTPUT.CSV")
    p.set_defaults(**defaults)

    p.add_option("-d", "--rpmsdir", help="Specify dir to find rpms [%default]")
    p.add_option("-T", "--tags",
        help="Specify rpm tags separated with command ',' [%default]"
    )

    (options, args) = p.parse_args(args[1:])

    if len(args) < 1:
        p.print_usage()
        sys.exit(1)

    with open(args[0], 'w') as output:
        tags = options.tags.split(',')

        # header:
        print >> output, ", ".join(s.title() for s in tags)
        format = "%(" + ")s,%(".join(tags) + ")s"

        rpms = sorted(
            rpms_g(options.rpmsdir),
            key=operator.itemgetter("name"),
        )

        for x in rpms:
            print >> output, format % x


if __name__ == '__main__':
    main(sys.argv)


# vim:sw=4:ts=4:et:
