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
    label TEXT,
    summary TEXT
);
CREATE TABLE IF NOT EXISTS files (
    path TEXT,
    basename TEXT,
    type TEXT,
    pid INTEGER
);
CREATE TABLE IF NOT EXISTS conflicts (
    name TEXT,
    flags TEXT,
    version TEXT,
    pid INTEGER
);
CREATE TABLE IF NOT EXISTS obsoletes (
    name TEXT,
    flags TEXT,
    version TEXT,
    pid INTEGER
);
CREATE TABLE IF NOT EXISTS provides (
    name TEXT,
    flags TEXT,
    version TEXT,
    pid INTEGER
);
CREATE TABLE IF NOT EXISTS requires (
    name TEXT,
    flags TEXT,
    version TEXT,
    pid INTEGER,
    rpid INTEGER,
    distance INTEGER,
    pre BOOLEAN DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS filepath ON files (path);
CREATE INDEX IF NOT EXISTS baseames ON files (basename);
CREATE INDEX IF NOT EXISTS packagename ON packages (name);
CREATE INDEX IF NOT EXISTS pkgconflicts on conflicts (pid);
CREATE INDEX IF NOT EXISTS pkgobsoletes on obsoletes (pid);
CREATE INDEX IF NOT EXISTS pkgprovides on provides (pid);
CREATE INDEX IF NOT EXISTS pkgrequires on requires (pid);
CREATE INDEX IF NOT EXISTS providesname ON provides (name);
CREATE INDEX IF NOT EXISTS requiresname ON requires (name);
CREATE TRIGGER IF NOT EXISTS removals AFTER DELETE ON packages
    BEGIN
        DELETE FROM files WHERE pid = old.pid;
        DELETE FROM requires WHERE pid = old.pid;
        DELETE FROM provides WHERE pid = old.pid;
        DELETE FROM conflicts WHERE pid = old.pid;
        DELETE FROM obsoletes WHERE pid = old.pid;
    END;
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

    def __init__(self, conn_params):
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

        details = rapi.call("packages.getDetails", pid)
        p.update(details)

        depends = rapi.call("packages.listDependencies", pid)
        files = rapi.call("packages.listFiles", pid)
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


if __name__ == '__main__':
    main()


# vim:sw=4 ts=4 et:
