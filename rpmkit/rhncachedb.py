#
# rhncachedb.py - RHN Caching database
#
# Copyright (C) 2011 Red Hat, Inc.
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
# Requirements: python-sqlalchemy, swapi
#
from sqlalchemy.ext.declarative import declarative_base
from rpmkit import swapi
from operator import itemgetter

import logging
import optparse
import shlex
import sqlalchemy as S
import sqlalchemy.orm as SO
import sys


DB_PATH = "rhncache.sqlite"


DeclBase = declarative_base()


class Package(DeclBase):
    """
    @see spacewalk.git/schema/spacewalk/common/tables/rhnPackageName.sql
    """

    __tablename__ = "packages"

    id = S.Column(S.Integer, primary_key=True)
    name = S.Column(S.String(256))
    version = S.Column(S.String(512))
    release = S.Column(S.String(512))
    epoch = S.Column(S.String(16))
    arcch = S.Column(S.String(64)

    def __init__(self, name, version, release, epoch, arch):
        self.name = name
        self.version = version
        self.release = release
        self.epoch = epoch
        self.arch = arch

    def __repr__(self):
        return "<Package('%(name)s', '%(version)s', '%(release)s', " + \
            "'%(epoch)s', '%(arch)s'>" % self.__dict__


class SoftwareChannel(DeclBase):

    __tablename__ = "softwarechannels"

    id = S.Column(S.Integer, primary_key=True)
    label = S.Column(S.String(128))
    name = S.Column(S.String(256))

    def __init__(self, label, name):
        self.label = label
        self.name = name


class Errata(DeclBase):

    __tablename__ = "errata"

    id = S.Column(S.Integer, primary_key=True)
    name = S.Column(S.String(256))
    type = S.Column(S.String(32))
    synopsis = S.Column(S.String(4000))
    date = S.Column(S.String(256))

    def __init__(self, name, type, synopsis, date):
        self.name = name
        self.type = type
        self.synopsis = synopsis
        self.date = date


class ChannelPackages(DeclBase):

    __tablename__ = "channelpackages"

    cid = S.Column(S.Integer, ForeignKey("softwarechannels.id"))
    pid = S.Column(S.Integer, ForeignKey("packages.id"))

    def __init__(self, cid, pid):
        self.cid = cid
        self.pid = pid


class PackageErrata(DeclBase):
    """
    package -> [errata]
    """

    __tablename__ = "packageerrata"

    pid = S.Column(S.Integer, ForeignKey("packages.id"))
    eid = S.Column(S.Integer, ForeignKey("errata.id"))

    def __init__(self, pid, eid):
        self.pid = pid
        self.eid = eid


class Bunch(dict):
    """
    Simple class implements 'Bunch Pattern'.

    @see http://ruslanspivak.com/2011/06/12/the-bunch-pattern/
    """

    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

    def __getstate__(self):
        return self.copy()

    def __setstate__(self, dic):
        self.__dict__ = dic


def get_engine(db_path=DB_PATH):
    return S.create_engine("sqlite:///" + db_path)


def rpc(cmd):
    return swapi.main(shlex.split(cmd))[0]


def get_xs(cmd, cls, keys):
    """
    :param cmd: command string passed to swapi.main :: str
    :param cls: Class to instantiate data and will be imported into database
    :param keys: keys to get data :: (str, ...)
    """
    return [cls(*itemgetter(*keys)(x)) for x in rpc(cmd)]


def get_channels():
    """
    @see http://docs.redhat.com/docs/en-US/Red_Hat_Network_Satellite/5.4.1/html/API_Overview/handlers/ChannelHandler.html
    """
    return get_xs(
        "channel.listAllChannels", SoftwareChannel, ("id", "label", "name"),
    )


def get_packages(channel):
    """
    :param channel: Software channel label
    """
    return get_xs(
        "-A %s channel.software.listAllPackages" % channel,
        Package,
        ("id", "name", "version", "release", "epoch", "arch_label"),
    ]


def get_errata(channel):
    return get_xs(
        "-A %s channel.software.listErrata" % channel,
        Errata,
        ("id", "advisory_name", "advisory_type", "advisory_synopsis", "date"),
    )

def get_errata_for_package(pid):
    """
    :param pid: Package ID
    """
    return get_xs(
        "-A %s packages.listProvidingErrata" % pid,
        PackageErrata,
        ("pid", "eid"),
    )


def make_data():
    data = Bunch()

    data.channels = get_channels()

    data.packages = []
    data.channelpackages = []
    data.errata = []
    data.packageerrata = []

    for c in data.channels:
        ps = get_packages(c.label)

        for p in ps:
            data.channelpackages.append(c.id, p.id)

            if p not in data.packages:
                data.packages.append(p)

                es = get_errata_for_package(p.id)
                data.packageerrata.extend(es)

    for c in data.channels:
        es = get_errata(c.label)

        for e in es:
            if e not in data.errata:
                data.errata.append(e)

    return data


def init_database(db_path=DB_PATH):
    engine = get_engine(db_path)

    DeclBase.metadata.create_all(engine)


def import_data(db_path=DB_PATH):
    engine = get_engine(db_path)

    session = SO.sessionmaker(bind=engine)
    data = make_data()

    session.add_all(data.channels)
    session.add_all(data.packages)
    session.add_all(data.channelpackages)
    session.add_all(data.errata)
    session.add_all(data.packageerrata)

    session.commit()


def do_init(db_path=DB_PATH):
    init_database(db_path)
    import_data(db_path)


def do_update(db_path=DB_PATH):
    print "Not implemented yet!"


def option_parser():
    defaults = dict(
        verbosity=0,
    )

    p = optparse.OptionParser("""%prog COMMAND [OPTION ...]

    Commands: i[init], b[uild]

    Examples:

    # initialize database
    %prog init -u foo -p rhns_pass

    # update database
    %prog update -v
    """)

    p.add_option("-d", "--dbpath", help="Database path")
    p.add_option("-v", "--verbose", action="count", dest="verbosity",
        help="Verbose mode")

    return p


def main(argv=sys.argv):
    logformat = "%(asctime)s [%(levelname)-4s] myrepo: %(message)s"
    logdatefmt = "%H:%M:%S"  # too much? "%a, %d %b %Y %H:%M:%S"

    logging.basicConfig(format=logformat, datefmt=logdatefmt)

    p = opt_parser()
    (options, args) = p.parse_args(argv[1:])

    try:
        loglevel = [
            logging.WARN, logging.INFO, logging.DEBUG
        ][options.verbosity]
    except IndexError:
        loglevel = logging.WARN

    logging.getLogger().setLevel(loglevel)

    if not args:
        p.print_usage()
        sys.exit(1)

    a0 = args[0]

    if a0.startswith('i'):
        do_init(options.dbpath)

    elif a0.startswith('u'):
        do_update(options.dbpath)

    else:
        logging.error(" Unknown command '%s'" % a0)
        sys.exit(1)


if __name__ == '__main__':
    main(sys.argv)


# vim:sw=4 ts=4 et:
