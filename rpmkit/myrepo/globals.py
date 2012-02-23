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
import rpmkit.Bunch as B


# timeouts [sec]:
(REMOTE_TIMEOUT, BUILD_TIMEOUT, LOCAL_TIMEOUT, MIN_TIMEOUT) = (
    60 * 10, 60 * 10, 60 * 5, 5
)

REPO_DEFAULT = B.Bunch(
    name="%(distname)s-%(hostname)s-%(user)s",
    subdir="yum",
    topdir="~%(user)s/public_html/%(subdir)s",
    baseurl="http://%(server)s/%(user)s/%(subdir)s/%(distdir)s",
    signkey="",
    keydir="/etc/pki/rpm-gpg",
    keyurl="file://%(keydir)s/RPM-GPG-KEY-%(name)s-%(distversion)s",
    metadata_expire="2h",
)


# vim:sw=4 ts=4 et:
