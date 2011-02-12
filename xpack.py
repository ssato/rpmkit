#! /usr/bin/python
#
# xpack.py - X (files, dirs, ...) Packager, successor of filelist2rpm.py.
#
# It will try gathering files in given file list, and then:
#
# * arrange src tree contains these files with these relative path kept
# * generate packaging metadata like RPM SPEC, debian/rules, etc.
# * build package such as rpm, src.rpm, deb, etc.
#
# NOTE: The permissions of the files may be lost during packaging.  If you want
# to force set permissions as you wanted, specify these in the %files section
# in the rpm spec explicitly.
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
# SEE ALSO: http://docs.fedoraproject.org/en-US/Fedora_Draft_Documentation/0.1/html/RPM_Guide/ch-creating-rpms.html
# SEE ALSO: http://docs.fedoraproject.org/en-US/Fedora_Draft_Documentation/0.1/html/RPM_Guide/ch-rpm-programming-python.html
# SEE ALSO: http://cdbs-doc.duckcorp.org
# SEE ALSO: https://wiki.duckcorp.org/DebianPackagingTutorial/CDBS
#
# Requirements:
# * python-cheetah: EPEL should be needed for RHEL
# * rpm-python
#
# TODO:
# * keep permissions of targets in tar archives
# * test --pkgfmt=deb (.deb output)
# * sort out command line options
#

from Cheetah.Template import Template
from itertools import chain, count, groupby

import copy
import datetime
import doctest
import email
import glob
import grp
import locale
import logging
import optparse
import os
import os.path
import cPickle as pickle
import pwd
import shutil
import socket
import stat
import subprocess
import sys
import unittest
import tempfile

import rpm

try:
    import xattr   # pyxattr
    USE_PYXATTR = True

except ImportError:
    # Make up a 'Null-Object' like class mimics xattr module.
    class xattr:
        @classmethod
        def get_all(*args):
            return ()
        @classmethod
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
    import md5
    import sha as sha1



__version__ = "0.0.99"


PKG_COMPRESSORS = {
    # extension: am_option,
    'xz'    : 'dist-xz',
    'bz2'   : 'dist-bzip2',
    'gz'    : '',
}


PKG_METADATA_FMTS = {
    'description': """\
This package provides some backup data collected on %(host)s
by %(packager)s at %(date)s.
""",
}


TEMPLATES = {
    "configure.ac": """\
AC_INIT([$name],[$version])
AM_INIT_AUTOMAKE([${compressor.am_opt} foreign subdir-objects])

dnl http://www.flameeyes.eu/autotools-mythbuster/automake/silent.html
m4_ifdef([AM_SILENT_RULES],[AM_SILENT_RULES([yes])])

dnl TODO: fix autoconf macros used.
AC_PROG_LN_S
AC_PROG_MKDIR_P
AC_PROG_SED

dnl TODO: Is it better to generate ${name}.spec from ${name}.spec.in ?
AC_CONFIG_FILES([
Makefile
])

AC_OUTPUT
""",
    "Makefile.am": """\
#if $rpm
EXTRA_DIST = ${name}.spec rpm.mk

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
""",
    "rpm.mk": """\
#raw
rpmdir = $(abs_builddir)/rpm
rpmdirs = $(addprefix $(rpmdir)/,RPMS BUILD BUILDROOT)

rpmbuild = rpmbuild \
--define "_topdir $(rpmdir)" \
--define "_srcrpmdir $(abs_builddir)" \
--define "_sourcedir $(abs_builddir)" \
--define "_buildroot $(rpmdir)/BUILDROOT" \
$(NULL)

$(rpmdirs):
\t$(MKDIR_P) $@

rpm srpm: $(PACKAGE).spec dist $(rpmdirs)

rpm:
\t$(rpmbuild) -bb $< && mv $(rpmdir)/RPMS/*/*.rpm $(abs_builddir)

srpm:
\t$(rpmbuild) -bs $<

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


%description
${description}


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

cat <<EOF > README
$summary
EOF

cat /dev/null > MANIFESTS
cat /dev/null > MANIFESTS.overrides

#for $fi in $fileinfos
#if $fi.conflicts
echo $fi.target >> MANIFESTS.overrides
#else
echo $fi.target >> MANIFESTS
#end if
#end for


%build
%configure
make


%install
rm -rf \$RPM_BUILD_ROOT
make install DESTDIR=\$RPM_BUILD_ROOT

# s,%files,%files -f files.list, if enable the following:
#find \$RPM_BUILD_ROOT -type f | sed "s,^\$RPM_BUILD_ROOT,,g" > files.list


%clean
rm -rf \$RPM_BUILD_ROOT


%files
%defattr(-,root,root,-)
%doc README
#for $fi in $fileinfos
#if not $fi.conflicts
$fi.rpm_attr$fi.target
#end if
#end for


#if $conflicts.names
%files          overrides
%defattr(-,root,root,-)
%doc MANIFESTS.overrides
#for $fi in $fileinfos
#if $fi.conflicts
$fi.rpm_attr$fi.target
#end if
#end for
#end if


%changelog
* $date.timestamp ${packager_name} <${packager_mail}> - ${version}-${release}
- Initial packaging.
""",
    "debian/control": """\
Source: $name
Priority: optional
Maintainer: $packager_name <$packager_mail>
Build-Depends: debhelper (>= 5), cdbs, autotools-dev
Standards-Version: 3.7.3
Homepage: $url

Package: $name
Section: database
Architecture: any
#set $requires_list = ', ' + ', '.join($requires)
Depends: \${misc:Depends}, \${shlibs:Depends}$requires_list
Description: $summary
  $summary
""",
    "debian/rules": """\
#!/usr/bin/make -f
#import os.path

include /usr/share/cdbs/1/rules/debhelper.mk
include /usr/share/cdbs/1/class/autotools.mk

DEB_INSTALL_DIRS_${name} = \\
#set $dirs = []
#for $fi in $fileinfos
#if $fi.target not in $conflicts.files
#set $dir = os.path.dirname($fi.target)
#if $dir not in $dirs
\t$dir \\
#set $dirs = $dirs + [$dir]
#end if
#end if
#end for
\t\$(NULL)

install/$name::
\tcp -ar debian/tmp/* debian/$name/
""",
    "debian/copyright": """\
This package was debianized by $packager_name <$packager_mail> on
$date.

This package is distributed under $license.
""",
    "debian/changelog": """\
$name ($version) unstable; urgency=low

  * New upstream release

 -- $packager_name <$packager_mail> $date.date
""",
}


EXAMPLE_LOGS = [
"""
$ ls
xpack.py  files.list
$ cat files.list
/etc/auto.master
/etc/auto.misc
/etc/auto.net
/etc/auto.smb
/etc/modprobe.d/blacklist-visor.conf
/etc/modprobe.d/blacklist.conf
/etc/modprobe.d/dist-alsa.conf
/etc/modprobe.d/dist-oss.conf
/etc/modprobe.d/dist.conf
/etc/modprobe.d/libmlx4.conf
/etc/resolv.conf
/etc/yum.repos.d/fedora.repo
$ python xpack.py -n foo -w ./0 -q files.list
$ ls
0  xpack.py  files.list
$ ls 0
foo-0.1  foo-0.1-1.fc14.src.rpm  foo.spec
$ ls 0/foo-0.1
Makefile     Makefile.in  autom4te.cache  config.status  configure.ac            foo-0.1.tar.gz  foo.spec    missing  rpm.mk
Makefile.am  aclocal.m4   config.log      configure      foo-0.1-1.fc14.src.rpm  foo-0.1.tar.xz  install-sh  rpm      src
$ make -C 0/foo-0.1 rpm > /dev/null 2> /dev/null
$ ls 0/foo-0.1
Makefile     autom4te.cache  configure.ac               foo-0.1.tar.xz                       missing
Makefile.am  config.log      foo-0.1-1.fc14.noarch.rpm  foo-overrides-0.1-1.fc14.noarch.rpm  rpm
Makefile.in  config.status   foo-0.1-1.fc14.src.rpm     foo.spec                             rpm.mk
aclocal.m4   configure       foo-0.1.tar.gz             install-sh                           src
$
$ cat files.list | python xpack.py -n foo -w ./1 -
12:10:06 [INFO]  /etc/auto.master is owned by autofs, that is, it will be conflicts with autofs
12:10:06 [INFO]  /etc/auto.misc is owned by autofs, that is, it will be conflicts with autofs
12:10:06 [INFO]  /etc/auto.net is owned by autofs, that is, it will be conflicts with autofs
12:10:06 [INFO]  /etc/auto.smb is owned by autofs, that is, it will be conflicts with autofs
12:10:06 [INFO]  /etc/modprobe.d/blacklist-visor.conf is owned by pilot-link, that is, it will be conflicts with pilot-link
12:10:06 [INFO]  /etc/modprobe.d/blacklist.conf is owned by hwdata, that is, it will be conflicts with hwdata
12:10:06 [INFO]  /etc/modprobe.d/dist-alsa.conf is owned by module-init-tools, that is, it will be conflicts with module-init-tools
12:10:06 [INFO]  /etc/modprobe.d/dist-oss.conf is owned by module-init-tools, that is, it will be conflicts with module-init-tools
12:10:06 [INFO]  /etc/modprobe.d/dist.conf is owned by module-init-tools, that is, it will be conflicts with module-init-tools
12:10:06 [INFO]  /etc/modprobe.d/libmlx4.conf is owned by libmlx4, that is, it will be conflicts with libmlx4
12:10:06 [INFO]  /etc/yum.repos.d/fedora.repo is owned by fedora-release, that is, it will be conflicts with fedora-release
12:10:06 [INFO]  Creating a directory: /tmp/t/1/foo-0.1
12:10:06 [INFO]  Creating a directory: /tmp/t/1/foo-0.1/src
12:10:06 [INFO]  Copying: /etc/auto.master -> /tmp/t/1/foo-0.1/src/etc/auto.master
12:10:06 [INFO]  Copying: /etc/auto.misc -> /tmp/t/1/foo-0.1/src/etc/auto.misc
12:10:06 [INFO]  Copying: /etc/auto.net -> /tmp/t/1/foo-0.1/src/etc/auto.net
12:10:06 [INFO]  Copying: /etc/auto.smb -> /tmp/t/1/foo-0.1/src/etc/auto.smb
12:10:06 [INFO]  Copying: /etc/resolv.conf -> /tmp/t/1/foo-0.1/src/etc/resolv.conf
12:10:06 [INFO]  Copying: /etc/modprobe.d/blacklist-visor.conf -> /tmp/t/1/foo-0.1/src/etc/modprobe.d/blacklist-visor.conf
12:10:06 [INFO]  Copying: /etc/modprobe.d/blacklist.conf -> /tmp/t/1/foo-0.1/src/etc/modprobe.d/blacklist.conf
12:10:06 [INFO]  Copying: /etc/modprobe.d/dist-alsa.conf -> /tmp/t/1/foo-0.1/src/etc/modprobe.d/dist-alsa.conf
12:10:06 [INFO]  Copying: /etc/modprobe.d/dist-oss.conf -> /tmp/t/1/foo-0.1/src/etc/modprobe.d/dist-oss.conf
12:10:06 [INFO]  Copying: /etc/modprobe.d/dist.conf -> /tmp/t/1/foo-0.1/src/etc/modprobe.d/dist.conf
12:10:06 [INFO]  Copying: /etc/modprobe.d/libmlx4.conf -> /tmp/t/1/foo-0.1/src/etc/modprobe.d/libmlx4.conf
12:10:06 [INFO]  Copying: /etc/yum.repos.d/fedora.repo -> /tmp/t/1/foo-0.1/src/etc/yum.repos.d/fedora.repo
12:10:06 [INFO]  Copying: /tmp/t/1/foo-0.1/foo.spec -> /tmp/t/1/foo-0.1/..
12:10:06 [INFO]  Run: autoreconf -vfi
12:10:10 [INFO]  Run: ./configure
12:10:11 [INFO]  Run: make srpm
12:10:12 [INFO]  Copying: /tmp/t/1/foo-0.1/foo-0.1-1.fc14.src.rpm -> /tmp/t/1/foo-0.1/../
$ ls 1
foo-0.1  foo-0.1-1.fc14.src.rpm  foo.spec
$ ls 1/foo-0.1
Makefile     Makefile.in  autom4te.cache  config.status  configure.ac            foo-0.1.tar.gz  foo.spec    missing  rpm.mk
Makefile.am  aclocal.m4   config.log      configure      foo-0.1-1.fc14.src.rpm  foo-0.1.tar.xz  install-sh  rpm      src
$
""",
"""
$ echo /etc/resolv.conf | python xpack.py -n resolvconf -w 2 --build-rpm -
12:12:20 [INFO]  Creating a directory: /tmp/t/2/resolvconf-0.1
12:12:20 [INFO]  Creating a directory: /tmp/t/2/resolvconf-0.1/src
12:12:20 [INFO]  Copying: /etc/resolv.conf -> /tmp/t/2/resolvconf-0.1/src/etc/resolv.conf
12:12:20 [INFO]  Copying: /tmp/t/2/resolvconf-0.1/resolvconf.spec -> /tmp/t/2/resolvconf-0.1/..
12:12:20 [INFO]  Run: autoreconf -vfi
12:12:23 [INFO]  Run: ./configure
12:12:25 [INFO]  Run: make srpm
12:12:25 [INFO]  Copying: /tmp/t/2/resolvconf-0.1/resolvconf-0.1-1.fc14.src.rpm -> /tmp/t/2/resolvconf-0.1/../
12:12:25 [INFO]  Run: mock --version > /dev/null
12:12:26 [INFO]  Run: mock -r fedora-14-i386 resolvconf-0.1-1.*.src.rpm
12:12:51 [INFO]  Copying: /var/lib/mock/fedora-14-i386/result/resolvconf-0.1-1.fc14.src.rpm -> /tmp/t/2/resolvconf-0.1/../
12:12:51 [INFO]  Copying: /var/lib/mock/fedora-14-i386/result/resolvconf-0.1-1.fc14.noarch.rpm -> /tmp/t/2/resolvconf-0.1/../
$ ls 2/
resolvconf-0.1  resolvconf-0.1-1.fc14.noarch.rpm  resolvconf-0.1-1.fc14.src.rpm  resolvconf.spec
$ rpm -qlp 2/resolvconf-0.1-1.fc14.noarch.rpm 
/etc/resolv.conf
/usr/share/doc/resolvconf-0.1
/usr/share/doc/resolvconf-0.1/README
$
""",
"""
$ ls
xpack.py  srv
$ ls srv/isos/
rhel-server-5.6-i386-dvd.iso
$ echo /tmp/t/srv/isos/rhel-server-5.6-i386-dvd.iso | \\
> python xpack.py -n rhel-server-5-6-i386-dvd-iso -w ./w \\
> --destdir /tmp/t/ --build-rpm --no-mock -
10:50:44 [INFO]  Creating a directory: /tmp/t/w/rhel-server-5-6-i386-dvd-iso-0.1
10:50:44 [INFO]  Creating a directory: /tmp/t/w/rhel-server-5-6-i386-dvd-iso-0.1/src
10:50:44 [INFO]  Copying: /tmp/t/srv/isos/rhel-server-5.6-i386-dvd.iso -> /tmp/t/w/rhel-server-5-6-i386-dvd-iso-0.1/src/srv/isos/rhel-server-5.6-i386-dvd.iso
10:50:44 [INFO]  Copying: /tmp/t/w/rhel-server-5-6-i386-dvd-iso-0.1/rhel-server-5-6-i386-dvd-iso.spec -> /tmp/t/w/rhel-server-5-6-i386-dvd-iso-0.1/..
10:50:44 [INFO]  Run: autoreconf -vfi
10:50:52 [INFO]  Run: ./configure
10:50:54 [INFO]  Run: make srpm
10:50:57 [INFO]  Copying: /tmp/t/w/rhel-server-5-6-i386-dvd-iso-0.1/rhel-server-5-6-i386-dvd-iso-0.1-1.fc14.src.rpm -> /tmp/t/w/rhel-server-5-6-i386-dvd-iso-0.1/../
10:50:57 [INFO]  Run: make rpm
10:51:03 [INFO]  Copying: /tmp/t/w/rhel-server-5-6-i386-dvd-iso-0.1/rhel-server-5-6-i386-dvd-iso-0.1-1.fc14.noarch.rpm -> /tmp/t/w/rhel-server-5-6-i386-dvd-iso-0.1/../
10:51:03 [INFO]  Copying: /tmp/t/w/rhel-server-5-6-i386-dvd-iso-0.1/rhel-server-5-6-i386-dvd-iso-0.1-1.fc14.src.rpm -> /tmp/t/w/rhel-server-5-6-i386-dvd-iso-0.1/../
$ ls
xpack.py  srv  w
$ ls w/rhel-server-5-6-i386-dvd-iso-0.1
Makefile     autom4te.cache  configure.ac                                        rhel-server-5-6-i386-dvd-iso-0.1-1.fc14.src.rpm  rpm
Makefile.am  config.log      install-sh                                          rhel-server-5-6-i386-dvd-iso-0.1.tar.gz          rpm.mk
Makefile.in  config.status   missing                                             rhel-server-5-6-i386-dvd-iso-0.1.tar.xz          src
aclocal.m4   configure       rhel-server-5-6-i386-dvd-iso-0.1-1.fc14.noarch.rpm  rhel-server-5-6-i386-dvd-iso.spec
$ rpm -qlp w/rhel-server-5-6-i386-dvd-iso-0.1/rhel-server-5-6-i386-dvd-iso-0.1-1.fc14.noarch.rpm
/srv/isos/rhel-server-5.6-i386-dvd.iso
/usr/share/doc/rhel-server-5-6-i386-dvd-iso-0.1
/usr/share/doc/rhel-server-5-6-i386-dvd-iso-0.1/README
$
""",
]


(TYPE_FILE, TYPE_DIR, TYPE_SYMLINK, TYPE_OTHER, TYPE_UNKNOWN) = \
    ('file', 'dir', 'symlink', 'other', 'unknown')



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
def flattern(xss):
    """
    >>> flattern([])
    []
    >>> flattern([[1,2,3],[4,5]])
    [1, 2, 3, 4, 5]
    >>> flattern([[1,2,[3]],[4,[5,6]]])
    [1, 2, 3, 4, 5, 6]

    tuple:

    >>> flattern([(1,2,3),(4,5)])
    [1, 2, 3, 4, 5]

    generator:

    >>> flattern(((i, i * 2) for i in range(0,5)))
    [0, 0, 1, 2, 2, 4, 3, 6, 4, 8]
    """
    ret = []

    for xs in xss:
        if isinstance(xs, list) or isinstance(xs, tuple) or callable(getattr(xs, 'next', None)):
            ret += flattern(xs)
        else:
            ret.append(xs)

    return ret


def concat(xss):
    """
    >>> concat([[]])
    []
    >>> concat([[1,2,3],[4,5]])
    [1, 2, 3, 4, 5]
    """
    return list(chain(*xss))


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
    FIXME: Is there any cases exist that socket.gethostname() fails?
    """
    try:
        return socket.gethostname()
    except:
        return os.uname()[1]


def date(rfc2822=False):
    if rfc2822:
        return email.Utils.formatdate()
    else:
        return datetime.date.today().strftime("%a %b %_d %Y")


def compile_template(template, params):
    """
    >>> tmpl_s = "a=$a b=$b"
    >>> params = {'a':1, 'b':'b'}
    >>> 
    >>> assert "a=1 b=b" == compile_template(tmpl_s, params)
    """
    if isinstance(template, file):
        tmpl = Template(file=template, searchList=params)
    else:
        tmpl = Template(source=template, searchList=params)

    return tmpl.respond()


def shell(cmd_s, workdir="", log=True):
    """TODO: Popen.communicate might be blocked. How about using
    Popen.wait instead?
    """
    if not workdir:
        workdir = os.path.abspath(os.curdir)

    logging.info(" Run: %s [%s]" % (cmd_s, workdir))

    try:
        pipe = subprocess.Popen([cmd_s], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, cwd=workdir)
        (output, errors) = pipe.communicate()
    except Exception, e:
        raise RuntimeError("Error (%s) during executing: %s" % (repr(e.__class__), e.message))

    if pipe.returncode == 0:
        return (output, errors)
    else:
        raise RuntimeError(" Failed: %s,\n err:\n'''%s'''" % (cmd_s, errors))



def createdir(dir, mode=0700):
    """Create a dir with specified mode.
    """
    logging.info(" Creating a directory: %s" % dir)

    if os.path.exists(dir):
        if os.path.isdir(dir):
            logging.warn(" Directory already exists! Skip it: %s" % dir)
        else:
            raise RuntimeError(" Already exists but not a directory: %s" % dir)
    else:
        os.makedirs(dir, mode)


def rm_rf(dir):
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
    if not os.path.exists(dir):
        return

    if os.path.isfile(dir):
        os.remove(dir)
        return 

    for x in glob.glob(os.path.join(dir, '*')):
        if os.path.isdir(x):
            rm_rf(x)
        else:
            os.remove(x)

    if os.path.exists(dir):
        os.removedirs(dir)


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
        self.assertEquals(checksum(), '0' * len(sha1('').hexdigest()))

    def test_flattern(self):
        self.assertEquals(flattern([]),                               [])
        self.assertEquals(flattern([[1,2,3],[4,5]]),                  [1, 2, 3, 4, 5])
        self.assertEquals(flattern([[1,2,[3]],[4,[5,6]]]),            [1, 2, 3, 4, 5, 6])
        self.assertEquals(flattern([(1,2,3),(4,5)]),                  [1, 2, 3, 4, 5])
        self.assertEquals(flattern(((i, i * 2) for i in range(0,5))), [0, 0, 1, 2, 2, 4, 3, 6, 4, 8])

    def test_unique(self):
        self.assertEquals(unique([]),                       [])
        self.assertEquals(unique([0, 3, 1, 2, 1, 0, 4, 5]), [0, 1, 2, 3, 4, 5])



class TestFuncsWithSideEffects(unittest.TestCase):

    def setUp(self):
        self.workdir = tempfile.mkdtemp()

    def tearDown(self):
        rm_rf(self.workdir)

    def test_createdir_normal(self):
        """TODO: Check mode (permission).
        """
        d = os.path.join(self.workdir, "a")
        createdir(d)

        self.assertTrue(os.path.isdir(d))

    def test_createdir_specials(self):
        self.assertIsNone(createdir(self.workdir))  # try creating dir already exists.

        f = os.path.join(self.workdir, 'a')
        open(f, "w").write("test")
        self.assertRaises(RuntimeError, createdir, f)

    def test_shell(self):
        (o, e) = shell('echo "" > /dev/null', '.', False)
        self.assertEquals(e, "")
        self.assertEquals(o, "")

        self.assertRaises(RuntimeError, shell, 'grep xyz /dev/null')

        if os.getuid() != 0:
            self.assertRaises(RuntimeError, shell, 'ls', '/root')



class Rpm(object):

    RPM_FILELIST_CACHE = os.path.join(os.environ['HOME'], '.cache', 'xpack.rpm.filelist.pkl')

    # RpmFi (FileInfo) keys:
    fi_keys = ('path', 'size', 'mode', 'mtime', 'flags', 'rdev', 'inode',
        'nlink', 'state', 'vflags', 'uid', 'gid', 'checksum')

    @classmethod
    def ts(self):
        return rpm.TransactionSet()

    @classmethod
    def pathinfo(self, path):
        """Get meta data of file or dir from RPM Database.

        @path    Path of the file or directory (relative or absolute)
        @return  A dict; keys are fi_keys (see below)

        >>> hosts = '/etc/hosts'
        >>> pm = '/proc/mounts'
        >>>  
        >>> if os.path.exists('/var/lib/rpm/Basenames'):
        ...     if os.path.exists(hosts):
        ...         pi = Rpm.pathinfo(hosts)
        ...         assert pi.get('path') == hosts
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

    @classmethod
    def each_fileinfo_by_package(self, pname='', pred=true):
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
    def filelist(self, cache=True, expires=1, pkl_proto=pickle.HIGHEST_PROTOCOL):
        """TODO: It should be a heavy and time-consuming task. How to shorten
        this time? - caching, utilize yum's file list database or whatever.

        >>> if os.path.exists('/var/lib/rpm/Basenames'):
        ...     db = Rpm.filelist()
        ...     assert db.get('/etc/hosts') == 'setup'
        """
        data = None

        cache_file = self.RPM_FILELIST_CACHE
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
            data = dict(concat(([(f, h['name']) for f in h['filenames']] for h in Rpm.ts().dbMatch())))

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
    """

    def __getattr__(self, key):
        return self.get(key, None)

    def __setattr__(self, key, val):
        self[key] = val



class FileInfo(ObjDict):
    """The class of which objects to hold meta data of regular files, dirs and
    symlinks. This is for regular file and the super class for other types.
    """
    __ftype = TYPE_FILE

    def __init__(self, path, mode, uid, gid, checksum, xattrs, **kwargs):
        self.path = path
        self.realpath = os.path.realpath(path)

        self.mode = mode
        self.uid= uid
        self.gid = gid
        self.checksum = checksum
        self.xattrs = xattrs or {}

        self.filetype = self.__ftype

        self.perm_default = '644'

        for k,v in kwargs.iteritems():
            self[k] = v

    def _copy_xattrs(self, dest):
        for k,v in self.xattrs.iteritems():
            xattr.set(dest, k, v)

    def _copy(self, dest):
        """Two steps needed to keep the content and metadata of the original file:

        1. Copy itself and its some metadata (owner, mode, etc.)
        2. Copy extra metadata not copyable with the above.

        'cp -a' do these at once and might be suited for most cases.
        """
        global USE_PYXATTR

        if USE_PYXATTR:
            shutil.copy2(self.path, dest)
            self._copy_xattrs(dest)
        else:
            shell("cp -a %s %s" % (self.path, dest))

    def _remove(self, target):
        os.remove(target)

    def __eq__(self, other):
        """self and other are identical, that is, these contents and metadata
        (except for path) are exactly same.

        TODO: Compare the part of the path?
          ex. lhs.path: '/path/to/xyz', rhs.path: '/var/lib/sp2/updates/path/to/xyz'
        """
        if dicts_comp(self, other, ('mode', 'uid', 'gid', 'checksum', 'filetype')):
            return dicts_comp(self.get('xattrs', {}), other.get('xattrs', {}))
        else:
            return False

    def equivalent(self, other):
        """These metadata (path, uid, gid, etc.) do not match but the checksums
        are same, that is, that contents are exactly same.
        """
        return self.checksum == other.checksum

    def copyable(self):
        return True

    def permission(self):
        """permission (mode) can be passed to 'chmod'.
        """
        return oct(stat.S_IMODE(self.mode & 0777))[1:]

    def need_to_chmod(self):
        return self.permission() != self.perm_default

    def need_to_chown(self):
        return self.uid != 0 or self.gid != 0  # 0 == root

    def remove(self):
        self._remove(self.path)

    def copy(self, dest, force=False):
        """Copy to $dest.  'Copy' action varys depends on actual filetype so
        that inherited class must overrride this and related methods (_remove
        and _copy).

        @dest      string  The destination path to copy to
        @force     bool    When True, force overwrite $dest even if it exists
        """
        assert self.path != dest, "Copying src and dst are same!"

        if not self.copyable():
            logging.warn(" Not copyable: %s" % str(self))
            return False

        if os.path.exists(dest):
            logging.info(" Copying destination already exists: '%s'" % dest)

            # TODO: It has negative impact for symlinks.
            #
            #if os.path.realpath(self.path) == os.path.realpath(dest):
            #    logging.warn("Copying src and dest are same actually.")
            #    return False

            if force:
                logging.info(" Removing dest: " % dest)
                self._remove(dest)
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
            shutil.copystat(os.path.dirname(self.path), destdir)

        logging.debug(" Copying from '%s' to '%s'" % (self.path, dest))
        self._copy(dest)

        return True



class DirInfo(FileInfo):

    __ftype = TYPE_DIR

    def __init__(self, path, mode, uid, gid, checksum, xattrs):
        super(DirInfo, self).__init__(path, mode, uid, gid, checksum, xattrs)

        self.perm_default = '755'

    def _remove(self, target):
        if not os.path.isdir(target):
            raise RuntimeError(" '%s' is not a directory! Aborting..." % target)

        os.removedirs(target)

    def _copy(self, dest):
        os.makedirs(dest, mode=self.mode)

        try:
            os.chown(dest, self.uid, self.gid)
        except OSError, e:
            logging.warn(e)

        shutil.copystat(self.path, dest)
        self._copy_xattrs(dest)



class SymlinkInfo(FileInfo):
    __ftype = TYPE_SYMLINK

    def __init__(self, path, mode, uid, gid, checksum, xattrs):
        super(SymlinkInfo, self).__init__(path, mode, uid, gid, checksum, xattrs)
        self.linkto = os.path.realpath(path)

    def _copy(self, dest):
        os.symlink(self.linkto, dest)

    def need_to_chmod(self):
        return False



class OtherInfo(FileInfo):
    """$path may be a socket, FIFO (named pipe), Character Dev or Block Dev, etc.
    """
    __ftype = TYPE_OTHER

    def __init__(self, path, mode, uid, gid, checksum, xattrs):
        super(OtherInfo, self).__init__(path, mode, uid, gid, checksum, xattrs)

    def copyable(self):
        return False



class UnknownInfo(FileInfo):
    """Special case that lstat() failed and cannot stat $path.
    """
    __ftype = TYPE_UNKNOWN

    def __init__(self, path, mode=-1, uid=-1, gid=-1, checksum=checksum(), xattrs={}):
        super(UnknownInfo, self).__init__(path, mode, uid, gid, checksum, xattrs)

    def copyable(self):
        return False



class FileInfoFactory(object):
    """Factory class for *Info.
    """

    def _stat(self, path):
        """
        @path    str     Object's path (relative or absolute)
        @return  A tuple of (mode, uid, gid) or None if OSError was raised.

        >>> ff = FileInfoFactory()
        >>> (_mode, uid, gid) = ff._stat('/etc/hosts')
        >>> assert uid == 0
        >>> assert gid == 0
        >>> #
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

        if fi.need_to_chmod() or fi.need_to_chown():
            fi.rpm_attr = rpm_attr(fi)
        else:
            fi.rpm_attr = ""

        return fi



def process_listfile(list_f):
    """Read paths from given file line by line and returns path list sorted by
    dir names. Empty lines or lines start with '#' are ignored.

    @list_f  File obj of file list.
    """
    return unique([l.rstrip() for l in list_f.readlines() if l and not l.startswith('#')], key=dirname)


def collect(list_f, pkg_name, options):
    """
    Collect FileInfo objects from given file list.
    """
    ff = (options.pkgfmt == 'rpm' and RpmFileInfoFactory() or FileInfoFactory())

    if options.pkgfmt != 'rpm' or options.no_rpmdb:
        filelist_db = dict()
    else:
        filelist_db = Rpm.filelist()

    fileinfos = []

    destdir = options.destdir

    fs = unique(process_listfile(list_f))

    for p in fs:
        fi = ff.create(p)

        f = fi.path

        # FIXME: Is there any better way?
        if destdir:
            if f.startswith(destdir):
                fi.target = f.split(destdir)[1]
            else:
                logging.error(" The path '%s' does not start with given destdir '%s'" % (f, destdir))
                raise RuntimeError("Destdir specified in --destdir and the actual file path are inconsistent.")
        else:
            fi.target = f

        p = filelist_db.get(fi.target, False)

        if p and p != pkg_name:
            logging.info(" %s is owned by %s, that is, it will be conflicts with %s" % (f, p, p))
            fi.conflicts = p
        else:
            fi.conflicts = ""

        fileinfos.append(fi)

    return fileinfos


def to_srcdir(path, workdir=''):
    """
    >>> to_srcdir('/a/b/c')
    'src/a/b/c'
    >>> to_srcdir('a/b')
    'src/a/b'
    >>> to_srcdir('/')
    'src/'
    """
    assert path != '', "Empty path was given"

    return os.path.join(workdir, 'src', path.strip(os.path.sep))


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
    '%attr(664, -, -) '
    >>> fi = FileInfo('/bin/foo', 33261, 1, 1, checksum(),{})
    >>> rpm_attr(fi)
    '%attr(755, bin, bin) '
    """
    m = fileinfo.permission() # ex. '755'
    u = (fileinfo.uid == 0 and '-' or pwd.getpwuid(fileinfo.uid).pw_name)
    g = (fileinfo.gid == 0 and '-' or grp.getgrgid(fileinfo.gid).gr_name)

    return "%%attr(%(m)s, %(u)s, %(g)s) " % {'m':m, 'u':u, 'g':g,}


class PackageMaker(object):

    def __init__(self, package, workdir, destdir="", *args, **kwargs):
        self.package = package
        self.workdir = workdir
        self.destdir = destdir

        self.srcdir = os.path.join(workdir, 'src')

        for k,v in kwargs.iteritems():
            setattr(self, k, v)

    def shell(self, *args):
        return shell(*args, workdir=self.workdir)

    def to_srcdir(self, path):
        """
        >>> pm = PackageMaker({}, '/tmp/w')
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
        global TEMPLATES

        outfile = os.path.join(self.workdir, (output or path))
        open(outfile, 'w').write(compile_template(TEMPLATES[path], self.package))

    def copyfiles(self):
        for fi in self.package['fileinfos']:
            p = fi.path

            if self.destdir:
                p = os.path.join(self.destdir, p.strip(os.path.sep))

            fi.copy(os.path.join(self.workdir, self.to_srcdir(p)))

    def setup(self):
        for d in ('workdir', 'srcdir'):
            createdir(self.package[d])

        self.copyfiles()

    def configure(self):
        self.package['distdata'] = distdata_in_makefile_am([fi.path for fi in self.package['fileinfos']])

        self.genfile('configure.ac')
        self.genfile('Makefile.am')
        self.shell('autoreconf -vfi')

    def build(self):
        self.shell('./configure')
        self.shell('make dist')



class TgzPackageMaker(PackageMaker):
    pass



class RpmPackageMaker(TgzPackageMaker):

    def __init__(self, package, workdir, destdir="", use_mock=False, build_all=False):
        super(RpmPackageMaker, self).__init__(package, workdir, destdir, use_mock, build_all)
        self.use_mock = use_mock
        self.build_all = build_all
        self.package['rpm'] = "yes"

    def build_srpm(self):
        return self.shell('make srpm')

    def build_rpm(self):
        if self.use_mock:
            try:
                self.shell("mock --version > /dev/null")
            except RuntimeError, e:
                logging.warn(" It sesms mock is not found on your system. Fallback to plain rpmbuild...")
                self.use_mock = False

        if self.use_mock:
            self.shell("mock -r %(dist)s %(name)s-%(version)s-%(release)s.*.src.rpm" % self.package)
            return self.shell("mv /var/lib/mock/%(dist)s/result/*.rpm %(workdir)s" % self.package)
        else:
            return self.shell("make rpm")

    def configure(self):
        self.genfile('rpm.mk')
        self.genfile("package.spec", "%s.spec" % self.package['name'])

        super(RpmPackageMaker, self).configure()

    def build(self):
        super(RpmPackageMaker, self).build()

        self.build_srpm()

        if self.build_all:
            self.build_rpm()



class DebPackageMaker(TgzPackageMaker):

    def configure(self):
        super(DebPackageMaker, self).configure()

        debiandir = os.path.join(self.workdir, 'debian')

        if not os.path.exists(debiandir):
            os.makedirs(debiandir, 0755)

        self.genfile('debian/rules')
        self.genfile('debian/control')
        self.genfile('debian/copyright')
        self.genfile('debian/changelog')

    def build(pkg):
        super(DebPackageMaker, self).build()
        self.shell('debuild -us -uc')



def do_packaging(pkg, options):
    pm = globals().get("%sPackageMaker" % options.pkgfmt.title(), TgzPackageMaker)(
        pkg, pkg['workdir'], options.destdir,
        use_mock=(not options.no_mock),
        build_all=options.build_rpm,
    )
    pm.setup()
    pm.configure()
    pm.build()


def show_examples(logs=EXAMPLE_LOGS):
    for log in logs:
        print >> sys.stdout, log



class TestMainProgram00SingleFileCases(unittest.TestCase):

    def setUp(self):
        self.workdir = tempfile.mkdtemp()
        logging.info("") # dummy log

    def tearDown(self):
        rm_rf(self.workdir)

    def test_packaging(self):
        cmd = "echo /etc/resolv.conf | python %s -n resolvconf -w %s -" % (sys.argv[0], self.workdir)
        self.assertEquals(os.system(cmd), 0)
        self.assertTrue(len(glob.glob("%s/*/*.src.rpm" % self.workdir)) > 0)

    def test_packaging_build_rpm(self):
        cmd = "echo /etc/resolv.conf | python %s -n resolvconf -w %s --build-rpm --no-mock -" % (sys.argv[0], self.workdir)
        self.assertEquals(os.system(cmd), 0)
        self.assertTrue(len(glob.glob("%s/*/*.noarch.rpm" % self.workdir)) > 0)

    def test_packaging_build_rpm_with_mock(self):
        cmd = "echo /etc/resolv.conf | python %s -n resolvconf -w %s --build-rpm -" % (sys.argv[0], self.workdir)
        self.assertEquals(os.system(cmd), 0)
        self.assertTrue(len(glob.glob("%s/*/*.noarch.rpm" % self.workdir)) > 0)



class TestMainProgram01MultipleFilesCases(unittest.TestCase):

    def setUp(self):
        self.workdir = tempfile.mkdtemp()
        logging.info("")

        self.filelist = os.path.join(self.workdir, 'file.list')

        targets = [
            '/etc/auto.master', '/etc/auto.misc', '/etc/auto.net', '/etc/auto.smb',
            '/etc/modprobe.d/blacklist.conf', '/etc/modprobe.d/dist-alsa.conf',
            '/etc/modprobe.d/dist-oss.conf', '/etc/modprobe.d/dist.conf',
            '/etc/resolv.conf',
            '/etc/security/limits.conf', '/etc/security/access.conf',
        ]
        self.files = [f for f in targets if os.path.exists(f)]

    def tearDown(self):
        rm_rf(self.workdir)

    def test_packaging_wo_rpmdb_wo_mock(self):
        open(self.filelist, 'w').write("\n".join(self.files))

        cmd = "python %s -n etcdata -w %s --build-rpm --no-rpmdb --no-mock %s" % (sys.argv[0], self.workdir, self.filelist)
        self.assertEquals(os.system(cmd), 0)
        self.assertEquals(len(glob.glob("%s/*/*.src.rpm" % self.workdir)), 1)
        self.assertEquals(len(glob.glob("%s/*/*.noarch.rpm" % self.workdir)), 1)

    def test_packaging_w_rpmdb_wo_mock(self):
        open(self.filelist, 'w').write("\n".join(self.files))

        cmd = "python %s -n etcdata -w %s --build-rpm --no-mock %s" % (sys.argv[0], self.workdir, self.filelist)
        self.assertEquals(os.system(cmd), 0)
        self.assertEquals(len(glob.glob("%s/*/*.src.rpm" % self.workdir)), 1)
        self.assertEquals(len(glob.glob("%s/*/*.noarch.rpm" % self.workdir)), 2) # etcdata and etcdata-overrides



def run_doctests(verbose):
    doctest.testmod(verbose=verbose)


def run_unittests(verbose):
    unittest.main(argv=sys.argv[:1], verbosity=(verbose and 2 or 0))


def option_parser(V=__version__):
    global PKG_COMPRESSORS

    ver_s = "%prog " + V

    workdir = os.path.join(os.path.abspath(os.curdir), 'workdir')
    packager = os.environ.get('USER', 'root')

    defaults = {
        'name': 'foo',
        'group': 'System Environment/Base',
        'license': 'GPLv3+',
        'url': 'file:///' + workdir,
        'description': False,
        'compressor': 'xz',
        'arch': False,
        'requires': [],
        'packager_name': packager,
        'packager_mail': "%s@localhost.localdomain" % packager,
        'package_version': '0.1',
        'workdir': workdir,
        'build_rpm': False,
        'no_mock': False,
         # TODO: Detect appropriate distribution (for mock) automatically.
        'dist': 'fedora-14-i386',
        'pkgfmt': 'rpm',
        'destdir': '',
        'no_rpmdb': False,
        'debug': False,
        'quiet': False,
        'show_examples': False,
        'test': False,
        'doctests': False,
        'unittests': False,
        'with_pyxattr': False,
    }

    p = optparse.OptionParser("""%prog [OPTION ...] FILE_LIST

  where FILE_LIST  = a file contains absolute file paths list or '-' (read
                     paths list from stdin).

                     The lines starting with '#' in the list file are ignored.

Examples:
  %prog -n foo files.list
  cat files.list | %prog -n foo -  # same as above.

  %prog -n foo -v 0.2 -l GPLv3+ files.list
  %prog -n foo --requires httpd,/sbin/service files.list

  see the output of `%prog --show-examples` for more detailed examples.""",
    version=ver_s
    )
    
    p.set_defaults(**defaults)

    pog = optparse.OptionGroup(p, "Package metadata options")
    pog.add_option('-n', '--name', help='Package name [%default]')
    pog.add_option('', '--group', help='The group of the package [%default]')
    pog.add_option('', '--license', help='The license of the package [%default]')
    pog.add_option('', '--url', help='The url of the package [%default]')
    pog.add_option('', '--summary', help='The summary of the package')
    pog.add_option('', '--description', help='The text file contains package description')
    pog.add_option('-z', '--compressor', type="choice", choices=PKG_COMPRESSORS.keys(),
        help="Tool to compress src archives [%default]")
    pog.add_option('', '--arch', action='store_true', help='Make package arch-dependent [false - noarch]')
    pog.add_option('', '--requires', help='Specify the package requirements as comma separated list')
    pog.add_option('', '--packager-name', help="Specify packager's name [%default]")
    pog.add_option('', '--packager-mail', help="Specify packager's mail address [%default]")
    pog.add_option('', '--package-version', help='Specify the package version [%default]')
    p.add_option_group(pog)

    bog = optparse.OptionGroup(p, "Build options")
    bog.add_option('-w', '--workdir', help='Working dir to dump outputs [%default]')
    bog.add_option('', '--build-rpm', action='store_true', help='Whether to build binary rpm [no - srpm only]')
    bog.add_option('', '--no-mock', action="store_true",
        help='Build RPM with using rpmbuild instead of mock (not recommended)')
    bog.add_option('', '--dist', help='Target distribution (for mock) [%default]')
    bog.add_option('', '--pkgfmt', help='Terget package format: tgz, rpm or deb [%default]')
    bog.add_option('', '--destdir', help="Destdir (prefix) you want to strip from installed path [%default]. "
        "For example, if the target path is '/builddir/dest/usr/share/data/foo/a.dat', "
        "and you want to strip '/builddir/dest' from the path when packaging 'a.dat' and "
        "make it installed as '/usr/share/foo/a.dat' with the package , you can accomplish "
        "that by this option: '--destdir=/builddir/destdir'")

    p.add_option_group(bog)

    rog = optparse.OptionGroup(p, "Rpm DB options")
    rog.add_option('', '--no-rpmdb', action='store_true', help='Do not refer rpm db to get extra information of target files')
    p.add_option_group(rog)

    aog = optparse.OptionGroup(p, "Other advanced options")
    aog.add_option('', '--with-pyxattr', action='store_true', help='Get/set xattributes of files with pure python code.')
    p.add_option_group(aog)

    p.add_option('-D', '--debug', action="store_true", help='Debug mode')
    p.add_option('-q', '--quiet', action="store_true", help='Quiet mode')

    p.add_option('', '--show-examples', action="store_true", help='Show examples')

    tog = optparse.OptionGroup(p, "Test options")
    tog.add_option('', '--test', action="store_true", help='Run all tests')
    tog.add_option('', '--doctests', action="store_true", help='Run doc tests')
    tog.add_option('', '--unittests', action="store_true", help='Run unit tests')
    p.add_option_group(tog)

    return p


def main():
    global PKG_COMPRESSORS, USE_PYXATTR, PKG_METADATA_FMTS

    verbose_test = False

    loglevel = logging.INFO
    logdatefmt = '%H:%M:%S' # too much? '%a, %d %b %Y %H:%M:%S'
    logformat = '%(asctime)s [%(levelname)-4s] %(message)s'

    logging.basicConfig(level=loglevel, format=logformat, datefmt=logdatefmt)

    pkg = dict()

    p = option_parser()
    (options, args) = p.parse_args()

    if options.show_examples:
        show_examples()
        sys.exit(0)

    if options.quiet:
        logging.getLogger().setLevel(logging.WARNING)
        verbose_test = False

    if options.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        verbose_test = True

    if options.test:
        run_doctests(verbose_test)
        run_unittests(verbose_test)
        sys.exit()

    if options.doctests:
        run_doctests(verbose_test)
        sys.exit()

    if options.unittests:
        run_unittests(verbose_test)
        sys.exit()

    if len(args) < 1:
        p.print_usage()
        sys.exit(1)

    filelist = args[0]

    if options.arch:
        pkg['noarch'] = False
    else:
        pkg['noarch'] = True

    pkg['name'] = options.name
    pkg['release'] = '1'
    pkg['group'] = options.group
    pkg['license'] = options.license
    pkg['url'] = options.url

    pkg['version'] = options.package_version
    pkg['packager_name'] = options.packager_name
    pkg['packager_mail'] = options.packager_mail

    pkg['date'] = date(rfc2822=True)

    if options.description:
        pkg['description'] = open(options.description).read()
    else:
        pkg['description'] = PKG_METADATA_FMTS.get('description') % \
            { 'host': hostname(), 'packager': pkg['packager_name'], 'date': date(rfc2822=True), }

    pkg['workdir'] = os.path.abspath(os.path.join(options.workdir, "%(name)s-%(version)s" % pkg))
    pkg['srcdir'] = os.path.join(pkg['workdir'], 'src')

    pkg['compressor'] = {
        'ext': options.compressor,
        'am_opt': PKG_COMPRESSORS.get(options.compressor),
    }

    pkg['dist'] = options.dist
    pkg['rpm'] = 1

    # TODO: Revert locale setting change just after timestamp was gotten.
    locale.setlocale(locale.LC_ALL, "C")
    pkg['date'] = {
        'date': date(rfc2822=True),
        'timestamp': date(),
    }

    if filelist == '-':
        list_f = sys.stdin
    else:
        list_f = open(filelist)

    if options.with_pyxattr:
        if not USE_PYXATTR:
            logging.warn(" pyxattr module is not found so that it will not use it")
    else:
        USE_PYXATTR = False

    destdir = options.destdir.rstrip(os.path.sep)
    pkg['destdir'] = destdir

    pkg['fileinfos'] = collect(list_f, pkg['name'], options)
    pkg['conflicts'] = {
        'names': unique((fi.conflicts for fi in pkg['fileinfos'] if fi.conflicts)),
        'files': unique((fi.target for fi in pkg['fileinfos'] if fi.conflicts)),
    }

    if options.summary:
        pkg['summary'] = options.summary
    else:
        pkg['summary'] = 'Custom package of ' + options.name

    if options.requires:
        pkg['requires'] = options.requires.split(',')
    else:
        pkg['requires'] = []

    do_packaging(pkg, options)


if __name__ == '__main__':
    main()

# vim: set sw=4 ts=4 expandtab:
