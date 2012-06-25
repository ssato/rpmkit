#
# Copyright (C) 2012 Satoru SATOH <ssato@redhat.com>
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
import rpmkit.memoize as M
import rpmkit.utils as U

import logging
import operator
import os
import re
import rpm
import sqlite3
import yum


class PackageDB(object):

    def __init__(self, dbpath):
        """
        :param dbpath: Path to database file,
            e.g. /var/lib/rhncachedb/rhel-x86_64-server-5.db
        """
        if not os.path.exists(dbpath):
            raise RuntimeError("DB file not found: " + dbpath)

        self.dbpath = dbpath
        self.conn = sqlite3.connect(dbpath)

    def query_g(self, sql, params=()):
        """
        :param sql: SQL statement, e.g "select * from aTable a where a.id = ?"
        :param params: tuple of parameters passed to the SQL statement
        """
        cur = self.conn.cursor()
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)

        for row in cur:
            yield row

        cur.close()

    def query(self, sql, params):
        return [r for r in self.query_g(sql, params)]

    def __del__(self):
        self.conn.close()


def sql_package_p(name, version, release, epoch, arch):
    pred = "p.name = :name AND p.version = :version AND p.release = :release"

    if epoch and epoch != '0':
        pred += " AND epoch = :epoch"

    pred += " AND arch = :arch"

    return pred


def sql_package(name, version, release, epoch, arch):
    return dict(name=name, version=version, release=release, epoch=epoch,
        arch=arch)


def package_id(nvrea, db):
    pids = db.query(
        "SELECT p.id FROM packages p WHERE " + sql_package_p(*nvrea),
        sql_package(*nvrea)
    )

    if not pids:
        logging.warn("Package not found: " + str(nvrea))
        return None
    else:
        assert len(pids) > 1, "Multiple IDs found: " + str(nvrea)
        return pids[0]


def _requires_to_packages(req_name, dbs, req_modifier=None):
    """Get package provides given requires.

    :param req_name: requires' name
    :param req_modifier: requires' modifier
    :param dbs: [PackageDB instance]

    :return: [dict(name, version, release, epoch, arch)]
    """
    # e.g. 'config(cups)' -> self-dependency
    if re.match(r"config(.+)", req_name):
        return []

    # e.g. 'rpmlib(CompressedFileNames)'. none provides it.
    elif req_name.startswith("rpmlib"):
        return []

    elif req_name.startswith("/"):  # it should be a file path.
        sql = """SELECT p.name, p.version, p.release, p.epoch, p.arch
FROM packages p INNER JOIN package_files pf ON p.id = pf.package_id
WHERE pf.name = ?
"""
    else:  # search from provides
        sql = """SELECT p.name, p.version, p.release, p.epoch, p.arch
FROM packages p INNER JOIN package_provides pp ON p.id = pp.package_id
WHERE pp.name = ?
"""

    for db in dbs:
        ps = db.query(sql, (req_name,))
        if ps:
            return ps

    logging.info("No package provides " + req_name)
    return []


requires_to_packages = M.memoize(_requires_to_packages)


def _package_requires(nvrea, dbs):
    """
    :param nvrea: package(name, version, release, epoch, arch)
    :param dbs: [PackageDB instance]

    TODO: Handle pr.modifier.
    """
    for db in dbs:
        sql = """SELECT DISTINCT pr.name, pr.modifier
FROM packages p INNER JOIN package_requires pr ON p.id = pr.package_id
WHERE %s""" % sql_package_p(*nvrea)
        # reqs :: [(pr.name, pr.modifier)]
        reqs = db.query(sql, sql_package(*nvrea))
        if reqs:
            break  # found.

    assert reqs, "should not be empty. sql=" + sql + ", nvrea=" + str(nvrea)

    return U.unique(U.concat(requires_to_packages(r[0], dbs) for r in reqs))


package_requires = M.memoize(_package_requires)


def package_names(nvreas):
    return U.unique(p[0] for p in nvreas)


def packages_requires_g(nvreas, dbs):
    """
    :param nvreas: [(name, version, release, epoch, arch)]
    :param dbs: [PackageDB instance]

    It yields (nvrea_required, nvrea, is_nvrea_required_found_in_nvreas_p).

    TODO: Handle pr.modifier.
    """
    for nvrea in nvreas:
        for r in package_requires(nvrea, dbs):
            if r == nvrea:  # skip itself.
                continue

            yield (r, nvrea, r in nvreas)


def packages_requires(nvreas, dbs, pred=operator.itemgetter(-1)):
    """
    :param pred: function to filter results; exclude itself by default.
    """
    reqs = [r for r in packages_requires_g(nvreas, dbs) if not pred(r)]

    return reqs


# vim:sw=4:ts=4:et:
