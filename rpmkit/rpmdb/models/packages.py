#
# rpmdb.modles.packages - Package related models in database
#
# Copyright (C) 2012 Red Hat, Inc.
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
from rpmkit.rpmdb.models.base import DeclBase, DeclMixin

import sqlalchemy as S
import sqlalchemy.orm as SO


class Package(DeclBase, DeclMixin):
    """
    @see spacewalk.git/schema/spacewalk/common/tables/rhnPackageName.sql
    @see spacewalk.git/schema/spacewalk/common/tables/rhnPackageEVR.sql
    @see spacewalk.git/schema/spacewalk/common/tables/rhnPackageArch.sql
    @see spacewalk.git/schema/spacewalk/oracle/tables/rhnPackage.sql
    """
    name = S.Column(S.String(256))  # rhnPackageName.name
    version = S.Column(S.String(512))  # rhnPackageEVR.version
    release = S.Column(S.String(512))  # rhnPackageEVR.release
    epoch = S.Column(S.String(16))  # rhnPackageEVR.epoch
    arch = S.Column(S.String(64))  # rhnPackageArch.label

    def __init__(self, id, name, version, release, epoch, arch):
        self.id = id
        self.name = name
        self.version = version
        self.release = release
        self.epoch = epoch
        self.arch = arch


class Errata(DeclBase, DeclMixin):
    """
    @see spacewalk.git/schema/spacewalk/common/tables/rhnErrata.sql
    """
    advisory = S.Column(S.String(100))  # rhnErrata.advisory
    name = S.Column(S.String(100))  # rhnErrata.name
    synopsis = S.Column(S.String(4000))  # rhnErrata.synopsis
    issue_date = S.Column(S.String(256))  # rhnErrata.issue_date

    def __init__(self, id, advisory, name, synopsis, issue_date):
        self.id = id
        self.advisory = advisory
        self.name = name
        self.synopsis = synopsis
        self.issue_date = issue_date


class CVE(DeclBase, DeclMixin):
    """
    @see spacewalk.git/schema/spacewalk/common/tables/rhnCVE.sql
    """
    name = S.Column(S.String(13))  # rhnCVE.name

    def __init__(self, id, name):
        self.id = id
        self.name = name


# Relations:
class PackageDetails(DeclBase, DeclMixin):
    pid = S.Column(S.Integer, S.ForeignKey("package.id"), nullable=False)
    package = SO.relationship(Package, backref="packagedetails")

    summary = S.Column(S.String(4000))  # rhnPackage.summary
    description = S.Column(S.String(4000))  # rhnPackage.description
    build_host = S.Column(S.String(256))  # rhnPackageName.build_host

    def __init__(self, pid, summary, description, build_host):
        self.pid = pid
        self.summary = summary
        self.description = description
        self.build_host = build_host


class PackageFile(DeclBase, DeclMixin):
    """file vs. package

    @see spacewalk.git/schema/spacewalk/common/tables/rhnPackageArch.sql
    @see spacewalk.git/java/code/src/com/redhat/rhn/common/db/\
         datasource/xml/Package_queries.xml
    """
    pid = S.Column(S.Integer, S.ForeignKey("package.id"), nullable=False)
    path = S.Column(S.String(4000))  # rhnPackageCapability.name

    package = SO.relationship(Package, backref="files")

    def __init__(self, pid, path):
        self.pid = pid
        self.path = path


class PackageRequires(DeclBase, DeclMixin):
    """package vs. requires

    @see spacewalk.git/schema/spacewalk/common/tables/rhnPackageRequires.sql
    """
    pid = S.Column(S.Integer, S.ForeignKey("package.id"), nullable=False)
    name = S.Column(S.String(4000))  # rhnPackageCapability.name
    version = S.Column(S.String(64))  # rhnPackageCapability.version

    package = SO.relationship(Package, backref="requires")

    def __init__(self, pid, name, version):
        self.pid = pid
        self.name = name
        self.version = version


class PackageProvides(DeclBase, DeclMixin):
    """package vs. provides

    @see spacewalk.git/schema/spacewalk/common/tables/rhnPackageProvides.sql
    """
    pid = S.Column(S.Integer, S.ForeignKey("package.id"), nullable=False)
    name = S.Column(S.String(4000))  # rhnPackageCapability.name

    package = SO.relationship(Package, backref="provides")

    def __init__(self, pid, name):
        self.pid = pid
        self.name = name


class PackageErrata(DeclBase, DeclMixin):
    """package vs. errata
    """
    pid = S.Column(S.Integer, S.ForeignKey("package.id"))
    eid = S.Column(S.Integer, S.ForeignKey("errata.id"))

    package = SO.relationship(Package, backref="packageerrata")
    errata = SO.relationship(Errata, backref="packageerrata")

    def __init__(self, pid, eid):
        self.pid = pid
        self.eid = eid


# vim:sw=4:ts=4:et:
