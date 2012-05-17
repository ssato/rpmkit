#
# rpmdb.datasrc.satellite - Retrieve data from RHN Satellite database
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
SELECT P.id, PN.name, PE.version, PE.release, PE.epoch, PA.label
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
SELECT P.id, PC.name
FROM rhnPackageFile F INNER JOIN (rhnPackage P INNER JOIN (rhnChannelPackage CP INNER JOIN rhnChannel C ON CP.channel_id = C.id) ON P.id = CP.package_id) ON F.package_id = P.id
     rhnPackageCapability PC
WHERE F.capability_id = PC.id
      AND C.label = '%s'
ORDER BY UPPER(PC.name)
"""

all_files_in_packages_in_channel_sql_2 = """\
SELECT P.id, PC.name
FROM rhnPackageFile F,
     rhnPackage P,
     rhnChannelPackage CP,
     rhnChannel C,
     rhnPackageCapability PC
WHERE C.label = '%s'
      AND CP.channel_id = C.id
      AND CP.package_id = P.id
      AND F.package_id = P.id
ORDER BY UPPER(PC.name)
"""

# packages_in_errata in .../Package_queries.xml
all_errata_in_packages_in_channel_sql = """\
SELECT P.id, PC.name
FROM rhnPackageFile F,
     rhnPackage P,
     rhnChannelPackage CP,
     rhnChannel C,
     rhnPackageCapability PC
WHERE C.label = '%s'
      AND CP.channel_id = C.id
      AND CP.package_id = P.id
      AND F.package_id = P.id
ORDER BY UPPER(PC.name)

 FROM rhnPackageName PN,
      rhnPackageEVR PE,
      rhnPackageArch PA,
      rhnPackage P,
      rhnErrataPackage EP
WHERE EP.errata_id = :eid
  AND EP.package_id = P.id
  AND PN.id = P.name_id
  AND PE.id = P.evr_id
  AND PA.id = P.package_arch_id
ORDER BY UPPER(PN.name), PE.version, PE.release, PE.epoch, PA.label, P.id
"""




def get_packages(repo):
    """
    :param repo: Repository (Software channel) label
    """
    conn = SQ.connect()
    sql = all_packages_in_channel_sql % repo
    rs = SQ.execute(conn, sql)  # [(id, name, version, release, epoch, arch)]


def get_errata(repo):
    conn = SQ.connect()
    sql = all_errata_in_channel_sql % repo
    rs = SQ.execute(conn, sql)  # [(id, name, version, release, epoch, arch)]


# vim:sw=4:ts=4:et:
