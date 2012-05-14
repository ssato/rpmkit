#
# rpmdb.datasrc.rhn - Retrieve from RHN w/ swapi
#
# Copyright (C) 2012 Red Hat, Inc.
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

import rpmkit.rpmdb.datasources.base as Base
import rpmkit.rpmdb.models.packages as MP
import rpmkit.swapi as SW

import operator
import shlex
import sys


def rpc(cmd):
    return SW.main(shlex.split(cmd))[0]


def get_xs(cmd, cls, keys):
    """
    :param cmd: command string passed to swapi.main :: str
    :param cls: Class to instantiate data and will be imported into database
    :param keys: keys to get data :: (str, ...)
    """
    return [cls(*operator.itemgetter(*keys)(x)) for x in rpc(cmd)]


def get_packages(repo):
    """
    :param repo: Repository (Software channel) label
    """
    return get_xs(
        "-A %s channel.software.listAllPackages" % repo,
        MP.Package,
        ("id", "name", "version", "release", "epoch", "arch_label"),
    )


def get_errata(repo):
    return get_xs(
        "-A %s channel.software.listErrata" % channel,
        MP.Errata,
        ("id", "advisory_name", "advisory_name", "advisory_synopsis", "date"),
    )


def get_package_id(name, version, release, epoch="", arch="x86_64"):
    return get_xs(
        "-A %s,%s,%s,%s,%s packages.findByNvrea" % (
            name, version, release, epoch, arch
        ),
        MP.Package,
        ("id", "name", "version", "release", "epoch", "arch_label"),
    )


def get_cves(advisory):
    return get_xs("-A %s errata.listCves" % advisory, MP.CVE, ("name", ))


def get_package_files(name, version, release, epoch="", arch="x86_64"):
    pid = get_package_id(name, version, release, epoch, arch)[-1]
    return get_xs("-A %s packages.listFiles" % pid, MP.PackageFile, ("path", ))


def get_package_dependencies(name, version, release, epoch="", arch="x86_64"):
    pid = get_package_id(name, version, release, epoch, arch)[-1]
    return [
        dict(zip(("dependency", "type", "modifier"), *x)) for x in
            rpc("-A %s packages.listDependencies" % pid)
    ]


def get_package_requires(name, version, release, epoch="", arch="x86_64"):
    #return [cls(*operator.itemgetter(*keys)(x)) for x in rpc(cmd)]
    return [
        MP.PackageRequires(x["dependency"], x["modifier"]) for x in
            (d for d in get_package_dependencies(
                name, version, release, epoch, arch
            ) if d["type"] == "requires")
    ]


class Swapi(Base):

    def get_packages(self, repo):
        return get_packages(repo)

    def get_errata(self, repo):
        return get_errata(repo)

    def get_package_files(self, name, version, release, epoch, arch):
        return get_package_files(name, version, release, epoch, arch)

    def get_package_requires(self, *args, **kwargs):
        pass

    def get_package_provides(self, *args, **kwargs):
        pass

    def get_package_errata(self, *args, **kwargs):
        pass

    def get_errata_cves(self, advisory):
        return get_cves(advisory)


# vim:sw=4:ts=4:et:
