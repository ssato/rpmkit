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
import optparse
import os.path


_DEFAULTS = dict(path=None, workdir=None, repos=[],
                 backend=RUM.DEFAULT_BACKEND, keywords=RUM.RHBA_KEYWORDS,
                 refdir=None, verbose=False)
_USAGE = """\
%prog [Options...] RPMDB_ROOT

    where RPMDB_ROOT = RPM DB root having var/lib/rpm from the target host"""


def option_parser(defaults=_DEFAULTS, usage=_USAGE, backends=RUM.BACKENDS):
    p = optparse.OptionParser(usage)
    p.set_defaults(**defaults)

    p.add_option("-w", "--workdir", help="Working dir [%default]")
    p.add_option("", "--repo", dest="repos", action="append",
                 help="Yum repo to fetch errata info, e.g. "
                      "'rhel-x86_64-server-6'. It can be given multiple times "
                      "to specify multiple yum repos. Note: Any other repos "
                      "are disabled if this option was set.")
    p.add_option("-B", "--backend", choices=backends.keys(),
                 help="Specify backend to get updates and errata. Choices: "
                      "%s [%%default]" % ', '.join(backends.keys()))
    p.add_option("-k", "--keyword", dest="keywords", action="append",
                 help="Keyword to select more 'important' bug errata. "
                      "You can specify this multiple times. "
                      "[%s]" % ', '.join(defaults["keywords"]))
    p.add_option("-R", "--refdir",
                 help="Output 'delta' result compared to the data in "
                      "specified dir")
    p.add_option("-v", "--verbose", action="store_true", help="Verbose mode")

    return p


def main():
    p = option_parser()
    (options, args) = p.parse_args()

    root = args[0] if args else raw_input("Root of RPM DB files > ")
    assert os.path.exists(root), "Not found RPM DB Root: %s" % root

    RUM.main(root, options.workdir, repos=options.repos,
             keywords=options.keywords, refdir=options.refdir,
             verbose=options.verbose)


if __name__ == '__main__':
    main()

# vim:sw=4:ts=4:et:
