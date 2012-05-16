#
# rpmdb.datasrc.rhn - Retrieve data from RHN w/ swapi
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
from rpmkit.Bunch import Bunch

import rpmkit.rpmdb.datasrc.base as B
import rpmkit.rpmdb.models.packages as MP
import rpmkit.swapi as SW

import operator
import shlex
import sys


def rpc(cmd):
    return SW.main(shlex.split(cmd))[0]


def get_xs(cmd, cls=Bunch, keys=[]):
    """
    :param cmd: command string passed to swapi.main :: str
    :param cls: Class to instantiate data and will be imported into database
    :param keys: keys to get data :: (str, ...)
    """
    if keys:
        return [cls(*operator.itemgetter(*keys)(x)) for x in rpc(cmd)]
    else:
        return [cls(x) for x in rpc(cmd)]


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
        "-A %s channel.software.listErrata" % repo,
        MP.Errata,
        ("id", "advisory_name", "advisory_name", "advisory_synopsis", "date"),
    )


def find_packages_by_nvrea(name, version, release, epoch=" ", arch="x86_64"):
    if not epoch:
        epoch = ' '

    return get_xs(
        "-A \"%s,%s,%s,%s,%s\" packages.findByNvrea" % (
            name, version, release, epoch, arch
        )
    )


def get_cves(advisory):
    return get_xs("-A %s errata.listCves" % advisory, MP.CVE)


def get_package_files(name, version, release, epoch="", arch="x86_64"):
    ps = find_packages_by_nvrea(name, version, release, epoch, arch)
    if not ps:
        return []

    pid = ps[0]["id"]
    return [
        MP.PackageFile(pid, f.path) for f in
            get_xs("-A %s packages.listFiles" % pid)
    ]


def get_package_errata(name, version, release, epoch="", arch="x86_64"):
    ps = find_packages_by_nvrea(name, version, release, epoch, arch)
    if not ps:
        return []

    pid = ps[0]["id"]
    return [
        MP.PackageErrata(pid, e.advisory) for e in
            get_xs("-A %s packages.listProvidingErrata" % pid)
    ]


def get_package_dependencies(name, version, release, epoch="", arch="x86_64"):
    """
    :return: [Bunch(dependency, dependency_type, dependency_modifier)]
    """
    ps = find_packages_by_nvrea(name, version, release, epoch, arch)
    if not ps:
        return []

    return get_xs("-A %s packages.listDependencies" % ps[0]["id"])


def get_package_dependencies_by_type(nvrea, dtype):
    """
    :param nvrea: tuple (name, version, release, epoch, arch)
    :parram dtype: dependency type ::
        "requires" | "conflicts" | "obsoletes" | "provides"

    :return: [Bunch(dependency, dependency_type, dependency_modifier)]
    """
    return [
        x for x in get_package_dependencies(*nvrea) \
                if x["dependency_type"] == dtype
    ]


def package_to_nvrea(p):
    return (p.name, p.version, p.release, p.epoch, p.arch)


class Swapi(B.Base):

    def _init_packages(self):
        self.packages = get_packages(self.repo)

    def _init_errata(self):
        self.errata = get_errata(self.repo)

    def get_packages(self):
        return self.packages

    def get_errata(self):
        return self.errata

    def get_package_files(self):
        return [
            get_package_files(*package_to_nvrea(p)) for p in
                self.get_packages()
        ]

    def get_package_requires(self):
        return [
            MP.PackageRequires(p.id, x.dependency, x.dependency_modifier) \
                for x in
                    get_package_dependencies_by_type(
                        package_to_nvrea(p), "requires"
                    ) for p in
                        self.get_packages()
        ]

    def get_package_provides(self):
        return [
            MP.PackageProvides(p.id, x.dependency) for x in
                    get_package_dependencies_by_type(
                        package_to_nvrea(p), "provides"
                    ) for p in
                        self.get_packages()
        ]

    def get_package_errata(self):
        return [
            get_package_errata(*package_to_nvrea(p)) for p in
                self.get_packages()
        ]

    def get_errata_cves(self, advisory):
        return [get_cves(e.name) for e in self.get_errata()]


# vim:sw=4:ts=4:et:
