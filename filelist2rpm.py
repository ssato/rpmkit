#! /usr/bin/python
#
# filelist2rpm.py - Create RPM from given file list.
#
# It will try gathering files, and then do the followings:
#
# * arrange src tree contains these files with these relative path kept
# * generate RPM SPEC
# * generate source rpm
# * generate binarry rpm [option]
#
# It's based on the idea by Masatake YAMATO <yamato&#64;redhat.com>.
#
#
# Copyright (C) 2011 Satoru SATOH <satoru.satoh&#64;gmail.com>
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
#

from Cheetah.Template import Template
from itertools import groupby, count

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
        def get_all(*args):
            return ()
        def set(*args):
            return ()

        get_all = classmethod(get_all)
        set = classmethod(set)



__version__ = "0.2.5"


# TODO: Detect appropriate distribution (for mock) automatically.
DIST_DEFAULT = 'fedora-14-i386'


COMPRESS_MAP = {
    # extension: am_option,
    'xz'    : 'dist-xz',
    'bz2'   : 'dist-bzip2',
    'gz'    : '',
}


PKG_CONFIGURE_AC_TMPL = """AC_INIT([${name}],[${version}])
AM_INIT_AUTOMAKE([${compress.am_opt} foreign subdir-objects])
##AM_INIT_AUTOMAKE([${compress.am_opt} foreign silent-rules subdir-objects])

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
"""


# FIXME: Ugly hack
PKG_MAKEFILE_AM_TMPL = """EXTRA_DIST = \\
${name}.spec \\
rpm.mk \\
\$(NULL)

include \$(abs_srcdir)/rpm.mk

$files_vars_in_makefile_am

"""


PKG_MAKEFILE_RPMMK = """
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
"""


PKG_RPM_SPEC_TMPL = """
Name:           ${name}
Version:        ${version}
Release:        1%{?dist}
Summary:        ${summary}
Group:          ${group}
License:        ${license}
URL:            file:///${workdir}
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
"""


PKG_DIST_INST_FILES_TMPL = """
pkgdata%(id)sdir = %(dir)s
dist_pkgdata%(id)s_DATA = %(files)s
"""


EXAMPLE_LOG = """
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
$ python filelist2rpm.py -n foo -w ./0 -q files.list
13:44:50 [WARNING]  ...This package will be conflict with autofs.
13:44:50 [WARNING]  ...This package will be conflict with autofs.
13:44:50 [WARNING]  ...This package will be conflict with autofs.
13:44:50 [WARNING]  ...This package will be conflict with autofs.
13:44:50 [WARNING]  ...This package will be conflict with pilot-link.
13:44:50 [WARNING]  ...This package will be conflict with hwdata.
13:44:50 [WARNING]  ...This package will be conflict with module-init-tools.
13:44:50 [WARNING]  ...This package will be conflict with module-init-tools.
13:44:50 [WARNING]  ...This package will be conflict with module-init-tools.
13:44:50 [WARNING]  ...This package will be conflict with libmlx4.
$ ls 0
foo-0.1  foo-0.1-1.fc14.src.rpm  foo.spec
$ make -C 0/foo-0.1 rpm > /dev/null 2> /dev/null
$ ls 0/foo-0.1
Makefile     aclocal.m4      config.status  foo-0.1-1.fc14.noarch.rpm  foo-0.1.tar.xz  missing  src
Makefile.am  autom4te.cache  configure      foo-0.1-1.fc14.src.rpm     foo.spec        rpm
Makefile.in  config.log      configure.ac   foo-0.1.tar.gz             install-sh      rpm.mk
$
$ cat files.list | python filelist2rpm.py -n foo -w ./1 -
14:05:37 [INFO]  /etc/auto.master is owned by autofs.
14:05:37 [WARNING]  ...This package will be conflict with autofs.
14:05:37 [INFO]  /etc/auto.misc is owned by autofs.
14:05:37 [WARNING]  ...This package will be conflict with autofs.
14:05:37 [INFO]  /etc/auto.net is owned by autofs.
14:05:37 [WARNING]  ...This package will be conflict with autofs.
14:05:37 [INFO]  /etc/auto.smb is owned by autofs.
14:05:37 [WARNING]  ...This package will be conflict with autofs.
14:05:37 [INFO]  /etc/modprobe.d/blacklist-visor.conf is owned by pilot-link.
14:05:37 [WARNING]  ...This package will be conflict with pilot-link.
14:05:37 [INFO]  /etc/modprobe.d/blacklist.conf is owned by hwdata.
14:05:37 [WARNING]  ...This package will be conflict with hwdata.
14:05:37 [INFO]  /etc/modprobe.d/dist-alsa.conf is owned by module-init-tools.
14:05:37 [WARNING]  ...This package will be conflict with module-init-tools.
14:05:37 [INFO]  /etc/modprobe.d/dist-oss.conf is owned by module-init-tools.
14:05:37 [WARNING]  ...This package will be conflict with module-init-tools.
14:05:37 [INFO]  /etc/modprobe.d/dist.conf is owned by module-init-tools.
14:05:37 [WARNING]  ...This package will be conflict with module-init-tools.
14:05:37 [INFO]  /etc/modprobe.d/libmlx4.conf is owned by libmlx4.
14:05:37 [WARNING]  ...This package will be conflict with libmlx4.
14:05:37 [INFO]  Creating a directory: /tmp/t/1/foo-0.1
14:05:37 [INFO]  Creating a directory: /tmp/t/1/foo-0.1/src
14:05:37 [INFO]  Copying: /etc/auto.master -> /tmp/t/1/foo-0.1/src/etc/auto.master
14:05:37 [INFO]  Copying: /etc/auto.misc -> /tmp/t/1/foo-0.1/src/etc/auto.misc
14:05:37 [INFO]  Copying: /etc/auto.net -> /tmp/t/1/foo-0.1/src/etc/auto.net
14:05:37 [INFO]  Copying: /etc/auto.smb -> /tmp/t/1/foo-0.1/src/etc/auto.smb
14:05:37 [INFO]  Copying: /etc/resolv.conf -> /tmp/t/1/foo-0.1/src/etc/resolv.conf
14:05:37 [INFO]  Copying: /etc/modprobe.d/blacklist-visor.conf -> /tmp/t/1/foo-0.1/src/etc/modprobe.d/blacklist-visor.conf
14:05:37 [INFO]  Copying: /etc/modprobe.d/blacklist.conf -> /tmp/t/1/foo-0.1/src/etc/modprobe.d/blacklist.conf
14:05:37 [INFO]  Copying: /etc/modprobe.d/dist-alsa.conf -> /tmp/t/1/foo-0.1/src/etc/modprobe.d/dist-alsa.conf
14:05:37 [INFO]  Copying: /etc/modprobe.d/dist-oss.conf -> /tmp/t/1/foo-0.1/src/etc/modprobe.d/dist-oss.conf
14:05:37 [INFO]  Copying: /etc/modprobe.d/dist.conf -> /tmp/t/1/foo-0.1/src/etc/modprobe.d/dist.conf
14:05:37 [INFO]  Copying: /etc/modprobe.d/libmlx4.conf -> /tmp/t/1/foo-0.1/src/etc/modprobe.d/libmlx4.conf
14:05:37 [INFO]  Copying: /tmp/t/1/foo-0.1/foo.spec -> /tmp/t/1/foo-0.1/..
14:05:37 [INFO]  Run: autoreconf -vfi
14:05:40 [INFO]  Run: ./configure
14:05:42 [INFO]  Run: make srpm
14:05:42 [INFO]  Copying: /tmp/t/1/foo-0.1/foo-0.1-1.fc14.src.rpm -> /tmp/t/1/foo-0.1/../
$ ls 1/
foo-0.1  foo-0.1-1.fc14.src.rpm  foo.spec
$ ls 1/foo-0.1
Makefile     Makefile.in  autom4te.cache  config.status  configure.ac            foo-0.1.tar.gz  foo.spec    missing  rpm.mk
Makefile.am  aclocal.m4   config.log      configure      foo-0.1-1.fc14.src.rpm  foo-0.1.tar.xz  install-sh  rpm      src
$
$ echo /etc/resolv.conf | python filelist2rpm.py -n resolvconf -w 2 --build-rpm -
14:07:22 [INFO]  Creating a directory: /tmp/t/2/resolvconf-0.1
14:07:22 [INFO]  Creating a directory: /tmp/t/2/resolvconf-0.1/src
14:07:22 [INFO]  Copying: /etc/resolv.conf -> /tmp/t/2/resolvconf-0.1/src/etc/resolv.conf
14:07:22 [INFO]  Copying: /tmp/t/2/resolvconf-0.1/resolvconf.spec -> /tmp/t/2/resolvconf-0.1/..
14:07:22 [INFO]  Run: autoreconf -vfi
14:07:26 [INFO]  Run: ./configure
14:07:27 [INFO]  Run: make srpm
14:07:28 [INFO]  Copying: /tmp/t/2/resolvconf-0.1/resolvconf-0.1-1.fc14.src.rpm -> /tmp/t/2/resolvconf-0.1/../
14:07:28 [INFO]  Run: mock -r fedora-14-i386 resolvconf-0.1-1.*.src.rpm
14:07:48 [INFO]  Copying: /var/lib/mock/fedora-14-i386/result/resolvconf-0.1-1.fc14.src.rpm -> /tmp/t/2/resolvconf-0.1/../
14:07:48 [INFO]  Copying: /var/lib/mock/fedora-14-i386/result/resolvconf-0.1-1.fc14.noarch.rpm -> /tmp/t/2/resolvconf-0.1/../
$ ls 2
resolvconf-0.1  resolvconf-0.1-1.fc14.noarch.rpm  resolvconf-0.1-1.fc14.src.rpm  resolvconf.spec
$ rpm -qlp 2/resolvconf-0.1-1.fc14.noarch.rpm
/etc/resolv.conf
/usr/share/doc/resolvconf-0.1
/usr/share/doc/resolvconf-0.1/README
$
$ ls
filelist2rpm.py  srv
$ ls srv/isos/
rhel-server-5.6-i386-dvd.iso
$ echo /tmp/t/srv/isos/rhel-server-5.6-i386-dvd.iso | \                                                                                                        > python filelist2rpm.py -n rhel-server-5-6-i386-dvd-iso -w ./w \
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
"""


CHECKSUM_NONE = '0000000000000000000000000000000000000000'
(TYPE_FILE, TYPE_DIR, TYPE_SYMLINK, TYPE_OTHER) = range(0,4)



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
        self['path'] = path
        self['mode'] = mode
        (self['uid'], self['gid']) = (uid, gid)
        self['checksum'] = checksum
        self['xattrs'] = xattrs or {}

        self['filetype'] = self.__ftype

        if kwargs:
            self.update(kwargs)

    def _remove(self, target):
        os.remove(target)

    def _copy(self, dest):
        """Two steps needed to keep the content and metadata of the original file:

        1. Copy itself and its some metadata (owner, mode, etc.)
        2. Copy extra metadata not copyable with the above.
        """
        shutil.copy2(self.path(), dest)

        _xattrs = self.xattrs()
        if _xattrs:
            for k,v in _xattrs.iteritems():
                xattr.set(dest, k, v)

    def __eq__(self, other):
        """(==) method. True if self and other exactly came from the same
        object, that is, these contents and metadata are exactly same.

        TODO: Compare the part of the path?
          ex. lhs.path: '/path/to/xyz', rhs.path: '/var/lib/sp2/updates/path/to/xyz'
        """
        keys = ('mode', 'uid', 'gid', 'checksum', 'filetype')
        if not all(((self.get(key) == other.get(key)) for key in keys)):
            return False

        _xattrs = self.get('xattrs')
        if _xattrs:
            _oxattrs = other.get('xattrs')
            if not _oxattrs:
                return False

            return all(((_xattrs.get(attr) == _oxattrs.get(attr)) for attr in _xattrs.keys()))

        return True  # The case that xattrs is not available but others are ok.

    def hasSameContent(self, other):
        """These metadata (path, uid, gid, etc.) do not match but the checksums
        are same. This indicatest that contents are same.
        """
        return self.get('checksum') == other.get('checksum')

    def copyable(self):
        return True

    def remove(self):
        self._remove(self.path())

    def copy(self, dest, force=False):
        """Copy to $dest.  'Copy' action varys depends on actual filetype so
        that inherited class must overrride this and related methods (_remove
        and _copy).

        @dest      string  The destination to copy
        @force     bool    Force overwrite it even if exists when True
        """
        assert self.path() != dest, "Try copying to the same path!"

        if not self.copyable():
            logging.warn("Cannot copyable.")
            return False

        if os.path.exists(dest):
            logging.info("Copying destination already exists: '%s'" % dest)

            # TODO: It has negative impact for symlinks.
            #
            #if os.path.realpath(self.path()) == os.path.realpath(dest):
            #    logging.warn("Copying src and dest are same actually.")
            #    return False

            if force:
                logging.info("Removing it...")
                self._remove(dest)
            else:
                logging.warn("Do not overwrite it")
                return False
        else:
            os.makedirs(os.path.dirname(dest))

        logging.info("Copying from '%s' to '%s'" % (self.path(), dest))
        self._copy(dest)

        return True



class DirInfo(FileInfo):
    __ftype = TYPE_DIR

    def __init__(self, path, mode, uid, gid, checksum, xattrs):
        FileInfo.__init__(self, path, mode, uid, gid, checksum, xattrs)

    def _remove(self, target):
        os.removedirs(target)

    def _copy(self, dest):
        os.makedirs(dest, mode=self.mode())
        try:
            os.chown(dest, self.uid(), self.gid())
        except OSError, e:
            logging.warn(e)
        shutil.copystat(self.path(), dest)

        # These are not copyed with the above.
        _xattrs = self.xattrs()
        if _xattrs:
            for k,v in _xattrs.iteritems():
                xattr.set(dest, k, v)



class SymlinkInfo(FileInfo):
    __ftype = TYPE_SYMLINK

    def __init__(self, path, mode, uid, gid, checksum, xattrs):
        FileInfo.__init__(self, path, mode, uid, gid, checksum, xattrs)
        self['linkto'] = os.path.realpath(path)

    def linkto(self):
        return self['linkto']

    def _copy(self, dest):
        os.symlink(self.linkto(), dest)



class OtherInfo(FileInfo):
    """Special case that lstat() failed and cannot stat $path.
    """
    __ftype = TYPE_OTHER

    def __init__(self, path, mode=-1, uid=-1, gid=-1, checksum=CHECKSUM_NONE, xattrs={}):
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


def __tmpl_compile(template_path, params, output):
    tmpl = Template(file=template_path, searchList=params)
    open(output, 'w').write(tmpl.respond())


def __tmpl_compile_2(template_src, params, output):
    tmpl = Template(source=template_src, searchList=params)
    open(output, 'w').write(tmpl.respond())


def __run(cmd_and_args_s, workdir="", log=True):
    """
    >>> __run("ls /dev/null")
    ('/dev/null\\n', '')
    """
    if not workdir:
        workdir = os.path.abspath(os.curdir)

    if log:
        logging.info(" Run: %s" % cmd_and_args_s)

    pipe = subprocess.Popen([cmd_and_args_s], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, cwd=workdir)
    (output, errors) = pipe.communicate()  # TODO: It might be blocked. Use Popen.wait() instead?

    if pipe.returncode == 0:
        return (output, errors)
    else:
        raise RuntimeError(" Failed: %s,\n err:\n'''%s'''" % (cmd_and_args_s, errors))


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
    __run("cp -a %s %s" % (src, dst), log=False)


def __count_sep(path):
    """Count the separator (ex. '/' in Unix like systems) in given path.

    >>> __count_sep('')
    0
    >>> __count_sep('/')
    1
    >>> __count_sep('/a/b/c')
    3
    """
    return path.count(os.path.sep)


def __dir(path):
    """dirname.

    >>> __dir('/a/b/c')
    '/a/b'
    """
    return os.path.dirname(path)


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

    return ''.join([fmt(d, [x for x in grp]) for d,grp in groupby(files, __dir)])


def flattern(xss):
    """
    >>> flattern([])
    []
    >>> flattern([[1,2,3],[4,5]])
    [1, 2, 3, 4, 5]
    >>> flattern([[1,2,[3]],[4,[5,6]]])
    [1, 2, 3, 4, 5, 6]
    """
    ret = []
    for xs in xss:
        if isinstance(xs, list):
            ys = flattern(xs)
            ret += ys
        else:
            ret.append(xs)
    return ret


def unique(xs, cmp_f=cmp, key=None):
    """Returns (sorted) list of no duplicated items.

    @xs     list of object (x)
    @cmp_f  comparison function for x

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

    rs = [ys[0]]

    for y in ys[1:]:
        if y == rs[-1]:
            continue
        rs.append(y)

    return rs


def rpmdb_mi():
    return rpm.TransactionSet().dbMatch()


def rpmdb_filelist():
    """TODO: It should be a heavy and time-consuming task. Caching the result somewhere?
    """
    return dict(flattern(([(f, h[rpm.RPMTAG_NAME]) for f in h[rpm.RPMTAG_FILENAMES]] for h in rpmdb_mi())))


def process_listfile(list_f):
    """Read file path from given list file line by line and returns sorted path
    list (key = __dir). Empty lines or lines start with '#' are ignored.
    """
    return unique([l.rstrip() for l in list_f.readlines() if l and not l.startswith('#')], key=__dir)


def gen_rpm_spec(pkg):
    wdir = pkg['workdir']

    spec_f = os.path.join(wdir, "%s.spec" % pkg['name'])
    __tmpl_compile_2(PKG_RPM_SPEC_TMPL, pkg, spec_f)
    __copy(spec_f, os.path.join(wdir, '..'))


def setup_dirs(pkg):
    __setup_dir(pkg['workdir'])
    __setup_dir(pkg['srcdir'])


def copy_files(pkg):
    for t in pkg['files']['targets']:
        t2 = (pkg['destdir'] and os.path.join(pkg['destdir'], t.strip(os.path.sep)) or t)
        __copy(t2, __to_srcdir(t, pkg['workdir']))


def gen_buildfiles(pkg):
    pkg['files_vars_in_makefile_am'] = __gen_files_vars_in_makefile_am(pkg['files']['targets'])

    __tmpl_compile_2(PKG_CONFIGURE_AC_TMPL, pkg, os.path.join(pkg['workdir'], 'configure.ac'))
    __tmpl_compile_2(PKG_MAKEFILE_AM_TMPL,  pkg, os.path.join(pkg['workdir'], 'Makefile.am'))

    open(os.path.join(pkg['workdir'], 'rpm.mk'), 'w').write(PKG_MAKEFILE_RPMMK)

    __run('autoreconf -vfi', workdir=pkg['workdir'])


def build_srpm(pkg):
    __run('./configure', workdir=pkg['workdir'])
    __run('make srpm', workdir=pkg['workdir'])
    for p in glob.glob(os.path.join(pkg['workdir'], "*.src.rpm")):
        __copy(p, os.path.join(pkg['workdir'], '../'))



def build_rpm_with_mock(pkg):
    """TODO: Identify the (single) src.rpm
    """
    try:
        __run("mock --version > /dev/null")
    except RuntimeError, e:
        logging.warn(" It sesms mock is not found on your system. Fallback to plain rpmbuild...")
        build_rpm_with_rpmbuild(pkg)
        return

    __run("mock -r %(dist)s %(name)s-%(version)s-%(release)s.*.src.rpm" % pkg, workdir=pkg['workdir'])

    for p in glob.glob("/var/lib/mock/%(dist)s/result/*.rpm" % pkg):
        __copy(p, os.path.join(pkg['workdir'], '../'))


def build_rpm_with_rpmbuild(pkg):
    __run('make rpm', workdir=pkg['workdir'])
    for p in glob.glob(os.path.join(pkg['workdir'], "*.rpm")):
        __copy(p, os.path.join(pkg['workdir'], '../'))


def do_packaging(pkg, options):
    setup_dirs(pkg)
    copy_files(pkg)
    gen_rpm_spec(pkg)
    gen_buildfiles(pkg)
    build_srpm(pkg)

    if options.build_rpm:
        if options.no_mock:
            build_rpm_with_rpmbuild(pkg)
        else:
            build_rpm_with_mock(pkg)


def show_examples(log=EXAMPLE_LOG):
    print >> sys.stdout, log


def run_tests():
    import doctest
    doctest.testmod(verbose=True)


def option_parser(compress_map=COMPRESS_MAP, dist_default=DIST_DEFAULT, V=__version__):
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
        'dist': dist_default,
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
    pog.add_option('-z', '--compress', type="choice", choices=compress_map.keys(), help="Tool to compress src archive [%default]")
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


def main(compress_map=COMPRESS_MAP):
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
        'am_opt': compress_map.get(options.compress),
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
