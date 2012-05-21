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
    export = """
SELECT DISTINCT P.id, PN.name, PE.version, PE.release, PE.epoch, PA.label, P.summary
FROM
  rhnPackageArch PA,
  rhnPackageName PN,
  rhnPackageEVR PE,
  rhnPackage P, %(since_tables)s
  rhnChannelPackage CP
    INNER JOIN rhnChannel C
    ON CP.channel_id = C.id
WHERE
  C.label = '%(repo)s'
  AND CP.package_id = P.id
  AND PN.id = P.name_id
  AND PE.id = P.evr_id
  AND PA.id = P.package_arch_id %(since_cond)s
ORDER BY PN.name, P.id
""",
    export_since_tables = "",
    export_since_cond = "AND P.last_modified > TO_DATE('%s', 'YYYY-MM-DD')",
    create = """CREATE TABLE IF NOT EXISTS packages(
    id INTEGER PRIMARY KEY,
    name VARCHAR(256) NOT NULL,
    version VARCHAR(512) NOT NULL,
    release VARCHAR(512) NOT NULL,
    epoch VARCHAR(16),
    arch VARCHAR(64) NOT NULL,
    summary VARCHAR(4000) NOT NULL
)
""",
    import_ = "INSERT OR IGNORE INTO packages VALUES (?, ?, ?, ?, ?, ?, ?)",
),

# spacewalk.git/schema/spacewalk/common/tables/rhnPackageFile.sql
# spacewalk.git/schema/spacewalk/common/tables/rhnPackageCapability.sql
package_files = dict(
    # package_files in
    # http://git.fedorahosted.org/git/?p=spacewalk.git;a=blob;f=java/code/src/com/redhat/rhn/common/db/datasource/xml/Package_queries.xml
    export = """SELECT DISTINCT F.package_id, PC.name
FROM
  rhnPackageCapability PC, %(since_tables)s
  rhnPackageFile F
  INNER JOIN (rhnChannelPackage CP
    INNER JOIN rhnChannel C
    ON CP.channel_id = C.id)
  ON F.package_id = CP.package_id
WHERE F.capability_id = PC.id
      AND C.label = '%(repo)s' %(since_cond)s
ORDER BY PC.name
""",
    export_since_tables = "rhnPackage P, ",
    export_since_cond = "AND F.package_id = P.id AND P.last_modified > TO_DATE('%s', 'YYYY-MM-DD')",
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
  rhnPackageCapability PC, %(since_tables)s
  rhnPackageRequires PR
  INNER JOIN (rhnChannelPackage CP
    INNER JOIN rhnChannel C
    ON CP.channel_id = C.id)
  ON PR.package_id = CP.package_id
WHERE C.label = '%(repo)s'
      AND PR.capability_id = PC.id %(since_cond)s
""",
    export_since_tables = "rhnPackage P, ",
    export_since_cond = "AND P.id = PR.package_id AND P.last_modified > TO_DATE('%s', 'YYYY-MM-DD')",
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
  rhnPackageCapability PC, %(since_tables)s
  rhnPackageProvides PP
  INNER JOIN (rhnChannelPackage CP
    INNER JOIN rhnChannel C
    ON CP.channel_id = C.id)
  ON PP.package_id = CP.package_id
WHERE C.label = '%(repo)s'
      AND PP.capability_id = PC.id %(since_cond)s
""",
    export_since_tables = "rhnPackage P, ",
    export_since_cond = "AND PP.package_id = P.id AND P.last_modified > TO_DATE('%s', 'YYYY-MM-DD')",
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
FROM
  rhnErrata E, %(since_tables)s
  rhnChannelErrata CE
    INNER JOIN rhnChannel C
    ON CE.channel_id = C.id
WHERE C.label = '%(repo)s' AND CE.errata_id = E.id %(since_cond)s
""",
    export_since_tables = "",
    export_since_cond = "AND E.last_modified > TO_DATE('%s', 'YYYY-MM-DD')",
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
    export = """SELECT DISTINCT EP.package_id, EP.errata_id
FROM
  rhnErrataPackage EP, %(since_tables)s
  rhnChannelPackage CP
    INNER JOIN rhnChannel C
    ON CP.channel_id = C.id
WHERE C.label = '%(repo)s' AND CP.package_id = EP.package_id %(since_cond)s
""",
    export_since_tables = "rhnErrata E, ",
    export_since_cond = "AND EP.errata_id = E.id AND E.last_modified > TO_DATE('%s', 'YYYY-MM-DD')",
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
  rhnCVE CVE, %(since_tables)s
  rhnErrataCVE ECVE
  INNER JOIN (rhnChannelErrata CE
    INNER JOIN rhnChannel C
    ON CE.channel_id = C.id)
  ON ECVE.errata_id = CE.errata_id
WHERE C.label = '%(repo)s' AND ECVE.cve_id = CVE.id %(since_cond)s
""",
    export_since_tables = "rhnErrata E, ",
    export_since_cond = "AND ECVE.errata_id = E.id AND E.last_modified > TO_DATE('%s', 'YYYY-MM-DD')",
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


def process_row(row, target):
    if target in ("package_requires", "package_provides"):
        return (row[0], row[1], getDependencyModifier(row[2], row[3]))
    elif target == "package_files":
        return (row[0], row[1], os.path.basename(row[1]))
    else:
        return row  # Do nothing.


def get_xs_g(target, conn, repo, sqls=SQLS, since=None):
    """Get xs in given repo (software channel).

    :param conn: cx_Oracle Connection object
    :param repo: Repository (Software channel) label
    :param sqls: SQL statements map
    :param since: date (YY-MM-DD) denotes "since ..."
    """
    if since:
        params = dict(
            repo=repo,
            since_tables=sqls[target]["export_since_tables"],
            since_cond=sqls[target]["export_since_cond"] % since,
        )
    else:
        params = dict(repo=repo, since_tables="", since_cond="")

    sql = sqls[target]["export"] % params

    for row in SQ.execute_g(conn, sql):
        yield process_row(row, target)


def export_g(target, iconn, repo, sqls=SQLS, since=None):
    logging.info("Collecting data of " + target)
    try:
        for row in get_xs_g(target, iconn, repo, sqls, since):
            yield row
    except:
        logging.error("target=%s, repo=%s" % (target, repo))
        raise


def export_and_import(target, iconn, oconn, repo, sqls=SQLS, since=None):
    logging.info("Importing data from: " + target)
    cur = oconn.cursor()

    for row in export_g(target, iconn, repo, sqls, since):
        cur.execute(sqls[target]["import_"], row)

    cur.close()
    oconn.commit()


def import_(target, oconn, rs, sqls=SQLS):
    logging.info("Importing %s data [%d] ..." % (target, len(rs)))
    cur = oconn.cursor()
    cur.executemany(sqls[target]["import_"], rs)
    cur.close()
    oconn.commit()


def collect_and_import_data(dsn, repo, output, sqls=SQLS, since=None,
        extra=False):
    iconn = SQ.connect(dsn)
    oconn = sqlite3.connect(output)

    targets = [
        "packages", "errata", "errata_cves", "package_requires",
        "package_provides", "package_errata",
    ]

    if extra:
        targets.append("package_files")

    for target in targets:
        logging.info("Creating table: " + target)
        create_ddl = sqls[target]["create"]
        try:
            cur = oconn.cursor()
            cur.execute(create_ddl)
            cur.close()
        except:
            logging.error("create_ddl was:\n" + create_ddl)
            raise

    for target in targets:
        if target == "package_files":
            export_and_import(target, iconn, oconn, repo, sqls, since)
        else:
            rs = [r for r in export_g(target, iconn, repo, sqls, since)]
            import_(target, oconn, rs, sqls)


def option_parser(prog="swapi"):
    defaults = dict(
        output=None,
        outdir=os.curdir,
        dsn="rhnsat/rhnsat@rhnsat",
        since=None,
        extra=False,
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
    p.add_option("-E", "--extra", help="Get extra detailed data")
    p.add_option("-S", "--since",
        help="Collect data since this date given in the form of \"yyyy-mm-dd\""
    )
    p.add_option("-D", "--debug", action="store_true", help="Debug mode")

    return p


def run(dsn, repo, output, since, sqls=SQLS, extra=False):
    start_time = time.time()
    logging.info("start at %s: repo=%s" % (datetime.datetime.now(), repo))
    logging.debug("repo=%s, output=%s, since=%s" % (repo, output, since))
    collect_and_import_data(dsn, repo, output, sqls, since, extra)
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

        run(options.dsn, chan, options.output, options.since, SQLS, options.extra)
    else:
        for chan in args:
            output = os.path.join(options.outdir, chan + ".db")
            run(options.dsn, chan, output, options.since, SQLS, options.extra)


if __name__ == '__main__':
    main(sys.argv)


# vim:sw=4:ts=4:et:
