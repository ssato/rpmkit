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
import rpmkit.myrepo.globals as G
import rpmkit.myrepo.repoops as RO
import rpmkit.Bunch as B

import os.path


is_noarch = RO.is_noarch


def _format(repo, fmt_or_val):
    """
    (Format Str | Str) -> Str
    """
    return fmt_or_val % repo.as_dict() if "%" in fmt_or_val else fmt_or_val


class Repo(object):
    """Yum repository.
    """
    name = G.REPO_DEFAULT.name
    subdir = G.REPO_DEFAULT.subdir
    topdir = G.REPO_DEFAULT.topdir
    baseurl = G.REPO_DEFAULT.baseurl

    signkey = G.REPO_DEFAULT.signkey
    keydir = G.REPO_DEFAULT.keydir
    keyurl = G.REPO_DEFAULT.keyurl

    metadata_expire = G.REPO_DEFAULT.metadata_expire

    def __init__(self, server, user, email, fullname, dname, dver, archs,
            name=None, subdir=None, topdir=None, baseurl=None, signkey=None,
            bdist=None, metadata_expire=None, timeout=None,
            genconf=False, *args, **kwargs):
        """
        :param server: Server's hostname to provide this yum repo
        :param user: Username on the server
        :param email: Email address or its format string
        :param fullname: User's full name, e.g. "John Doe".
        :param name: Repository name or its format string,
            e.g. "rpmfusion-free", "%(distname)s-%(hostname)s-%(user)s"
        :param dname: Distribution name, e.g. "fedora", "rhel"
        :param dver: Distribution version, e.g. "16", "6"
        :param archs: Architecture list, e.g. ["i386", "x86_64"]
        :param subdir: Sub directory for this repository
        :param topdir: Topdir or its format string for this repository,
            e.g. "/var/www/html/%(subdir)s".
        :param baseurl: Base url or its format string, e.g. "file://%(topdir)s".
        :param signkey: GPG key ID to sign built, or None indicates will never sign
        :param bdist: Distribution label to build srpms,
            e.g. "fedora-custom-addons-14-x86_64"
        :param metadata_expire: Metadata expiration period, e.g. "2h", "1d"
        :param timeout: Timeout
        """
        self.server = server
        self.user = user
        self.fullname = fullname
        self.archs = archs

        self.hostname = server.split('.')[0]
        self.multiarch = "i386" in self.archs and "x86_64" in self.archs
        self.primary_arch = "x86_64" if self.multiarch else self.archs[0]

        self.bdist = bdist
        self.genconf = genconf

        self.distname = dname
        self.distversion = dver
        self.dist = "%s-%s" % (dname, dver)

        self.dists = [
            D.Distribution(dname, dver, a, bdist) for a in self.archs
        ]
        self.distdir = "%s/%s" % (dname, dver)
        self.subdir = self.subdir if subdir is None else subdir
        self.email = _format(self, email)

        if name is None:
            name = Repo.name

        if topdir is None:
            topdir = Repo.topdir

        if baseurl is None:
            baseurl = Repo.baseurl

        # expand parameters which are format strings:
        self.name = _format(self, name)
        self.topdir = _format(self, topdir)
        self.baseurl = _format(self, baseurl)

        self.keydir = Repo.keydir

        if signkey is None:
            self.signkey = self.keyurl = self.keyfile = ""
        else:
            self.signkey = signkey
            self.keyurl = _format(self, Repo.keyurl)
            self.keyfile = os.path.join(
                self.keydir,
                os.path.basename(self.keyurl)
            )

        if metadata_expire is not None:
            self.metadata_expire = metadata_expire

        self.timeout = timeout

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
