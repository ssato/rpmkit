#
# rpmdb.modles - Rpm related models in database
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
# Requirements: python-sqlalchemy, swapi
#
from sqlalchemy.ext.declarative import declarative_base, declared_attr

import sqlalchemy as S
import sqlalchemy.orm as SO


# Use 'Declarative' extension
# (http://docs.sqlalchemy.org/en/rel_0_7/orm/extensions/declarative.html)
DeclBase = declarative_base()


class DeclMixin(object):

    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()

    id = S.Column(S.Integer, primary_key=True)  # It's always needed.


class Package(DeclBase, DeclMixin):
    """
    @see spacewalk.git/schema/spacewalk/common/tables/rhnPackageName.sql
    @see spacewalk.git/schema/spacewalk/common/tables/rhnPackageEVR.sql
    @see spacewalk.git/schema/spacewalk/common/tables/rhnPackageArch.sql
    """
    name = S.Column(S.String(256))  # rhnPackageName.name
    version = S.Column(S.String(512))  # rhnPackageEVR.version
    release = S.Column(S.String(512))  # rhnPackageEVR.release
    epoch = S.Column(S.String(16))  # rhnPackageEVR.epoch
    arch = S.Column(S.String(64))  # rhnPackageArch.label


class SoftwareChannel(DeclBase, DeclMixin):
    """
    @see spacewalk.git/schema/spacewalk/common/tables/rhnChannel.sql
    """
    label = S.Column(S.String(128))  # rhnChannel.label
    name = S.Column(S.String(256))  # rhnChannel.name


class Errata(DeclBase, DeclMixin):
    """
    @see spacewalk.git/schema/spacewalk/common/tables/rhnErrata.sql
    """
    advisory = S.Column(S.String(100))  # rhnErrata.advisory
    name = S.Column(S.String(100))  # rhnErrata.name
    synopsis = S.Column(S.String(4000))  # rhnErrata.synopsis
    issue_date = S.Column(S.String(256))  # rhnErrata.issue_date


class CVE(DeclBase, DeclMixin):
    """
    @see spacewalk.git/schema/spacewalk/common/tables/rhnCVE.sql
    """
    name = S.Column(S.String(13))  # rhnCVE.name


# Relations:
class PackageFile(DeclBase, DeclMixin):
    """file vs. package

    @see spacewalk.git/schema/spacewalk/common/tables/rhnPackageArch.sql
    @see spacewalk.git/java/code/src/com/redhat/rhn/common/db/datasource/xml/Package_queries.xml
    """
    pid = S.Column(S.Integer, S.ForeignKey("package.id"), nullable=False)
    path = S.Column(S.String(4000))  # rhnPackageCapability.name

    package = SO.relationship(Package, backref="files")


class PackageRequires(DeclBase, DeclMixin):
    """package vs. requires

    @see spacewalk.git/schema/spacewalk/common/tables/rhnPackageRequires.sql
    """
    pid = S.Column(S.Integer, S.ForeignKey("package.id"), nullable=False)
    name = S.Column(S.String(4000))  # rhnPackageCapability.name
    version = S.Column(S.String(64))  # rhnPackageCapability.version

    package = SO.relationship(Package, backref="requires")


class PackageProvides(DeclBase, DeclMixin):
    """package vs. provides

    @see spacewalk.git/schema/spacewalk/common/tables/rhnPackageProvides.sql
    """
    pid = S.Column(S.Integer, S.ForeignKey("package.id"), nullable=False)
    name = S.Column(S.String(4000))  # rhnPackageCapability.name

    package = SO.relationship(Package, backref="provides")


class ChannelPackage(DeclBase, DeclMixin):
    """channel vs. packages
    """
    cid = S.Column(
        S.Integer, S.ForeignKey("softwarechannel.id"), nullable=False
    )
    pid = S.Column(S.Integer, S.ForeignKey("package.id"), nullable=False)

    channel = SO.relationship(SoftwareChannel, backref="channelpackages")
    package = SO.relationship(Package, backref="channelpackages")


class PackageErrata(DeclBase, DeclMixin):
    """package vs. errata
    """
    pid = S.Column(S.Integer, S.ForeignKey("package.id"))
    eid = S.Column(S.Integer, S.ForeignKey("errata.id"))

    package = SO.relationship(Package, backref="packageerrata")
    errata = SO.relationship(Errata, backref="packageerrata")


# vim:sw=4:ts=4:et:
