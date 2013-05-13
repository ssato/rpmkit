#! /usr/bin/python -tt
# updateinfo.py - collect info of update and errata applicable to given rpm db
# with utilizing swapi and yum-surrogate.
#
# Copyright (C) 2013 Satoru SATOH <ssato@redhat.com>
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
from logging import DEBUG, INFO

import rpmkit.rpmutils as RU
import rpmkit.yum_surrogate as YS

import logging
import optparse
import os
import os.path
import re
import sys

try:
    import json
except ImportError:
    import simplejson as json


_DEFAULTS = dict(path=None, root=_WORKDIR, dist="auto", format=False,
                 copy=False, force=False, verbose=False,
                 other_db=False)

_RPMDB_SUBDIR = "var/lib/rpm"


def export_rpm_list(datadir, subdir=_RPMDB_SUBDIR):
    """
    :param datadir: RPM DB top dir where ``subdir`` exists
    :param subdir: sub dir of ``datadir`` in which RPM DB files exist

    :return: The list of RPM package (NVREA) ::
             [{name, version, release, epoch, arch}]
    """
    f = os.paht.join(datadir, subdir, "Packages")
    assert os.path.exists(f), "RPM DB file looks not exist under " + datadir

    return RU.rpm_list(datadir)


def dump_rpm_list(rpm_list, workdir):
    """
    """
    json.dump(rpm_list, open(os.path.join(workdir, "packages.json"), 'w')


def get_errata_list_g(ppath):
    """
    Get errata applicable to given RPM db ``ppath`` (Packages) with
    yum-surrogate's help: yum-surrogate -p ``ppath`` -r ``root`` -F -- list-sec

    :param ppath: The path to RPM DB 'Packages' of target host or system group
    :return: [{errata_advisory, errata_type, errata_severity_or_None,
               rpm_name, rpm_epoch, rpm_version, rpm_release, rpm_arch}]
    """
    defaults = YU._DEFAULTS
    defaults["path"] = ppath
    defaults["format"] = True

    yum_argv = ["list-sec"]

    p = YU.option_parser(defaults)
    (options, _args) = p.parse_args([])

    if options.path.endswith("/var/lib/rpm/Packages"):
        options.root = options.path.replace("/var/lib/rpm/Packages", "")
    else:
        options.root = os.path.dirname(options.path)
        YU.setup_data(options.path, options.root, options.force,
                      options.copy, options.other_db)

    for e in YU.list_errata_g(options.root):
        yield e


# vim:sw=4:ts=4:et:
