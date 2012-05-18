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


SQLS = dict(
# spacewalk.git/schema/spacewalk/common/tables/rhnPackageName.sql
# spacewalk.git/schema/spacewalk/common/tables/rhnPackageEVR.sql
# spacewalk.git/schema/spacewalk/common/tables/rhnPackageArch.sql
packages = dict(
    # all_packages_in_channel in
    # packages_in_channel in
    #   spacewalk.git/java/code/src/com/redhat/rhn/common/db/datasource/xml/Package_queries.xml
    # all_channel_tree in
    #   spacewalk.git/java/code/src/com/redhat/rhn/common/db/datasource/xml/Channel_queries.xml
    export = """\
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
""",
    create = """CREATE TABLE IF NOT EXISTS packages(
    id INTEGER PRIMARY KEY,
    name VARCHAR(256) NOT NULL,
    version VARCHAR(512) NOT NULL,
    release VARCHAR(512) NOT NULL,
    epoch VARCHAR(16),
    arch VARCHAR(64) NOT NULL
)
""",
    import_ = "INSERT OR REPLACE INTO packages VALUES (?, ?, ?, ?, ?, ?)",
),

# spacewalk.git/schema/spacewalk/common/tables/rhnPackageFile.sql
# spacewalk.git/schema/spacewalk/common/tables/rhnPackageCapability.sql
package_files = dict(
    # package_files in
    # http://git.fedorahosted.org/git/?p=spacewalk.git;a=blob;f=java/code/src/com/redhat/rhn/common/db/datasource/xml/Package_queries.xml
    export = """SELECT DISTINCT F.package_id, PC.name
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
""",
    create = """CREATE TABLE IF NOT EXISTS package_files(
    package_id INTEGER CONSTRAINT pf_ps REFERENCES packages(id) ON DELETE CASCADE,
    name VARCHAR(4000) NOT NULL
)
""",
    import_ = "INSERT OR REPLACE INTO package_files VALUES (?, ?)",
),

# spacewalk.git/schema/spacewalk/common/tables/rhnPackageRequires.sql
# spacewalk.git/schema/spacewalk/common/tables/rhnPackageCapability.sql
package_requires = dict(
    # package_requires in .../Package_queries.xml
    export = """SELECT DISTINCT PR.package_id, PC.name, PC.version, PR.sense
FROM
  rhnPackageCapability PC,
  rhnPackageRequires PR
  INNER JOIN (rhnChannelPackage CP
    INNER JOIN rhnChannel C
    ON CP.channel_id = C.id)
  ON PR.package_id = CP.package_id
WHERE C.label = '%s' AND PR.capability_id = PC.id
""",
    create = """CREATE TABLE IF NOT EXISTS package_requires(
    package_id INTEGER CONSTRAINT pr_ps REFERENCES packages(id) ON DELETE CASCADE,
    name VARCHAR(4000) NOT NULL,
    modifier VARCHAR(100)
)
""",
    import_ = "INSERT OR REPLACE INTO package_requires VALUES (?, ?, ?)",
),

# spacewalk.git/schema/spacewalk/common/tables/rhnPackageProvides.sql
# spacewalk.git/schema/spacewalk/common/tables/rhnPackageCapability.sql
package_provides = dict(
    # package_provides in .../Package_queries.xml
    export = """SELECT DISTINCT PP.package_id, PC.name, PC.version, PP.sense
FROM
  rhnPackageCapability PC,
  rhnPackageProvides PP
  INNER JOIN (rhnChannelPackage CP
    INNER JOIN rhnChannel C
    ON CP.channel_id = C.id)
  ON PP.package_id = CP.package_id
WHERE C.label = '%s' AND PP.capability_id = PC.id
""",
    create = """CREATE TABLE IF NOT EXISTS package_provides(
    package_id INTEGER CONSTRAINT pp_ps REFERENCES packages(id) ON DELETE CASCADE,
    name VARCHAR(4000) NOT NULL,
    modifier VARCHAR(100)
)
""",
    import_ = "INSERT OR REPLACE INTO package_provides VALUES (?, ?, ?)",
),

# spacewalk.git/schema/spacewalk/common/tables/rhnErrata.sql
errata = dict(
    # in_channel in
    # http://git.fedorahosted.org/git/?p=spacewalk.git;a=blob;f=java/code/src/com/redhat/rhn/common/db/datasource/xml/Errata_queries.xml
    export = """SELECT DISTINCT E.id, E.advisory, E.advisory_name, E.synopsis,
                TO_CHAR(E.issue_date, 'YYYY-MM-DD HH24:MI:SS')
FROM rhnErrata E, rhnChannelErrata CE, rhnChannel C
WHERE CE.channel_id = C.id AND C.label = '%s' AND CE.errata_id = E.id
""",
    create = """CREATE TABLE IF NOT EXISTS errata(
    id INTEGER PRIMARY KEY,
    advisory VARCHAR(100) NOT NULL,
    name VARCHAR(100) NOT NULL,
    synopsis VARCHAR(4000) NOT NULL,
    issue_date VARCHAR(100) NOT NULL
)
""",
    import_ = "INSERT OR REPLACE INTO errata VALUES (?, ?, ?, ?, ?)",
),

package_errata = dict(
    # packages_in_errata in .../Package_queries.xml
    export = """\
SELECT DISTINCT EP.package_id, EP.errata_id
FROM
  rhnErrataPackage EP
  INNER JOIN (rhnChannelPackage CP
    INNER JOIN rhnChannel C
    ON CP.channel_id = C.id)
  ON EP.package_id = CP.package_id
WHERE C.label = '%s'
""",
    create = """CREATE TABLE IF NOT EXISTS package_errata(
    package_id INTEGER CONSTRAINT pe_ps REFERENCES packages(id) ON DELETE CASCADE,
    errata_id INTEGER CONSTRAINT pe2_ps REFERENCES errata(id) ON DELETE CASCADE
)
""",
    import_ = "INSERT OR REPLACE INTO package_errata VALUES (?, ?)",
),

errata_cves = dict(
    # cves_for_errata in .../Errata_querys.xml
    export = """SELECT DISTINCT ECVE.errata_id, CVE.name
FROM
  rhnCVE CVE,
  rhnErrataCVE ECVE
  INNER JOIN (rhnChannelErrata CE
    INNER JOIN rhnChannel C
    ON CE.channel_id = C.id)
  ON ECVE.errata_id = CE.errata_id
WHERE C.label = '%s' AND ECVE.cve_id = CVE.id
""",
    create = """CREATE TABLE IF NOT EXISTS errata_cves(
    errata_id INTEGER CONSTRAINT ec_ps REFERENCES errata(id) ON DELETE CASCADE,
    name VARCHAR(13)
)
""",
    import_ = "INSERT OR REPLACE INTO errata_cves VALUES (?, ?)",
),
)


def getDependencyModifier(version, sense):
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

        return "%s %s" % (op, str(version))
    else:
        return "- " + str(version)


def get_xs(target, conn, repo, sqls=SQLS):
    """Get xs in given repo (software channel).

    :param conn: cx_Oracle Connection object
    :param repo: Repository (Software channel) label
    """
    sql = sqls[target]["export"] % repo
    rs = SQ.execute(conn, sql)

    if target in ("package_requires", "package_provides"):
	return [(r[0], r[1], getDependencyModifier(r[2], r[3])) for r in rs]
    else:
        return rs


def export(target, iconn, repo, sqls=SQLS):
    logging.info("Collecting %s data..." % target)
    rs = get_xs(target, iconn, repo, sqls)
    logging.info("...Done")
    logging.debug(" rs[0]=" + str(rs[0]))

    return rs


def import_(target, oconn, ocur, rs, sqls=SQLS):
    logging.info("Importing %s data [%d] ..." % (target, len(rs)))
    import_dml = sqls[target]["import_"]
    ocur.executemany(import_dml, rs)
    oconn.commit()
    logging.info("...Done")


def collect_and_dump_data(dsn, repo, output, sqls=SQLS):
    iconn = SQ.connect(dsn)

    oconn = sqlite3.connect(output)
    cur = oconn.cursor()

    for tbl, sts in sqls.iteritems():
        create_ddl = sts["create"]
        logging.info("Creating table: " + tbl)
        cur.execute(create_ddl)

    for target in ("packages", "errata", "package_files",
            "package_requires", "package_provides", "package_errata",
            "errata_cves"):
        rs = export(target, iconn, repo)
        import_(target, oconn, cur, rs)

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

    collect_and_dump_data(options.dsn, chan, options.output)


if __name__ == '__main__':
    main(sys.argv)


# vim:sw=4:ts=4:et:
