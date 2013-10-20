#! /usr/bin/python
#
# Quick hacked script to generate files to make autotoolized source
# distribution of files under given dir.
#
# Copyright (C) 2013 Satoru SATOH <satoru.satoh @ gmail.com>
# License: MIT
#
from logging import INFO, DEBUG

import itertools
import logging
import optparse
import os.path
import os
import subprocess
import sys


def to_abspath(path):
    """
    >>> to_abspath("/a/b/c")
    '/a/b/c'
    >>> to_abspath("a/b/c")
    '/a/b/c'
    """
    if path.startswith(os.path.sep):
        return path
    else:
        return os.path.sep + path


def rstrip_seps(path, sep=os.path.sep):
    """
    >>> rstrip_seps("/a/b/c/d")
    '/a/b/c/d'
    >>> rstrip_seps("/a/b/c/d/")
    '/a/b/c/d'
    >>> rstrip_seps("/a/b/c/d///////")
    '/a/b/c/d'
    """
    while True:
        if len(path) == 1:
            return path
        else:
            if path[-1] == sep:
                path = path[:-1]
            else:
                return path


_MAKEFILE_AM_DISTDATA_TMPL = """pkgdata%(i)ddir = %(dir)s
dist_pkgdata%(i)d_DATA = \\
%(fs)s
"""


def mk_Makefile_am_distdata_snippets_g(topdir, destdir='',
                                       tmpl=_MAKEFILE_AM_DISTDATA_TMPL):
    """
    List file paths under ``topdir`` and make distdata targets in Makefile.am
    for each subdirs one by one.

    :param topdir: Path to the top dir to search file paths.
    :param destdir: DESTDIR to strip from the front of each file paths
    :param tmpl: Template string for Makefile.am distdata snippets

    :yield: distdata snippet in Makefile.am
    """
    assert os.path.exists(topdir), "Not found: " + topdir
    assert os.path.isdir(topdir), "Not a dir: " + topdir

    ig = itertools.count()

    for root, dirs, files in os.walk(topdir):
        if root == topdir:
            continue  # Skip files in topdir.

        logging.debug("%d files in the dir %s" % (len(files), root))
        reldir = os.path.relpath(root, topdir)
        fs = [os.path.relpath(os.path.join(root, f), topdir) for f
              in files]

        if not fs:
            continue

        if destdir:
            reldir = reldir.replace(destdir, '', 1)

        logging.debug("reldir=" + reldir)

        yield tmpl % dict(i=ig.next(), dir=to_abspath(reldir),
                          fs=" \\\n".join(f for f in fs))


def gen_Makefile_am(topdir, destdir=''):
    """
    List file paths under ``topdir`` and make Makefile.am.

    :param topdir: Path to the top dir to search file paths.
    :param destdir: DESTDIR to strip from the front of each file paths
    """
    return '\n'.join(mk_Makefile_am_distdata_snippets_g(topdir, destdir))


_CONFIGURE_AC_TMPL = """\
AC_INIT([%(name)s],[%(version)s])
AM_INIT_AUTOMAKE([dist-xz foreign subdir-objects tar-pax])

m4_ifdef([AM_SILENT_RULES],[AM_SILENT_RULES([yes])])

AC_CONFIG_FILES([Makefile])
AC_OUTPUT
"""


def gen_configure_ac(name, version, tmpl=_CONFIGURE_AC_TMPL):
    """
    :param name: Distribution (package) name
    :param version: Version
    :param tmpl: Template string for configure.ac
    """
    return tmpl % dict(name=name, version=version)


def make_dist(workdir):
    subprocess.check_call("autoreconf -vfi", cwd=workdir, shell=True)
    subprocess.check_call("./configure && make dist", cwd=workdir, shell=True)


def gen_autotools_files(topdir, name, version, destdir='', workdir=None,
                        makedist=False):
    """
    """
    if workdir is not None:
        if not os.path.exists(workdir):
            os.makedirs(workdir)

        subprocess.check_call("cp -a %s/* %s" % (topdir, workdir),
                              shell=True)
        topdir = workdir

    logging.info("Generating Makefile.am in " + topdir)
    c = gen_Makefile_am(topdir, destdir)
    open(os.path.join(topdir, "Makefile.am"), 'w').write(c)

    logging.info("Generating configure.ac in " + topdir)
    c = gen_configure_ac(name, version)
    open(os.path.join(topdir, "configure.ac"), 'w').write(c)

    if makedist:
        make_dist(topdir)


_DEFAULTS = dict(destdir='', workdir=None, name=None, version="0.0.1",
                 makedist=False)


def option_parser(defaults=_DEFAULTS):
    p = optparse.OptionParser("%prog [OPTION ...] TARGETS_TOPDIR")
    p.set_defaults(**defaults)

    p.add_option("-n", "--name",
                 help="Distribution (package) name. Given target topdir "
                      "name will be used by default.")
    p.add_option("", "--version",
                 help="Disribution (package) version [%default]")
    p.add_option("-d", "--destdir",
                 help="DESTDIR to strip from the front of each "
                      "file paths [%default]")
    p.add_option("-w", "--workdir",
                 help="Specify working dir if you do not want to "
                      "generate autotools files in given target topdir. "
                      "All of the files under given topdir will be copied "
                      "into this directory before making src distribution.")
    p.add_option("", "--makedist", action="store_true",
                 help="Make src distribution")
    p.add_option("-v", "--verbose", action="store_true", help="Verbose mode")
    return p


def main(argv=sys.argv):
    p = option_parser()
    (options, args) = p.parse_args(argv[1:])

    if not args:
        p.print_usage()
        sys.exit(0)

    logging.basicConfig(level=(DEBUG if options.verbose else INFO),
                        format="%(asctime)s [%(levelname)s] %(message)s")
    topdir = args[0]

    if not options.name:
        options.name = os.path.basename(topdir)

    gen_autotools_files(topdir, options.name, options.version, options.destdir,
                        options.workdir, options.makedist)

if __name__ == '__main__':
    main()

# vim:sw=4:ts=4:et:
