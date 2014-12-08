#
# Copyright (C) 2014 Satoru SATOH <ssato redhat.com>
# License: GPLv3+
#
"""Base class.
"""
import rpmkit.updateinfo.utils

import collections
import logging
import os.path


LOG = logging.getLogger("rpmkit.updateinfo.base")


class Base(object):
    name = 'rpmkit.updateinfo.base'

    def __init__(self, root='/', repos=[], disabled_repos=['*'],
                 workdir=None, cachedir=None, **kwargs):
        """
        :param root: RPM DB root dir
        :param repos: A list of repos to enable
        :param disabled_repos: A list of repos to disable
        :param workdir: Working dir to save logs and results

        >>> base = Base()
        """
        self.root = os.path.abspath(root)
        self.workdir = root if workdir is None else workdir
        self.repos = repos
        self.disabled_repos = disabled_repos
        self._packages = collections.defaultdict(list)

        if cachedir is None:
            self.cachedir = os.path.join(self.root, "var/cache")
        else:
            self.cachedir = cachedir

    def is_rpmdb_available(self, readonly=False):
        return rpmkit.updateinfo.utils.check_rpmdb_root(self.root, readonly)

    def packages(self, pkgnarrow):
        return self._packages[pkgnarrow]

    def list_installed(self, **kwargs):
        xs = self.packages("installed")
        if not xs:
            xs = self.list_installed_impl(**kwargs)

        return xs

    def list_updates(self, **kwargs):
        xs = self.packages("updates")
        if not xs:
            xs = self.list_updates_impl(**kwargs)

        return xs

    def list_errata(self, **kwargs):
        xs = self.packages("errata")
        if not xs:
            xs = self.list_errata_impl(**kwargs)

        return xs

    def list_installed_impl(self, **kwargs):
        raise NotImplementedError("list_installed_impl")

    def list_updates_impl(self, **kwargs):
        raise NotImplementedError("list_updates_impl")

    def list_errata_impl(self, **kwargs):
        raise NotImplementedError("list_errata_impl")


def may_be_rebuilt(vendor, buildhost):
    vbmap = dict([("Red Hat, Inc.", "redhat.com"),
                  ("Fedora Project", "fedoraproject.org")])
    bhsuffix = vbmap.get(vendor, False)

    return not (bhsuffix and buildhost.endswith(bhsuffix))


class Package(dict):

    def __init__(self, name, version, release, arch, epoch=0, summary=None,
                 vendor=None, buildhost=None, originally_from=None):
        """
        :param name: Package name
        """
        self["name"] = name
        self["version"] = version
        self["release"] = release
        self["arch"] = arch
        self["epoch"] = epoch
        self["summary"] = summary
        self["vendor"] = vendor
        self["buildhost"] = buildhost
        self["originally_from"] = originally_from

        if vendor and buildhost:
            self["may_be_rebuilt"] = may_be_rebuilt(vendor, buildhost)
        else:
            self["may_be_rebuilt"] = False

    def __str__(self):
        return "({name}, {version}, {release}, {epoch}, {arch})" % self

# vim:sw=4:ts=4:et:
