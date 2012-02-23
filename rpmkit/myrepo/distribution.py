#
# Copyright (C) 2011, 2012 Red Hat, Inc.
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


def _get_mockcfg_path(bdist, topdir="/etc/mock"):
    """
    :param bdist: Build target distribution name, e.g. fedora-16-x86_64
    :param topdir: Mock's top dir to build srpms

    >>> _get_mockcfg_path("fedora-16-x86_64")
    '/etc/mock/fedora-16-x86_64.cfg'
    """
    return os.path.join(topdir, bdist + ".cfg")


def _load_mockcfg_config(bdist, cfg=collections.OrderedDict()):
    """
    FIXME: This is very naive and frail. It may be better to implement in
    similar manner as setup_default_config_opts() does in /usr/sbin/mock.
    """
    mockcfg = _get_mockcfg_path(bdist)
    try:
        execfile(mockcfg, cfg)
        return cfg

    except KeyError, e:
        ## Make it constructs a dict recursively:
        #cfg[str(e)] = collections.OrderedDict()
        #return _load_mockcfg_config(mockcfg, cfg)  # run recursively
        #
        ## or just make it raising an exception (current choice):
        raise RuntimeError(str(e))


def _load_mockcfg_config_opts(bdist):
    """
    Load mock config file and returns $mock_config["config_opts"] as a
    dict (collections.OrderedDict).

    :param bdist: Build target distribution label, e.g. fedora-addon-16-x86_64
    """
    cfg = collections.OrderedDict()
    cfg["config_opts"] = collections.OrderedDict()

    # see also: setup_default_config_opts() in /usr/sbin/mock.
    for k in ["macros", "plugin_conf"]:
        cfg["config_opts"][k] = collections.OrderedDict()

    cfg = _load_mockcfg_config(bdist, cfg)

    return cfg["config_opts"]


@M.memoize
def load_mockcfg_config_opts(bdist):
    return _load_mockcfg_config_opts(bdist)


def build_cmd(bdist, srpm):
    """
    NOTE: mock will print log messages to stderr (not stdout).
    """
    # suppress log messages from mock in accordance with log level:
    if logging.getLogger().level >= logging.WARNING:
        logc = "> /dev/null 2> /dev/null"
    else:
        logc = ""

    return ' '.join(("mock -r", bdist, srpm, logc))


class Distribution(object):

    def __init__(self, dname, dver, arch="x86_64", bdist=None):
        """
        :param dname:  Distribution name, e.g. "fedora", "rhel"
        :param dver:   Distribution version, e.g. "16", "6"
        :param arch:   Architecture, e.g. "i386", "x86_64"
        :param bdist:  Build target distribution, e.g. "fedora-14-i386"
        """
        self.name = dname
        self.version = dver
        self.arch = arch

        self.label = '-'.join((dname, dver, arch))
        self.bdist = self.label if bdist is None else bdist

    def load_mockcfg_config_opts(self):
        return load_mockcfg_config_opts(self.bdist)

    def rpmdir(self):
        """Dir to save built RPMs.
        """
        return "/var/lib/mock/%s/result" % self.bdist

    def build_cmd(self, srpm):
        return build_cmd(self.bdist, srpm)


# vim:sw=4 ts=4 et:
