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
from itertools import groupby

import datetime
import glob
import locale
import logging
import optparse
import os
import os.path
import rpm
import shutil
import subprocess
import sys



__version__ = "0.2.2"


PKG_CONFIGURE_AC_TMPL = """AC_INIT([${name}],[${version}])
AM_INIT_AUTOMAKE([$compress_am_opt foreign silent-rules subdir-objects])

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

$filelist_vars_in_makefile_am

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
\t$(rpmbuild) -bb $< && mv $(rpmdir)/RPMS/*/* $(abs_builddir)

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
Source0:        %{name}-%{version}.tar.$compress_ext
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
#for $req in $requires
Requires: $req
#end for

%description
${summary}


%prep
%setup -q

# FIXME: arrange contents of README.
touch README


%build
#test -f Makefile.in || autoreconf -vfi
%configure
make


%install
rm -rf \$RPM_BUILD_ROOT

#cp -a src/* \$RPM_BUILD_ROOT/
make install DESTDIR=\$RPM_BUILD_ROOT

# s,%files,%files -f files.list, if enable the following:
#find \$RPM_BUILD_ROOT -type f | sed "s,^\$RPM_BUILD_ROOT,,g" > files.list


%clean
rm -rf \$RPM_BUILD_ROOT


%files
%defattr(-,root,root,-)
%doc README
#for $f in $target_filelist
$f
#end for


%changelog
* ${timestamp} ${packager_name} <${packager_mail}> - ${version}-${release}
- Initial packaging.
"""


PKG_DIST_INST_FILES_TMPL = """
pkgdata%(idx)ddir = %(dir)s
dist_pkgdata%(idx)d_DATA = %(files)s
"""


PKG_DIST_NOINST_FILES_TMPL = """
dist_noinst_pkgdata%(idx)d_DATA = %(files)s
"""



def __copy(src, dst):
    logging.info(" Copying %s to %s" % (src, dst))

    if os.path.isdir(src):
        if os.path.exists(dst):
            if not os.path.isdir(dst):
                raise RuntimeError(" '%s' already exists and it's not a directory! Aborting..." % dst)
        else:
            logging.info(" Copying target is a directory")
        return

    dstdir = os.path.dirname(dst)

    if os.path.exists(dstdir):
        if not os.path.isdir(dstdir):
            raise RuntimeError(" '%s' (in which %s will be) already exists and it's not a directory! Aborting..." % (dstdir, src))
    else:
        os.makedirs(dstdir, 0755)

    shutil.copy2(src, dst)


def __setup_dir(dir):
    logging.info(" Creating the directory: %s" % dir)

    if os.path.exists(dir):
        if os.path.isdir(dir):
            logging.warn(" Target directory '%s' already exists! Skip creation" % dir)
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


def __g_filelist(filelist):
    return (l.rstrip() for l in filelist.readlines() if not l.startswith('#'))


def __run(cmd_and_args_s, workdir=""):
    """
    >>> __run('ls /dev/null')
    (0, '/dev/null')
    """
    if not workdir:
        workdir = os.path.abspath(os.curdir)

    logging.info(" Run: %s" % cmd_and_args_s)

    pipe = subprocess.Popen([cmd_and_args_s], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, cwd=workdir)
    (output, errors) = pipe.communicate()  # TODO: It might be blocked. Use Popen.wait() instead?

    if pipe.returncode == 0:
        logging.info(" ...done")
        return (output, errors)
    else:
        raise RuntimeError(" Failed: %s" % cmd_and_args_s)


def __count_sep(path):
    return path.count(os.path.sep)


# FIXME: Ugly
def __gen_filelist_vars_in_makefile_am(filelist, tmpl=PKG_DIST_INST_FILES_TMPL):
    fs_am_vars_gen = lambda idx, fs: tmpl % \
        {'idx':idx, 'files': " \\\n".join(fs), 'dir':os.path.dirname(fs[0]).replace('src', '')}

    return ''.join([fs_am_vars_gen(k, [x for x in grp]) for k,grp in groupby(filelist, __count_sep)])


def flattern(xss):
    ret = []
    for xs in xss:
        if isinstance(xs, list):
            ys = flattern(xs)
            ret += ys
        else:
            ret.append(xs)
    return ret


def rpmdb_mi():
    return rpm.TransactionSet().dbMatch()


def rpmdb_filelist():
    return dict(flattern([[(f, h[rpm.RPMTAG_NAME]) for f in h[rpm.RPMTAG_FILENAMES]] for h in rpmdb_mi()]))


def gen_rpm_spec(pkg):
    spec_f = os.path.join(pkg['workdir'], "%s.spec" % pkg['name'])
    __tmpl_compile_2(PKG_RPM_SPEC_TMPL, pkg, spec_f)
    __run('cp *.spec ../', workdir=pkg['workdir'])


def setup_dirs(pkg):
    __setup_dir(pkg['workdir'])
    __setup_dir(pkg['srcdir'])


def copy_files(pkg):
    for src,dst_subdir in zip(pkg['target_filelist'], pkg['filelist']):
        __copy(src, os.path.join(pkg['workdir'], dst_subdir))


def gen_buildfiles(pkg):
    pkg['filelist_vars_in_makefile_am'] = __gen_filelist_vars_in_makefile_am(pkg['filelist'])

    __tmpl_compile_2(PKG_CONFIGURE_AC_TMPL, pkg, os.path.join(pkg['workdir'], 'configure.ac'))
    __tmpl_compile_2(PKG_MAKEFILE_AM_TMPL,  pkg, os.path.join(pkg['workdir'], 'Makefile.am'))

    open(os.path.join(pkg['workdir'], 'rpm.mk'), 'w').write(PKG_MAKEFILE_RPMMK)

    __run('autoreconf -vfi', workdir=pkg['workdir'])


def gen_srpm(pkg):
    __run('./configure', workdir=pkg['workdir'])
    __run('make srpm', workdir=pkg['workdir'])


def gen_rpm_with_mock(pkg):
    dist = pkg['dist']

    # FIXME: How to specify _single_ src.rpm ?
    __run("mock -r %s *.src.rpm" % dist, workdir=pkg['workdir'])

    for p in glob.glob("/var/lib/mock/%s/result/*.rpm" % dist):
        __copy(p, os.path.abspath(os.path.join(pkg['workdir'], '../')))


def gen_rpm(pkg):
    raise NotImplementedError("TBD")


def do_packaging(pkg, options):
    setup_dirs(pkg)
    copy_files(pkg)
    gen_rpm_spec(pkg)
    gen_buildfiles(pkg)
    gen_srpm(pkg)

    if options.build_rpm:
        gen_rpm_with_mock(pkg)
    else:
        for p in glob.glob(os.path.join(pkg['workdir'], "*.src.rpm")):
            __copy(p, os.path.abspath(os.path.join(pkg['workdir'], '../')))


def main(V=__version__):
    pkg = dict()
    ver_s = "%prog " + V

    workdir = os.path.join(os.path.abspath(os.curdir), 'workdir')
    packager_name = os.environ.get('USER', 'root')
    packager_mail = "%s@localhost.localdomain" % packager_name

    compress_map = {
        # extension: am_option,
        'xz'    : 'dist-xz',
        'bz2'   : 'dist-bzip2',
        'gz'    : '',
    }

    p = optparse.OptionParser("""%prog [OPTION ...] FILE_LIST

Examples:
  %prog -n foo files.list
  cat files.list | %prog -n foo -  # same as above.

  %prog -n foo -v 0.2 -l GPLv3+ files.list
  %prog -n foo --requires httpd,/sbin/service files.list""",
    version=ver_s
    )
    p.add_option('-n', '--name', default='foo', help='Package name [%default]')
    p.add_option('-g', '--group', default='System Environment/Base', help='The group of the package [%default]')
    p.add_option('-l', '--license', default='GPLv3+', help='The license of the package [%default]')
    p.add_option('-s', '--summary', help='The summary of the package')
    p.add_option('-z', '--compress', default='xz', type="choice", choices=compress_map.keys(),
        help="Which to used for compressing the src archive [%default]")

    p.add_option('', '--noarch', default=False, action='store_true', help='Build packaeg as noarch')
    p.add_option('', '--requires', default=[], help='Specify the package requirements as comma separated list')
    p.add_option('', '--packager-name', default=packager_name, help="Specify packager's name [%default]")
    p.add_option('', '--packager-mail', default=packager_mail, help="Specify packager's mail address [%default]")
    p.add_option('', '--package-version', default='0.1', help='Specify the package version [%default]')

    rog = optparse.OptionGroup(p, "Rpm DB options")
    rog.add_option('', '--skip-owned', default=False, action='store_true', help='Skip files owned by other package')
    p.add_option_group(rog)

    bog = optparse.OptionGroup(p, "Build options")
    bog.add_option('', '--workdir', default=workdir, help='Specify working dir to dump outputs in absolute path [%default]')
    bog.add_option('', '--build-rpm', default=False, action="store_true", help='Build RPM with mock')
    bog.add_option('', '--dist', default='default', help='Specify the target distribution such like fedora-13-x86_64 [%default]')
    bog.add_option('', '--quiet', default=False, action="store_true", help='Run in quiet (less verbose) mode')
    p.add_option_group(bog)

    (options, args) = p.parse_args()

    if len(args) < 1:
        p.print_usage()
        sys.exit(1)

    filelist = args[0]

    if options.quiet:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.DEBUG)

    pkg['name'] = options.name
    pkg['release'] = '1'
    pkg['group'] = options.group
    pkg['license'] = options.license
    pkg['noarch'] = options.noarch

    pkg['version'] = options.package_version
    pkg['packager_name'] = options.packager_name
    pkg['packager_mail'] = options.packager_mail

    pkg['workdir'] = os.path.join(options.workdir, "%(name)s-%(version)s" % pkg)
    pkg['srcdir'] = os.path.join(pkg['workdir'], 'src')

    pkg['compress_ext'] = options.compress
    pkg['compress_am_opt'] = compress_map.get(options.compress)

    pkg['dist'] = options.dist

    # TODO: Revert locale setting change just after timestamp was gotten.
    locale.setlocale(locale.LC_ALL, "C")
    pkg['timestamp'] = datetime.date.today().strftime("%a %b %_d %Y")

    if filelist == '-':
        list_f = sys.stdin
    else:
        list_f = open(filelist)

    filelist_db = rpmdb_filelist()
    files = []

    for f in __g_filelist(list_f):
        p = filelist_db.get(f, False)

        if p and p != pkg['name']:
            logging.info(" %s is owned by %s." % (f, p))
            if options.skip_owned:
                logging.info(" ...skipped: %s" % f)
                continue
            else:
                logging.warn(" ...This package will be conflict with %s." % p)

        files.append(f)

    pkg['target_filelist'] = files
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
