#
# Copyright (C) 2011, 2012 Red Hat, Inc.
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
import rpmkit.myrepo.repoops as RO

import os.path


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

    def __init__(self, server, user, email, fullname, dname, dver, archs,
            name=None, subdir=None, topdir=None, baseurl=None, signkey=None,
            bdist_label=None, metadata_expire=None, timeout=None,
            genconf=False, *args, **kwargs):
        """
        @server    server's hostname to provide this yum repo
        @user      username on the server
        @email     email address or its format string
        @fullname  full name, e.g. "John Doe".
        @name      repository name or its format string, e.g. "rpmfusion-free",
                   "%(distname)s-%(hostname)s-%(user)s"
        @dname     distribution name, e.g. "fedora", "rhel"
        @dver      distribution version, e.g. "16", "6"
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
        self.archs = archs

        self.hostname = server.split('.')[0]
        self.multiarch = "i386" in self.archs and "x86_64" in self.archs
        self.primary_arch = "x86_64" if self.multiarch else self.archs[0]

        self.bdist_label = bdist_label
        self.genconf = genconf

        self.distname = dname
        self.distversion = dver
        self.dist = "%s-%s" % (dname, dver)

        self.dists = [
            D.Distribution(dname, dver, a, bdist_label) for a in self.archs
        ]
        self.distdir = "%s/%s" % (dname, dver)
        self.subdir = self.subdir if subdir is None else subdir
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

    def as_dict(self):
        return self.__dict__.copy()

    def destdir(self):
        return os.path.join(self.topdir, self.distdir)

    def rpmdirs(self):
        return [
            os.path.join(self.destdir(), d) for d in ["sources"] + self.archs
        ]

    def update_metadata(self):
        return RO.update_metadata(self)


# vim:sw=4 ts=4 et:
