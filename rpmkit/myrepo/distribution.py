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


def parse_dist(dist):
    return dist.rsplit("-", 1)


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

    def __init__(self, dist, arch="x86_64", bdist_label=None):
        """
        @dist  str   Distribution label, e.g. "fedora-14"
        @arch  str   Architecture, e.g. "i386"
        @bdist_label  str  Distribution label to build, e.g. "fedora-14-i386"
        """
        self.label = "%s-%s" % (dist, arch)
        (self.name, self.version) = parse_dist(dist)
        self.arch = arch

        self.arch_pattern = (arch == "i386" and "i*86" or self.arch)

        self.bdist_label = bdist_label is None and self.label or bdist_label

        self.mock_config_opts = mockcfg_opts(self.mockcfg())

    def mockcfg_opts_get(self, key, fallback=None):
        return self.mock_config_opts.get(key, fallback)

    def buildroot(self):
        return self.mockcfg_opts_get("root", self.bdist_label)

    def mockdir(self):
        return "/var/lib/mock/%s/result" % self.buildroot()

    def mockcfg(self):
        return "/etc/mock/%s.cfg" % self.bdist_label

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
