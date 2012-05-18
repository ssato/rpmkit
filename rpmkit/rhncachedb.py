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
import datetime
import logging
import optparse
import os.path
import os
import sqlite3
import sys
import time


SQLS = dict(
# spacewalk.git/schema/spacewalk/common/tables/rhnPackageName.sql
# spacewalk.git/schema/spacewalk/common/tables/rhnPackageEVR.sql
# spacewalk.git/schema/spacewalk/common/tables/rhnPackageArch.sql
packages = dict(
    # all_packages_in_channel and all_packages_in_channel_after, packages_in_channel in
    #   spacewalk.git/java/code/src/com/redhat/rhn/common/db/datasource/xml/Package_queries.xml
    # all_channel_tree in
    #   spacewalk.git/java/code/src/com/redhat/rhn/common/db/datasource/xml/Channel_queries.xml
    export = """SELECT DISTINCT P.id, PN.name, PE.version, PE.release, PE.epoch, PA.label
FROM rhnPackageArch PA, rhnPackageName PN, rhnPackageEVR PE,
     rhnPackage P, rhnChannelPackage CP, rhnChannel C
WHERE CP.channel_id = C.id
      AND C.label = '%s'
      AND CP.package_id = P.id
      AND P.name_id = PN.id
      AND P.evr_id = PE.id
      AND PA.id = P.package_arch_id %s
ORDER BY UPPER(PN.name), P.id
""",
    export_since = "AND P.last_modified > TO_DATE('%s', 'YYYY-MM-DD')",
    create = """CREATE TABLE IF NOT EXISTS packages(
    id INTEGER PRIMARY KEY,
    name VARCHAR(256) NOT NULL,
    version VARCHAR(512) NOT NULL,
    release VARCHAR(512) NOT NULL,
    epoch VARCHAR(16),
    arch VARCHAR(64) NOT NULL
)
""",
    import_ = "INSERT OR IGNORE INTO packages VALUES (?, ?, ?, ?, ?, ?)",
),

# spacewalk.git/schema/spacewalk/common/tables/rhnPackageFile.sql
# spacewalk.git/schema/spacewalk/common/tables/rhnPackageCapability.sql
package_files = dict(
    # package_files in
    # http://git.fedorahosted.org/git/?p=spacewalk.git;a=blob;f=java/code/src/com/redhat/rhn/common/db/datasource/xml/Package_queries.xml
    export = """SELECT DISTINCT F.package_id, PC.name
FROM
  rhnPackageCapability PC,
  rhnPackage P,
  rhnPackageFile F
  INNER JOIN (rhnChannelPackage CP
    INNER JOIN rhnChannel C
    ON CP.channel_id = C.id)
  ON F.package_id = CP.package_id
WHERE F.capability_id = PC.id
      AND C.label = '%s' %s
ORDER BY UPPER(PC.name)
""",
    export_since = "AND F.package_id = P.id AND P.last_modified > TO_DATE('%s', 'YYYY-MM-DD')",
    create = """CREATE TABLE IF NOT EXISTS package_files(
    package_id INTEGER CONSTRAINT pf_ps REFERENCES packages(id) ON DELETE CASCADE,
    name VARCHAR(4000) NOT NULL,
    basename VARCHAR(4000) NOT NULL
)
""",
    import_ = "INSERT OR IGNORE INTO package_files VALUES (?, ?, ?)",
),

# spacewalk.git/schema/spacewalk/common/tables/rhnPackageRequires.sql
# spacewalk.git/schema/spacewalk/common/tables/rhnPackageCapability.sql
package_requires = dict(
    # package_requires in .../Package_queries.xml
    export = """SELECT DISTINCT PR.package_id, PC.name, PC.version, PR.sense
FROM
  rhnPackage P,
  rhnPackageCapability PC,
  rhnPackageRequires PR
  INNER JOIN (rhnChannelPackage CP
    INNER JOIN rhnChannel C
    ON CP.channel_id = C.id)
  ON PR.package_id = CP.package_id
WHERE C.label = '%s' AND PR.capability_id = PC.id %s
""",
    export_since = "AND P.id = PR.package_id and P.last_modified > TO_DATE('%s', 'YYYY-MM-DD')",
    create = """CREATE TABLE IF NOT EXISTS package_requires(
    package_id INTEGER CONSTRAINT pr_ps REFERENCES packages(id) ON DELETE CASCADE,
    name VARCHAR(4000) NOT NULL,
    modifier VARCHAR(100)
)
""",
    import_ = "INSERT OR IGNORE INTO package_requires VALUES (?, ?, ?)",
),

# spacewalk.git/schema/spacewalk/common/tables/rhnPackageProvides.sql
# spacewalk.git/schema/spacewalk/common/tables/rhnPackageCapability.sql
package_provides = dict(
    # package_provides in .../Package_queries.xml
    export = """SELECT DISTINCT PP.package_id, PC.name, PC.version, PP.sense
FROM
  rhnPackage P,
  rhnPackageCapability PC,
  rhnPackageProvides PP
  INNER JOIN (rhnChannelPackage CP
    INNER JOIN rhnChannel C
    ON CP.channel_id = C.id)
  ON PP.package_id = CP.package_id
WHERE C.label = '%s' AND PP.capability_id = PC.id %s
""",
    export_since = "AND PP.package_id = P.id AND P.last_modified > TO_DATE('%s', 'YYYY-MM-DD')",
    create = """CREATE TABLE IF NOT EXISTS package_provides(
    package_id INTEGER CONSTRAINT pp_ps REFERENCES packages(id) ON DELETE CASCADE,
    name VARCHAR(4000) NOT NULL,
    modifier VARCHAR(100)
)
""",
    import_ = "INSERT OR IGNORE INTO package_provides VALUES (?, ?, ?)",
),

# spacewalk.git/schema/spacewalk/common/tables/rhnErrata.sql
errata = dict(
    # in_channel in
    # http://git.fedorahosted.org/git/?p=spacewalk.git;a=blob;f=java/code/src/com/redhat/rhn/common/db/datasource/xml/Errata_queries.xml
    export = """SELECT DISTINCT E.id, E.advisory, E.advisory_name, E.synopsis,
                TO_CHAR(E.issue_date, 'YYYY-MM-DD HH24:MI:SS')
FROM rhnErrata E, rhnChannelErrata CE, rhnChannel C
WHERE CE.channel_id = C.id AND C.label = '%s' AND CE.errata_id = E.id %s
""",
    export_since = "AND E.last_modified > TO_DATE('%s', 'YYYY-MM-DD')",
    create = """CREATE TABLE IF NOT EXISTS errata(
    id INTEGER PRIMARY KEY,
    advisory VARCHAR(100) NOT NULL,
    name VARCHAR(100) NOT NULL,
    synopsis VARCHAR(4000) NOT NULL,
    issue_date VARCHAR(100) NOT NULL
)
""",
    import_ = "INSERT OR IGNORE INTO errata VALUES (?, ?, ?, ?, ?)",
),

package_errata = dict(
    # packages_in_errata in .../Package_queries.xml
    export = """\
SELECT DISTINCT EP.package_id, EP.errata_id
FROM
  rhnPackage P,
  rhnErrataPackage EP
  INNER JOIN (rhnChannelPackage CP
    INNER JOIN rhnChannel C
    ON CP.channel_id = C.id)
  ON EP.package_id = CP.package_id
WHERE C.label = '%s' %s
""",
    export_since = "AND EP.package_id = P.id AND P.last_modified > TO_DATE('%s', 'YYYY-MM-DD')",
    create = """CREATE TABLE IF NOT EXISTS package_errata(
    package_id INTEGER CONSTRAINT pe_ps REFERENCES packages(id) ON DELETE CASCADE,
    errata_id INTEGER CONSTRAINT pe2_ps REFERENCES errata(id) ON DELETE CASCADE
)
""",
    import_ = "INSERT OR IGNORE INTO package_errata VALUES (?, ?)",
),

errata_cves = dict(
    # cves_for_errata in .../Errata_querys.xml
    export = """SELECT DISTINCT ECVE.errata_id, CVE.name
FROM
  rhnErrata E,
  rhnCVE CVE,
  rhnErrataCVE ECVE
  INNER JOIN (rhnChannelErrata CE
    INNER JOIN rhnChannel C
    ON CE.channel_id = C.id)
  ON ECVE.errata_id = CE.errata_id
WHERE C.label = '%s' AND ECVE.cve_id = CVE.id %s
""",
    export_since = "AND ECVE.errata_id = E.id AND E.last_modified > TO_DATE('%s', 'YYYY-MM-DD')",
    create = """CREATE TABLE IF NOT EXISTS errata_cves(
    errata_id INTEGER CONSTRAINT ec_ps REFERENCES errata(id) ON DELETE CASCADE,
    name VARCHAR(13)
)
""",
    import_ = "INSERT OR IGNORE INTO errata_cves VALUES (?, ?)",
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


def get_xs(target, conn, repo, sqls=SQLS, since=None):
    """Get xs in given repo (software channel).

    :param conn: cx_Oracle Connection object
    :param repo: Repository (Software channel) label
    :param sqls: SQL statements map
    :param since: date (YY-MM-DD) denotes "since ..."
    """
    since_ = sqls[target]["export_since"] % since if since else ""
    sql = sqls[target]["export"] % (repo, since_)

    rs = SQ.execute(conn, sql)

    if target in ("package_requires", "package_provides"):
        return [(r[0], r[1], getDependencyModifier(r[2], r[3])) for r in rs]
    elif target == "package_files":
        return [(r[0], r[1], os.path.basename(r[1])) for r in rs]
    else:
        return rs


def export(target, iconn, repo, sqls=SQLS, since=None):
    logging.info("Collecting %s data..." % target)
    rs = get_xs(target, iconn, repo, sqls, since)
    if rs:
        logging.debug(" rs[0]=" + str(rs[0]))

    return rs


def import_(target, oconn, ocur, rs, sqls=SQLS):
    logging.info("Importing %s data [%d] ..." % (target, len(rs)))
    ocur.executemany(sqls[target]["import_"], rs)
    oconn.commit()


def collect_and_import_data(dsn, repo, output, sqls=SQLS, since=None):
    iconn = SQ.connect(dsn)

    oconn = sqlite3.connect(output)
    cur = oconn.cursor()

    targets = (
        "packages", "errata", "package_files", "package_requires",
        "package_provides", "package_errata", "errata_cves",
    )

    for target in targets:
        logging.info("Creating table: " + target)
        create_ddl = sqls[target]["create"]
        try:
            cur.execute(create_ddl)
        except:
            logging.error("create_ddl was:\n" + create_ddl)
            raise

    for target in targets:
        rs = export(target, iconn, repo, sqls, since)
        import_(target, oconn, cur, rs)

    cur.close()


def option_parser(prog="swapi"):
    defaults = dict(
        output=None,
        outdir=os.curdir,
        dsn="rhnsat/rhnsat@rhnsat",
        since=None,
        debug=False,
    )
    p = optparse.OptionParser(
        "%prog [OPTION ...] CHANNEL_LABEL_0 [CHANNEL_LABEL_1 ...]"
    )
    p.set_defaults(**defaults)

    p.add_option("-o", "--output",
        help="Output filename [<channel_label>.db]. " + \
            "Ignored if multiple channels given."
    )
    p.add_option("-O", "--outdir", help="Output directory. [%default]")
    p.add_option("", "--dsn", help="Data source name [%default]")
    p.add_option("-S", "--since",
        help="Collect data since this date given in the form of \"yyyy-mm-dd\""
    )
    p.add_option("-D", "--debug", action="store_true", help="Debug mode")

    return p


def run(dsn, chan, output, since, sqls=SQLS):
    start_time = time.time()
    logging.info("start at %s: channel=%s" % (datetime.datetime.now(), chan))
    logging.debug(
        "dsn=%s, chan=%s, output=%s, since=%s" % (dsn, chan, output, since)
    )
    collect_and_import_data(dsn, chan, output, sqls, since)
    logging.info(
        "finished at %s [%f sec]" % (
            datetime.datetime.now(), time.time() - start_time
        )
    )


def main(argv=sys.argv):
    logging.getLogger().setLevel(logging.INFO)

    p = option_parser()
    (options, args) = p.parse_args(argv[1:])

    if not args:
        p.print_help()
        sys.exit(0)

    if options.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if len(args) == 1:
        chan = args[0]

        if not options.output:
            options.output = os.path.join(options.outdir, chan + ".db")

        run(options.dsn, chan, options.output, options.since)
    else:
        for chan in args:
            output = os.path.join(options.outdir, chan + ".db")
            run(options.dsn, chan, output, options.since)


if __name__ == '__main__':
    main(sys.argv)


# vim:sw=4:ts=4:et:
