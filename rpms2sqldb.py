#! /usr/bin/python
#
# rpms2sqldb.py - Dump rpm metadata from rpm files to sqlite database
#
# Copyright (C) 2010 Satoru SATOH <satoru.satoh@gmail.com>
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
# Reference: http://docs.fedoraproject.org/drafts/rpm-guide-en/ch-rpm-programming-python.html
#

import datetime
import glob
import optparse
import os
import pprint
import rpm
import sqlite3 as sqlite
import sys

try:
    import hashlib # python 2.5+
    def hexdigest(s):
        return hashlib.md5(s).hexdigest()
except ImportError:
    import md5
    def hexdigest(s):
        return md5.md5(s).hexdigest()


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
"""



def zip3(xs, ys, zs):
    """
    >>> zip3([0,3],[1,4],[2,5])
    [(0, 1, 2), (3, 4, 5)]
    """
    return [(x,y,z) for (x,y),z in zip(zip(xs, ys), zs)]


def concat(xss):
    """
    >>> concat([[1,2],[3,4,5]])
    [1, 2, 3, 4, 5]
    """
    ys = []
    for xs in xss:
        if isinstance(xs, list):
            ys += xs
        else:
            ys.append(xs)

    return ys



class PackageMetadata(dict):
    """Package Metadata set.
    """
    def __init__(self, rpmfile):
        self.createFromRpmfile(rpmfile)

    def rpmheader(self, rpmfile):
        """Read rpm header from a rpm file.

        @see http://docs.fedoraproject.org/drafts/rpm-guide-en/ch16s04.html
        """
        ts = rpm.TransactionSet()
        ts.setVSFlags(rpm._RPMVSF_NOSIGNATURES)
        fd = os.open(rpmfile, os.O_RDONLY)
        h = ts.hdrFromFdno(fd)
        os.close(fd)

        return h

    def guess_os_version(self, header):
        """Guess RHEL major version from rpm header of the rpmfile.

        - RHEL 3 => rpm.RPMTAG_RPMVERSION = '4.2.x' where x = 1,2,3
            or '4.2' or '4.3.3' (comps-*3AS-xxx) or '4.1.1' (comps*-3[aA][Ss])
        - RHEL 4 => rpm.RPMTAG_RPMVERSION = '4.3.3'
        - RHEL 5 => rpm.RPMTAG_RPMVERSION = '4.4.2' or '4.4.2.3'
        - RHEL 6 (beta) => rpm.RPMTAG_RPMVERSION = '4.7.0-rc1'
        """
        rpmver = header[rpm.RPMTAG_RPMVERSION]
        (name, version) = (header[rpm.RPMTAG_NAME], header[rpm.RPMTAG_VERSION])

        irpmver = int(''.join(rpmver.split('.')[:3])[:3])

        # Handle special cases at first:
        if name in ('comps', 'comps-extras') and version in ('3AS', '3as'):
            osver = 3
        elif name in ('comps', 'comps-extras') and version == '4AS':
            osver = 4
        elif name == 'rpmdb-redhat' and version == '3':
            osver = 3
        elif (irpmver >= 421 and irpmver <= 423) or irpmver == 42:
            osver = 3
        elif irpmver == 433 or irpmver == 432 or irpmver == 431:
            osver = 4
        elif irpmver == 442:
            osver = 5
        elif irpmver == 470:
            osver = 6
        else:
            osver = 0

        return osver

    def createFromRpmfile(self, rpmfile):
        h = self.rpmheader(rpmfile)

        self['name'] = h[rpm.RPMTAG_NAME]
        self['version'] = h[rpm.RPMTAG_VERSION]
        self['release'] = h[rpm.RPMTAG_RELEASE]
        self['arch'] = h[rpm.RPMTAG_ARCH]
        self['epoch'] = h[rpm.RPMTAG_EPOCH]  # May be None
        self['summary'] = h[rpm.RPMTAG_SUMMARY]
        self['description'] = h[rpm.RPMTAG_DESCRIPTION]
        self['url'] = h[rpm.RPMTAG_URL]
        self['license'] = h[rpm.RPMTAG_LICENSE]
        self['vendor'] = h[rpm.RPMTAG_VENDOR]
        self['group'] = h[rpm.RPMTAG_GROUP]
        self['buildhost'] = h[rpm.RPMTAG_BUILDHOST]
        self['sourcerpm'] = h[rpm.RPMTAG_SOURCERPM]
        self['packager'] = h[rpm.RPMTAG_PACKAGER]
        self['size_package'] = h[rpm.RPMTAG_SIZE]
        self['size_archive'] = h[rpm.RPMTAG_ARCHIVESIZE]

        self['os_version'] = self.guess_os_version(h)
        self['srpmname'] = h[rpm.RPMTAG_SOURCERPM].split(h[rpm.RPMTAG_VERSION])[0][:-1]

        dirs = h[rpm.RPMTAG_DIRNAMES]
        self['files'] = [
            {'path': f, 'basename': os.path.basename(f), 'type': (f in dirs and 'd' or 'f')}
                for f in h[rpm.RPMTAG_FILENAMES]
        ]

        self['conflicts'] = [
            {'name':n, 'version':v, 'flags':f} for n,v,f in \
                zip3(h[rpm.RPMTAG_CONFLICTS], h[rpm.RPMTAG_CONFLICTFLAGS], h[rpm.RPMTAG_CONFLICTVERSION])
        ]

        self['obsoletes'] = [
            {'name':n, 'version':v, 'flags':f} for n,v,f in \
                zip3(h[rpm.RPMTAG_OBSOLETES], h[rpm.RPMTAG_OBSOLETEFLAGS], h[rpm.RPMTAG_OBSOLETEVERSION])
        ]

        self['provides'] = [
            {'name':n, 'version':v, 'flags':f} for n,v,f in \
                zip3(h[rpm.RPMTAG_PROVIDES], h[rpm.RPMTAG_PROVIDEFLAGS], h[rpm.RPMTAG_PROVIDEVERSION])
        ]

        self['requires'] = [
            {'name':n, 'version':v, 'flags':f} for n,v,f in \
                zip3(h[rpm.RPMTAG_REQUIRES], h[rpm.RPMTAG_REQUIREFLAGS], h[rpm.RPMTAG_REQUIREVERSION])
        ]



class RpmDB(object):
    def guess_arch(self, archs):
        archs = [a for a in archs if a != 'noarch']

        if not archs:
            return 'i386'  # maybe

        if 'x86_64' in archs:
            return 'x86_64'
        else:
            return archs[0]

    def collect(self, rpmdir='./'):
        dists = {}

        for f in glob.glob("%s/*.rpm" % rpmdir):
            p = PackageMetadata(f)
            osver = p['os_version']

            if osver not in dists.keys():
                dists[osver] = {}
                dists[osver]['packages'] = [p]
                dists[osver]['archs'] = [p['arch']]
            else:
                dists[osver]['packages'].append(p)
                if p['arch'] not in dists[osver]['archs']:
                    dists[osver]['archs'].append(p['arch'])

        for dist in dists.keys():
            dists[dist]['arch'] = self.guess_arch(dists[dist]['archs'])

        self.dists = dists

    def createdb(self, db, sql=DATABASE_SQL_DDL):
        conn = sqlite.connect(db)
        cur = conn.cursor()
        cur.executescript(sql)
        conn.commit()
        cur.execute('INSERT INTO db_info(dbversion) VALUES (1)')
        conn.commit()
        conn.close()

    def dumpdata(self, db, packages):
        conn = sqlite.connect(db)
        conn.text_factory = str
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM packages")
        index = cur.fetchone()[0] + 1

        ps = [p for p in packages]

        for p in ps:
            p['pid'] = index; index += 1

            cur.execute(
                "INSERT INTO packages(pid, name, version, release, arch, epoch, summary, description, url, license, vendor, pgroup, buildhost, sourcerpm, packager, size_package, size_archive, srpmname) VALUES(:pid, :name, :version, :release, :arch, :epoch, :summary, :description, :url, :license, :vendor, :group, :buildhost, :sourcerpm, :packager, :size_package, :size_archive, :srpmname)",
                p
            )

        conn.commit()

        files = concat([
            [{'path':f['path'], 'basename':f['basename'], 'type':f['type'], 'pid':p['pid']} for f in p['files']] \
                for p in ps
        ])

        cur.executemany("INSERT INTO files(path, basename, type, pid) VALUES(:path, :basename, :type, :pid)", files)
        conn.commit()

        for g in ('conflicts', 'obsoletes', 'provides', 'requires'):
            xs = concat([
                [{'name':x['name'], 'flags':x['flags'], 'version':x['version'], 'pid':p['pid']} for x in p[g]] \
                    for p in ps
            ])

            cur.executemany(
                "INSERT INTO %s(name, flags, version, pid) VALUES(:name, :flags, :version, :pid)" % g,
                xs
            )
            conn.commit()

        conn.close()

    def dumpdb(self, destdir='./', dist_fmt='rhel-%(arch)s-%(os_version)d', force=False):
        for osver in self.dists.keys():
            label = dist_fmt % {'os_version': osver, 'arch': self.dists[osver]['arch']}
            db = os.path.join(destdir, "%s.sqlite" % label)
            ps = self.dists[osver]['packages']

            if not os.path.exists(db) or force:
                self.createdb(db)

            self.dumpdata(db, ps)



def main():
    tstamp = datetime.date.today().strftime("%Y%m%d")
    outdir = "rpmdb_%s" % tstamp

    p = optparse.OptionParser("%prog [OPTION ...] RPMDIR_0 [RPMDIR_1 ...]")
    p.add_option('', '--outdir', default=outdir, help='Output dir. [%default]')
    #p.add_option('', '--force', default=False, action='store_true', help='Force overwrite existing dbs. [false]')
    (options, args) = p.parse_args()

    if len(args) < 1:
        p.print_usage()
        sys.exit(1)

    rpmdirs = args

    for dir in rpmdirs:
        rpmdb = RpmDB()
        rpmdb.collect(dir)

        if not os.path.isdir(options.outdir):
            os.makedirs(options.outdir)

        rpmdb.dumpdb(options.outdir)
        #rpmdb.dumpdb(options.outdir, force=options.force)


if __name__ == '__main__':
    main()


# vim: set sw=4 ts=4 et:
