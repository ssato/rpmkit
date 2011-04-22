#! /usr/bin/python
#
# PackageMaker is a successor of xpack.py, a script to build packages from
# existing files on your system.
#
# It will try gathering the info of files, dirs and symlinks in given path
# list, and then:
#
# * arrange src tree contains these files, dirs and symlinks with these
#   relative path kept, and build files (Makefile.am, configure.ac, etc.)
#   to install these.
#
# * generate packaging metadata like RPM SPEC, debian/rules, etc.
#
# * build package such as rpm, src.rpm, deb, etc.
#
#
# NOTE: The permissions of the files might be lost during packaging. If you
# want to ensure these are saved or force set permissions as you wanted,
# specify these explicitly in Makefile.am or rpm spec, etc.
#
#
# Copyright (C) 2011 Satoru SATOH <satoru.satoh @ gmail.com>
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
#
# Requirements:
# * python-cheetah: EPEL should be needed for RHEL (option: it's not needed if
#   you just want to setup src tree)
# * autotools: both autoconf and automake (option: see the above comment)
# * rpm-python
# * pyxattr (option; if you want to try with --use-pyxattr)
#
#
# TODO:
# * correct wrong English expressions
# * more complete tests
# * refactor the process to collect FileInfo objects
# * detect parameters automatically as much as possible:
#   * username, mail, fullname: almost done
#   * url: "git config --get remote.origin.url", etc.
# * sort out command line options
# * plugin system: started working on it
# * --tag option or something like that to support injection of other relationships
#   among packages such as "Obsoletes: xpack" and "Provides: xpack", etc.
# * refactor collect() and around methods and classes
# * find causes of warnings during deb build and fix them all
# * eliminate the strong dependency to rpm and make it runnable on debian based
#   systems (w/o rpm-python)
# * keep permissions of targets in tar archives
# * configuration file support: almost done
# * make it runnable on rhel 5 w/o python-cheetah: almost done
# * test --format=deb = .deb output: almost done
# * handle symlinks and dirs correctly: partially done
#
#
# References (in random order):
# * http://docs.fedoraproject.org/en-US/Fedora_Draft_Documentation/0.1/html/RPM_Guide/ch-creating-rpms.html
# * http://docs.fedoraproject.org/en-US/Fedora_Draft_Documentation/0.1/html/RPM_Guide/ch-rpm-programming-python.html
# * http://cdbs-doc.duckcorp.org
# * https://wiki.duckcorp.org/DebianPackagingTutorial/CDBS
# * http://kitenet.net/~joey/talks/debhelper/debhelper-slides.pdf
# * http://wiki.debian.org/IntroDebianPackaging
# * http://www.debian.org/doc/maint-guide/ch-dother.ja.html
#
#
# Alternatives:
# * buildrpm: http://magnusg.fedorapeople.org/buildrpm/
#
#
# Internal:
#
# Make some pylint errors ignored:
# pylint: disable=E0611
# pylint: disable=E1101
# pylint: disable=E1103
# pylint: disable=W0613
#
# How to run pylint: pylint --rcfile pylintrc pmaker.py
#

from distutils.sysconfig import get_python_lib
from functools import reduce as foldl
from itertools import count, groupby

import ConfigParser as cp
import copy
import datetime
import doctest
import glob
import grp
import inspect
import locale
import logging
import operator
import optparse
import os
import os.path
import cPickle as pickle
import platform
import pwd
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import unittest

import rpm

try:
    from Cheetah.Template import Template
    UPTO = 'build'
except ImportError:
    logging.warn("python-cheetah is not found so that packaging process will go up to only 'setup' step.")

    UPTO = 'setup'

    def Template(*args, **kwargs):
        raise RuntimeError("python-cheetah is missing and cannot proceed any more.")


try:
    import xattr   # pyxattr
    USE_PYXATTR = True

except ImportError:
    # Make up a 'Null-Object' like class mimics xattr module.
    class xattr:
        @staticmethod
        def get_all(*args):
            return ()

        @staticmethod
        def set(*args):
            return ()

        # TODO: Older versions of python do not support decorator expressions
        # and should need the followings:
        #get_all = classmethod(get_all)
        #set = classmethod(set)
    
    USE_PYXATTR = False


try:
    from hashlib import md5, sha1 #, sha256, sha512
except ImportError:  # python < 2.5
    from md5 import md5
    from sha import sha as sha1


try:
    all
except NameError:  # python < 2.5
    def all(xs):
        for x in xs:
            if not x:
                return False
        return True



__title__   = "Xpack"
__version__ = "0.2"
__author__  = "Satoru SATOH"
__email__   = "satoru.satoh@gmail.com"
__website__ = "https://github.com/ssato/rpmkit"


PACKAGE_MAKERS = {}


PKG_COMPRESSORS = {
    # extension: am_option,
    'xz'    : 'no-dist-gzip dist-xz',
    'bz2'   : 'no-dist-gzip dist-bzip2',
    'gz'    : '',
}


TEMPLATES = {
    "configure.ac": """\
AC_INIT([$name],[$version])
AM_INIT_AUTOMAKE([${compressor.am_opt} foreign subdir-objects])

dnl http://www.flameeyes.eu/autotools-mythbuster/automake/silent.html
m4_ifdef([AM_SILENT_RULES],[AM_SILENT_RULES([yes])])

dnl TODO: fix autoconf macros used.
AC_PROG_LN_S
m4_ifdef([AC_PROG_MKDIR_P],[AC_PROG_MKDIR_P],[AC_SUBST([MKDIR_P],[mkdir -p])])
m4_ifdef([AC_PROG_SED],[AC_PROG_SED],[AC_SUBST([SED],[sed])])

dnl TODO: Is it better to generate ${name}.spec from ${name}.spec.in ?
AC_CONFIG_FILES([
Makefile
])

AC_OUTPUT
""",
    "Makefile.am": """\
#import os.path
EXTRA_DIST = MANIFEST MANIFEST.overrides
#if $format == 'rpm'
EXTRA_DIST += ${name}.spec rpm.mk

abs_srcdir  ?= .
include \$(abs_srcdir)/rpm.mk
#end if

#for $dd in $distdata
pkgdata${dd.id}dir = $dd.dir
dist_pkgdata${dd.id}_DATA = \\
#for $f in $dd.files
$f \\
#end for
\$(NULL)

#end for

#for $fi in $fileinfos
#if $fi.type() == 'symlink'
#set $dir = os.path.dirname($fi.target)
#set $bn = os.path.basename($fi.target)
install-data-hook::
\t\$(AM_V_at)test -d \$(DESTDIR)$dir || \$(MKDIR_P) \$(DESTDIR)$dir
\t\$(AM_V_at)cd \$(DESTDIR)$dir && \$(LN_S) $fi.linkto $bn

#else
#if $fi.type() == 'dir'
install-data-hook::
\t\$(AM_V_at)test -d \$(DESTDIR)$fi.target || \$(MKDIR_P) \$(DESTDIR)$fi.target

#end if
#end if
#end for

MKDIR_P ?= mkdir -p
SED ?= sed
""",
    "README": """\
This package provides some backup data collected on
$host by $packager at $date.date.
""",
    "MANIFEST": """\
#for $fi in $fileinfos
#if not $fi.conflicts
$fi.target
#end if
#end for
""",
    "MANIFEST.overrides": """\
#for $fi in $fileinfos
#if $fi.conflicts
$fi.target
#end if
#end for
""",
    "rpm.mk": """\
#raw
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
#end raw
""",
    "package.spec": """\
Name:           $name
Version:        $version
Release:        1%{?dist}
Summary:        $summary
Group:          $group
License:        $license
URL:            $url
Source0:        %{name}-%{version}.tar.${compressor.ext}
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
#if $noarch
BuildArch:      noarch
#end if
#for $req in $requires
Requires:       $req
#end for
#for $fi in $fileinfos
#if $fi.type() == 'symlink'
#set $linkto = $fi.linkto
#BuildRequires:  $linkto
#end if
#end for
#for $rel in $relations
$rel.type:\t$rel.targets
#end for


%description
This package provides some backup data collected on
$host by $packager at $date.date.


#if $conflicts.names
%package        overrides
Summary:        Some more extra data
Group:          $group
Requires:       %{name} = %{version}-%{release}
#for $p in $conflicts.names
Conflicts:      $p
#end for


%description    overrides
Some more extra data will override and replace other packages'.
#end if


%prep
%setup -q


%build
%configure --quiet --enable-silent-rules
make %{?_smp_mflags} V=0


%install
rm -rf \$RPM_BUILD_ROOT
make install DESTDIR=\$RPM_BUILD_ROOT


%clean
rm -rf \$RPM_BUILD_ROOT

$getVar('scriptlets', '')

%files
%defattr(-,root,root,-)
%doc README
%doc MANIFEST
#for $fi in $fileinfos
#if not $fi.conflicts
$fi.rpm_attr()$fi.target
#end if
#end for


#if $conflicts.names
%files          overrides
%defattr(-,root,root,-)
%doc MANIFEST.overrides
#for $fi in $fileinfos
#if $fi.conflicts
$fi.rpm_attr()$fi.target
#end if
#end for
#end if


%changelog
* $date.timestamp ${packager} <${mail}> - ${version}-${release}
- Initial packaging.
""",
    "debian/control": """\
Source: $name
Priority: optional
Maintainer: $packager <$mail>
Build-Depends: debhelper (>= 7.3.8), autotools-dev
Standards-Version: 3.9.0
Homepage: $url

Package: $name
Section: database
#if $noarch
Architecture: all
#else
Architecture: any
#end if
#if $requires
#set $requires_list = ', ' + ', '.join($requires)
#else
#set $requires_list = ''
#end if
Depends: \${shlibs:Depends}, \${misc:Depends}$requires_list
Description: $summary
  $summary
""",
    "debian/rules": """\
#!/usr/bin/make -f
%:
\tdh \$@

override_dh_builddeb:
\tdh_builddeb -- -Zbzip2
""",
    "debian/dirs": """\
#for $fi in $fileinfos
#if $fi.type == 'dir'
#set $dir = $fi.target[1:]
$dir
#end if
#end for
""",
    "debian/compat": """7
""",
    "debian/source/format": """3.0 (native)
""",
    "debian/source/options": """\
# Use bzip2 instead of gzip
compression = "bzip2"
compression-level = 9
""",
    "debian/copyright": """\
This package was debianized by $packager <$mail> on
$date.date.

This package is distributed under $license.
""",
    "debian/changelog": """\
$name ($version) unstable; urgency=low

  * New upstream release

 -- $packager <$mail>  $date.date
""",
}


EXAMPLE_LOGS = [
    """## A. Packaing files in given files list, "files.list":

$ ls
files.list  pmaker.py
$ cat files.list
/etc/auto.*
/etc/modprobe.d/*
/etc/resolv.conf
/etc/yum.repos.d/fedora.repo
#/etc/aliases.db
/etc/system-release
/etc/httpd/conf.d
$ python pmaker.py -n sysdata -w ./0 -q files.list
03:52:50 [WARNING]  /etc/auto.master is owned by autofs and it (sysdata) will conflict with autofs
03:52:50 [WARNING]  /etc/auto.misc is owned by autofs and it (sysdata) will conflict with autofs
03:52:51 [WARNING]  /etc/auto.net is owned by autofs and it (sysdata) will conflict with autofs
03:52:51 [WARNING]  /etc/auto.smb is owned by autofs and it (sysdata) will conflict with autofs
03:52:51 [WARNING]  /etc/httpd/conf.d is owned by httpd and it (sysdata) will conflict with httpd
03:52:51 [WARNING]  /etc/modprobe.d/blacklist-visor.conf is owned by pilot-link and it (sysdata) will conflict with pilot-link
03:52:51 [WARNING]  /etc/modprobe.d/blacklist.conf is owned by hwdata and it (sysdata) will conflict with hwdata
03:52:51 [WARNING]  /etc/modprobe.d/dist-alsa.conf is owned by module-init-tools and it (sysdata) will conflict with module-init-tools
03:52:52 [WARNING]  /etc/modprobe.d/dist-oss.conf is owned by module-init-tools and it (sysdata) will conflict with module-init-tools
03:52:52 [WARNING]  /etc/modprobe.d/dist.conf is owned by module-init-tools and it (sysdata) will conflict with module-init-tools
03:52:52 [WARNING]  /etc/modprobe.d/libmlx4.conf is owned by libmlx4 and it (sysdata) will conflict with libmlx4
03:52:52 [WARNING]  /etc/modprobe.d/poulsbo.conf is owned by xorg-x11-drv-psb and it (sysdata) will conflict with xorg-x11-drv-psb
03:52:52 [WARNING]  /etc/system-release is owned by fedora-release and it (sysdata) will conflict with fedora-release
03:52:53 [WARNING]  /etc/yum.repos.d/fedora.repo is owned by fedora-release and it (sysdata) will conflict with fedora-release
03:52:53 [WARNING] [Errno 1] Operation not permitted: '/tmp/t/0/sysdata-0.1/src/etc/httpd/conf.d'
$ ls
0  files.list  pmaker.py
$ ls 0
sysdata-0.1
$ ls 0/sysdata-0.1/
MANIFEST            README          configure     rpm.mk                         sysdata-0.1.tar.gz                       pmaker-package-filelist.pkl
MANIFEST.overrides  aclocal.m4      configure.ac  src                            sysdata-overrides-0.1-1.fc14.noarch.rpm  pmaker-sbuild.stamp
Makefile            autom4te.cache  install-sh    sysdata-0.1-1.fc14.noarch.rpm  sysdata.spec                             pmaker-setup.stamp
Makefile.am         config.log      missing       sysdata-0.1-1.fc14.src.rpm     pmaker-build.stamp
Makefile.in         config.status   rpm           sysdata-0.1.tar.bz2            pmaker-configure.stamp
$ rpm -qlp 0/sysdata-0.1/sysdata-0.1-1.fc14.noarch.rpm
/etc/resolv.conf
/usr/share/doc/sysdata-0.1
/usr/share/doc/sysdata-0.1/MANIFEST
/usr/share/doc/sysdata-0.1/README
$ rpm -qlp 0/sysdata-0.1/sysdata-overrides-0.1-1.fc14.noarch.rpm
/etc/auto.master
/etc/auto.misc
/etc/auto.net
/etc/auto.smb
/etc/httpd/conf.d
/etc/modprobe.d/blacklist-visor.conf
/etc/modprobe.d/blacklist.conf
/etc/modprobe.d/dist-alsa.conf
/etc/modprobe.d/dist-oss.conf
/etc/modprobe.d/dist.conf
/etc/modprobe.d/libmlx4.conf
/etc/modprobe.d/poulsbo.conf
/etc/system-release
/etc/yum.repos.d/fedora.repo
/usr/share/doc/sysdata-overrides-0.1
/usr/share/doc/sysdata-overrides-0.1/MANIFEST.overrides
$
""",
    """## B. Same as above except that files list is read from stdin and mock
## is not used for building rpms:

$ ls
files.list  pmaker.py
$ cat files.list | python pmaker.py -n sysdata -w ./0 -q --no-mock -
04:03:35 [WARNING]  /etc/auto.master is owned by autofs and it (sysdata) will conflict with autofs
04:03:35 [WARNING]  /etc/auto.misc is owned by autofs and it (sysdata) will conflict with autofs
04:03:35 [WARNING]  /etc/auto.net is owned by autofs and it (sysdata) will conflict with autofs
04:03:36 [WARNING]  /etc/auto.smb is owned by autofs and it (sysdata) will conflict with autofs
04:03:36 [WARNING]  /etc/httpd/conf.d is owned by httpd and it (sysdata) will conflict with httpd
04:03:36 [WARNING]  /etc/modprobe.d/blacklist-visor.conf is owned by pilot-link and it (sysdata) will conflict with pilot-link
04:03:36 [WARNING]  /etc/modprobe.d/blacklist.conf is owned by hwdata and it (sysdata) will conflict with hwdata
04:03:36 [WARNING]  /etc/modprobe.d/dist-alsa.conf is owned by module-init-tools and it (sysdata) will conflict with module-init-tools
04:03:37 [WARNING]  /etc/modprobe.d/dist-oss.conf is owned by module-init-tools and it (sysdata) will conflict with module-init-tools
04:03:37 [WARNING]  /etc/modprobe.d/dist.conf is owned by module-init-tools and it (sysdata) will conflict with module-init-tools
04:03:37 [WARNING]  /etc/modprobe.d/libmlx4.conf is owned by libmlx4 and it (sysdata) will conflict with libmlx4
04:03:37 [WARNING]  /etc/modprobe.d/poulsbo.conf is owned by xorg-x11-drv-psb and it (sysdata) will conflict with xorg-x11-drv-psb
04:03:37 [WARNING]  /etc/system-release is owned by fedora-release and it (sysdata) will conflict with fedora-release
04:03:38 [WARNING]  /etc/yum.repos.d/fedora.repo is owned by fedora-release and it (sysdata) will conflict with fedora-release
04:03:38 [WARNING] [Errno 1] Operation not permitted: '/tmp/t/0/sysdata-0.1/src/etc/httpd/conf.d'
$ ls 0/sysdata-0.1/
MANIFEST            README          configure     rpm.mk                         sysdata-0.1.tar.gz                       pmaker-package-filelist.pkl
MANIFEST.overrides  aclocal.m4      c --silentonfigure.ac  src                            sysdata-overrides-0.1-1.fc14.noarch.rpm  pmaker-sbuild.stamp
Makefile            autom4te.cache  install-sh    sysdata-0.1-1.fc14.noarch.rpm  sysdata.spec                             pmaker-setup.stamp
Makefile.am         config.log      missing       sysdata-0.1-1.fc14.src.rpm     pmaker-build.stamp
Makefile.in         config.status   rpm           sysdata-0.1.tar.bz2            pmaker-configure.stamp
$ rpm -qlp 0/sysdata-0.1/sysdata-0.1-1.fc14.noarch.rpm
/etc/resolv.conf
/usr/share/doc/sysdata-0.1
/usr/share/doc/sysdata-0.1/MANIFEST
/usr/share/doc/sysdata-0.1/README
$ rpm -qlp 0/sysdata-0.1/sysdata-overrides-0.1-1.fc14.noarch.rpm
/etc/auto.master
/etc/auto.misc
/etc/auto.net
/etc/auto.smb
/etc/httpd/conf.d
/etc/modprobe.d/blacklist-visor.conf
/etc/modprobe.d/blacklist.conf
/etc/modprobe.d/dist-alsa.conf
/etc/modprobe.d/dist-oss.conf
/etc/modprobe.d/dist.conf
/etc/modprobe.d/libmlx4.conf
/etc/modprobe.d/poulsbo.conf
/etc/system-release
/etc/yum.repos.d/fedora.repo
/usr/share/doc/sysdata-overrides-0.1
/usr/share/doc/sysdata-overrides-0.1/MANIFEST.overrides
$
""",
    """## C. Packaing single file, /etc/resolve.conf:

$ echo /etc/resolv.conf | python pmaker.py -n resolvconf -w 2 --debug -
04:06:53 [INFO] Setting up src tree in /tmp/t/2/resolvconf-0.1: resolvconf
04:06:55 [DEBUG]  Could load the cache: /home/ssato/.cache/pmaker.rpm.filelist.pkl
04:06:55 [DEBUG]  Creating a directory: /tmp/t/2/resolvconf-0.1
04:06:55 [DEBUG]  Creating a directory: /tmp/t/2/resolvconf-0.1/src
04:06:55 [DEBUG]  Copying from '/etc/resolv.conf' to '/tmp/t/2/resolvconf-0.1/src/etc/resolv.conf'
04:06:55 [DEBUG]  Run: cp -a /etc/resolv.conf /tmp/t/2/resolvconf-0.1/src/etc/resolv.conf [/tmp/t]
04:06:55 [DEBUG]  Run: touch /tmp/t/2/resolvconf-0.1/pmaker-setup.stamp [/tmp/t/2/resolvconf-0.1]
04:06:55 [INFO] Configuring src distribution: resolvconf
04:06:56 [DEBUG]  Run: autoreconf -fi [/tmp/t/2/resolvconf-0.1]
04:07:15 [DEBUG]  Run: touch /tmp/t/2/resolvconf-0.1/pmaker-configure.stamp [/tmp/t/2/resolvconf-0.1]
04:07:15 [INFO] Building src package: resolvconf
04:07:15 [DEBUG]  Run: ./configure [/tmp/t/2/resolvconf-0.1]
04:07:19 [DEBUG]  Run: make dist [/tmp/t/2/resolvconf-0.1]
04:07:20 [DEBUG]  Run: make srpm [/tmp/t/2/resolvconf-0.1]
04:07:21 [DEBUG]  Run: touch /tmp/t/2/resolvconf-0.1/pmaker-sbuild.stamp [/tmp/t/2/resolvconf-0.1]
04:07:21 [INFO] Building bin packages: resolvconf
04:07:21 [DEBUG]  Run: mock --version > /dev/null [/tmp/t/2/resolvconf-0.1]
04:07:24 [DEBUG]  Run: mock -r fedora-14-i386 resolvconf-0.1-1.*.src.rpm [/tmp/t/2/resolvconf-0.1]
04:09:18 [DEBUG]  Run: mv /var/lib/mock/fedora-14-i386/result/*.rpm /tmp/t/2/resolvconf-0.1 [/tmp/t/2/resolvconf-0.1]
04:09:18 [DEBUG]  Run: touch /tmp/t/2/resolvconf-0.1/pmaker-build.stamp [/tmp/t/2/resolvconf-0.1]
04:09:18 [INFO] Successfully created packages in /tmp/t/2/resolvconf-0.1: resolvconf
$ ls 2/resolvconf-0.1/
MANIFEST            Makefile.in     config.log     install-sh                        resolvconf-0.1.tar.bz2  rpm.mk                 pmaker-package-filelist.pkl
MANIFEST.overrides  README          config.status  missing                           resolvconf-0.1.tar.gz   src                    pmaker-sbuild.stamp
Makefile            aclocal.m4      configure      resolvconf-0.1-1.fc14.noarch.rpm  resolvconf.spec         pmaker-build.stamp      pmaker-setup.stamp
Makefile.am         autom4te.cache  configure.ac   resolvconf-0.1-1.fc14.src.rpm     rpm                     pmaker-configure.stamp
$ rpm -qlp 2/resolvconf-0.1/resolvconf-0.1-1.fc14.noarch.rpm
/etc/resolv.conf
/usr/share/doc/resolvconf-0.1
/usr/share/doc/resolvconf-0.1/MANIFEST
/usr/share/doc/resolvconf-0.1/README
$ cat 2/resolvconf-0.1/MANIFEST
/etc/resolv.conf
$ cat 2/resolvconf-0.1/MANIFEST.overrides
$
""",
    """## D. Packaing single file, /tmp/t/srv/isos/rhel-server-5.6-i386-dvd.iso,
## will be installed as srv/isos/rhel-server-5.6-i386-dvd.iso:

$ ls
pmaker.py  srv
$ ls srv/isos/
rhel-server-5.6-i386-dvd.iso
$ echo /tmp/t/srv/isos/rhel-server-5.6-i386-dvd.iso | \\
> python pmaker.py -n rhel-server-5-6-i386-dvd-iso -w ./w \\
> --destdir /tmp/t/ --upto build --no-mock -
...(snip)...
$ ls
pmaker.py  srv  w
$ rpm -qlp w/rhel-server-5-6-i386-dvd-iso-0.1/rhel-server-5-6-i386-dvd-iso-0.1-1.fc14.noarch.rpm
/srv/isos/rhel-server-5.6-i386-dvd.iso
/usr/share/doc/rhel-server-5-6-i386-dvd-iso-0.1
/usr/share/doc/rhel-server-5-6-i386-dvd-iso-0.1/MANIFEST
/usr/share/doc/rhel-server-5-6-i386-dvd-iso-0.1/README
$
""",
    """## E. Packaging itself:

$ python pmaker.py --build-self
04:20:47 [INFO]  executing: echo /tmp/pmaker-build-YaDaOn/usr/bin/pmaker | python pmaker.py -n pmaker --pversion 0.0.99 -w /tmp/pmaker-build-YaDaOn --debug --upto build --no-rpmdb --no-mock --destdir=/tmp/pmaker-build-YaDaOn --ignore-owner -
04:20:49 [INFO] Setting up src tree in /tmp/pmaker-build-YaDaOn/pmaker-0.0.99: pmaker
04:20:49 [DEBUG]  force set uid and gid of /tmp/pmaker-build-YaDaOn/usr/bin/pmaker
04:20:49 [DEBUG]  Rewrote target path of fi from /tmp/pmaker-build-YaDaOn/usr/bin/pmaker to /usr/bin/pmaker
04:20:49 [DEBUG]  Creating a directory: /tmp/pmaker-build-YaDaOn/pmaker-0.0.99
04:20:49 [DEBUG]  Creating a directory: /tmp/pmaker-build-YaDaOn/pmaker-0.0.99/src
04:20:49 [DEBUG]  Copying from '/tmp/pmaker-build-YaDaOn/usr/bin/pmaker' to '/tmp/pmaker-build-YaDaOn/pmaker-0.0.99/src/usr/bin/pmaker'
04:20:49 [DEBUG]  Run: cp -a /tmp/pmaker-build-YaDaOn/usr/bin/pmaker /tmp/pmaker-build-YaDaOn/pmaker-0.0.99/src/usr/bin/pmaker [/tmp/t]
04:20:49 [DEBUG]  Run: touch /tmp/pmaker-build-YaDaOn/pmaker-0.0.99/pmaker-setup.stamp [/tmp/pmaker-build-YaDaOn/pmaker-0.0.99]
04:20:49 [INFO] Configuring src distribution: pmaker
04:20:50 [DEBUG]  Run: autoreconf -fi [/tmp/pmaker-build-YaDaOn/pmaker-0.0.99]
04:21:10 [DEBUG]  Run: touch /tmp/pmaker-build-YaDaOn/pmaker-0.0.99/pmaker-configure.stamp [/tmp/pmaker-build-YaDaOn/pmaker-0.0.99]
04:21:10 [INFO] Building src package: pmaker
04:21:10 [DEBUG]  Run: ./configure [/tmp/pmaker-build-YaDaOn/pmaker-0.0.99]
04:21:13 [DEBUG]  Run: make dist [/tmp/pmaker-build-YaDaOn/pmaker-0.0.99]
04:21:14 [DEBUG]  Run: make srpm [/tmp/pmaker-build-YaDaOn/pmaker-0.0.99]
04:21:16 [DEBUG]  Run: touch /tmp/pmaker-build-YaDaOn/pmaker-0.0.99/pmaker-sbuild.stamp [/tmp/pmaker-build-YaDaOn/pmaker-0.0.99]
04:21:16 [INFO] Building bin packages: pmaker
04:21:16 [DEBUG]  Run: make rpm [/tmp/pmaker-build-YaDaOn/pmaker-0.0.99]
04:21:22 [DEBUG]  Run: touch /tmp/pmaker-build-YaDaOn/pmaker-0.0.99/pmaker-build.stamp [/tmp/pmaker-build-YaDaOn/pmaker-0.0.99]
04:21:22 [INFO] Successfully created packages in /tmp/pmaker-build-YaDaOn/pmaker-0.0.99: pmaker
$ rpm -qlp /tmp/pmaker-build-YaDaOn/pmaker-0.0.99/pmaker-0.0.99-1.fc14.noarch.rpm
/usr/bin/pmaker
/usr/share/doc/pmaker-0.0.99
/usr/share/doc/pmaker-0.0.99/MANIFEST
/usr/share/doc/pmaker-0.0.99/README
$ sed -n "/^%files/,/^$/p" /tmp/pmaker-build-YaDaOn/pmaker-0.0.99/pmaker.spec
%files
%defattr(-,root,root,-)
%doc README
%doc MANIFEST
%attr(755, -, -) /usr/bin/pmaker

$
""",
    """## F. Packaging files under /etc which is not owned by any RPMs:

$ list_files () { dir=$1; sudo find $dir -type f; }                                                                                                            $ is_not_from_rpm () { f=$1; LANG=C sudo rpm -qf $f | grep -q 'is not owned' 2>/dev/null; }
$ (for f in `list_files /etc`; do is_not_from_rpm $f && echo $f; done) \\
>  > etc.not_from_package.files
$ sudo python pmaker.py -n etcdata --pversion $(date +%Y%m%d) \\
> --debug -w etcdata-build etc.not_from_package.files
[sudo] password for ssato:
14:15:03 [DEBUG]  Could load the cache: /root/.cache/pmaker.rpm.filelist.pkl
14:15:09 [INFO] Setting up src tree in /tmp/t/etcdata-build/etcdata-20110217: etcdata
14:15:09 [DEBUG]  Creating a directory: /tmp/t/etcdata-build/etcdata-20110217
...(snip)...
14:16:33 [INFO] Successfully created packages in /tmp/t/etcdata-build/etcdata-20110217: etcdata
$ sudo chown -R ssato.ssato etcdata-build/
$ ls etcdata-build/etcdata-20110217/
MANIFEST            Makefile.am  aclocal.m4      config.status  etcdata-20110217-1.fc14.src.rpm  etcdata.spec  rpm
MANIFEST.overrides  Makefile.in  autom4te.cache  configure      etcdata-20110217.tar.bz2         install-sh    rpm.mk
Makefile            README       config.log      configure.ac   etcdata-20110217.tar.gz          missing       src
$ sudo make -C etcdata-build/etcdata-20110217/ rpm
...(snip)...
$ rpm -qlp etcdata-build/etcdata-20110217/etcdata-20110217-1.fc14.noarch.rpm
/etc/.pwd.lock
/etc/X11/xorg.conf
/etc/X11/xorg.conf.by-psb-config-display
/etc/X11/xorg.conf.d/01-poulsbo.conf
/etc/X11/xorg.conf.livna-config-backup
/etc/aliases.db
/etc/crypttab
/etc/gconf/gconf.xml.defaults/%gconf-tree-af.xml
...(snip)...
/etc/yum.repos.d/fedora-chromium.repo
/usr/share/doc/etcdata-20110217
/usr/share/doc/etcdata-20110217/MANIFEST
/usr/share/doc/etcdata-20110217/README
$
""",
    """## G. Packaging single file on RHEL 5 host and build it on fedora 14 host:

$ ssh builder@rhel-5-6-vm-0
builder@rhel-5-6-vm-0's password:
[builder@rhel-5-6-vm-0 ~]$ cat /etc/redhat-release
Red Hat Enterprise Linux Server release 5.6 (Tikanga)
[builder@rhel-5-6-vm-0 ~]$ curl -s https://github.com/ssato/rpmkit/raw/master/pmaker.py > pmaker
[builder@rhel-5-6-vm-0 ~]$ echo /etc/puppet/manifests/site.pp | \\
> python pmaker -n puppet-manifests -w 0 --debug --upto setup -
WARNING:root:python-cheetah is not found so that packaging process will go up to only 'setup' step.
19:42:48 [INFO] Setting up src tree in /home/builder/0/puppet-manifests-0.1: puppet-manifests
19:42:50 [DEBUG]  Could save the cache: /home/builder/.cache/pmaker.rpm.filelist.pkl
19:42:50 [DEBUG]  Creating a directory: /home/builder/0/puppet-manifests-0.1
19:42:50 [DEBUG]  Creating a directory: /home/builder/0/puppet-manifests-0.1/src
19:42:50 [DEBUG]  Copying from '/etc/puppet/manifests/site.pp' to '/home/builder/0/puppet-manifests-0.1/src/etc/puppet/manifests/site.pp'
19:42:50 [DEBUG]  Run: cp -a /etc/puppet/manifests/site.pp /home/builder/0/puppet-manifests-0.1/src/etc/puppet/manifests/site.pp [/home/builder]
19:42:50 [DEBUG]  Run: touch /home/builder/0/puppet-manifests-0.1/pmaker-setup.stamp [/home/builder/0/puppet-manifests-0.1]
[builder@rhel-5-6-vm-0 ~]$ tar jcvf puppet-manifests-0.1.tar.bz2 0/puppet-manifests-0.1/
0/puppet-manifests-0.1/
0/puppet-manifests-0.1/pmaker-setup.stamp
0/puppet-manifests-0.1/pmaker-package-filelist.pkl
0/puppet-manifests-0.1/src/
0/puppet-manifests-0.1/src/etc/
0/puppet-manifests-0.1/src/etc/puppet/
0/puppet-manifests-0.1/src/etc/puppet/manifests/
0/puppet-manifests-0.1/src/etc/puppet/manifests/site.pp
[builder@rhel-5-6-vm-0 ~]$ ls
0  puppet-manifests-0.1.tar.bz2  rpms  pmaker
[builder@rhel-5-6-vm-0 ~]$ ^D
$ cat /etc/fedora-release
Fedora release 14 (Laughlin)
$ scp builder@rhel-5-6-vm-0:~/puppet-manifests-0.1.tar.bz2 ./
builder@rhel-5-6-vm-0's password:
puppet-manifests-0.1.tar.bz2                 100%  722     0.7KB/s   00:00
$ tar jxvf puppet-manifests-0.1.tar.bz2
0/puppet-manifests-0.1/
0/puppet-manifests-0.1/pmaker-setup.stamp
0/puppet-manifests-0.1/pmaker-package-filelist.pkl
0/puppet-manifests-0.1/src/
0/puppet-manifests-0.1/src/etc/
0/puppet-manifests-0.1/src/etc/puppet/
0/puppet-manifests-0.1/src/etc/puppet/manifests/
0/puppet-manifests-0.1/src/etc/puppet/manifests/site.pp
$ echo /etc/puppet/manifests/site.pp | \\
> python pmaker.py -n puppet-manifests -w 0 --upto build \\
> --dist epel-5-i386 --debug -
05:27:55 [INFO] Setting up src tree in /tmp/w/0/puppet-manifests-0.1: puppet-manifests
05:27:55 [INFO] ...It looks already done. Skip the step: setup
05:27:55 [INFO] Configuring src distribution: puppet-manifests
05:27:55 [DEBUG]  Run: autoreconf -fi [/tmp/w/0/puppet-manifests-0.1]
05:27:58 [DEBUG]  Run: touch /tmp/w/0/puppet-manifests-0.1/pmaker-configure.stamp [/tmp/w/0/puppet-manifests-0.1]
05:27:58 [INFO] Building src package: puppet-manifests
05:27:58 [DEBUG]  Run: ./configure [/tmp/w/0/puppet-manifests-0.1]
05:27:59 [DEBUG]  Run: make dist [/tmp/w/0/puppet-manifests-0.1]
05:28:00 [DEBUG]  Run: make srpm [/tmp/w/0/puppet-manifests-0.1]
05:28:00 [DEBUG]  Run: touch /tmp/w/0/puppet-manifests-0.1/pmaker-sbuild.stamp [/tmp/w/0/puppet-manifests-0.1]
05:28:00 [INFO] Building bin packages: puppet-manifests
05:28:00 [DEBUG]  Run: mock --version > /dev/null [/tmp/w/0/puppet-manifests-0.1]
05:28:00 [DEBUG]  Run: mock -r epel-5-i386 puppet-manifests-0.1-1.*.src.rpm [/tmp/w/0/puppet-manifests-0.1]
05:28:59 [DEBUG]  Run: mv /var/lib/mock/epel-5-i386/result/*.rpm /tmp/w/0/puppet-manifests-0.1 [/tmp/w/0/puppet-manifests-0.1]
05:28:59 [DEBUG]  Run: touch /tmp/w/0/puppet-manifests-0.1/pmaker-build.stamp [/tmp/w/0/puppet-manifests-0.1]
05:28:59 [INFO] Successfully created packages in /tmp/w/0/puppet-manifests-0.1: puppet-manifests
$ rpm -qlp 0/puppet-manifests-0.1/puppet-manifests-0.1-1.^I
puppet-manifests-0.1-1.el5.noarch.rpm  puppet-manifests-0.1-1.el5.src.rpm  puppet-manifests-0.1-1.fc14.src.rpm
$ rpm -qlp 0/puppet-manifests-0.1/puppet-manifests-0.1-1.el5.noarch.rpm
/etc/puppet/manifests/site.pp
/usr/share/doc/puppet-manifests-0.1
/usr/share/doc/puppet-manifests-0.1/MANIFEST
/usr/share/doc/puppet-manifests-0.1/README
$
""",
    """## H. Packaging single file on debian host:

# echo /etc/resolv.conf | ./pmaker.py -n resolvconf -w w --format deb -
13:11:59 [WARNING] get_email: 'module' object has no attribute 'check_output'
13:11:59 [WARNING] get_fullname: 'module' object has no attribute 'check_output'
configure.ac:2: installing `./install-sh'
configure.ac:2: installing `./missing'
dh binary
   dh_testdir
   dh_auto_configure
configure: WARNING: unrecognized options: --disable-maintainer-mode, --disable-dependency-tracking
checking for a BSD-compatible install... /usr/bin/install -c
checking whether build environment is sane... yes
checking for a thread-safe mkdir -p... /bin/mkdir -p
checking for gawk... no
checking for mawk... mawk
checking whether make sets $(MAKE)... yes
checking whether ln -s works... yes
checking for a sed that does not truncate output... /bin/sed
configure: creating ./config.status
config.status: creating Makefile
configure: WARNING: unrecognized options: --disable-maintainer-mode, --disable-dependency-tracking
   dh_auto_build
make[1]: Entering directory `/root/w/resolvconf-0.1'
make[1]: Nothing to be done for `all'.
make[1]: Leaving directory `/root/w/resolvconf-0.1'
   dh_auto_test
   dh_testroot
   dh_prep
   dh_installdirs
   dh_auto_install
make[1]: Entering directory `/root/w/resolvconf-0.1'
make[2]: Entering directory `/root/w/resolvconf-0.1'
make[2]: Nothing to be done for `install-exec-am'.
test -z "/etc" || /bin/mkdir -p "/root/w/resolvconf-0.1/debian/resolvconf/etc"
 /usr/bin/install -c -m 644 src/etc/resolv.conf '/root/w/resolvconf-0.1/debian/resolvconf/etc'
make[2]: Leaving directory `/root/w/resolvconf-0.1'
make[1]: Leaving directory `/root/w/resolvconf-0.1'
   dh_install
   dh_installdocs
   dh_installchangelogs
   dh_installexamples
   dh_installman
   dh_installcatalogs
   dh_installcron
   dh_installdebconf
   dh_installemacsen
   dh_installifupdown
   dh_installinfo
   dh_pysupport
   dh_installinit
   dh_installmenu
   dh_installmime
   dh_installmodules
   dh_installlogcheck
   dh_installlogrotate
   dh_installpam
   dh_installppp
   dh_installudev
   dh_installwm
   dh_installxfonts
   dh_bugfiles
   dh_lintian
   dh_gconf
   dh_icons
   dh_perl
   dh_usrlocal
   dh_link
   dh_compress
   dh_fixperms
   dh_strip
   dh_makeshlibs
   dh_shlibdeps
   dh_installdeb
   dh_gencontrol
dpkg-gencontrol: warning: Depends field of package resolvconf: unknown substitution variable ${shlibs:Depends}
   dh_md5sums
   debian/rules override_dh_builddeb
make[1]: Entering directory `/root/w/resolvconf-0.1'
dh_builddeb -- -Zbzip2
dpkg-deb: building package `resolvconf' in `../resolvconf_0.1_all.deb'.
make[1]: Leaving directory `/root/w/resolvconf-0.1'
#
""",
]


EXAMPLE_RC = """\
#
# This is a configuration file example for pmaker.py
#
# Read the output of `pmaker.py --help` and edit the followings as needed.
#
[DEFAULT]
# working directory in absolute path:
workdir =

# packaging process will go up to this step:
upto    = build

# package format:
format  = rpm

# the tool to compress collected data archive. choices are xz, bz2 or gz:
compressor = bz2

# flags to control logging levels:
debug   = False
quiet   = False

# set to True if owners of target objects are ignored during packaging process:
ignore_owner    = False

# destination directory to be stripped from installed path in absolute path:
destdir =

# advanced option to be enabled if you want to use pyxattr to get extended
# attributes of target files, dirs and symlinks:
with_pyxattr    = False


## package:
# name of the package:
name    = pmade-data

# version of the package:
pversion = 0.1

# group of the package:
group   = System Environment/Base

# license of the package
license = GPLv2+

# url of the package to provide information:
url     = http://localhost.localdomain

# summary (short description) of the package:
summary =

# Does the package depend on architecture?:
arch    = False

# a list of other package names separated with comma, required for the output package:
requires        =

# Full name of the packager, ex. John Doe
packager =

# Mail address of the packager
mail    =


## rpm:
# build target distribution will be used for mock:
dist    = fedora-14-i386

# whether to refer rpm database:
no_rpmdb   = False

# build rpm with only rpmbuild w/o mock (not recommended):
no_mock    = False
"""


(TYPE_FILE, TYPE_DIR, TYPE_SYMLINK, TYPE_OTHER, TYPE_UNKNOWN) = \
    ('file', 'dir', 'symlink', 'other', 'unknown')

TEST_CHOICES = (TEST_BASIC, TEST_FULL) = ("basic", "full")



def dicts_comp(lhs, rhs, keys=False):
    """Compare dicts. $rhs may have keys (and values) $lhs does not have.

    >>> dicts_comp({},{})
    True
    >>> dicts_comp({'a':1},{})
    False
    >>> d0 = {'a': 0, 'b': 1, 'c': 2}
    >>> d1 = copy.copy(d0)
    >>> dicts_comp(d0, d1)
    True
    >>> d1['d'] = 3
    >>> dicts_comp(d0, d1)
    True
    >>> dicts_comp(d0, d1, ('d'))
    False
    >>> d2 = copy.copy(d0)
    >>> d2['c'] = 3
    >>> dicts_comp(d0, d2)
    False
    >>> dicts_comp(d0, d2, ('a', 'b'))
    True
    """
    if lhs == {}:
        return True
    elif rhs == {}:
        return False
    else:
        return all(((lhs.get(key) == rhs.get(key)) for key in (keys and keys or lhs.keys())))


def memoize(fn):
    """memoization decorator.
    """
    cache = {}

    def wrapped(*args, **kwargs):
        key = repr(args) + repr(kwargs)
        if not cache.has_key(key):
            cache[key] = fn(*args, **kwargs)

        return cache[key]

    return wrapped


@memoize
def checksum(filepath='', algo=sha1, buffsize=8192):
    """compute and check md5 or sha1 message digest of given file path.

    TODO: What should be done when any exceptions such like IOError (e.g. could
    not open $filepath) occur?
    """
    if not filepath:
        return '0' * len(algo('').hexdigest())

    f = open(filepath, 'r')
    m = algo()

    while True:
        data = f.read(buffsize)
        if not data:
            break
        m.update(data)

    f.close()

    return m.hexdigest()


@memoize
def is_foldable(xs):
    """@see http://www.haskell.org/haskellwiki/Foldable_and_Traversable

    >>> is_foldable([])
    True
    >>> is_foldable(())
    True
    >>> is_foldable((x for x in range(3)))
    True
    """
    return isinstance(xs, list) or isinstance(xs, tuple) or callable(getattr(xs, 'next', None))


def listplus(list_x, foldable_y):
    return list_x + list(foldable_y)


@memoize
def flatten(xss):
    """
    >>> flatten([])
    []
    >>> flatten([[1,2,3],[4,5]])
    [1, 2, 3, 4, 5]
    >>> flatten([[1,2,[3]],[4,[5,6]]])
    [1, 2, 3, 4, 5, 6]

    tuple:

    >>> flatten([(1,2,3),(4,5)])
    [1, 2, 3, 4, 5]

    generator:

    >>> flatten(((i, i * 2) for i in range(0,5)))
    [0, 0, 1, 2, 2, 4, 3, 6, 4, 8]
    """
    if is_foldable(xss):
        return foldl(operator.add, (flatten(xs) for xs in xss), [])
    else:
        return [xss]


def concat(xss):
    """
    >>> concat([[]])
    []
    >>> concat((()))
    []
    >>> concat([[1,2,3],[4,5]])
    [1, 2, 3, 4, 5]
    >>> concat([[1,2,3],[4,5,[6,7]]])
    [1, 2, 3, 4, 5, [6, 7]]
    >>> concat(((1,2,3),(4,5,[6,7])))
    [1, 2, 3, 4, 5, [6, 7]]
    >>> concat(((1,2,3),(4,5,[6,7])))
    [1, 2, 3, 4, 5, [6, 7]]
    >>> concat(((i, i*2) for i in range(3)))
    [0, 0, 1, 2, 2, 4]
    """
    assert is_foldable(xss)

    return foldl(listplus, (xs for xs in xss), [])


@memoize
def unique(xs, cmp_f=cmp, key=None):
    """Returns new sorted list of no duplicated items.

    >>> unique([])
    []
    >>> unique([0, 3, 1, 2, 1, 0, 4, 5])
    [0, 1, 2, 3, 4, 5]
    """
    if xs == []:
        return xs

    ys = sorted(xs, cmp=cmp_f, key=key)

    if ys == []:
        return ys

    ret = [ys[0]]

    for y in ys[1:]:
        if y == ret[-1]:
            continue
        ret.append(y)

    return ret


def true(x):
    return True


def dirname(path):
    """dirname.

    >>> dirname('/a/b/c')
    '/a/b'
    >>> dirname('/a/b/')
    '/a/b'
    >>> dirname('')
    ''
    """
    return os.path.dirname(path)


def hostname():
    """
    Is there any cases exist that socket.gethostname() fails?
    """
    return socket.gethostname() or os.uname()[1]


def date(rfc2822=False, simple=False):
    """TODO: how to output in rfc2822 format w/o email.Utils.formatdate?
    ('%z' for strftime does not look working.)
    """
    if rfc2822:
        fmt = "%a, %d %b %Y %T +0000"
    else:
        fmt = (simple and "%Y%m%d" or "%a %b %_d %Y")

    return datetime.datetime.now().strftime(fmt)


def compile_template(template, params, is_file=False):
    """
    TODO: Add test case that $template is a filename.

    >>> tmpl_s = "a=$a b=$b"
    >>> params = {'a':1, 'b':'b'}
    >>> 
    >>> assert "a=1 b=b" == compile_template(tmpl_s, params)
    """
    if is_file:
        tmpl = Template(file=template, searchList=params)
    else:
        tmpl = Template(source=template, searchList=params)

    return tmpl.respond()


@memoize
def get_arch():
    """Returns 'normalized' architecutre this host can support.
    """
    ia32_re = re.compile(r"i.86") # i386, i686, etc.

    arch = platform.machine() or "i386"

    if ia32_re.match(arch) is not None:
        return "i386"
    else:
        return arch


@memoize
def get_username():
    """Get username.
    """
    return os.environ.get("USER", False) or os.getlogin()


@memoize
def get_email(use_git=True):
    if use_git:
        try:
            email = subprocess.check_output("git config --get user.email 2>/dev/null", shell=True)
            return email.rstrip()
        except Exception, e:
            logging.warn("get_email: " + str(e))
            pass

    return os.environ.get("MAIL_ADDRESS", False) or "%s@localhost.localdomain" % get_username()


@memoize
def get_fullname(use_git=True):
    """Get full name of the user.
    """
    if use_git:
        try:
            fullname = subprocess.check_output("git config --get user.name 2>/dev/null", shell=True)
            return fullname.rstrip()
        except Exception, e:
            logging.warn("get_fullname: " + str(e))
            pass

    return os.environ.get("FULLNAME", False) or get_username()


def shell(cmd_s, workdir=os.curdir):
    """NOTE: This function (subprocess.Popen.communicate()) may block.
    """
    if not workdir:
        workdir = os.path.abspath(os.curdir)

    logging.debug(" Run: %s [%s]" % (cmd_s, workdir))

    try:
        pipe = subprocess.Popen([cmd_s], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, cwd=workdir)
        (output, errors) = pipe.communicate()
    except Exception, e:
        # e.message looks not available in python < 2.5:
        #raise RuntimeError("Error (%s) during executing: %s" % (repr(e.__class__), e.message))
        raise RuntimeError("Error (%s) during executing: %s" % (repr(e.__class__), str(e)))

    if pipe.returncode == 0:
        return (output, errors)
    else:
        raise RuntimeError(" Failed: %s,\n err:\n'''%s'''" % (cmd_s, errors))



def shell2(cmd, workdir=os.curdir, log=True, dryrun=False, stop_on_error=True):
    """
    @cmd      str   command string, e.g. "ls -l ~".
    @workdir  str   in which dir to run given command?
    @log      bool  whether to print log messages or not.
    @dryrun   bool  if True, just print command string to run and returns.
    @stop_on_error bool  if True, RuntimeError will not be raised.

    TODO: Popen.communicate might be blocked. How about using Popen.wait
    instead?

    >>> assert 0 == shell2("echo ok > /dev/null", '.', False)
    >>> assert 0 == shell2("ls null", "/dev", False)
    >>> try:
    ...    rc = shell2("ls /root", '.', False)
    ... except RuntimeError:
    ...    pass
    >>> assert 0 == shell2("ls /root", '.', False, True)
    """
    if not workdir:
        workdir = os.path.abspath(os.curdir)

    logging.info(" Run: %s [%s]" % (cmd, workdir))

    if dryrun:
        logging.info(" exit as we're in dry run mode.")
        return 0

    llevel = logging.getLogger().level
    if llevel < logging.WARN:
        cmd += " > /dev/null"
    elif llevel < logging.INFO:
        cmd += " 2> /dev/null"
    else:
        pass

    try:
        proc = subprocess.Popen([cmd], shell=True, cwd=workdir)
        proc.wait()
        rc = proc.returncode
    except Exception, e:
        # NOTE: e.message looks not available in python < 2.5:
        #raise RuntimeError("Error (%s) during executing: %s" % (repr(e.__class__), e.message))
        raise RuntimeError("Error (%s) during executing: %s" % (repr(e.__class__), str(e)))

    if rc == 0:
        return rc
    else:
        if stop_on_error:
            raise RuntimeError(" Failed: %s,\n rc=%d" % (cmd, rc))
        else:
            logging.error(" cmd=%s, rc=%d" % (cmd, rc))
            return rc


def createdir(targetdir, mode=0700):
    """Create a dir with specified mode.
    """
    logging.debug(" Creating a directory: %s" % targetdir)

    if os.path.exists(targetdir):
        if os.path.isdir(targetdir):
            logging.warn(" Directory already exists! Skip it: %s" % targetdir)
        else:
            raise RuntimeError(" Already exists but not a directory: %s" % targetdir)
    else:
        os.makedirs(targetdir, mode)


def rm_rf(targetdir):
    """'rm -rf' in python.

    >>> d = tempfile.mkdtemp(dir='/tmp')
    >>> rm_rf(d)
    >>> rm_rf(d)
    >>> 
    >>> d = tempfile.mkdtemp(dir='/tmp')
    >>> for c in "abc":
    ...     os.makedirs(os.path.join(d, c))
    >>> os.makedirs(os.path.join(d, "c", "d"))
    >>> open(os.path.join(d, 'x'), "w").write("test")
    >>> open(os.path.join(d, 'a', 'y'), "w").write("test")
    >>> open(os.path.join(d, 'c', 'd', 'z'), "w").write("test")
    >>> 
    >>> rm_rf(d)
    """
    if not os.path.exists(targetdir):
        return

    if os.path.isfile(targetdir):
        os.remove(targetdir)
        return 

    assert targetdir != '/'                    # avoid 'rm -rf /'
    assert os.path.realpath(targetdir) != '/'  # likewise

    for x in glob.glob(os.path.join(targetdir, '*')):
        if os.path.isdir(x):
            rm_rf(x)
        else:
            os.remove(x)

    if os.path.exists(targetdir):
        os.removedirs(targetdir)


def cache_needs_updates_p(cache_file, expires=0):
    if expires == 0 or not os.path.exists(cache_file):
        return True

    try:
        mtime = os.stat(cache_file).st_mtime
    except OSError:  # It indicates that the cache file cannot be updated.
        return True  # FIXME: How to handle the above case?

    cur_time = datetime.datetime.now()
    cache_mtime = datetime.datetime.fromtimestamp(mtime)

    delta = cur_time - cache_mtime  # TODO: How to do if it's negative value?

    return (delta >= datetime.timedelta(expires))


class TestDecoratedFuncs(unittest.TestCase):
    """It seems that doctests in decarated functions are not run.  This class
    is a workaround for this issue.
    """

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_checksum_null(self):
        """if checksum() returns null
        """
        self.assertEquals(checksum(), '0' * len(sha1('').hexdigest()))

    def test_flatten(self):
        """if flatten() works as expected.
        """
        self.assertEquals(flatten([]),                                [])
        self.assertEquals(flatten([[1, 2, 3], [4, 5]]),               [1, 2, 3, 4, 5])
        self.assertEquals(flatten([[1, 2, [3]], [4, [5, 6]]]),        [1, 2, 3, 4, 5, 6])
        self.assertEquals(flatten([(1, 2, 3), (4, 5)]),               [1, 2, 3, 4, 5])
        self.assertEquals(flatten(((i, i * 2) for i in range(0, 5))), [0, 0, 1, 2, 2, 4, 3, 6, 4, 8])

    def test_is_foldable(self):
        """if is_foldable() works as expected.
        """
        self.assertTrue((is_foldable([])))
        self.assertTrue((is_foldable(())))
        self.assertTrue((is_foldable((x for x in range(3)))))
        self.assertFalse((is_foldable(None)))
        self.assertFalse((is_foldable(True)))
        self.assertFalse((is_foldable(1)))

    def test_unique(self):
        """if unique() works as expected.
        """
        self.assertEquals(unique([]),                       [])
        self.assertEquals(unique([0, 3, 1, 2, 1, 0, 4, 5]), [0, 1, 2, 3, 4, 5])



class TestFuncsWithSideEffects(unittest.TestCase):

    def setUp(self):
        logging.info("start") # dummy log
        self.workdir = tempfile.mkdtemp(dir='/tmp', prefix='pmaker-tests')

    def tearDown(self):
        rm_rf(self.workdir)

    def test_createdir_normal(self):
        """TODO: Check mode (permission).
        """
        d = os.path.join(self.workdir, "a")
        createdir(d)

        self.assertTrue(os.path.isdir(d))

    def test_createdir_specials(self):
        # assertIsNone is not available in python < 2.5:
        #self.assertIsNone(createdir(self.workdir))
        self.assertEquals(createdir(self.workdir), None)  # try creating dir already exists.

        f = os.path.join(self.workdir, 'a')
        open(f, "w").write("test")
        self.assertRaises(RuntimeError, createdir, f)

    def test_shell(self):
        (o, e) = shell('echo "" > /dev/null', '.')
        self.assertEquals(e, "")
        self.assertEquals(o, "")

        self.assertRaises(RuntimeError, shell, "grep xyz /dev/null")

        if os.getuid() != 0:
            self.assertRaises(RuntimeError, shell, 'ls', '/root')

    def test_init_defaults_by_conffile_config(self):
        conf = """\
[DEFAULT]
a: aaa
b: bbb
"""
        path = os.path.join(self.workdir, "config")
        open(path, "w").write(conf)

        params = init_defaults_by_conffile(path)
        assert params["a"] == "aaa"
        assert params["b"] == "bbb"

    def test_init_defaults_by_conffile_config_and_profile_0(self):
        conf = """\
[profile0]
a: aaa
b: bbb
"""
        path = os.path.join(self.workdir, "config")
        open(path, "w").write(conf)

        params = init_defaults_by_conffile(path, "profile0")
        assert params["a"] == "aaa"
        assert params["b"] == "bbb"



class Rpm(object):

    RPM_FILELIST_CACHE = os.path.join(os.environ['HOME'], '.cache', 'pmaker.rpm.filelist.pkl')

    # RpmFi (FileInfo) keys:
    fi_keys = ('path', 'size', 'mode', 'mtime', 'flags', 'rdev', 'inode',
        'nlink', 'state', 'vflags', 'uid', 'gid', 'checksum')

    @staticmethod
    def ts():
        return rpm.TransactionSet()

    @staticmethod
    def pathinfo(path):
        """Get meta data of file or dir from RPM Database.

        @path    Path of the file or directory (relative or absolute)
        @return  A dict; keys are fi_keys (see below)

        >>> f1 = '/etc/fstab'
        >>> pm = '/proc/mounts'
        >>>  
        >>> if os.path.exists('/var/lib/rpm/Basenames'):
        ...     if os.path.exists(f1):
        ...         pi = Rpm.pathinfo(f1)
        ...         assert pi.get('path') == f1
        ...         assert sorted(pi.keys()) == sorted(Rpm.fi_keys)
        ...     #
        ...     if os.path.exists(pm):
        ...         pi = Rpm.pathinfo(pm)
        ...         assert pi == {}, "result was '%s'" % str(pi)
        """
        _path = os.path.abspath(path)

        try:
            fis = [h.fiFromHeader() for h in Rpm.ts().dbMatch('basenames', _path)]
            if fis:
                xs = [x for x in fis[0] if x and x[0] == _path]
                if xs:
                    return dict(zip(Rpm.fi_keys, xs[0]))
        except:  # FIXME: Careful excpetion handling
            pass

        return dict()

    @staticmethod
    def each_fileinfo_by_package(pname='', pred=true):
        """RpmFi (File Info) of installed package, matched packages or all
        packages generator.

        @pname  str       A package name or name pattern (ex. 'kernel*') or ''
                          which means all packages.
        @pred   function  A predicate to sort out only necessary results.
                          $pred :: RpmFi -> bool.

        @return  A dict which has keys (Rpm.fi_keys and 'package' = package name)
                 and corresponding values.

        @see rpm/python/rpmfi-py.c
        """
        if '*' in pname:
            mi = Rpm.ts().dbMatch()
            mi.pattern('name', rpm.RPMMIRE_GLOB, pname)

        elif pname:
            mi = Rpm.ts().dbMatch('name', pname)

        else:
            mi = Rpm.ts().dbMatch()

        for h in mi:
            for fi in h.fiFromHeader():
                if pred(fi):
                    yield dict(zip(Rpm.fi_keys + ['package',], list(fi) + [h['name'],]))

        # Release them to avoid core dumped or getting wrong result next time.
        del mi

    @classmethod
    def filelist(cls, cache=True, expires=1, pkl_proto=pickle.HIGHEST_PROTOCOL):
        """TODO: It should be a heavy and time-consuming task. How to shorten
        this time? - caching, utilize yum's file list database or whatever.

        >>> f = '/etc/fstab'
        >>> if os.path.exists('/var/lib/rpm/Basenames'):
        ...     db = Rpm.filelist()
        ...     assert db.get(f) == 'setup'
        """
        data = None

        cache_file = cls.RPM_FILELIST_CACHE
        cachedir = os.path.dirname(cache_file)

        if not os.path.exists(cachedir):
            os.makedirs(cachedir, 0755)

        if cache and not cache_needs_updates_p(cache_file, expires):
            try:
                data = pickle.load(open(cache_file, 'rb'))
                logging.debug(" Could load the cache: %s" % cache_file)
            except:
                logging.warn(" Could not load the cache: %s" % cache_file)
                date = None

        if data is None:
            data = dict(concat((((f, h['name']) for f in h['filenames']) for h in Rpm.ts().dbMatch())))

            try:
                # TODO: How to detect errors during/after pickle.dump.
                pickle.dump(data, open(cache_file, 'wb'), pkl_proto)
                logging.debug(" Could save the cache: %s" % cache_file)
            except:
                logging.warn(" Could not save the cache: %s" % cache_file)

        return data



class ObjDict(dict):
    """
    Dict class works like object.

    >>> o = ObjDict()
    >>> o['a'] = 'aaa'
    >>> assert o.a == o['a']
    >>> assert o.a == 'aaa'
    >>> o.a = 'bbb'
    >>> assert o.a == 'bbb'
    >>> assert o['a'] == o.a
    >>> 

    TODO: pickle support. (The following does not work):

    #>>> workdir = tempfile.mkdtemp(dir='/tmp', prefix='objdict-doctest-')
    #>>> pkl_f = os.path.join(workdir, 'objdict.pkl')
    #>>> pickle.dump(o, open(pkl_f, 'wb'), protocol=pickle.HIGHEST_PROTOCOL)
    #>>> assert o == pickle.load(open(pkl_f))
    """

    def __getattr__(self, key):
        return self.__dict__.get(key, None)

    def __setattr__(self, key, val):
        self.__dict__[key] = val

    def __getitem__(self, key):
        return self.__dict__.get(key, None)

    def __setitem__(self, key, val):
        self.__dict__[key] = val

    def __getstate__(self):
        return self.__dict__

    def __setstate__(self, d):
        self.__dict__.update(d)



class FileOperations(object):
    """Class to implement operations for FileInfo classes.

    This class will not be instatiated and mixed in FileInfo classes.
    """

    @classmethod
    def equals(cls, lhs, rhs):
        """lhs and rhs are identical, that is, these contents and metadata
        (except for path) are exactly same.

        TODO: Compare the part of the path?
          ex. lhs.path: '/path/to/xyz', rhs.path: '/var/lib/sp2/updates/path/to/xyz'

        >>> lhs = FileInfoFactory().create("/etc/resolv.conf")
        >>> rhs = copy.copy(lhs)
        >>> setattr(rhs, "other_attr", "xyz")
        >>> 
        >>> FileOperations.equals(lhs, rhs)
        True
        >>> rhs.mode = "755"
        >>> FileOperations.equals(lhs, rhs)
        False
        """
        keys = ("mode", "uid", "gid", "checksum", "filetype")
        res = all((getattr(lhs, k) == getattr(rhs, k) for k in keys))

        return res and dicts_comp(lhs.xattrs, rhs.xattrs) or False

    @classmethod
    def equivalent(cls, lhs, rhs):
        """These metadata (path, uid, gid, etc.) do not match but the checksums
        are same, that is, that contents are exactly same.

        @lhs  FileInfo object
        @rhs  Likewise

        >>> class FakeFileInfo(object):
        ...     checksum = checksum()
        >>> 
        >>> lhs = FakeFileInfo(); rhs = FakeFileInfo()
        >>> FileOperations.equivalent(lhs, rhs)
        True
        >>> rhs.checksum = checksum("/etc/resolv.conf")
        >>> FileOperations.equivalent(lhs, rhs)
        False
        """
        return lhs.checksum == rhs.checksum

    @classmethod
    def permission(cls, mode):
        """permission (mode) can be passed to 'chmod'.

        NOTE: There are some special cases, e.g. /etc/gshadow- and
        /etc/shadow-, such that mode == 0.

        @mode  stat.mode

        >>> file0 = "/etc/resolv.conf"
        >>> if os.path.exists(file0):
        ...     mode = os.lstat(file0).st_mode
        ...     expected = oct(stat.S_IMODE(mode & 0777))[1:]
        ...     assert expected == FileOperations.permission(mode)
        >>> 
        >>> gshadow = "/etc/gshadow-"
        >>> if os.path.exists(gshadow):
        ...     mode = os.lstat(gshadow).st_mode
        ...     assert "000" == FileOperations.permission(mode)
        """
        m = stat.S_IMODE(mode & 0777)
        return m == 0 and "000" or oct(m)[1:]

    @classmethod
    def copy_main(cls, fileinfo, dest, use_pyxattr=USE_PYXATTR):
        """Two steps needed to keep the content and metadata of the original file:

        1. Copy itself and its some metadata (owner, mode, etc.)
        2. Copy extra metadata not copyable with the above.

        'cp -a' (cp in GNU coreutils) does the above operations at once and
        might be suited for most cases, I think.

        @fileinfo   FileInfo object
        @dest  str  Destination path to copy to
        @use_pyxattr bool  Whether to use pyxattr module
        """
        if use_pyxattr:
            shutil.copy2(fileinfo.path, dest)  # correponding to "cp -p ..."
            cls.copy_xattrs(fileinfo.xattrs, dest)
        else:
            shell2("cp -a %s %s" % (fileinfo.path, dest))

    @classmethod
    def copy_xattrs(cls, src_xattrs, dest):
        """
        @src_xattrs  dict  Xattributes of source FileInfo object to copy
        @dest        str   Destination path
        """
        for k, v in src_xattrs.iteritems():
            xattr.set(dest, k, v)

    @classmethod
    def remove(cls, path):
        os.remove(path)

    @classmethod
    def copy(cls, fileinfo, dest, force=False):
        """Copy to $dest.  'Copy' action varys depends on actual filetype so
        that inherited class must overrride this and related methods (_remove
        and _copy).

        @fileinfo  FileInfo  FileInfo object
        @dest      string    The destination path to copy to
        @force     bool      When True, force overwrite $dest even if it exists
        """
        assert fileinfo.path != dest, "Copying src and dst are same!"

        if not fileinfo.copyable():
            logging.warn(" Not copyable: %s" % str(self))
            return False

        if os.path.exists(dest):
            logging.warn(" Copying destination already exists: '%s'" % dest)

            # TODO: It has negative impact for symlinks.
            #
            #if os.path.realpath(self.path) == os.path.realpath(dest):
            #    logging.warn("Copying src and dest are same actually.")
            #    return False

            if force:
                logging.info(" Removing old one before copying: " + dest)
                fileinfo.operations.remove(dest)
            else:
                logging.warn(" Do not overwrite it")
                return False
        else:
            destdir = os.path.dirname(dest)

            # TODO: which is better?
            #os.makedirs(os.path.dirname(dest)) or ...
            #shutil.copytree(os.path.dirname(self.path), os.path.dirname(dest))

            if not os.path.exists(destdir):
                os.makedirs(destdir)
            shutil.copystat(os.path.dirname(fileinfo.path), destdir)

        logging.debug(" Copying from '%s' to '%s'" % (fileinfo.path, dest))
        cls.copy_main(fileinfo, dest)

        return True



class DirOperations(FileOperations):

    @classmethod
    def remove(cls, path):
        if not os.path.isdir(path):
            raise RuntimeError(" '%s' is not a directory! Aborting..." % path)

        os.removedirs(path)

    @classmethod
    def copy_main(cls, fileinfo, dest, use_pyxattr=False):
        os.makedirs(dest, mode=fileinfo.mode)

        try:
            os.chown(dest, fileinfo.uid, fileinfo.gid)
        except OSError, e:
            logging.warn(e)

        shutil.copystat(fileinfo.path, dest)
        cls.copy_xattrs(fileinfo.xattrs, dest)



class SymlinkOperations(FileOperations):

    @classmethod
    def copy_main(cls, fileinfo, dest, use_pyxattr=False):
        os.symlink(fileinfo.linkto, dest)
        #shell2("cp -a %s %s" % (fileinfo.path, dest))



class TestFileOperations(unittest.TestCase):

    def setUp(self):
        self.workdir = tempfile.mkdtemp(dir="/tmp", prefix="pmaker-tests")
        logging.info("start")
        self.fo = FileOperations
        self.path = [f for f in glob.glob(os.path.join(os.path.expanduser("~"), ".*")) if os.path.isfile(f)][0]

    def tearDown(self):
        rm_rf(self.workdir)

    def test_copy_main_and_remove(self):
        dest = os.path.join(self.workdir, os.path.basename(self.path))
        dest2 = dest + ".xattrs"

        fileinfo = FileInfoFactory().create(self.path)

        self.fo.copy_main(fileinfo, dest)
        self.fo.copy_main(fileinfo, dest2, True)

        src_attrs = xattr.get_all(self.path)
        if src_attrs:
            assert src_attrs == xattr.get_all(dest)
            assert src_attrs == xattr.get_all(dest2)

        assert os.path.exists(dest)
        assert os.path.exists(dest2)

        self.fo.remove(dest)
        assert not os.path.exists(dest)

        self.fo.remove(dest2)
        assert not os.path.exists(dest2)

    def test_copy(self):
        dest = os.path.join(self.workdir, os.path.basename(self.path))
        fileinfo = FileInfoFactory().create(self.path)

        self.fo.copy(fileinfo, dest)
        self.fo.copy(fileinfo, dest, True)

        assert os.path.exists(dest)
        self.fo.remove(dest)
        assert not os.path.exists(dest)



class FileInfo(object):
    """The class of which objects to hold meta data of regular files, dirs and
    symlinks. This is for regular file and the super class for other types.
    """

    operations = FileOperations
    filetype = TYPE_FILE
    is_copyable = True

    def __init__(self, path, mode, uid, gid, checksum, xattrs, **kwargs):
        self.path = path
        self.realpath = os.path.realpath(path)

        self.mode = mode
        self.uid= uid
        self.gid = gid
        self.checksum = checksum
        self.xattrs = xattrs or {}

        self.perm_default = '644'

        for k, v in kwargs.iteritems():
            self[k] = v

    @classmethod
    def type(cls):
        return cls.filetype

    @classmethod
    def copyable(cls):
        return cls.is_copyable

    def __eq__(self, other):
        return self.operations(self, other)

    def equivalent(self, other):
        return self.operations.equivalent(self, other)

    def permission(self):
        return self.operations.permission(self.mode)

    def need_to_chmod(self):
        return self.permission() != self.perm_default

    def need_to_chown(self):
        return self.uid != 0 or self.gid != 0  # 0 == root

    def copy(self, dest, force=False):
        return self.operations.copy(self, dest, force)

    def rpm_attr(self):
        if self.need_to_chmod() or self.need_to_chown():
            return rpm_attr(self) + " "
        else:
            return ""



class DirInfo(FileInfo):

    operations = DirOperations
    filetype = TYPE_DIR

    def __init__(self, path, mode, uid, gid, checksum, xattrs):
        super(DirInfo, self).__init__(path, mode, uid, gid, checksum, xattrs)
        self.perm_default = '755'

    def rpm_attr(self):
        return super(DirInfo, self).rpm_attr() + "%dir "



class SymlinkInfo(FileInfo):

    operations = SymlinkOperations
    filetype = TYPE_SYMLINK

    def __init__(self, path, mode, uid, gid, checksum, xattrs):
        super(SymlinkInfo, self).__init__(path, mode, uid, gid, checksum, xattrs)
        self.linkto = os.path.realpath(path)

    def need_to_chmod(self):
        return False



class OtherInfo(FileInfo):
    """$path may be a socket, FIFO (named pipe), Character Dev or Block Dev, etc.
    """
    filetype = TYPE_OTHER
    is_copyable = False

    def __init__(self, path, mode, uid, gid, checksum, xattrs):
        super(OtherInfo, self).__init__(path, mode, uid, gid, checksum, xattrs)



class UnknownInfo(FileInfo):
    """Special case that lstat() failed and cannot stat $path.
    """
    filetype = TYPE_UNKNOWN
    is_copyable = False

    def __init__(self, path, mode=-1, uid=-1, gid=-1, checksum=checksum(), xattrs={}):
        super(UnknownInfo, self).__init__(path, mode, uid, gid, checksum, xattrs)



class FileInfoFactory(object):
    """Factory class for *Info.
    """

    def _stat(self, path):
        """
        @path    str     Object's path (relative or absolute)
        @return  A tuple of (mode, uid, gid) or None if OSError was raised.

        >>> ff = FileInfoFactory()
        >>> f0 = "/etc/hosts"
        >>> if os.path.exists(f0):
        ...     (_mode, uid, gid) = ff._stat(f0)
        ...     assert uid == 0
        ...     assert gid == 0
        ... else:
        ...     print "Test target file does not exist. Skip it"
        >>> 
        >>> if os.getuid() != 0:
        ...    assert ff._stat('/root/.bashrc') is None
        """
        try:
            _stat = os.lstat(path)
        except OSError, e:
            logging.warn(e)
            return None

        return (_stat.st_mode, _stat.st_uid, _stat.st_gid)

    def _guess_ftype(self, st_mode):
        """
        @st_mode    st_mode

        TODO: More appropriate doctest cases.

        >>> ff = FileInfoFactory()
        >>> st_mode = lambda f: os.lstat(f)[0]
        >>> 
        >>> if os.path.exists('/etc/grub.conf'):
        ...     assert TYPE_SYMLINK == ff._guess_ftype(st_mode('/etc/grub.conf'))
        >>> 
        >>> if os.path.exists('/etc/hosts'):
        ...     assert TYPE_FILE == ff._guess_ftype(st_mode('/etc/hosts'))
        >>> 
        >>> if os.path.isdir('/etc'):
        ...     assert TYPE_DIR == ff._guess_ftype(st_mode('/etc'))
        >>> 
        >>> if os.path.exists('/dev/null'):
        ...     assert TYPE_OTHER == ff._guess_ftype(st_mode('/dev/null'))
        """
        if stat.S_ISLNK(st_mode):
            ft = TYPE_SYMLINK

        elif stat.S_ISREG(st_mode):
            ft = TYPE_FILE

        elif stat.S_ISDIR(st_mode):
            ft = TYPE_DIR

        elif stat.S_ISCHR(st_mode) or stat.S_ISBLK(st_mode) \
            or stat.S_ISFIFO(st_mode) or stat.S_ISSOCK(st_mode):
            ft = TYPE_OTHER
        else:
            ft = TYPE_UNKNOWN  # Should not be reached

        return ft

    def create(self, path):
        """Factory method. Create and return the *Info instance.

        @path       str   Object path (relative or absolute)
        """
        st = self._stat(path)

        if st is None:
            return UnknownInfo(path)
        else:
            (_mode, _uid, _gid) = st

        xs = xattr.get_all(path)
        _xattrs = (xs and dict(xs) or {})

        _filetype = self._guess_ftype(_mode)

        if _filetype == TYPE_UNKNOWN:
            logging.info(" Could not get the result: %s" % path)

        if _filetype == TYPE_FILE:
            _checksum = checksum(path)
        else:
            _checksum = checksum()

        _cls = globals().get("%sInfo" % _filetype.title(), False)
        assert _cls, "Should not reached here! _filetype.title() was '%s'" % _filetype.title()

        return _cls(path, _mode, _uid, _gid, _checksum, _xattrs)



class RpmFileInfoFactory(FileInfoFactory):

    def __init__(self):
        super(RpmFileInfoFactory, self).__init__()

    def _stat(self, path):
        """Stat with using RPM database instead of lstat().

        There are cases to get no results if the target objects not owned by
        any packages.

        >>> if os.path.exists('/var/lib/rpm/Basenames'):
        ...     ff = RpmFileInfoFactory()
        ... 
        ...     if os.path.exists('/etc/hosts'):
        ...         (_mode, uid, gid) = ff._stat('/etc/hosts')
        ...         assert uid == 0
        ...         assert gid == 0
        ... 
        ...     if os.path.exists('/etc/resolv.conf'):  # not in the rpm database.
        ...         (_mode, uid, gid) = ff._stat('/etc/resolv.conf')
        ...         assert uid == 0
        ...         assert gid == 0
        """
        try:
            fi = Rpm.pathinfo(path)
            if fi:
                uid = pwd.getpwnam(fi['uid']).pw_uid   # uid: name -> id
                gid = grp.getgrnam(fi['gid']).gr_gid   # gid: name -> id

                return (fi['mode'], uid, gid)
        except:
            pass

        return super(RpmFileInfoFactory, self)._stat(path)

    def create(self, path):
        """TODO: what should be done for objects of *infos other than fileinfo?
        """
        fi = super(RpmFileInfoFactory, self).create(path)

        return fi



def distdata_in_makefile_am(paths, srcdir='src'):
    """
    @paths  file path list

    >>> ps0 = ['/etc/resolv.conf', '/etc/sysconfig/iptables']
    >>> rs0 = [{'dir': '/etc', 'files': ['src/etc/resolv.conf'], 'id': '0'}, {'dir': '/etc/sysconfig', 'files': ['src/etc/sysconfig/iptables'], 'id': '1'}]
    >>> 
    >>> ps1 = ps0 + ['/etc/sysconfig/ip6tables', '/etc/modprobe.d/dist.conf']
    >>> rs1 = [{'dir': '/etc', 'files': ['src/etc/resolv.conf'], 'id': '0'}, {'dir': '/etc/sysconfig', 'files': ['src/etc/sysconfig/iptables', 'src/etc/sysconfig/ip6tables'], 'id': '1'}, {'dir': '/etc/modprobe.d', 'files': ['src/etc/modprobe.d/dist.conf'], 'id': '2'}]
    >>> 
    >>> _cmp = lambda ds1, ds2: all([dicts_comp(*dt) for dt in zip(ds1, ds2)])
    >>> 
    >>> rrs0 = distdata_in_makefile_am(ps0)
    >>> rrs1 = distdata_in_makefile_am(ps1)
    >>> 
    >>> assert _cmp(rrs0, rs0), "expected %s but got %s" % (str(rs0), str(rrs0))
    >>> assert _cmp(rrs1, rs1), "expected %s but got %s" % (str(rs1), str(rrs1))
    """
    cntr = count()

    return [
        {
            'id': str(cntr.next()),
            'dir':d,
            'files': [os.path.join('src', p.strip(os.path.sep)) for p in ps]
        } \
        for d,ps in groupby(paths, dirname)
    ]


def rpm_attr(fileinfo):
    """Returns '%attr(...)' to specify the file attribute of $fileinfo.path in
    the %files section in rpm spec.

    >>> fi = FileInfo('/dummy/path', 33204, 0, 0, checksum(),{})
    >>> rpm_attr(fi)
    '%attr(664, -, -)'
    >>> fi = FileInfo('/bin/foo', 33261, 1, 1, checksum(),{})
    >>> rpm_attr(fi)
    '%attr(755, bin, bin)'
    """
    m = fileinfo.permission() # ex. '755'
    u = (fileinfo.uid == 0 and '-' or pwd.getpwuid(fileinfo.uid).pw_name)
    g = (fileinfo.gid == 0 and '-' or grp.getgrgid(fileinfo.gid).gr_name)

    return "%%attr(%(m)s, %(u)s, %(g)s)" % {'m':m, 'u':u, 'g':g,}


def srcrpm_name_by_rpmspec(rpmspec):
    """Returns the name of src.rpm gotten from given RPM spec file.
    """
    cmd = 'rpm -q --specfile --qf "%{n}-%{v}-%{r}.src.rpm\n" ' + rpmspec
    (o, e) = shell(cmd)
    return o.split("\n")[0]


def srcrpm_name_by_rpmspec_2(rpmspec):
    """Returns the name of src.rpm gotten from given RPM spec file.

    Utilize rpm python binding instead of calling 'rpm' command.

    FIXME: rpm-python does not look stable and dumps core often.
    """
    p = rpm.TransactionSet().parseSpec(rpmspec).packages[0]
    h = p.header
    return "%s-%s-%s.src.rpm" % (h["n"], h["v"], h["r"])


def do_nothing(*args, **kwargs):
    return


def on_debug_mode():
    return logging.getLogger().level < logging.INFO



class Collector(object):

    _enabled = True

    def __init__(self, *args, **kwargs):
        pass

    def enabled(self):
        return self._enabled

    def make_enabled(self):
        self._enabled = False

    def collect(self, *args, **kwargs):
        if not self.enabled():
            raise RuntimeError("Pluing %s cannot run as necessary function is not available." % self.__name__)



class FilelistCollector(Collector):
    """
    Collector to collect fileinfo list from files list in simple format:

    Format: A file or dir path (absolute or relative) |
            Comment line starts with '#' |
            Glob pattern to list multiple files or dirs
    """

    def __init__(self, filelist, pkgname, options):
        """
        @filelist  str  file to list files and dirs to collect or "-"
                        (read files and dirs list from stdin)
        @pkgname     str  package name to build
        """
        super(FilelistCollector, self).__init__(filelist, options)

        self.filelist = filelist
        self.pkgname = pkgname
        self.options = options  # Ugly.

        self.destdir = options.destdir
        self.force_set_uid_and_gid = options.ignore_owner

        if self.options.format == "rpm":
            self.fi_factory = RpmFileInfoFactory()
            self.database_fun = self.options.no_rpmdb and dict or Rpm.filelist
        else:
            self.fi_factory = FileInfoFactory()
            self.database_fun = dict

    @staticmethod
    def open(path):
        return path == "-" and sys.stdin or open(path)

    @staticmethod
    def expand_list(alist):
        return unique(concat((glob.glob(f) for f in alist if not f.startswith("#"))))

    @classmethod
    def list_paths(cls, listfile):
        """Read paths from given file line by line and returns path list sorted by
        dir names. There some speical parsing rules for the file list:

        * Empty lines or lines start with '#' are ignored.
        * The lines contain '*' (glob match) will be expanded to real dir or file
          names: ex. '/etc/httpd/conf/*' will be
          ['/etc/httpd/conf/httpd.conf', '/etc/httpd/conf/magic', ...] .

        @listfile  str  Path list file name or "-" (read list from stdin)
        """
        return cls.expand_list((l.rstrip() for l in cls.open(listfile).readlines() if l and not l.startswith('#')))

    @classmethod
    def rewrite_with_destdir(cls, path, destdir):
        """Rewrite target (install destination) path.

        By default, target path will be same as $path. This method will change
        it as needed.

        >>> FilelistCollector.rewrite_with_destdir("/a/b/c", "/a/b")
        '/c'
        >>> FilelistCollector.rewrite_with_destdir("/a/b/c", "/a/b/")
        '/c'
        >>> try:
        ...     FilelistCollector.rewrite_with_destdir("/a/b/c", "/x/y")
        ... except RuntimeError, e:
        ...     pass
        """
        if path.startswith(destdir):
            new_path = path.split(destdir)[1]
            if not new_path.startswith(os.path.sep):
                new_path = os.path.sep + new_path

            logging.debug("Rewrote target path from %s to %s" % (path, new_path))
            return new_path
        else:
            logging.error(" The path '%s' does not start with '%s'" % (path, destdir))
            raise RuntimeError("Destdir given in --destdir and the actual file path are inconsistent.")

    def find_conflicts(self, path, pkgname):
        """Find the package owns given path.

        @path       str   Target path
        @pkgname    str   Package name will own the above path
        """
        filelist_database = self.database_fun()
        other_pkgname = filelist_database.get(path, False)

        if other_pkgname and other_pkgname != pkgname:
            m = "%(path)s is owned by %(other)s and this package will conflict with it" % \
                {"path": path, "other": other_pkgname}
            logging.warn(m)
            return pkgname
        else:
            return ""

    def _collect(self, listfile, trace=False):
        """Collect FileInfo objects from given path list.

        @listfile  str  File, dir and symlink paths list
        """
        fileinfos = []

        for path in self.list_paths(listfile):
            fi = self.fi_factory.create(path)

            # Too verbose but useful in some cases:
            if trace:
                logging.debug(" fi=%s" % str(fi))

            if fi.type() not in (TYPE_FILE, TYPE_SYMLINK, TYPE_DIR):
                logging.warn(" '%s' is not supported type. Skip %s" % (fi.type(), path))
                continue

            if self.force_set_uid_and_gid:
                logging.debug(" force set uid and gid of %s" % fi.path)
                fi.uid = fi.gid = 0

            if self.destdir:
                fi.target = self.rewrite_with_destdir(fi.path, self.destdir)
            else:
                # Too verbose but useful in some cases:
                if trace:
                    logging.debug(" Do not need to rewrite the path: " + fi.path)

                fi.target = fi.path

            fi.conflicts = self.find_conflicts(fi.target, self.pkgname)

            fileinfos.append(fi)

        return fileinfos

    def collect(self):
        return self._collect(self.filelist)



class JsonFilelistCollector(FilelistCollector):
    """
    Collector to collect fileinfo list from files list in JSON format:
    """

    try:
        import json
        _enabled = True
    except:
        _enabled = False

    @classmethod
    def list_paths(cls, listfile):
        pass



class TestFilelistCollector(unittest.TestCase):

    def setUp(self):
        self.workdir = tempfile.mkdtemp(dir="/tmp", prefix="pmaker-tests")
        logging.info("start")

    def tearDown(self):
        rm_rf(self.workdir)

    def test_expand_list(self):
        ps0 = ["#/etc/resolv.conf"]
        ps1 = ["/etc/resolv.conf"]
        ps2 = ps1 + ps1
        ps3 = ["/etc/resolv.conf", "/etc/rc.d/rc"]
        ps4 = ["/etc/auto.*"]
        ps5 = ps3 + ps4

        self.assertListEqual(FilelistCollector.expand_list(ps0), [])
        self.assertListEqual(FilelistCollector.expand_list(ps1), ps1)
        self.assertListEqual(FilelistCollector.expand_list(ps2), ps1)
        self.assertListEqual(FilelistCollector.expand_list(ps3), sorted(ps3))
        self.assertListEqual(FilelistCollector.expand_list(ps4), sorted(glob.glob(ps4[0])))
        self.assertListEqual(FilelistCollector.expand_list(ps5), sorted(ps3 + glob.glob(ps4[0])))

    def test_list_paths(self):
        paths = [
            "/etc/auto.*",
            "#/etc/aliases.db",
            "/etc/httpd/conf.d",
            "/etc/httpd/conf.d/*",
            "/etc/modprobe.d/*",
            "/etc/rc.d/init.d",
            "/etc/rc.d/rc",
            "/etc/reslv.conf",
        ]
        listfile = os.path.join(self.workdir, "files.list")

        f = open(listfile, "w")
        for p in paths:
            f.write("%s\n" % p)
        f.close()

        self.assertListEqual(FilelistCollector.list_paths(listfile), FilelistCollector.expand_list(paths))

    def test_run(self):
        paths = [
            "/etc/auto.*",
            "#/etc/aliases.db",
            "/etc/httpd/conf.d",
            "/etc/httpd/conf.d/*",
            "/etc/modprobe.d/*",
            "/etc/rc.d/init.d",
            "/etc/rc.d/rc",
            "/etc/resolv.conf",
            "/etc/reslv.conf",  # should not be exist.
        ]
        listfile = os.path.join(self.workdir, "files.list")

        f = open(listfile, "w")
        for p in paths:
            f.write("%s\n" % p)
        f.close()

        option_values = {
            "format": "rpm",
            "destdir": "",
            "ignore_owner": False,
            "no_rpmdb": False,
        }

        options = optparse.Values(option_values)
        fc = FilelistCollector(listfile, "foo", options)
        fs = fc.collect()

        option_values["format"] = "deb"
        options = optparse.Values(option_values)
        fc = FilelistCollector(listfile, "foo", options)
        fs = fc.collect()
        option_values["format"] = "rpm"

        option_values["destdir"] = "/etc"
        options = optparse.Values(option_values)
        fc = FilelistCollector(listfile, "foo", options)
        fs = fc.collect()
        option_values["destdir"] = ""

        option_values["ignore_owner"] = True
        options = optparse.Values(option_values)
        fc = FilelistCollector(listfile, "foo", options)
        fs = fc.collect()
        option_values["ignore_owner"] = False

        option_values["no_rpmdb"] = True
        options = optparse.Values(option_values)
        fc = FilelistCollector(listfile, "foo", options)
        fs = fc.collect()
        option_values["no_rpmdb"] = False



class PackageMaker(object):
    """Abstract class for classes to implement various packaging processes.
    """
    global TEMPLATES

    _templates = TEMPLATES
    _type = "filelist"
    _format = None
    _collector = FilelistCollector
    _relations = {}

    @classmethod
    def register(cls, pmmaps=PACKAGE_MAKERS):
        pmmaps[(cls.type(), cls.format())] = cls

    @classmethod
    def templates(cls):
        return cls._templates

    @classmethod
    def type(cls):
        return cls._type

    @classmethod
    def format(cls):
        return cls._format

    @classmethod
    def collector(cls):
        return cls._collector

    def __init__(self, package, filelist, options, *args, **kwargs):
        self.package = package
        self.filelist = filelist
        self.options = options

        self.workdir = package['workdir']
        self.destdir = package['destdir']
        self.pname = package['name']

        self.force = options.force
        self.upto = options.upto

        self.srcdir = os.path.join(self.workdir, 'src')

        relmap = []
        if package.has_key("relations"):
            for reltype, reltargets in package["relations"]:
                rel = self._relations.get(reltype, False)
                if rel:
                    relmap.append({"type": rel, "targets": reltargets})

        self.package["relations"] = relmap

        for k, v in kwargs.iteritems():
            setattr(self, k, v)

    def shell(self, cmd_s):
        return shell2(cmd_s, workdir=self.workdir)

    def to_srcdir(self, path):
        """
        >>> class O(object):
        ...     pass
        >>> o = O(); o.upto = "build"; o.force = False
        >>> pm = PackageMaker({'name': 'foo', 'workdir': '/tmp/w', 'destdir': '',}, '/tmp/filelist', o)
        >>> pm.to_srcdir('/a/b/c')
        '/tmp/w/src/a/b/c'
        >>> pm.to_srcdir('a/b')
        '/tmp/w/src/a/b'
        >>> pm.to_srcdir('/')
        '/tmp/w/src/'
        """
        assert path != '', "Empty path was given"

        return os.path.join(self.srcdir, path.strip(os.path.sep))

    def genfile(self, path, output=False):
        outfile = os.path.join(self.workdir, (output or path))
        open(outfile, 'w').write(compile_template(self.templates()[path], self.package))

    def copyfiles(self):
        for fi in self.package['fileinfos']:
            fi.copy(os.path.join(self.workdir, self.to_srcdir(fi.target)), self.force)

    def dumpfile_path(self):
        return os.path.join(self.workdir, "pmaker-package-filelist.pkl")

    def save(self, pkl_proto=pickle.HIGHEST_PROTOCOL):
        pickle.dump(self.package['fileinfos'], open(self.dumpfile_path(), 'wb'), pkl_proto)

    def load(self):
        self.package['fileinfos'] = pickle.load(open(self.dumpfile_path()))

    def touch_file(self, step):
        return os.path.join(self.workdir, "pmaker-%s.stamp" % step)

    def try_the_step(self, step):
        if os.path.exists(self.touch_file(step)):
            msg = "...The step looks already done"

            if self.force:
                logging.info(msg + ": " + step)
            else:
                logging.info(msg + ". Skip the step: " + step)
                return

        getattr(self, step, do_nothing)() # TODO: or eval("self." + step)() ?
        self.shell("touch %s" % self.touch_file(step))

        if step == self.upto:
            if step == 'build':
                logging.info("Successfully created packages in %s: %s" % (self.workdir, self.pname))
            sys.exit()

    def collect(self, *args, **kwargs):
        clctr = self.collector()(self.filelist, self.package["name"], self.options)
        return clctr.collect()

    def setup(self):
        self.package['fileinfos'] = self.collect()

        for d in ('workdir', 'srcdir'):
            createdir(self.package[d])

        self.copyfiles()
        self.save()

    def pre_configure(self):
        if not self.package.get('fileinfos', False):
            self.load()

        if not self.package.get('conflicts', False):
            self.package['conflicts'] = {
                'names': unique((fi.conflicts for fi in self.package['fileinfos'] if fi.conflicts)),
                'files': unique((fi.target for fi in self.package['fileinfos'] if fi.conflicts)),
            }

    def configure(self):
        self.pre_configure()

        self.package['distdata'] = distdata_in_makefile_am(
            [fi.target for fi in self.package['fileinfos'] if fi.type() == TYPE_FILE]
        )

        self.genfile('configure.ac')
        self.genfile('Makefile.am')
        self.genfile('README')
        self.genfile('MANIFEST')
        self.genfile('MANIFEST.overrides')

        if on_debug_mode():
            self.shell('autoreconf -vfi')
        else:
            self.shell('autoreconf -fi')

    def sbuild(self):
        if on_debug_mode():
            self.shell("./configure --quiet")
            self.shell("make")
            self.shell("make dist")
        else:
            self.shell("./configure --quiet --enable-silent-rules")
            self.shell("make V=0 > /dev/null")
            self.shell("make dist V=0 > /dev/null")

    def build(self):
        pass

    def run(self):
        """run all of the packaging processes: setup, configure, build, ...
        """
        steps = (
            ("setup", "Setting up src tree in %s: %s" % (self.workdir, self.pname)),
            ("configure", "Configuring src distribution: %s" % self.pname),
            ("sbuild", "Building src package: %s" % self.pname),
            ("build", "Building bin packages: %s" % self.pname),
        )

        for step, msg in steps:
            logging.info(msg)
            self.try_the_step(step)



class TgzPackageMaker(PackageMaker):
    _format = "tgz"



class RpmPackageMaker(TgzPackageMaker):
    _format = "rpm"

    _relations = {
        "requires": "Requires",
        "requires.pre": "Requires(pre)",
        "requires.preun": "Requires(preun)",
        "requires.post": "Requires(post)",
        "requires.postun": "Requires(postun)",
        "requires.verify": "Requires(verify)",
        "conflicts": "Conflicts",
        "provides": "Provides",
        "obsoletes": "Obsoletes",
    }

    def __init__(self, package, filelist, options, *args, **kwargs):
        super(RpmPackageMaker, self).__init__(package, filelist, options)
        self.use_mock = (not options.no_mock)

    def rpmspec(self):
        return os.path.join(self.workdir, "%s.spec" % self.pname)

    def build_srpm(self):
        if on_debug_mode:
            return self.shell("make srpm")
        else:
            return self.shell("make srpm V=0 > /dev/null")

    def build_rpm(self):
        if self.use_mock:
            try:
                self.shell("mock --version > /dev/null")
            except RuntimeError, e:
                logging.warn(" It seems mock is not found on your system. Fallback to plain rpmbuild...")
                self.use_mock = False

        if self.use_mock:
            silent = (on_debug_mode() and "" or "--quiet")
            self.shell("mock -r %s %s %s" % \
                (self.package['dist'], srcrpm_name_by_rpmspec(self.rpmspec()), silent)
            )
            return self.shell("mv /var/lib/mock/%(dist)s/result/*.rpm %(workdir)s" % self.package)
        else:
            if on_debug_mode:
                return self.shell("make rpm")
            else:
                return self.shell("make rpm V=0 > /dev/null")

    def configure(self):
        super(RpmPackageMaker, self).configure()

        self.genfile('rpm.mk')
        self.genfile("package.spec", "%s.spec" % self.pname)

    def sbuild(self):
        super(RpmPackageMaker, self).sbuild()

        self.build_srpm()

    def build(self):
        super(RpmPackageMaker, self).build()

        self.build_rpm()



class DebPackageMaker(TgzPackageMaker):
    _format = "deb"

    def configure(self):
        super(DebPackageMaker, self).configure()

        debiandir = os.path.join(self.workdir, 'debian')

        if not os.path.exists(debiandir):
            os.makedirs(debiandir, 0755)

        os.makedirs(os.path.join(debiandir, 'source'), 0755)

        self.genfile('debian/rules')
        self.genfile('debian/control')
        self.genfile('debian/copyright')
        self.genfile('debian/changelog')
        self.genfile('debian/dirs')
        self.genfile('debian/compat')
        self.genfile('debian/source/format')
        self.genfile('debian/source/options')

        os.chmod(os.path.join(self.workdir, 'debian/rules'), 0755)

    def sbuild(self):
        """FIXME: What should be done for building source packages?
        """
        super(DebPackageMaker, self).sbuild()
        self.shell("dpkg-buildpackage -S")

    def build(self):
        """Which is better to build?

        * debuild -us -uc
        * fakeroot debian/rules binary
        """
        super(DebPackageMaker, self).build()
        self.shell('fakeroot debian/rules binary')



TgzPackageMaker.register()
RpmPackageMaker.register()
DebPackageMaker.register()



def load_plugins(package_makers_map=PACKAGE_MAKERS):
    plugins = os.path.join(get_python_lib(), "pmaker", "*plugin*.py")
    csfx = "PackageMaker"

    for modpy in glob.glob(plugins):
        modn = os.path.basename(modpy).replace(".py")
        mod = __import__("pmaker.%s" % modn)
        pms = [c for n, c in inspect.getmembers(mod) if inspect.isclass(c) and n.endswith(csfx)]
        c.register(package_makers_map)


def do_packaging(pkg, filelist, options, pmaps=PACKAGE_MAKERS):
    cls = pmaps.get((options.type, options.format), TgzPackageMaker)
    logging.info(" Use %s class: type=%s, format=%s" % (cls.__name__, cls.type(), cls.format()))
    cls(pkg, filelist, options).run()


def do_packaging_self(options):
    version = __version__
    if not options.release_build:
        version += ".%s" % date(simple=True)

    plugin_files = []
    if options.include_plugins:
        plugin_files = options.include_plugins.split(",")

    name = "packagemaker"
    workdir = tempfile.mkdtemp(dir='/tmp', prefix='pm-')
    summary = "A python script to build packages from existing files on your system"
    relations = ""
    packager = __author__
    mail = __email__
    url = __website__

    pkglibdir = os.path.join(workdir, get_python_lib()[1:], "pmaker")
    bindir = os.path.join(workdir, 'usr', 'bin')
    bin = os.path.join(bindir, 'pmaker')

    filelist = os.path.join(workdir, "files.list")

    prog = sys.argv[0]

    cmd_opts = "-n %s --pversion %s -w %s --license GPLv3+ --ignore-owner " % (name, version, workdir)
    cmd_opts += " --destdir %s --no-rpmdb --url %s --upto %s" % (workdir, url, options.upto)
    cmd_opts += " --summary '%s' --packager '%s' --mail %s" % (summary, packager, mail)

    if relations:
        cmd_opts += " --relations '%s' " % relations

    if options.debug:
        cmd_opts += " --debug"

    if options.no_mock:
        cmd_opts += " --no-mock"

    if options.dist:
        cmd_opts += " --dist %s" % options.dist

    if options.format:
        cmd_opts += " --format %s" % options.format

    createdir(pkglibdir, mode=0755)
    shell2("install -m 644 %s %s/__init__.py" % (prog, pkglibdir))

    for f in plugin_files:
        if not os.path.exists(f):
            logging.warn("Plugin %s does not found. Skip it" % f)
            continue

        nf = f.replace("pmaker-", "")
        shell2("install -m 644 %s %s" % (f, os.path.join(pkglibdir, nf)))

    createdir(bindir)

    open(bin, "w").write("""\
#! /usr/bin/python
import sys, pmaker

pmaker.main(sys.argv)
""")
    shell("chmod +x %s" % bin)

    open(filelist, "w").write("""\
%s
%s/*
""" % (bin, pkglibdir))

    # @see /usr/lib/rpm/brp-python-bytecompile:
    pycompile = "import compileall, os; compileall.compile_dir(os.curdir, force=1)"
    compile_pyc = "python -c '%s'" % pycompile
    compile_pyo = "python -O -c '%s' > /dev/null" % pycompile

    shell2(compile_pyc, pkglibdir)
    shell2(compile_pyo, pkglibdir)

    cmd = "python %s %s %s" % (prog, cmd_opts, filelist)

    logging.info(" executing: %s" % cmd)
    os.system(cmd)


def show_examples(logs=EXAMPLE_LOGS):
    for log in logs:
        print >> sys.stdout, log


def dump_rc(rc=EXAMPLE_RC):
    print >> sys.stdout, rc



class TestMainProgram00SingleFileCases(unittest.TestCase):

    def setUp(self):
        self.workdir = tempfile.mkdtemp(dir='/tmp', prefix='pmaker-tests')

        target = "/etc/resolv.conf"
        self.cmd = "echo %s | python %s -n resolvconf -w %s " % (target, sys.argv[0], self.workdir)

        logging.info("start") # dummy log

    def tearDown(self):
        rm_rf(self.workdir)

    def test_packaging_setup_wo_rpmdb(self):
        """Setup without rpm database
        """
        cmd = self.cmd + "--upto setup --no-rpmdb -"
        self.assertEquals(os.system(cmd), 0)

    def test_packaging_configure_wo_rpmdb(self):
        """Configure without rpm database
        """
        cmd = self.cmd + "--upto configure --no-rpmdb -"
        self.assertEquals(os.system(cmd), 0)

    def test_packaging_sbuild_wo_rpmdb_wo_mock(self):
        """Build src package without rpm database without mock
        """
        cmd = self.cmd + "--upto sbuild --no-rpmdb --no-mock -"
        self.assertEquals(os.system(cmd), 0)
        self.assertTrue(len(glob.glob("%s/*/*.src.rpm" % self.workdir)) > 0)

    def test_packaging_build_rpm_wo_rpmdb_wo_mock(self):
        """Build package without rpm database without mock
        """
        cmd = self.cmd + "--upto build --no-rpmdb --no-mock -"
        self.assertEquals(os.system(cmd), 0)
        self.assertTrue(len(glob.glob("%s/*/*.noarch.rpm" % self.workdir)) > 0)

    def test_packaging_wo_rpmdb_wo_mock(self):
        """Build package without rpm database without mock (no --upto option)
        """
        cmd = self.cmd + "--no-rpmdb --no-mock -"
        self.assertEquals(os.system(cmd), 0)
        self.assertTrue(len(glob.glob("%s/*/*.noarch.rpm" % self.workdir)) > 0)

    def test_packaging_with_relations_wo_rpmdb_wo_mock(self):
        """Build package with some additional relations without rpm database
        without mock (no --upto option).
        """
        cmd = self.cmd + "--relations \"requires:bash,zsh;obsoletes:sysdata;conflicts:sysdata\" "
        cmd += "--no-rpmdb --no-mock -"
        self.assertEquals(os.system(cmd), 0)
        self.assertTrue(len(glob.glob("%s/*/*.noarch.rpm" % self.workdir)) > 0)

    def test_packaging_symlink_wo_rpmdb_wo_mock(self):
        idir = os.path.join(self.workdir, "var", "lib", "net")
        os.makedirs(idir)
        os.symlink("/etc/resolv.conf", os.path.join(idir, "resolv.conf"))

        cmd = "echo %s/resolv.conf | python %s -n resolvconf -w %s --no-rpmdb --no-mock -" % (idir, sys.argv[0], self.workdir)

        self.assertEquals(os.system(cmd), 0)
        self.assertTrue(len(glob.glob("%s/*/*.noarch.rpm" % self.workdir)) > 0)

    def test_packaging_wo_rpmdb_wo_mock_with_destdir(self):
        destdir = os.path.join(self.workdir, "destdir")
        createdir(os.path.join(destdir, 'etc'))
        shell("cp /etc/resolv.conf %s/etc" % destdir)

        cmd = "echo %s/etc/resolv.conf | python %s -n resolvconf -w %s --no-rpmdb --no-mock --destdir=%s -" % \
            (destdir, sys.argv[0], self.workdir, destdir)

        self.assertEquals(os.system(cmd), 0)
        self.assertTrue(len(glob.glob("%s/*/*.noarch.rpm" % self.workdir)) > 0)

    def test_packaging_with_rpmdb_wo_mock(self):
        cmd = self.cmd + "--no-mock -"
        self.assertEquals(os.system(cmd), 0)
        self.assertTrue(len(glob.glob("%s/*/*.noarch.rpm" % self.workdir)) > 0)

    def test_packaging_with_rpmdb_with_mock(self):
        cmd = self.cmd + "-"
        self.assertEquals(os.system(cmd), 0)
        self.assertTrue(len(glob.glob("%s/*/*.noarch.rpm" % self.workdir)) > 0)

    def test_packaging_deb(self):
        """'dh' may not be found on this system so that it will only go up to
        'configure' step.
        """
        cmd = self.cmd + "--upto configure --format deb --no-rpmdb -"
        self.assertEquals(os.system(cmd), 0)

    def test_packaging_with_rc(self):
        rc = os.path.join(self.workdir, "rc")
        prog = sys.argv[0]

        #PMAKERRC=./pmakerrc.sample python pmaker.py files.list --upto configure
        cmd = "python %s --dump-rc > %s" % (prog, rc)
        self.assertEquals(os.system(cmd), 0)

        cmd = "echo /etc/resolv.conf | PMAKERRC=%s python %s -w %s --upto configure -" % (rc, prog, self.workdir)
        self.assertEquals(os.system(cmd), 0)

    def test_packaging_wo_rpmdb_wo_mock_with_a_custom_template(self):
        global TEMPLATES

        prog = sys.argv[0]
        tmpl0 = os.path.join(self.workdir, "package.spec")

        open(tmpl0, 'w').write(TEMPLATES['package.spec'])

        cmd = self.cmd + "--no-rpmdb --no-mock --templates=\"package.spec:%s\" -" % tmpl0
        self.assertEquals(os.system(cmd), 0)
        self.assertTrue(len(glob.glob("%s/*/*.src.rpm" % self.workdir)) > 0)



class TestMainProgram01MultipleFilesCases(unittest.TestCase):

    def setUp(self):
        self.workdir = tempfile.mkdtemp(dir='/tmp', prefix='pmaker-tests')
        logging.info("start")

        self.filelist = os.path.join(self.workdir, 'file.list')

        targets = [
            '/etc/auto.*', '/etc/modprobe.d/*', '/etc/resolv.conf',
            '/etc/security/limits.conf', '/etc/security/access.conf',
            '/etc/grub.conf', '/etc/system-release', '/etc/skel',
        ]
        self.files = [f for f in targets if os.path.exists(f)]

    def tearDown(self):
        rm_rf(self.workdir)

    def test_packaging_build_rpm_wo_mock(self):
        open(self.filelist, 'w').write("\n".join(self.files))

        cmd = "python %s -n etcdata -w %s --upto build --no-mock %s" % (sys.argv[0], self.workdir, self.filelist)
        self.assertEquals(os.system(cmd), 0)
        self.assertEquals(len(glob.glob("%s/*/*.src.rpm" % self.workdir)), 1)
        self.assertEquals(len(glob.glob("%s/*/*.noarch.rpm" % self.workdir)), 2) # etcdata and etcdata-overrides



def run_doctests(verbose):
    doctest.testmod(verbose=verbose)


def run_unittests(verbose, test_choice):
    minor = sys.version_info[1]

    def tsuite(testcase):
        return unittest.TestLoader().loadTestsFromTestCase(testcase)

    basic_tests = [
        TestDecoratedFuncs,
        TestFuncsWithSideEffects,
        TestFileOperations,
        TestFilelistCollector,
    ]

    system_tests = [
        TestMainProgram01MultipleFilesCases,
        TestMainProgram00SingleFileCases,
    ]

    suites = [tsuite(c) for c in basic_tests]

    if test_choice == TEST_FULL:
        suites += [tsuite(c) for c in system_tests]

    tests = unittest.TestSuite(suites)

    if minor >= 5:
        unittest.TextTestRunner(verbosity=(verbose and 2 or 0)).run(tests)
        #unittest.main(argv=sys.argv[:1], verbosity=)
    else:
        unittest.TextTestRunner().run(tests)


def run_alltests(verbose, test_choice):
    run_doctests(verbose)
    run_unittests(verbose, test_choice)


def parse_conf_value(s):
    """Simple and naive parser to parse value expressions in config files.

    >>> assert 0 == parse_conf_value("0")
    >>> assert 123 == parse_conf_value("123")
    >>> assert True == parse_conf_value("True")
    >>> assert [1,2,3] == parse_conf_value("[1,2,3]")
    >>> assert "a string" == parse_conf_value("a string")
    >>> assert "0.1" == parse_conf_value("0.1")
    """
    intp = re.compile(r"^([0-9]|([1-9][0-9]+))$")
    boolp = re.compile(r"^(true|false)$", re.I)
    listp = re.compile(r"^(\[\s*((\S+),?)*\s*\])$")

    def matched(pat, s):
        m = pat.match(s)
        return m is not None

    if not s:
        return ""

    if matched(boolp, s):
        return bool(s)

    if matched(intp, s):
        return int(s)

    if matched(listp, s):
        return eval(s)  # TODO: too danger. safer parsing should be needed.

    return s


def parse_template_list_str(templates):
    """
    simple parser for options.templates.

    >>> assert parse_template_list_str("") == {}
    >>> assert parse_template_list_str("a:b") == {'a': 'b'}
    >>> assert parse_template_list_str("a:b,c:d") == {'a': 'b', 'c': 'd'}
    """
    if templates:
        return dict((kv.split(':') for kv in templates.split(',')))
    else:
        return dict()


def init_defaults_by_conffile(config=None, profile=None, prog="pmaker"):
    """
    Initialize default values for options by loading config files.
    """
    if config is None:
        home = os.environ.get("HOME", os.curdir) # Is there case that $HOME is empty?

        confs = ["/etc/%s.conf" % prog]
        confs += sorted(glob.glob("/etc/%s.d/*.conf" % prog))
        confs += [os.environ.get("%sRC" % prog.upper(), os.path.join(home, ".%src" % prog))]
    else:
        confs = (config,)

    cparser = cp.SafeConfigParser()
    loaded = False

    for c in confs:
        if os.path.exists(c):
            logging.info("Loading config: %s" % c)
            cparser.read(c)
            loaded = True

    if not loaded:
        return {}

    if profile:
        defaults = dict((k, parse_conf_value(v)) for k,v in cparser.items(profile))
    else:
        defaults = cparser.defaults()

#    for sec in cparser.sections():
#        defaults.update(dict(((k, parse_conf_value(v)) for k, v in cparser.items(sec))))

    return defaults


def option_parser(V=__version__, pmaps=PACKAGE_MAKERS, test_choices=TEST_CHOICES):
    global PKG_COMPRESSORS, UPTO

    ver_s = "%prog " + V

    steps = (
        ("setup", "setup the package dir and copy target files in it"),
        ("configure", "arrange build files such like configure.ac, Makefile.am, rpm spec file, debian/*, etc. autotools and python-cheetah will be needed"),
        ("sbuild", "build src package[s]"),
        ("build", "build binary package[s]"),
    )

    upto_params = {
        "choices": [fst for fst, snd in steps],
        "choices_str": ", ".join(("%s (%s)" % (fst, snd) for fst, snd in steps)),
        "default": UPTO,
    }

    ptypes = unique([tf[0] for tf in pmaps.keys()])
    ptypes_help = "Target package type: " + ", ".join(ptypes) + " [%default]"

    pformats = unique([tf[1] for tf in pmaps.keys()])
    pformats_help = "Target package format: " + ", ".join(pformats) + " [%default]"

    use_git = os.system("git --version > /dev/null 2> /dev/null") == 0

    mail = get_email(use_git)
    packager = get_fullname(use_git)
    dist = "fedora-14-%s" % get_arch()

    workdir = os.path.join(os.path.abspath(os.curdir), 'workdir')

    cds = init_defaults_by_conffile()

    defaults = {
        'workdir': cds.get("workdir", workdir),
        'upto': cds.get("upto", upto_params["default"]),
        'type': cds.get("type", "filelist"),
        'format': cds.get("format", "rpm"),
        'compressor': cds.get("compressor", "bz2"),
        'verbose': cds.get("verbose", False),
        'quiet': cds.get("quiet", False),
        'debug': cds.get("debug", False),
        'ignore_owner': cds.get("ignore_owner", False),
        'destdir': cds.get("destdir", ''),
        'with_pyxattr': cds.get("with_pyxattr", False),

        'name': cds.get("name", ""),
        'pversion': cds.get("pversion", "0.1"),
        'group': cds.get("group", "System Environment/Base"),
        'license': cds.get("license", "GPLv2+"),
        'url': cds.get("url", "http://localhost.localdomain"),
        'summary': cds.get("summary", ""),
        'arch': cds.get("arch", False),
        'relations': cds.get("relations", ""),
        'requires': cds.get("requires", ""),
        'packager': cds.get("packager", packager),
        'mail': cds.get("mail", mail),

         # TODO: Detect appropriate distribution (for mock) automatically.
        'dist': cds.get("dist", dist),
        'no_rpmdb': cds.get("no_rpmdb", False),
        'no_mock': cds.get("no_mock", False),

        'force': False,

        # these are not in conf file:
        'show_examples': False,
        'dump_rc': False,
        'tests': False,
        'tlevel': test_choices[0],
        'build_self': False,

        "release_build": False,
        "include_plugins": ",".join(glob.glob("pmaker-plugin-libvirt.py")),
    }

    p = optparse.OptionParser("""%prog [OPTION ...] FILE_LIST

Arguments:

  FILE_LIST  a file contains absolute file paths list or '-' (read paths list
             from stdin).

             The lines starting with '#' in the list file are ignored.

             The '*' character in lines will be treated as glob pattern and
             expanded to the real file names list.

Environment Variables:

  PMAKERRC    Configuration file path. see also: `%prog --dump-rc`

Examples:
  %prog -n foo files.list
  cat files.list | %prog -n foo -  # same as above.

  %prog -n foo --pversion 0.2 -l MIT files.list
  %prog -n foo --requires httpd,/sbin/service files.list

  %prog --tests --debug  # run test suites

  %prog --build-self    # package itself

  see the output of `%prog --show-examples` for more detailed examples.""",
    version=ver_s
    )
    
    p.set_defaults(**defaults)

    bog = optparse.OptionGroup(p, "Build options")
    bog.add_option('-w', '--workdir', help='Working dir to dump outputs [%default]')
    bog.add_option('', '--upto', type="choice", choices=upto_params['choices'],
        help="Which packaging step you want to proceed to: " + upto_params['choices_str'] + " [Default: %default]")
    bog.add_option('', '--type', type="choice", choices=ptypes, help=ptypes_help)
    bog.add_option('', '--format', type="choice", choices=pformats, help=pformats_help)
    bog.add_option('', '--destdir', help="Destdir (prefix) you want to strip from installed path [%default]. "
        "For example, if the target path is '/builddir/dest/usr/share/data/foo/a.dat', "
        "and you want to strip '/builddir/dest' from the path when packaging 'a.dat' and "
        "make it installed as '/usr/share/foo/a.dat' with the package , you can accomplish "
        "that by this option: '--destdir=/builddir/destdir'")
    bog.add_option('', '--templates', help="Use custom template files. "
        "TEMPLATES is a comma separated list of template output and file after the form of "
        "RELATIVE_OUTPUT_PATH_IN_SRCDIR:TEMPLATE_FILE such like 'package.spec:/tmp/foo.spec.tmpl', "
        "and 'debian/rules:mydebrules.tmpl, Makefile.am:/etc/foo/mymakefileam.tmpl'. "
        "Supported template syntax is Python Cheetah: http://www.cheetahtemplate.org .")
    bog.add_option('', '--rewrite-linkto', action='store_true',
        help="Whether to rewrite symlink\'s linkto (path of the objects "
            "that symlink point to) if --destdir is specified")
    bog.add_option('', '--with-pyxattr', action='store_true', help='Get/set xattributes of files with pure python code.')
    p.add_option_group(bog)

    pog = optparse.OptionGroup(p, "Package metadata options")
    pog.add_option('-n', '--name', help='Package name [%default]')
    pog.add_option('', '--group', help='The group of the package [%default]')
    pog.add_option('', '--license', help='The license of the package [%default]')
    pog.add_option('', '--url', help='The url of the package [%default]')
    pog.add_option('', '--summary', help='The summary of the package')
    pog.add_option('-z', '--compressor', type="choice", choices=PKG_COMPRESSORS.keys(),
        help="Tool to compress src archives [%default]")
    pog.add_option('', '--arch', action='store_true', help='Make package arch-dependent [false - noarch]')
    pog.add_option("", "--relations",
        help="Semicolon (;) separated list of a pair of relation type and targets "
        "separated with comma, separated with colon (:), "
        "e.g. 'requires:curl,sed;obsoletes:foo-old'. "
        "Expressions of relation types and targets are varied depends on "
        "package format to use")
    pog.add_option('', '--requires', help='Specify the package requirements as comma separated list')
    pog.add_option('', '--packager', help="Specify packager's name [%default]")
    pog.add_option('', '--mail', help="Specify packager's mail address [%default]")
    pog.add_option('', '--pversion', help="Specify the package version [%default]")
    pog.add_option('', '--ignore-owner', action='store_true', help="Ignore owner and group of files and then treat as root's")
    p.add_option_group(pog)

    rog = optparse.OptionGroup(p, "Options for rpm")
    rog.add_option('', '--dist', help='Target distribution (for mock) [%default]')
    rog.add_option('', '--no-rpmdb', action='store_true', help='Do not refer rpm db to get extra information of target files')
    rog.add_option('', '--no-mock', action="store_true", help='Build RPM with only using rpmbuild (not recommended)')
    rog.add_option('', '--scriptlets', help='Specify the file contains rpm scriptlets')
    p.add_option_group(rog)

    sog = optparse.OptionGroup(p, "Self-build options")
    sog.add_option('', '--release-build', action='store_true', help="Make a release build")
    sog.add_option('', '--include-plugins', help="Comma separated list of plugin files to be included in dist.")
    p.add_option_group(sog)

    tog = optparse.OptionGroup(p, "Test options")
    tog.add_option('', '--tests', action='store_true', help="Run tests.")
    tog.add_option('', '--tlevel', type="choice", choices=test_choices,
        help="Select the level of tests to run. Choices are " + ", ".join(test_choices) + " [%default]")
    p.add_option_group(tog)

    p.add_option('', '--force', action="store_true", help='Force going steps even if the steps looks done')
    p.add_option('-v', '--verbose', action="store_true", help='Verbose mode')
    p.add_option('-q', '--quiet', action="store_true", help='Quiet mode')
    p.add_option('-D', '--debug', action="store_true", help='Debug mode')

    p.add_option('', '--build-self', action="store_true", help='Package itself (self-build)')
    p.add_option('', '--show-examples', action="store_true", help='Show examples')
    p.add_option('', '--dump-rc', action="store_true", help='Show conf file example')

    return p


def main(argv=sys.argv):
    global PKG_COMPRESSORS, TEMPLATES, USE_PYXATTR

    verbose_test = False

    loglevel = logging.INFO
    logdatefmt = '%H:%M:%S' # too much? '%a, %d %b %Y %H:%M:%S'
    logformat = '%(asctime)s [%(levelname)-4s] %(message)s'

    logging.basicConfig(level=loglevel, format=logformat, datefmt=logdatefmt)

    pkg = dict()

    p = option_parser()
    (options, args) = p.parse_args(argv[1:])

    if options.show_examples:
        show_examples()
        sys.exit(0)

    if options.dump_rc:
        dump_rc()
        sys.exit(0)

    if options.verbose:
        logging.getLogger().setLevel(logging.INFO)
        verbose_test = False
    else:
        logging.getLogger().setLevel(logging.WARNING)
        verbose_test = False

    if options.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        verbose_test = True

    if options.build_self:
        if options.tests:
            rc = os.system("python %s --tests --tlevel=full -v" % argv[0])
            if rc != 0:
                sys.exit(rc)

        do_packaging_self(options)
        sys.exit()

    if options.tests:
        run_alltests(verbose_test, options.tlevel)
        sys.exit()

    if len(args) < 1:
        p.print_usage()
        sys.exit(1)

    filelist = args[0]

    if options.arch:
        pkg['noarch'] = False
    else:
        pkg['noarch'] = True

    if options.relations:  # e.g. 'requires:curl,sed;obsoletes:foo-old'
        pkg['relations'] = [rel.split(":") for rel in options.relations.split(";")]

    if options.templates:
        for tgt, tmpl in parse_template_list_str(options.templates).iteritems():
            if TEMPLATES.has_key(tgt):
                TEMPLATES[tgt] = open(tmpl).read()
            else:
                logging.warn(" target output %s is not defined in template list" % tgt)

    if options.scriptlets:
        try:
            scriptlets = open(options.scriptlets).read()
        except IOError:
            logging.warn(" Could not open %s to read scriptlets" % options.scriptlets)
            scriptlets = ""

        pkg['scriptlets'] = scriptlets

    if not options.name:
        print >> sys.stderr, "You must specify the package name with '--name' option"
        sys.exit(-1)

    pkg['name'] = options.name
    pkg['release'] = '1'
    pkg['group'] = options.group
    pkg['license'] = options.license
    pkg['url'] = options.url

    pkg['version'] = options.pversion
    pkg['packager'] = options.packager
    pkg['mail'] = options.mail

    pkg['workdir'] = os.path.abspath(os.path.join(options.workdir, "%(name)s-%(version)s" % pkg))
    pkg['srcdir'] = os.path.join(pkg['workdir'], 'src')

    pkg['compressor'] = {
        'ext': options.compressor,
        'am_opt': PKG_COMPRESSORS.get(options.compressor),
    }

    pkg['dist'] = options.dist

    # TODO: Revert locale setting change just after timestamp was gotten.
    locale.setlocale(locale.LC_ALL, "C")
    pkg['date'] = {
        'date': date(rfc2822=True),
        'timestamp': date(),
    }
    pkg['host'] = hostname()

    pkg['format'] = options.format

    if options.with_pyxattr:
        if not USE_PYXATTR:
            logging.warn(" pyxattr module is not found so that it will not be used.")
    else:
        USE_PYXATTR = False

    pkg['destdir'] = options.destdir.rstrip(os.path.sep)

    if options.summary:
        pkg['summary'] = options.summary
    else:
        pkg['summary'] = 'Custom package of ' + options.name

    if options.requires:
        pkg['requires'] = options.requires.split(',')
    else:
        pkg['requires'] = []

    do_packaging(pkg, filelist, options)


if __name__ == '__main__':
    main()

# vim: set sw=4 ts=4 expandtab:
