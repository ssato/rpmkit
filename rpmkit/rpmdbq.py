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
import os
import re
import rpm
import sqlite3
import yum


SYSTEM_RHNCACHEDB_DIR = "/var/lib/rhncachedb"


class PackageDB(object):

    def __init__(self, dist, dbdir=SYSTEM_RHNCACHEDB_DIR):
        """
        :param dist: Distribution or channel label, e.g. rhel-x86_64-server-5.db
        :param dbdir: Database File topdir
        """
        dbpath = os.path.join(dbdir, dist + ".db")

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
    pred = "p.name = ? AND p.version = ? AND p.release = ? AND arch = ?"

    if epoch and epoch != '0':
        pred += " AND epoch = ?"

    return pred


def sql_package(name, version, release, epoch, arch):
    if epoch and epoch != '0':
        return (name, version, release, epoch, arch)
    else:
        return (name, version, release, arch)


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


def _requires_to_packages(req_name, db, req_modifier=None):
    """Get package provides given requires.

    :param req_name: requires' name
    :param req_modifier: requires' modifier
    :param db: PackageDB instance

    :return: [dict(name, version, release, epoch, arch)]
    """
    # e.g. 'config(cups)' -> self-dependency
    if re.match(r"config(.+)", req_name):
        return []

    elif req_name.startswith("/"):  # it should be a file path.
        sql = """SELECT p.name, p.version, p.release, p.epoch, p.arch
FROM packages p INNER JOIN package_files pf ON p.id = pf.package_id
WHERE pf.name = ?
"""
        return db.query(sql, (req_name,))

    else:  # search from provides
        sql = """SELECT p.name, p.version, p.release, p.epoch, p.arch
FROM packages p INNER JOIN package_provides pp ON p.id = pp.package_id
WHERE pp.name = ?
"""
        return db.query(sql, (req_name,))


requires_to_packages = M.memoize(_requires_to_packages)


def _package_requires(nvrea, db):
    """
    :param nvrea: package(name, version, release, epoch, arch)
    :param db: PackageDB instance

    TODO: Handle pr.modifier.
    """
    sql = """SELECT DISTINCT pr.name, pr.modifier
FROM packages p INNER JOIN package_requires pr ON p.id = pr.package_id
WHERE %s""" % sql_package_p(*nvrea)
    reqs = db.query(sql, sql_package(*nvrea))  # :: [(pr.name, pr.modifier)]

    assert reqs, "should not be empty. sql=" + sql + ", nvrea=" + str(nvrea)

    return U.unique(U.concat(requires_to_packages(r[0], db) for r in reqs))


package_requires = M.memoize(_package_requires)


# vim:sw=4:ts=4:et:
