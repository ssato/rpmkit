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
from operator import itemgetter

import rpmkit.rpmutils as RU
import rpmkit.utils as U
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

_RPM_LIST_FILE = "packages.json"
_ERRATA_SUMMARY_FILE = "errata_summary.json"
_ERRATA_LIST_FILE = "errata.json"


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


def dump_rpm_list(rpm_list, workdir, filename=_RPM_LIST_FILE):
    """
    :param rpm_list: The list of RPM package (NVREA) retuned from
        export_rpm_list() :: [{name, version, release, epoch, arch}]
    :param workdir: Working dir to dump the result
    :param filename: Output file basename
    """
    json.dump(rpm_list, open(os.path.join(workdir, filename), 'w')


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


_ERRATA_KEYS = ("advisory", "type", "severity")


def _mkedic(errata, packages, ekeys=_ERRATA_KEYS):
    """
    >>> e = (u'RHSA-2013:0771', u'Security', u'Moderate')
    >>> ps = [{u'advisory': u'RHSA-2013:0771',  # doctest: +NORMALIZE_WHITESPACE
    ...        u'arch': u'x86_64', u'epoch': u'0', u'name': u'curl',
    ...        u'release': u'36.el6_4', u'severity': u'Moderate',
    ...        u'type': u'Security', u'version': u'7.19.7'},
    ...       {u'advisory': u'RHSA-2013:0771', u'arch': u'x86_64',
    ...        u'epoch': u'0', u'name': u'libcurl', u'release': u'36.el6_4',
    ...        u'severity': u'Moderate', u'type': u'Security',
    ...        u'version': u'7.19.7'}])
    >>> d = _mkedic(e, ps)
    """
    pkeys = ("name", "version", "release", "epoch", "arch")

    d = dict(zip(ekeys, errata))
    d["packages"] = [dict(zip(pkeys, itemgetter(pkeys)(p))) for p in packages]

    return d


def dump_errata_summary(ppath, workdir, filename=_ERRATA_SUMMARY_FILE,
                        ekeys=_ERRATA_KEYS):
    """
    :param ppath: The path to RPM DB 'Packages' of target host or system group
    :param workdir: Working dir to dump the result
    :param filename: Output file basename
    """
    es = sorted((e for e in get_errata_list_g(ppath)),
                key=itemgetter("advisory"))

    es = [_mkedic(e, ps) for e, ps in U.groupby_key(es, itemgetter(*ekeys))]
    json.dump(es, open(os.path.join(workdir, filename), 'w')


# vim:sw=4:ts=4:et:
