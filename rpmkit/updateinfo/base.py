#
# Copyright (C) 2014 Satoru SATOH <ssato redhat.com>
# License: GPLv3+
#
"""Base class.
"""
import rpmkit.updateinfo.utils
import rpmkit.memoize

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
            self._cachedir = os.path.join(self.root, "var/cache")
        else:
            self._cachedir = cachedir

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


_VENDOR_RH = "Red Hat, Inc."
_VENDOR_MAPS = {_VENDOR_RH: ("redhat", ".redhat.com"),
                "Symantec Corporation": ("symantec", ".veritas.com"),
                "ZABBIX-JP": ("zabbixjp", ".zabbix.jp"),
                "Fedora Project": ("fedora", ".fedoraproject.org"),
                }


def inspect_origin(name, vendor, buildhost, extras=[], extra_names=[],
                   vmaps=_VENDOR_MAPS, exp_vendor=_VENDOR_RH):
    """
    Inspect package info and detect its origin, etc.

    :param name: Package name
    :param vendor: Package vendor
    :param buildhost: Package buildhost
    :param extras: Extra packages not available from yum repos
    :param extra_names: Extra package names
    """
    origin = vmaps.get(vendor, ("Unknown", ))[0]

    if name not in extra_names:  # May be rebuilt or replaced.
        if vendor != exp_vendor:
            return dict(origin=origin, rebuilt=False, replaced=True)

        bh_esfx = vmaps.get(vendor, (None, ''))[1]
        if bh_esfx and not buildhost.endswith(bh_esfx):
            return dict(origin=origin, rebuilt=True, replaced=False)

    return dict(origin=origin, rebuilt=False, replaced=False)


class Package(dict):

    def __init__(self, name, version, release, arch, epoch=0, summary=None,
                 vendor=None, buildhost=None, extras=[], extra_names=[],
                 **kwargs):
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

        d = inspect_origin(name, vendor, buildhost, extras, extra_names)
        self.update(**d)

        for k, v in kwargs.items():
            self[k] = v

    def __str__(self):
        return "({name}, {version}, {release}, {epoch}, {arch})" % self

# vim:sw=4:ts=4:et:
