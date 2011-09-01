#! /usr/bin/python
#
# rhncachedb.py - Create a cache database of rhn with using swapi.
#
# Copyright (C) 2011 Satoru SATOH <ssato@redhat.com>
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
from rpmkit import swapi

import datetime
import glob
import logging
import optparse
import os
import os.path
import pprint
import re
import shlex
import sqlite3 as sqlite
import sys



# some special dependency names.
REQ_SPECIALS = re.compile(r'^rpmlib|rtld')


DATABASE_SQL_DDL = \
"""
CREATE TABLE IF NOT EXISTS db_info ( dbversion INTEGER );
CREATE TABLE IF NOT EXISTS packages (
    pid INTEGER PRIMARY KEY,
    name TEXT, version TEXT, release TEXT, arch TEXT, epoch TEXT,
    summary TEXT, description TEXT, url TEXT,
    license TEXT, vendor TEXT, pgroup TEXT, buildhost TEXT, sourcerpm TEXT, packager TEXT,
    size_package INTEGER, size_archive INTEGER,
    srpmname TEXT
);
CREATE TABLE IF NOT EXISTS errata (
    advisory TEXT PRIMARY KEY,
    description TEXT,
    synopsis TEXT,
    topic TEXT,
    references TEXT,
    notes TEXT,
    type TEXT,
    severity TEXT,
    issue_date TEXT,
    update_date TEXT,
    last_modified_date TEXT,
);
CREATE TABLE IF NOT EXISTS channels (
    cid INTEGER PRIMARY KEY,
    label TEXT
);
CREATE TABLE IF NOT EXISTS files (
    path TEXT,
    basename TEXT,
    type TEXT,
    pid INTEGER
);
CREATE TABLE IF NOT EXISTS dependencies (
    pid INTEGER,
    name TEXT,
    type TEXT,
    modifier TEXT
);
CREATE TABLE IF NOT EXISTS package_errata (
    pid INTEGER,
    advisory TEXT
);
CREATE TABLE IF NOT EXISTS errata_bugzilla (
    advisory TEXT,
    bugzilla INTEGER
);
CREATE TABLE IF NOT EXISTS errata_cves (
    advisory TEXT,
    cve TEXT,
);
CREATE TABLE IF NOT EXISTS channel_packages (
    cid INTEGER,
    pid INTEGER
);
CREATE TABLE IF NOT EXISTS channel_errata (
    cid INTEGER,
    advisory TEXT
);
CREATE INDEX IF NOT EXISTS filepath ON files (path);
CREATE INDEX IF NOT EXISTS baseames ON files (basename);
CREATE INDEX IF NOT EXISTS packagename ON packages (name);
CREATE TRIGGER IF NOT EXISTS removals AFTER DELETE ON packages
    BEGIN
        DELETE FROM files WHERE pid = old.pid;
        DELETE FROM dependencies WHERE pid = old.pid;
    END;
"""



def zip3(xs, ys, zs):
    """
    >>> zip3([0,3],[1,4],[2,5])
    [(0, 1, 2), (3, 4, 5)]
    """
    return [(x,y,z) for (x,y),z in zip(zip(xs, ys), zs)]


def unique(xs, cmp_f=cmp):
    """Returns sorted list of no duplicated items.

    @param xs:  list of object (x)
    @param cmp_f:  comparison function for x

    >>> unique([0, 3, 1, 2, 1, 0, 4, 5])
    [0, 1, 2, 3, 4, 5]
    """
    if xs == []:
        return xs

    ys = sorted(xs, cmp=cmp_f)
    if ys == []:
        return ys

    rs = [ys[0]]

    for y in ys[1:]:
        if y == rs[-1]:
            continue
        rs.append(y)

    return rs



class RApi(object):

    def __init__(self, swapi_args=""):
        (options, args) = swapi.option_parser().parse_args(shlex.split(swapi_args))
        conn_params = swapi.configure(options)

        self.rapi = swapi.RpcApi(conn_params)
        self.rapi.login()

    def __call__(self, api, args):
        """
        :param api: 
        """
        args = swapi.parse_api_args(args)
        res = rapi.call(api, *args)

        if isinstance(res, list) or getattr(res, "next", False):
            res = [swapi.shorten_dict_keynames(r) for r in res]
        else:
            res = swapi.shorten_dict_keynames(res)

        return res



def get_packages(rapi, channel):
    """
    Get Packages metadata from RHNS.

    :param channel:  software channel label to get packages.

    :ref: https://access.redhat.com/knowledge/docs/Red_Hat_Network/API_Documentation/channel/software/ChannelSoftwareHandler.html
    :ref: https://access.redhat.com/knowledge/docs/Red_Hat_Network/API_Documentation/packages/PackagesHandler.html
    """
    ps = rapi.call("channel.software.listAllPackages", channel)
    assert ps

    for p in ps:
        pid = p["id"]

        p["arch"] = p["arch_label"]
        p["pid"] = pid

        details = rapi.call("packages.getDetails", pid)
        p.update(details)

        files = rapi.call("packages.listFiles", pid)
        depends = rapi.call("packages.listDependencies", pid)
        errata = rapi.call("packages.listErrata", pid)

        p.update(
            dict(
                depends = depends,
                files = files,
                errata = errata,
            )
        )

        yield p


def get_errata(rapi, channel):
    """
    Get errata data in given channel from RHNS.

    :param channel:  software channel label to get packages.

    :ref: https://access.redhat.com/knowledge/docs/Red_Hat_Network/API_Documentation/channel/software/ChannelSoftwareHandler.html
    :ref: https://access.redhat.com/knowledge/docs/Red_Hat_Network/API_Documentation/errata/ErrataHandler.html
    """
    errata = rapi.call("channel.software.listErrata", channel)
    assert errata

    for e in errata:
        advisory = e["advisory"]

        details = rapi.call("errata.getDetails", advisory)
        e.update(details)

        bugzilla = rapi.call("errata.bugzillaFixes", advisory)
        cves = rapi.call("errata.listCves", advisory)
        packages = rapi.call("errata.listPackages", advisory)

        e.update(
            dict(
                bugzilla = bugzilla,
                cves = cves,
                packages = packages,
            )
        )

        yield e


def dump_packages(self, db, cid, packages):
    conn = sqlite.connect(db)
    conn.text_factory = str
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM packages")

    for p in packages:
        logging.info("p=%s" % str(p)[:30])
        
        cur.execute(
            """INSERT INTO channel_packages(cid, pid)
                VALUES(:cid, :pid)""",
            dict(cid = cid, pid = p["pid"])
        )
        conn.commit()

        cur.execute(
            """INSERT INTO packages(pid,
                                    name,
                                    version,
                                    release,
                                    arch,
                                    epoch,
                                    summary,
                                    description,
                                    license,
                                    vendor,
                                    build_host)
            VALUES(:pid,
                   :name,
                   :version,
                   :release,
                   :arch,
                   :epoch,
                   :summary,
                   :description,
                   :license,
                   :vendor,
                   :build_host)
            """, p)
        conn.commit()

        package_files = [
            dict(
                path = f["path"],
                basename = os.path.basename(f["path"]),
                type = f["type"],
                pid = p["pid"],
            ) for f in p["files"]
        ]

        cur.executemany(
            """INSERT INTO files(path, basename, type, pid)
                VALUES(:path, :basename, :type, :pid)""",
            package_files
        )
        conn.commit()

        package_depends = [
            dict(
                pid = p["pid"],
                name = d["dependency"],
                type = d["dependency_type"],
                modifier = d["dependency_modifier"],
            ) for d in p["depends"]
        ]

        cur.executemany(
            """INSERT INTO dependencies(pid, name, type, modifier)
                VALUES(:pid, :name, :type, :modifier)""",
            package_depends
        )
        conn.commit()

        package_errata = [
            dict(pid = pid, advisory = e["advisory"]) for e in p["errata"]
        ]

        cur.executemany(
            "INSERT INTO package_errata(pid, advisory) VALUES(:pid, :advisory)",
            package_errata
        )
        conn.commit()

    conn.close()


def dump_results(rapi, db, channels):
    conn = sqlite.connect(db)
    conn.text_factory = str
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM channels")
    index = cur.fetchone()[0] + 1

    conn.close()

    for c in channels:
        cid = index; cid += 1

        packages_g = get_packages(rapi, channel)
        errata_g = get_errata(rapi, channel)

        dump_packages


if __name__ == '__main__':
    main()


# vim:sw=4 ts=4 et:
