#! /usr/bin/python
#
# dpack.py - Data Packager, successor of filelist2rpm.py.
#
# It will try gathering files in given file list, and then:
#
# * arrange src tree contains these files with these relative path kept
# * generate packaging metadata like RPM SPEC, debian/rules, etc.
# * build package such as rpm, src.rpm, deb, etc.
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
# SEE ALSO: http://docs.fedoraproject.org/en-US/Fedora_Draft_Documentation/0.1/html/RPM_Guide/ch-creating-rpms.html
# SEE ALSO: http://docs.fedoraproject.org/en-US/Fedora_Draft_Documentation/0.1/html/RPM_Guide/ch-rpm-programming-python.html
# SEE ALSO: http://cdbs-doc.duckcorp.org
# SEE ALSO: https://wiki.duckcorp.org/DebianPackagingTutorial/CDBS
#

from Cheetah.Template import Template
from itertools import chain, count, groupby

import copy
import datetime
import glob
import grp
import locale
import logging
import optparse
import os
import os.path
import pwd
import rpm
import shutil
import stat
import subprocess
import sys

try:
    import xattr   # pyxattr
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

try:
    from hashlib import md5, sha1 #, sha256, sha512
except ImportError:  # python < 2.5
    import md5
    import sha as sha1



__version__ = "0.1"


# TODO: Detect appropriate distribution (for mock) automatically.
TARGET_DIST_DEFAULT = 'fedora-14-i386'


PKG_COMPRESSORS = {
    # extension: am_option,
    'xz'    : 'dist-xz',
    'bz2'   : 'dist-bzip2',
    'gz'    : '',
}


TEMPLATES = {
    "configure.ac": """\
AC_INIT([$name],[$version])
AM_INIT_AUTOMAKE([${compress.am_opt} foreign subdir-objects])

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
    # FIXME: Ugly hack in $files_vars_in_makefile_am.
    "Makefile.am": """\
EXTRA_DIST = ${name}.spec rpm.mk

include \$(abs_srcdir)/rpm.mk

$files_vars_in_makefile_am
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
URL:            file:///$workdir
Source0:        %{name}-%{version}.tar.${compress.ext}
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
#if $noarch
BuildArch:      noarch
#end if
#for $req in $requires
Requires:       $req
#end for


%description
${summary}


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

#if $conflicts.names
cat /dev/null > MANIFESTS.overrides
#for $f in $conflicts.files
echo $f >> MANIFESTS.overrides
#end for
#end if


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
#if $conflicts.names
#for $f in $files.targets
#if $f not in $conflicts.files
$f
#end if
#end for
#else
#for $f in $files.targets
$f
#end for
#end if


#if $conflicts.names
%files          overrides
%defattr(-,root,root,-)
%doc MANIFESTS.overrides
#for $f in $conflicts.files
$f
#end for
#end if


%changelog
* ${timestamp} ${packager_name} <${packager_mail}> - ${version}-${release}
- Initial packaging.
""",
    "debian/control": """\
Source: $name
Priority: optional
Maintainer: $packager_name <$packager_mail>
Build-Depends: debhelper (>= 5), cdbs, autotools-dev
Standards-Version: 3.7.3
Homepage: file:///$workdir

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
#for $f in $files.targets
#if $f not in $conflicts.files
#set $dir = os.path.dirname($f)
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
$timestamp.

This package is distributed under $license.
""",
    "debian/changelog": """\
$name ($version) unstable; urgency=low

  * New upstream release

 -- $packager_name <$packager_mail> $timestamp
""",
}



PKG_DIST_INST_FILES_TMPL = """
pkgdata%(id)sdir = %(dir)s
dist_pkgdata%(id)s_DATA = %(files)s
"""


EXAMPLE_LOGS = [
"""
$ ls
filelist2rpm.py  files.list
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
$ python filelist2rpm.py -n foo -w ./0 -q files.list
$ ls
0  filelist2rpm.py  files.list
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
$ cat files.list | python filelist2rpm.py -n foo -w ./1 -
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
$ echo /etc/resolv.conf | python filelist2rpm.py -n resolvconf -w 2 --build-rpm -
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
filelist2rpm.py  srv
$ ls srv/isos/
rhel-server-5.6-i386-dvd.iso
$ echo /tmp/t/srv/isos/rhel-server-5.6-i386-dvd.iso | \\
> python filelist2rpm.py -n rhel-server-5-6-i386-dvd-iso -w ./w \\
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
filelist2rpm.py  srv  w
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


(TYPE_FILE, TYPE_DIR, TYPE_SYMLINK, TYPE_OTHER) = range(0,4)



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


def compile_template(template, params, outfile):
    if isinstance(template, file):
        tmpl = Template(file=template, searchList=params)
    else:
        tmpl = Template(source=template, searchList=params)

    open(outfile, 'w').write(tmpl.respond())


def shell(cmd_s, workdir="", log=True):
    """TODO: Popen.communicate might be blocked. How about using Popen.wait instead?
    """
    if not workdir:
        workdir = os.path.abspath(os.curdir)

    logging.info(" Run: %s [in %s]" % (cmd_s, workdir))

    pipe = subprocess.Popen([cmd_s], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, cwd=workdir)
    (output, errors) = pipe.communicate()

    if pipe.returncode == 0:
        return (output, errors)
    else:
        raise RuntimeError(" Failed: %s,\n err:\n'''%s'''" % (cmd_s, errors))


def rpmdb_filelist():
    """TODO: It should be a heavy and time-consuming task. Caching the result somewhere?

    >>> if os.path.exists('/var/lib/rpm/Basenames'): db = rpmdb_filelist(); assert db.get('/etc/hosts') == 'setup'
    """
    return dict(concat(([(f, h['name']) for f in h['filenames']] for h in rpm.TransactionSet().dbMatch())))



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

        for k,v in kwargs.iteritems():
            self[k] = v

    def _copy_xattrs(self, dest):
        for k,v in self.xattrs.iteritems():
            xattr.set(dest, k, v)

    def _copy(self, dest):
        """Two steps needed to keep the content and metadata of the original file:

        1. Copy itself and its some metadata (owner, mode, etc.)
        2. Copy extra metadata not copyable with the above.
        """
        shutil.copy2(self.path(), dest)
        self._copy_xattrs(dest)

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

    def remove(self):
        self._remove(self.path())

    def copy(self, dest, force=False):
        """Copy to $dest.  'Copy' action varys depends on actual filetype so
        that inherited class must overrride this and related methods (_remove
        and _copy).

        @dest      string  The destination path to copy to
        @force     bool    When True, force overwrite $dest even if it exists
        """
        assert self.path != dest, "Copying src and dst are same!"

        if not self.copyable():
            logging.warn(" Not copyable")
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
            os.makedirs(os.path.dirname(dest))

        logging.info(" Copying from '%s' to '%s'" % (self.path, dest))
        self._copy(dest)

        return True



class DirInfo(FileInfo):
    __ftype = TYPE_DIR

    def __init__(self, path, mode, uid, gid, checksum, xattrs):
        FileInfo.__init__(self, path, mode, uid, gid, checksum, xattrs)

    def _remove(self, target):
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
        FileInfo.__init__(self, path, mode, uid, gid, checksum, xattrs)
        self.linkto = os.path.realpath(path)

    def _copy(self, dest):
        os.symlink(self.linkto, dest)



class OtherInfo(FileInfo):
    """Special case that lstat() failed and cannot stat $path.
    """
    __ftype = TYPE_OTHER

    def __init__(self, path, mode=-1, uid=-1, gid=-1, checksum=checksum(), xattrs={}):
        FileInfo.__init__(self, path, mode, uid, gid, checksum, xattrs)

    def copyable(self):
        return False



def __setup_dir(dir):
    logging.info(" Creating a directory: %s" % dir)

    if os.path.exists(dir):
        if os.path.isdir(dir):
            logging.warn(" Target directory already exists! Skipping: %s" % dir)
        else:
            raise RuntimeError(" '%s' already exists and it's not a directory! Aborting..." % dir)
    else:
        os.makedirs(dir, 0700)


def __copy(src, dst):
    """Copy $src to $dst.
    """
    logging.info(" Copying: %s -> %s" % (src, dst))

    if os.path.isdir(src):
        if os.path.exists(dst):
            if not os.path.isdir(dst):
                raise RuntimeError(" '%s' already exists and it's not a directory! Aborting..." % dst)
        else:
            logging.info(" The target is a directory")
        return

    dstdir = os.path.dirname(dst)

    if os.path.exists(dstdir):
        if not os.path.isdir(dstdir):
            raise RuntimeError(" '%s' (in which %s will be) already exists and it's not a directory! Aborting..." % (dstdir, src))
    else:
        os.makedirs(dstdir, 0755)

    # NOTE: shutil.copy2 is corresponding to 'cp --preserve=mode,ownership,timestamps'
    # and sufficient for most cases, I guess. But to make safer, choose 'cp --preserve=all'
    # at present.
    #
    #shutil.copy2(src, dst)
    shell("cp -a %s %s" % (src, dst), log=False)


def __to_srcdir(path, workdir=''):
    """
    >>> __to_srcdir('/a/b/c')
    'src/a/b/c'
    >>> __to_srcdir('a/b')
    'src/a/b'
    >>> __to_srcdir('/')
    'src/'
    """
    assert path != '', "Empty path was given"

    return os.path.join(workdir, 'src', path.strip(os.path.sep))


def __gen_files_vars_in_makefile_am(files, tmpl=PKG_DIST_INST_FILES_TMPL):
    """FIXME: ugly code
    """
    cntr = count()
    fmt = lambda d, fs: tmpl % {'id': str(cntr.next()), 'files': " \\\n".join((__to_srcdir(f) for f in fs)), 'dir':d}

    return ''.join([fmt(d, [x for x in grp]) for d,grp in groupby(files, dirname)])


def process_listfile(list_f):
    """Read paths from given file line by line and returns path list sorted by
    dir names. Empty lines or lines start with '#' are ignored.
    """
    return unique([l.rstrip() for l in list_f.readlines() if l and not l.startswith('#')], key=dirname)


def setup_dirs(pkg):
    __setup_dir(pkg['workdir'])
    __setup_dir(pkg['srcdir'])


def copy_files(pkg):
    for t in pkg['files']['targets']:
        t2 = (pkg['destdir'] and os.path.join(pkg['destdir'], t.strip(os.path.sep)) or t)
        __copy(t2, __to_srcdir(t, pkg['workdir']))


def gen_buildfiles(pkg):
    global TEMPLATES

    workdir = pkg['workdir']
    pkg['files_vars_in_makefile_am'] = __gen_files_vars_in_makefile_am(pkg['files']['targets'])

    def genfile(filepath, output=""):
        compile_template(TEMPLATES[filepath], pkg, os.path.join(workdir, (output or filepath)))

    genfile('configure.ac')
    genfile('Makefile.am')
    genfile('rpm.mk')

    spec_f = "%s.spec" % pkg['name']
    genfile("package.spec", spec_f)
    __copy(os.path.join(workdir, spec_f), os.path.join(workdir, '..'))

    debiandir = os.path.join(workdir, 'debian')
    if not os.path.exists(debiandir):
        os.makedirs(debiandir)

    genfile('debian/rules')
    genfile('debian/control')
    genfile('debian/copyright')
    genfile('debian/changelog')

    shell('autoreconf -vfi', workdir=pkg['workdir'])


def build_srpm(pkg):
    shell('./configure', workdir=pkg['workdir'])
    shell('make srpm', workdir=pkg['workdir'])

    for p in glob.glob(os.path.join(pkg['workdir'], "*.src.rpm")):
        __copy(p, os.path.join(pkg['workdir'], '../'))


def build_rpm_with_mock(pkg):
    """TODO: Identify the (single) src.rpm
    """
    try:
        shell("mock --version > /dev/null")
    except RuntimeError, e:
        logging.warn(" It sesms mock is not found on your system. Fallback to plain rpmbuild...")
        build_rpm_with_rpmbuild(pkg)
        return

    shell("mock -r %(dist)s %(name)s-%(version)s-%(release)s.*.src.rpm" % pkg, workdir=pkg['workdir'])

    for p in glob.glob("/var/lib/mock/%(dist)s/result/*.rpm" % pkg):
        __copy(p, os.path.join(pkg['workdir'], '../'))


def build_rpm_with_rpmbuild(pkg):
    shell('make rpm', workdir=pkg['workdir'])
    for p in glob.glob(os.path.join(pkg['workdir'], "*.rpm")):
        __copy(p, os.path.join(pkg['workdir'], '../'))


def build_deb_with_debuild(pkg):
    shell('debuild -us -uc', workdir=pkg['workdir'])


def do_packaging(pkg, options):
    setup_dirs(pkg)
    copy_files(pkg)
    gen_buildfiles(pkg)
    build_srpm(pkg)

    if options.build_rpm:
        if options.no_mock:
            build_rpm_with_rpmbuild(pkg)
        else:
            build_rpm_with_mock(pkg)


def show_examples(logs=EXAMPLE_LOGS):
    for log in logs:
        print >> sys.stdout, log


def run_tests():
    import doctest
    doctest.testmod(verbose=True)


def option_parser(V=__version__):
    global PKG_COMPRESSORS, TARGET_DIST_DEFAULT

    ver_s = "%prog " + V

    workdir = os.path.join(os.path.abspath(os.curdir), 'workdir')
    packager = os.environ.get('USER', 'root')

    defaults = {
        'name': 'foo',
        'group': 'System Environment/Base',
        'license': 'GPLv3+',
        'compress': 'xz',
        'arch': False,
        'requires': [],
        'packager_name': packager,
        'packager_mail': "%s@localhost.localdomain" % packager,
        'package_version': '0.1',
        'workdir': workdir,
        'build_rpm': False,
        'no_mock': False,
        'dist': TARGET_DIST_DEFAULT,
        'destdir': '',
        'no_rpmdb': False,
        'debug': False,
        'quiet': False,
        'show_examples': False,
        'test': False,
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
    pog.add_option('-S', '--summary', help='The summary of the package')
    pog.add_option('-z', '--compress', type="choice", choices=PKG_COMPRESSORS.keys(),
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
    bog.add_option('', '--destdir', help="Destdir (prefix) you want to strip from installed path [%default]. "
        "For example, if the target path is '/builddir/dest/usr/share/data/foo/a.dat', "
        "and you want to strip '/builddir/dest' from the path when packaging 'a.dat' and "
        "make it installed as '/usr/share/foo/a.dat' with rpm built, you can accomplish "
        "that by this option: '--destdir=/builddir/destdir'")

    p.add_option_group(bog)

    rog = optparse.OptionGroup(p, "Rpm DB options")
    rog.add_option('', '--no-rpmdb', action='store_true', help='Do not refer rpm db to get extra information of target files')
    p.add_option_group(rog)

    p.add_option('-D', '--debug', action="store_true", help='Debug mode')
    p.add_option('-q', '--quiet', action="store_true", help='Quiet mode')

    p.add_option('', '--show-examples', action="store_true", help='Show examples')
    p.add_option('-T', '--test', action="store_true", help='Run tests')

    return p


def main():
    global PKG_COMPRESSORS, TARGET_DIST_DEFAULT

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

    if options.test:
        run_tests()
        sys.exit(0)

    if len(args) < 1:
        p.print_usage()
        sys.exit(1)

    filelist = args[0]

    if options.quiet:
        logging.getLogger().setLevel(logging.WARN)

    if options.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if options.arch:
        pkg['noarch'] = False
    else:
        pkg['noarch'] = True

    pkg['name'] = options.name
    pkg['release'] = '1'
    pkg['group'] = options.group
    pkg['license'] = options.license

    pkg['version'] = options.package_version
    pkg['packager_name'] = options.packager_name
    pkg['packager_mail'] = options.packager_mail

    pkg['workdir'] = os.path.abspath(os.path.join(options.workdir, "%(name)s-%(version)s" % pkg))
    pkg['srcdir'] = os.path.join(pkg['workdir'], 'src')

    pkg['compress'] = {
        'ext': options.compress,
        'am_opt': PKG_COMPRESSORS.get(options.compress),
    }

    pkg['dist'] = options.dist

    # TODO: Revert locale setting change just after timestamp was gotten.
    locale.setlocale(locale.LC_ALL, "C")
    pkg['timestamp'] = datetime.date.today().strftime("%a %b %_d %Y")

    if filelist == '-':
        list_f = sys.stdin
    else:
        list_f = open(filelist)

    if options.no_rpmdb:
        filelist_db = dict()
    else:
        filelist_db = rpmdb_filelist()

    files = []
    conflicts = dict()

    destdir = options.destdir.rstrip(os.path.sep)
    pkg['destdir'] = destdir

    for f in process_listfile(list_f):
        # FIXME: Is there any better way?
        if destdir:
            if f.startswith(destdir):
                f = f.split(destdir)[1]
            else:
                logging.error(" The path '%s' does not start with given destdir '%s'" % (f, destdir))
                raise RuntimeError("Destdir specified in --destdir and the actual file path are inconsistent.")

        p = filelist_db.get(f, False)

        if p and p != pkg['name']:
            logging.info(" %s is owned by %s, that is, it will be conflicts with %s" % (f, p, p))
            conflicts[f] = p

        files.append(f)

    pkg['files'] = {
        'targets': files,
        'sources': [os.path.join('src', p[1:]) for p in files]
    }

    pkg['conflicts'] = {
        'names': unique(conflicts.values()),
        'files': conflicts.keys(),
    }

    pkg['filelist'] = [os.path.join('src', p[1:]) for p in files]

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
