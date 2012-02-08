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
import rpmkit.memoize as M

import collections
import logging


def __mockcfg_path(bdist, topdir="/etc/mock"):
    """
    >>> __mockcfg_path("fedora-16-x86_64")
    '/etc/mock/fedora-16-x86_64.cfg'
    """
    return "%s/%s.cfg" % (topdir, bdist)


@M.memoize
def mockcfg_opts(bdist):
    """
    Load mock config file and returns $mock_config["config_opts"] as a
    dict (collections.OrderedDict).

    :param bdist: Build target distribution label, e.g. fedora-addon-16-x86_64
    """
    cfg = collections.OrderedDict()
    cfg["config_opts"] = collections.OrderedDict()

    execfile(__mockcfg_path(bdist), cfg)

    return cfg["config_opts"]


def build_cmd(bdist_label, srpm):
    """
    NOTE: mock will print log messages to stderr (not stdout).
    """
    c = "mock -r %s %s" % (bdist_label, srpm)

    # suppress log messages from mock in accordance with log level:
    if logging.getLogger().level >= logging.WARNING:
        c += " > /dev/null 2> /dev/null"

    return c


class Distribution(object):

    def __init__(self, dname, dver, arch="x86_64", bdist_label=None):
        """
        :param dname:  Distribution name, e.g. "fedora", "rhel"
        :param dver:   Distribution version, e.g. "16", "6"
        :param arch:   Architecture, e.g. "i386", "x86_64"
        :param bdist_label:  Build target distribution, e.g. "fedora-14-i386"
        """
        self.name = dname
        self.version = dver
        self.arch = arch

        self.label = "%s-%s-%s" % (dname, dver, arch)
        self.bdist_label = self.label if bdist_label is None else bdist_label
        self.arch_pattern = "i*86" if arch == "i386" else self.arch
        self.mockcfg_opts = mockcfg_opts(self.bdist_label)

    def __buildroot(self):
        return self.mockcfg_opts.get("root", bdist_label)

    def mockdir(self):
        return "/var/lib/mock/%s/result" % self.__buildroot()

    def build_cmd(self, srpm):
        return build_cmd(self.bdist_label, srpm)


# vim:sw=4 ts=4 et:
