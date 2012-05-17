#
# rpmkit.rhncachedb - Create cache database from RHN Satellite database
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
import rpmkit.sqlminus as SQ
import logging
import optparse
import os.path
import sqlite3
import sys


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

# spacewalk.git/schema/spacewalk/common/tables/rhnPackageName.sql
# spacewalk.git/schema/spacewalk/common/tables/rhnPackageEVR.sql
# spacewalk.git/schema/spacewalk/common/tables/rhnPackageArch.sql
PACKAGES_CREATE = """
CREATE TABLE packages IF NOT EXISTS (
    id INTEGER PRIMARY KEY,
    name VARCHAR(256) NOT NULL,
    version VARCHAR(512) NOT NULL,
    release VARCHAR(512) NOT NULL,
    epoch VARCHAR(16),
    arch VARCHAR(64) NOT NULL
)
"""
PACKAGES_INS = "INSERT INTO packages VALUES (?, ?, ?, ?, ?, ?)"


# spacewalk.git/schema/spacewalk/common/tables/rhnPackageFile.sql
# spacewalk.git/schema/spacewalk/common/tables/rhnPackageCapability.sql
PACKAGE_FILES_CREATE = """
CREATE TABLE package_files IF NOT EXISTS (
    package_id INTEGER CONSTRAINT pf_ps REFERENCES packages(id) ON DELETE CASCADE,
    name VARCHAR(4000) NOT NULL
)
"""
PACKAGE_FILES_INS = "INSERT INTO package_files VALUES (?, ?)"

# spacewalk.git/schema/spacewalk/common/tables/rhnPackageRequires.sql
# spacewalk.git/schema/spacewalk/common/tables/rhnPackageCapability.sql
PACKAGE_REQUIRES_CREATE = """
CREATE TABLE package_requires IF NOT EXISTS (
    package_id INTEGER CONSTRAINT pr_ps REFERENCES packages(id) ON DELETE CASCADE,
    name VARCHAR(4000) NOT NULL,
    modifier VARCHAR(100) NOT NULL
)
"""
PACKAGE_REQUIRES_INS = "INSERT INTO package_requires VALUES (?, ?, ?)"

# spacewalk.git/schema/spacewalk/common/tables/rhnPackageProvides.sql
# spacewalk.git/schema/spacewalk/common/tables/rhnPackageCapability.sql
PACKAGE_PROVIDES_CREATE = """
CREATE TABLE package_provides IF NOT EXISTS (
    package_id INTEGER CONSTRAINT pp_ps REFERENCES packages(id) ON DELETE CASCADE,
    name VARCHAR(4000) NOT NULL,
    modifier VARCHAR(100) NOT NULL
)
"""
PACKAGE_PROVIDES_INS = "INSERT INTO package_provides VALUES (?, ?, ?)"

# spacewalk.git/schema/spacewalk/common/tables/rhnErrata.sql
ERRATA_CREATE = """
CREATE TABLE errata IF NOT EXISTS (
    id INTEGER PRIMARY KEY,
    advisory VARCHAR(100) NOT NULL,
    name VARCHAR(100) NOT NULL,
    synopsis VARCHAR(4000) NOT NULL,
    issue_date VARCHAR(100) NOT NULL
)
"""
ERRATA_INS = "INSERT INTO errata VALUES (?, ?, ?, ?, ?)"

PACKAGE_ERRATA_CREATE = """
CREATE TABLE package_errata IF NOT EXISTS (
    package_id INTEGER CONSTRAINT pe_ps REFERENCES packages(id) ON DELETE CASCADE,
    errata_id INTEGER CONSTRAINT pe2_ps REFERENCES errata(id) ON DELETE CASCADE
)
"""
PACKAGE_ERRATA_INS = "INSERT INTO package_errata VALUES (?, ?)"

ERRATA_CVES_CREATE = """
CREATE TABLE errata_cves IF NOT EXISTS (
    errata_id INTEGER CONSTRAINT ec_ps REFERENCES errata(id) ON DELETE CASCADE,
    name VARCHAR(13)
)
"""
ERRATA_CVES_INS = "INSERT INTO errata_cves VALUES (?, ?)"


def ts2d(tuple, keys):
    return dict(zip(tuple, keys))


def get_packages(conn, repo):
    """
    Get all packages in given repo (software channel).

    :param conn: cx_Oracle Connection object
    :param repo: Repository (Software channel) label
    """
    sql = all_packages_in_channel_sql % repo
    rs = SQ.execute(conn, sql)
    keys = ("id", "name", "version", "release", "epoch", "arch")

    return [ts2d(r, keys) for r in rs]


def get_errata(conn, repo):
    """
    Get all errata in given repo (software channel).

    :param conn: cx_Oracle Connection object
    :param repo: Repository (Software channel) label
    """
    sql = all_errata_in_channel_sql % repo
    rs = SQ.execute(conn, sql)
    keys = ("id", "advisory", "name", "synopsis", "issue_date")

    return [ts2d(r, keys) for r in rs]


def get_packages_files(conn, repo):
    """
    Get all files in packages in given repo (software channel).

    :param conn: cx_Oracle Connection object
    :param repo: Repository (Software channel) label
    """
    sql = all_files_in_packages_in_channel_sql % repo
    rs = SQ.execute(conn, sql)
    keys = ("package_id", "filepath")

    return [ts2d(r, keys) for r in rs]


def get_packages_errata(conn, repo):
    """
    Get all errata in packages in given repo (software channel).

    :param conn: cx_Oracle Connection object
    :param repo: Repository (Software channel) label
    """
    sql = all_errata_in_packages_in_channel_sql % repo
    rs = SQ.execute(conn, sql)
    keys = ("package_id", "errata_id")

    return [ts2d(r, keys) for r in rs]


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
    Get all requires of packages in given repo (software channel).

    :param conn: cx_Oracle Connection object
    :param repo: Repository (Software channel) label
    """
    sql = all_requires_in_packages_in_channel_sql % repo

    # [(package_id, cabability_name, capability_version, requires_sense)]
    rs = SQ.execute(conn, sql)
    keys = ("package_id", "name", "modifier")

    return [
        ts2d((r[0], r[1], getDependencyModifier(r[2], r[3])), keys) for r in rs
    ]


def get_packages_provides(conn, repo):
    """
    Get all provides of packages in given repo (software channel).

    :param conn: cx_Oracle Connection object
    :param repo: Repository (Software channel) label
    """
    sql = all_provides_in_packages_in_channel_sql % repo

    # [(package_id, cabability_name, capability_version, provides_sense)]
    rs = SQ.execute(conn, sql)
    keys = ("package_id", "name", "modifier")

    return [
        ts2d((r[0], r[1], getDependencyModifier(r[2], r[3])), keys) for r in rs
    ]


def get_errata_cves(conn, repo):
    """
    Get all cves of errata in given repo (software channel).

    :param conn: cx_Oracle Connection object
    :param repo: Repository (Software channel) label
    :return: [(errata_id, cve)]
    """
    sql = all_cves_in_errata_in_channel_sql % repo
    rs = SQ.execute(conn, sql)
    keys = ("errata_id", "name")

    return [ts2d(r, keys) for r in rs]


def create_db(output):
    conn = sqlite3.connect(output)
    cur = conn.cursor()

    for ddl in (PACKAGES_CREATE, PACKAGE_FILES_CREATE, PACKAGE_REQUIRES_CREATE,
            PACKAGE_PROVIDES_CREATE, ERRATA_CREATE, PACKAGE_ERRATA_CREATE,
            ERRATA_CVES_CREATE):
        cur.execute(ddl)

    conn.commit()
    cur.close()



def collect_and_dump_data(dsn, repo, output):
    iconn = SQ.connect(dsn)

    oconn = sqlite3.connect(output)
    cur = conn.cursor()

    packages = get_packages(iconn, repo)
    cur.executemany(PACKAGES_INS, packages)
    oconn.commit()

    errata = get_errata(iconn, repo)
    cur.executemany(ERRATA_INS, errata)
    oconn.commit()

    package_files = get_packages_files(iconn, repo)
    cur.executemany(PACKAGE_FILES_INS, package_files)
    oconn.commit()

    package_errata = get_packages_errata(iconn, repo)
    cur.executemany(PACKAGE_ERRATA_INS, package_errata)
    oconn.commit()

    package_requires = get_packages_requires(iconn, repo)
    cur.executemany(PACKAGE_REQUIRES_INS, package_requires)
    oconn.commit()

    package_provides = get_packages_provides(iconn, repo)
    cur.executemany(PACKAGE_PROVIDES_INS, package_provides)
    oconn.commit()

    errata_cves = get_errata_cves(iconn, repo)
    cur.executemany(ERRATA_CVES_INS, errata_cves)
    oconn.commit()

    cur.close()


def option_parser(prog="swapi"):
    defaults = dict(
        output=None,
        dsn="rhnsat/rhnsat@rhnsat",
        debug=False,
    )
    p = optparse.OptionParser("%prog [OPTION ...] CHANNEL_LABEL")
    p.set_defaults(**defaults)

    p.add_option("-o", "--output", help="Output filename [<channel_label>.db]")
    p.add_option("", "--dsn", help="Data source name [%default]")
    p.add_option("-D", "--debug", action="store_true", help="Debug mode")

    return p


def main(argv=sys.argv):
    logging.getLogger().setLevel(logging.INFO)

    p = option_parser()
    (options, args) = p.parse_args(argv[1:])

    if not args:
        p.print_help()
        sys.exit(0)

    if options.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    chan = args[0]

    if not options.output:
        options.output = chan + ".db"

    create_db(options.output)

    collect_and_dump_data(options.dsn, chan, options.output)


if __name__ == '__main__':
    main(sys.argv)


# vim:sw=4:ts=4:et:
