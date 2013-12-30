#
# Copyright (C) 2013 Red Hat, Inc.
# Author: Satoru SATOH <ssato@redhat.com>
# License: GPLv3+
#
from __future__ import print_function
from logging import DEBUG, INFO

import rpmkit.rpmutils as RR
import logging
import optparse
import os.path
import re
import sys
import yaml


def list_rpms_installed_g(rpms, all_rpms):
    """
    :param rpms: The list of RPM names to find from ``all_rpms``.
    :param all_rpms: Installed RPM list
    """
    for r in rpms:
        if r in all_rpms:
            yield r

        elif '*' in r:  # Glob pattern
            for x in all_rpms:
                if re.match(r, x):
                    yield x
        else:
            logging.warn("Given RPM does not look installed: " + r)


def list_removed(rpms, root=None, excludes=[]):
    """
    :param rpms: The list of RPM names to remove (uninstall)
    :param root: Root dir where var/lib/rpm/ exists. '/' will be used if none
        was given.

    :return: a list of RPM names to be removed along with given ``rpms``.
    """
    root = os.path.abspath(root)
    all_rpms = [p["name"] for p in RR.list_installed_rpms(root)]
    rpms = list(list_rpms_installed_g(rpms, all_rpms))

    return RR.compute_removed(rpms, root, excludes=excludes)


_USAGE = """\
%prog [OPTION ...] RPM_NAME_OR_PATTERNS_OR_FILE...

Examples:
  %prog -R ./rhel-6-client-1 libreport abrt
  %prog -R ./rhel-6-client-1 -v /path/to/rpm_list_to_removes.txt
  %prog -R ./rhel-6-client-1 -x ./rpm_list_to_keep.txt NetworkManager'*'"""


def option_parser(usage=_USAGE):
    defaults = dict(verbose=False, root=None, excludes=None, format="simple")
    p = optparse.OptionParser(usage)
    p.set_defaults(**defaults)

    p.add_option("-R", "--root",
                 help="Relative or absolute path to root dir where "
                      "var/lib/rpm exists. [/]")
    p.add_option("-x", "--excludes", 
                 help="Comma separated RPM names to exclude from removes "
                      "or path to file listing such RPM names line by line")
    p.add_option("-f", "--format", choices=("simple", "yaml"),
                 help="Output format selected from %choices [%default]")
    p.add_option("-v", "--verbose", action="store_true", help="Verbose mode")

    return p


def load_list_from_file(filepath):
    """
    :param filepath: List file path
    :return: A list of results in ``filepath``
    """
    return [l.rstrip() for l in open(filepath).readlines()
            if l and not l.startswith('#')]


def is_file(filepath):
    """
    :param filepath: Maybe file path :: str
    """
    return os.path.exists(filepath) and os.path.isfile(filepath)


def main():
    p = option_parser()
    (options, rpms) = p.parse_args()

    logging.getLogger().setLevel(DEBUG if options.verbose else INFO)

    if not rpms:
        p.print_usage()
        sys.exit(1)

    if options.excludes:
        if is_file(options.excludes):
            excludes = load_list_from_file(options.excludes)
        else:
            excludes = options.excludes.split(',')
    else:
        excludes = []

    if len(rpms) == 1 and is_file(rpms[0]):
        rpms = load_list_from_file(rpms[0])

    xs = list_removed(rpms, options.root, excludes)
    if options.format == "yaml":
        yaml.dump(dict(data=dict(removed=xs, ), ), sys.stdout)
    else:
        for x in xs:
            print(x)


if __name__ == "__main__":
    main()

# vim:sw=4:ts=4:et:
