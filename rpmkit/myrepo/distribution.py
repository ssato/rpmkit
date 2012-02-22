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
import os.path


def __mockcfg_path(bdist, topdir="/etc/mock"):
    """
    >>> __mockcfg_path("fedora-16-x86_64")
    '/etc/mock/fedora-16-x86_64.cfg'
    """
    return os.path.join(topdir, bdist + ".cfg")


def __mockcfg_file_to_obj(mockcfg, cfg=collections.OrderedDict()):
    """
    FIXME: This is very naive and frail. It may be better to implement in
    similar manner as setup_default_config_opts() does in /usr/sbin/mock.
    """
    try:
        execfile(mockcfg, cfg)
        return cfg

    except KeyError, e:
        cfg[str(e)] = collections.OrderedDict()
        return __mockcfg_file_to_obj(mockcfg, cfg)  # run recursively


def _buildroot(mockcfg_opts, bdist_label=None):
    """

    >>> bdist = "fedora-16-x86_64"
    >>> cfg = {"root": bdist}
    >>> _buildroot(cfg) == _buildroot({}, bdist)
    True
    """
    return mockcfg_opts.get("root", bdist_label)


@M.memoize
def mockcfg_opts(bdist):
    """
    Load mock config file and returns $mock_config["config_opts"] as a
    dict (collections.OrderedDict).

    :param bdist: Build target distribution label, e.g. fedora-addon-16-x86_64
    """
    cfg = collections.OrderedDict()
    cfg["config_opts"] = collections.OrderedDict()

    cfg = __mockcfg_file_to_obj(__mockcfg_path(bdist), cfg)

    return cfg["config_opts"]


def build_cmd(bdist_label, srpm):
    """
    NOTE: mock will print log messages to stderr (not stdout).
    """
    # suppress log messages from mock in accordance with log level:
    if logging.getLogger().level >= logging.WARNING:
        logc = "> /dev/null 2> /dev/null"
    else:
        logc = ""

    return ' '.join(("mock -r", bdist_label, srpm, logc))


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

        self.label = '-'.join((dname, dver, arch))
        self.bdist_label = self.label if bdist_label is None else bdist_label
        self.arch_pattern = "i*86" if arch == "i386" else self.arch
        self._mockcfg_opts = mockcfg_opts(self.bdist_label)

    def mockcfg_opts(self):
        return self._mockcfg_opts

    def mockdir(self):
        return "/var/lib/mock/%s/result" % \
            _buildroot(self.mockcfg_opts(), self.bdist_label)

    def build_cmd(self, srpm):
        return build_cmd(self.bdist_label, srpm)


# vim:sw=4 ts=4 et:
