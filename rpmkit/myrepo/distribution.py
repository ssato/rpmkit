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
import collections
import logging


def mockcfg_opts(mockcfg_path):
    """
    Load mock config file and returns $mock_config["config_opts"] as a
    dict (collections.OrderedDict).
    """
    cfg = collections.OrderedDict()
    cfg["config_opts"] = collections.OrderedDict()

    execfile(mockcfg_path, cfg)

    return cfg["config_opts"]


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

        self.bdist_label = self.label if bdist_label is None else bdist_label

        self.label = "%s-%s-%s" % (dname, dver, arch)
        self.arch_pattern = "i*86" if arch == "i386" or self.arch

        self.mock_config_opts = mockcfg_opts(self.mockcfg_path())

    def mockcfg_path(self):
        return "/etc/mock/%s.cfg" % self.bdist_label

    def mockcfg_opts_get(self, key, fallback=None):
        return self.mock_config_opts.get(key, fallback)

    def buildroot(self):
        return self.mockcfg_opts_get("root", self.bdist_label)

    def mockdir(self):
        return "/var/lib/mock/%s/result" % self.buildroot()

    def build_cmd(self, srpm):
        """
        NOTE: mock will print log messages to stderr (not stdout).
        """
        # suppress log messages from mock in accordance with log level:
        if logging.getLogger().level >= logging.WARNING:
            fmt = "mock -r %s %s > /dev/null 2> /dev/null"
        else:
            fmt = "mock -r %s %s"

        return fmt % (self.bdist_label, srpm)


# vim:sw=4 ts=4 et:
