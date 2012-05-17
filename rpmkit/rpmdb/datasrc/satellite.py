#
# rpmdb.datasrc.satellite - Retrieve data from RHN Satellite database
#
# Copyright (C) 2012 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato@redhat.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.
#
from rpmkit.Bunch import Bunch

import rpmkit.rpmdb.datasrc.base as B
import rpmkit.rpmdb.models.packages as MP
import rpmkit.sqlminus as SQ


# all_packages_in_channel in 
# packages_in_channel in
#   spacewalk.git/java/code/src/com/redhat/rhn/common/db/datasource/xml/Package_queries.xml
# all_channel_tree in 
#   spacewalk.git/java/code/src/com/redhat/rhn/common/db/datasource/xml/Channel_queries.xml
all_packages_in_channel_sql = """\
SELECT DISTINCT P.id, PN.name, PE.version, PE.release, PE.epoch, PA.label
FROM rhnPackageArch PA, rhnPackageName PN, rhnPackageEVR PE,
     rhnPackage P, rhnChannelPackage CP, rhnChannel C
WHERE CP.channel_id = C.id
      AND C.label = '%s'
      AND CP.package_id = P.id
      AND P.name_id = PN.id
      AND P.evr_id = PE.id
      AND PA.id = P.package_arch_id
ORDER BY UPPER(PN.name), P.id
"""

# in_channel in
# http://git.fedorahosted.org/git/?p=spacewalk.git;a=blob;f=java/code/src/com/redhat/rhn/common/db/datasource/xml/Errata_queries.xml
all_errata_in_channel_sql = """\
SELECT DISTINCT E.id, E.advisory, E.advisory_name, E.synopsis,
                TO_CHAR(E.issue_date, 'YYYY-MM-DD HH24:MI:SS')
FROM rhnErrata E, rhnChannelErrata CE, rhnChannel C
WHERE CE.channel_id = C.id AND C.label = '%s' AND CE.errata_id = E.id
"""

# package_files in
# http://git.fedorahosted.org/git/?p=spacewalk.git;a=blob;f=java/code/src/com/redhat/rhn/common/db/datasource/xml/Package_queries.xml
all_files_in_packages_in_channel_sql = """\
SELECT DISTINCT F.package_id, PC.name
FROM
  rhnPackageCapability PC,
  rhnPackageFile F
  INNER JOIN (rhnChannelPackage CP
    INNER JOIN rhnChannel C
    ON CP.channel_id = C.id)
  ON F.package_id = CP.package_id
WHERE F.capability_id = PC.id
      AND C.label = '%s'
ORDER BY UPPER(PC.name)
"""

# package_requires in .../Package_queries.xml
all_requires_in_packages_in_channel_sql = """\
SELECT DISTINCT PR.package_id, PC.name, PC.version, PR.sense
FROM
  rhnPackageCapability PC,
  rhnPackageRequires PR
  INNER JOIN (rhnChannelPackage CP
    INNER JOIN rhnChannel C
    ON CP.channel_id = C.id)
  ON PR.package_id = CP.package_id
WHERE C.label = '%s' AND PR.capability_id = PC.id
"""

# package_provides in .../Package_queries.xml
all_provides_in_packages_in_channel_sql = """\
SELECT DISTINCT PP.package_id, PC.name, PC.version, PP.sense
FROM
  rhnPackageCapability PC,
  rhnPackageProvides PP
  INNER JOIN (rhnChannelPackage CP
    INNER JOIN rhnChannel C
    ON CP.channel_id = C.id)
  ON PP.package_id = CP.package_id
WHERE C.label = '%s' AND PP.capability_id = PC.id
"""

# packages_in_errata in .../Package_queries.xml
all_errata_in_packages_in_channel_sql = """\
SELECT DISTINCT EP.package_id, EP.errata_id
FROM
  rhnErrataPackage EP
  INNER JOIN (rhnChannelPackage CP
    INNER JOIN rhnChannel C
    ON CP.channel_id = C.id)
  ON EP.package_id = CP.package_id
WHERE C.label = '%s'
"""

# cves_for_errata in .../Errata_querys.xml
all_cves_in_errata_in_channel_sql = """
SELECT DISTINCT ECVE.errata_id, CVE.name
FROM
  rhnCVE CVE,
  rhnErrataCVE ECVE
  INNER JOIN (rhnChannelErrata CE
    INNER JOIN rhnChannel C
    ON CE.channel_id = C.id)
  ON ECVE.errata_id = CE.errata_id
WHERE C.label = '%s' AND ECVE.cve_id = CVE.id
"""


def get_packages(conn, repo):
    """
    :param conn: cx_Oracle Connection object
    :param repo: Repository (Software channel) label
    """
    sql = all_packages_in_channel_sql % repo
    rs = SQ.execute(conn, sql)  # [(id, name, version, release, epoch, arch)]

    return [MP.Package(*r) for r in rs]


def get_errata(conn, repo):
    sql = all_errata_in_channel_sql % repo
    rs = SQ.execute(conn, sql)  # [(id, advisory, name, synopsis, issue_date)]

    return [MP.Errata(*r) for r in rs]


def get_packages_files(conn, repo):
    """
    :return: [(package_id, filepath)]
    """
    sql = all_files_in_packages_in_channel_sql % repo
    rs = SQ.execute(conn, sql)  # [(package_id, filepath)]

    return [MP.PackageFile(*r) for r in rs]


def get_packages_errata(conn, repo):
    """
    :return: [(package_id, filepath)]
    """
    sql = all_errata_in_packages_in_channel_sql % repo
    rs = SQ.execute(conn, sql)  # [(package_id, errata_id)]

    return [MP.PackageErrata(*r) for r in rs]


def getDependencyModifier(sense, version):
    """
    see also: getDependencyModifier in
    spacewalk.git/java/code/src/com/redhat/rhn/frontend/xmlrpc/packages/PackagesHandler.java

    (spacewalk's code is distributed under GPLv2)
    """
    if not version:
        return None

    if sense:
        op = ""
        if sense & 4 > 0:
            op = ">"
        elif sense & 2 > 0:
            op = "<"

        if sense & 8 > 0:
            op += "="

        return " ".join(op, version)
    else:
        return "- " + version


def get_packages_requires(conn, repo):
    """
    :return: [(package_id, requires_name, modifier)]

    see also: getDependencyModifier in
    spacewalk.git/java/code/src/com/redhat/rhn/frontend/xmlrpc/packages/PackagesHandler.java
    """
    sql = all_requires_in_packages_in_channel_sql % repo

    # [(package_id, cabability_name, capability_version, requires_sense)]
    rs = SQ.execute(conn, sql)

    return [
        MP.PackageRequires(
            r[0], r[1], getDependencyModifier(r[2], r[3])
        ) for r in rs
    ]


def get_packages_provides(conn, repo):
    """
    :return: [(package_id, provides_name, modifier)]
    """
    sql = all_provides_in_packages_in_channel_sql % repo
    rs = SQ.execute(conn, sql)

    return [
        MP.PackageProvides(
            r[0], r[1], getDependencyModifier(r[2], r[3])
        ) for r in rs
    ]


def get_errata_cves(conn, repo):
    """
    :return: [(errata_id, cve)]
    """
    sql = all_cves_in_errata_in_channel_sql % repo
    rs = SQ.execute(conn, sql)

    return rs


# vim:sw=4:ts=4:et:
