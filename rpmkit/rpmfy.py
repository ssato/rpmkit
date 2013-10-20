#! /usr/bin/python
#
# Quick hacked script to generate files to make autotoolized source
# distribution of files under given dir.
#
# Copyright (C) 2013 Satoru SATOH <satoru.satoh @ gmail.com>
# License: MIT
#
from logging import INFO, DEBUG

import datetime
import itertools
import locale
import logging
import optparse
import os.path
import os
import subprocess
import sys

# Make this script works w/o rpmkit.environ:
try:
    from rpmkit.environ import get_fullname, get_email
except ImportError:
    get_fullname = lambda: "RPMfy"
    get_email = lambda: "rpmfy@localhost"


_MAKEFILE_AM_HEADER_TMPL = """\
EXTRA_DIST = %(name)s.spec rpm.mk
include $(abs_top_srcdir)/rpm.mk
"""

_MAKEFILE_AM_DISTDATA_TMPL = """pkgdata%(i)ddir = %(dir)s
dist_pkgdata%(i)d_DATA = \\
%(fs)s
"""

_CONFIGURE_AC_TMPL = """\
AC_INIT([%(name)s],[%(version)s])
AM_INIT_AUTOMAKE([dist-xz foreign subdir-objects tar-pax])

m4_ifdef([AM_SILENT_RULES],[AM_SILENT_RULES([yes])])

AC_CONFIG_FILES([Makefile])
AC_OUTPUT
"""

_RPMSPEC_TMPL = """\
Name:           %(name)s
Version:        %(version)s
Release:        1%%{?dist}
Summary:        Packaged data of %%{name}
License:        Commercial
URL:            http://example.com
Source0:        %%{name}-%%{version}.tar.xz

%%description
Packaged data of %%{name}

%%prep
%%setup -q

%%build
%%configure
make %%{?_smp_mflags}

%%install
rm -rf $RPM_BUILD_ROOT
%%make_install

find $RPM_BUILD_ROOT -type f | sed "s,^$RPM_BUILD_ROOT,,g" > files.list

%%files -f files.list
#%%doc

%%changelog
* %(timestamp)s %(packager)s <%(email)s> - %(version)s-1
- Initial (static) packaging
"""

_RPMMK_TMPL = """\
abs_builddir    ?= $(shell pwd)

rpmdir = $(abs_builddir)/rpm
rpmdirs = $(addprefix $(rpmdir)/,RPMS BUILD BUILDROOT)

rpmbuild = rpmbuild \
--quiet \
--define "_topdir $(rpmdir)" \
--define "_srcrpmdir $(abs_builddir)" \
--define "_sourcedir $(abs_builddir)" \
--define "_buildroot $(rpmdir)/BUILDROOT" \
$(NULL)

$(rpmdirs):
\t$(AM_V_at)$(MKDIR_P) $@

rpm srpm: $(PACKAGE).spec dist $(rpmdirs)

rpm:
\t$(AM_V_GEN)$(rpmbuild) -bb $<
\t$(AM_V_at)mv $(rpmdir)/RPMS/*/*.rpm $(abs_builddir)

srpm:
\t$(AM_V_GEN)$(rpmbuild) -bs $<

.PHONY: rpm srpm
"""


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


def timestamp(dtobj=datetime.datetime.now()):
    """
    >>> dtobj = datetime.datetime(2013, 10, 20, 12, 11, 59, 345135)
    >>> timestamp(dtobj)
    'Sun Oct 20 2013'
    """
    locale.setlocale(locale.LC_TIME, "C")
    return dtobj.strftime("%a %b %_d %Y")


def mk_Makefile_am_distdata_snippets_g(topdir, name, destdir='',
                                       header_tmpl=_MAKEFILE_AM_HEADER_TMPL,
                                       tmpl=_MAKEFILE_AM_DISTDATA_TMPL):
    """
    List file paths under ``topdir`` and make distdata targets in Makefile.am
    for each subdirs one by one.

    :param topdir: Path to the top dir to search file paths.
    :param name: Distribution (package) name
    :param destdir: DESTDIR to strip from the front of each file paths
    :param tmpl: Template string for Makefile.am distdata snippets

    :yield: distdata snippet in Makefile.am
    """
    assert os.path.exists(topdir), "Not found: " + topdir
    assert os.path.isdir(topdir), "Not a dir: " + topdir

    ig = itertools.count()

    yield header_tmpl % dict(name=name, )

    for root, dirs, files in os.walk(topdir):
        if root == topdir:
            continue  # Skip files in topdir.

        logging.debug("%d files in the dir %s" % (len(files), root))
        reldir = os.path.relpath(root, topdir)
        fs = [os.path.relpath(os.path.join(root, f), topdir) for f
              in files]

        if not fs:
            logging.info("No files in this dir. Skipped: " + root)
            continue

        if destdir:
            reldir = reldir.replace(destdir, '', 1)

        logging.debug("reldir=" + reldir)

        yield tmpl % dict(i=ig.next(), dir=to_abspath(reldir),
                          fs=" \\\n".join(f for f in fs))


def gen_Makefile_am(topdir, name, destdir=''):
    """
    List file paths under ``topdir`` and make Makefile.am.

    :param topdir: Path to the top dir to search file paths.
    :param name: Distribution (package) name
    :param destdir: DESTDIR to strip from the front of each file paths
    """
    return '\n'.join(mk_Makefile_am_distdata_snippets_g(topdir, name, destdir))


def gen_configure_ac(name, version, tmpl=_CONFIGURE_AC_TMPL):
    """
    :param name: Distribution (package) name
    :param version: Version
    :param tmpl: Template string for configure.ac
    """
    return tmpl % dict(name=name, version=version)


def gen_rpmspec(topdir, name, version, packager=None, email=None,
                tmpl=_RPMSPEC_TMPL):
    """
    """
    if packager is None:
        packager = get_fullname()

    if email is None:
        email = get_email()

    return tmpl % dict(name=name, version=version, timestamp=timestamp(),
                       packager=packager, email=email)


def make_dist(workdir):
    subprocess.check_call("autoreconf -vfi", cwd=workdir, shell=True)
    subprocess.check_call("./configure && make dist", cwd=workdir, shell=True)


def tweak_topdir(topdir, workdir=None):
    if workdir is not None:
        if not os.path.exists(workdir):
            os.makedirs(workdir)

        subprocess.check_call("cp -a %s/* %s" % (topdir, workdir),
                              shell=True)
        topdir = workdir

    return topdir


def gen_autotools_files(topdir, name, version, destdir='', packager=None,
                        email=None, rpmspec_tmpl=None, rpmmk_tmpl=_RPMMK_TMPL,
                        makedist=False, rpmspec_tmpl_s=_RPMSPEC_TMPL):
    """
    :param topdir: Path to the top dir to package files under
    :param name: Package name
    :param version: Package version
    :param destdir: DESTDIR to strip from the front of each file paths
    :param packager: Packager's fullname
    :param email: Packager's email address
    :param rpmspec_tmpl: Template string of the RPM SPEC file to generate
    """
    if rpmspec_tmpl is None:
        rpmspec_tmpl = rpmspec_tmpl_s
    else:
        rpmspec_tmpl = open(rpmspec_tmpl).read()

    logging.info("Generating Makefile.am in " + topdir)
    c = gen_Makefile_am(topdir, name, destdir)
    open(os.path.join(topdir, "Makefile.am"), 'w').write(c)

    logging.info("Generating configure.ac in " + topdir)
    c = gen_configure_ac(name, version)
    open(os.path.join(topdir, "configure.ac"), 'w').write(c)

    logging.info("Generating the RPM SPEC and aux files in " + topdir)
    c = gen_rpmspec(topdir, name, version, packager, email, rpmspec_tmpl)
    open(os.path.join(topdir, "%s.spec" % name), 'w').write(c)
    open(os.path.join(topdir, "rpm.mk"), 'w').write(rpmmk_tmpl)

    if makedist:
        make_dist(topdir)


_DEFAULTS = dict(destdir='', workdir=None, name=None, version="0.0.1",
                 packager=None, email=None, rpmspec_tmpl=None,
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
    p.add_option("-P", "--packager",
                 help="Specify packager's fullname [%default]")
    p.add_option("-E", "--email",
                 help="Specify packager's email address [%default]")
    p.add_option("-T", "--rpmspec-tmpl",
                 help="Specify the path to alternative RPM SPEC template file")
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

    topdir = tweak_topdir(args[0], options.workdir)

    if not options.name:
        options.name = os.path.basename(topdir)

    gen_autotools_files(topdir, options.name, options.version, options.destdir,
                        options.packager, options.email, options.rpmspec_tmpl,
                        makedist=options.makedist)


if __name__ == '__main__':
    main()

# vim:sw=4:ts=4:et:
