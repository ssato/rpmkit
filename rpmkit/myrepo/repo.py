#
# Copyright (C) 2011 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato@redhat.com>
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
import rpmkit.myrepo.distribution as D
import rpmkit.myrepo.utils as U

import logging
import os.path
import rpm


TEMPLATES = {
    "mock.cfg":
"""\
#for $k, $v in $cfg.iteritems()
#if "\\n" in $v
config_opts['$k'] = \"\"\"
$v
\"\"\"
#else if "," in $v
config_opts['$k'] = $v
#else
config_opts['$k'] = '$v'
#end if

#end for
""",
    "release_file_tmpl":
"""\
[${repo.name}]
name=Custom yum repository on ${repo.server} by ${repo.user} (\$basearch)
baseurl=${repo.baseurl}/\$basearch/
metadata_expire=${repo.metadata_expire}
enabled=1
#if $repo.signkey
gpgcheck=1
gpgkey=${repo.keyurl}
#else
gpgcheck=0
#end if

[${repo.name}-source]
name=Custom yum repository on ${repo.server} by ${repo.user} (source)
baseurl=${repo.baseurl}/sources/
metadata_expire=${repo.metadata_expire}
enabled=0
gpgcheck=0
""",
    "release_file_build_tmpl":
"""\
#if not $repo.signkey
    echo "${repo.release_file},rpmattr=%config" | \\
#end if
pmaker -n ${repo.name}-release --license MIT \\
-w ${repo.workdir} \\
--stepto sbuild \\
--group "System Environment/Base" \\
--url ${repo.baseurl} \\
--summary "Yum repo files for ${repo.name}" \\
--packager "${repo.fullname}" \\
--email "${repo.email}" \\
--pversion ${repo.distversion}  \\
--no-rpmdb --no-mock \\
--ignore-owner \\
${repo.logopt} \\
--destdir ${repo.workdir} \\
#if $repo.signkey
$repo.release_file_list
#else
-
#end if
""",
    "mock_cfg_rpm_build_tmpl":
"""\
pmaker -n mock-data-${repo.name} \\
    --license MIT \\
    -w ${repo.workdir} \\
    --stepto sbuild \\
    --group "Development/Tools" \\
    --url ${repo.baseurl} \\
    --summary "Mock cfg files of yum repo ${repo.name}" \\
    --packager "${repo.fullname}" \\
    --email "${repo.email}" \\
    --pversion ${repo.distversion}  \\
    --no-rpmdb --no-mock \\
    --ignore-owner \\
    --destdir ${repo.workdir} \\
    $repo.mock_cfg_file_list
""",
}


def snd(x, y):
    """
    >>> snd(1, 2)
    2
    """
    return y


def rpm_header_from_rpmfile(rpmfile):
    """Read rpm.hdr from rpmfile.
    """
    return rpm.TransactionSet().hdrFromFdno(open(rpmfile, "rb"))


@U.memoize
def is_noarch(srpm):
    """Detect if given srpm is for noarch (arch-independent) package.
    """
    return rpm_header_from_rpmfile(srpm)["arch"] == "noarch"


def mock_cfg_add_repos(repo, dist, repos_content):
    """
    Updated mock.cfg with addingg repository definitions in
    given content and returns it.

    @repo  Repo object
    @dist  Distribution object
    @repos_content  str  Repository definitions to add into mock.cfg
    """
    cfg_opts = D.mockcfg_opts(dist.mockcfg())

    cfg_opts["root"] = repo.buildroot(dist)
    cfg_opts["myrepo_distname"] = dist.name
    cfg_opts["yum.conf"] += "\n\n" + repos_content

    return U.compile_template("mock.cfg", cfg_opts)


class Repo(object):
    """Yum repository.
    """
    name = "%(distname)s-%(hostname)s-%(user)s"
    subdir = "yum"
    topdir = "~%(user)s/public_html/%(subdir)s"
    baseurl = "http://%(server)s/%(user)s/%(subdir)s/%(distdir)s"

    signkey = ""
    keydir = "/etc/pki/rpm-gpg"
    keyurl = "file://%(keydir)s/RPM-GPG-KEY-%(name)s-%(distversion)s"

    metadata_expire = "2h"

    def __init__(self, server, user, email, fullname, dist, archs,
            name=None, subdir=None, topdir=None, baseurl=None, signkey=None,
            bdist_label=None, metadata_expire=None, timeout=None,
            *args, **kwargs):
        """
        @server    server's hostname to provide this yum repo
        @user      username on the server
        @email     email address or its format string
        @fullname  full name, e.g. "John Doe".
        @name      repository name or its format string, e.g. "rpmfusion-free",
                   "%(distname)s-%(hostname)s-%(user)s"
        @dist      distribution string, e.g. "fedora-14"
        @archs     architecture list, e.g. ["i386", "x86_64"]
        @subdir    repo's subdir
        @topdir    repo's topdir or its format string, e.g.
                   "/var/www/html/%(subdir)s".
        @baseurl   base url or its format string, e.g. "file://%(topdir)s".
        @signkey   GPG key ID to sign built, or None indicates will never sign
        @bdist_label  Distribution label to build srpms, e.g.
                   "fedora-custom-addons-14-x86_64"
        @metadata_expire  Metadata expiration time, e.g. "2h", "1d"
        @timeout   Timeout
        """
        self.server = server
        self.user = user
        self.fullname = fullname
        self.dist = dist
        self.archs = archs

        self.hostname = server.split('.')[0]
        self.multiarch = "i386" in self.archs and "x86_64" in self.archs

        self.bdist_label = bdist_label

        (self.distname, self.distversion) = D.parse_dist(self.dist)
        self.dists = [
            D.Distribution(self.dist, arch, bdist_label) for arch in self.archs
        ]
        self.distdir = os.path.join(
            self.dists[0].mockcfg_opts_get("myrepo_distname", self.distname),
            self.distversion
        )

        self.subdir = subdir is None and self.subdir or subdir

        self.email = self._format(email)

        if name is None:
            name = Repo.name

        if topdir is None:
            topdir = Repo.topdir

        if baseurl is None:
            baseurl = Repo.baseurl

        # expand parameters in format strings:
        self.name = self._format(name)
        self.topdir = self._format(topdir)
        self.baseurl = self._format(baseurl)

        self.keydir = Repo.keydir

        if signkey is None:
            self.signkey = self.keyurl = self.keyfile = ""
        else:
            self.signkey = signkey
            self.keyurl = self._format(Repo.keyurl)
            self.keyfile = os.path.join(
                self.keydir,
                os.path.basename(self.keyurl)
            )

        if metadata_expire is not None:
            self.metadata_expire = metadata_expire

        self.timeout = timeout

    def _format(self, fmt_or_var):
        return "%" in fmt_or_var and fmt_or_var % self.__dict__ or fmt_or_var

    def buildroot(self, dist):
        return "%s-%s" % (self.name, dist.label)

    def rpmdirs(self, destdir=None):
        f = destdir is None and snd or os.path.join

        return [f(destdir, d) for d in ["sources"] + self.archs]

    def copy_cmd(self, src, dst):
        if U.is_local(self.server):
            cmd = "cp -a %s %s" % \
                (src, ("~" in dst and os.path.expanduser(dst) or dst))
        else:
            cmd = "scp -p %s %s@%s:%s" % (src, self.user, self.server, dst)

        return cmd

    def build_cmd(self, srpm, dist):
        """Returns Command object to build src.rpm
        """
        return dist.build_cmd(srpm)

    def dists_by_srpm(self, srpm):
        return (is_noarch(srpm) and self.dists[:1] or self.dists)

    def release_file_content(self):
        return U.compile_template("release_file", self.__dict__)

    def mock_file_content(self, dist, release_file_content=None):
        """
        Returns the content of mock.cfg for given dist.

        @dist  Distribution  Distribution object
        @release_file_content  str  The content of this repo's release file
        """
        if release_file_content is None:
            release_file_content = self.release_file_content()

        return mock_cfg_add_repos(self, dist, release_file_content)

    def release_rpm_build_cmd(self, workdir, release_file_path):
        logopt = logging.getLogger().level < logging.INFO and "--verbose" or ""

        context = self.__dict__.copy()
        context.update({
            "release_file": release_file_path,
            "workdir": workdir,
            "logopt": logopt,
            "release_file_list": os.path.join(workdir, "files.list"),
        })

        return U.compile_template("release_file_build", context)

    def mock_cfg_rpm_build_cmd(self, workdir, mock_cfg_file_list_path):
        context = self.__dict__.copy()
        context.update({
            "workdir": workdir,
            "mock_cfg_file_list": mock_cfg_file_list_path
        })

        return U.compile_template("mock_cfg_build", context)


# vim:sw=4 ts=4 et:
