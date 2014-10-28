#
# Copyright (C) 2014 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato@redhat.com>
# License: GPLv3+
#
import rpmkit.updateinfo.base
import rpmkit.utils as RU

import itertools
import logging
import os.path
import yum


LOG = logging.getLogger("rpmkit.updateinfo.yumbase")

_REPO_ACTIONS = (_REPO_ENABLE, _REPO_DISABLE) = ("enable", "disable")
_PKG_NARROWS = ("installed", "updates", "obsoletes")


def noop(*args, **kwargs):
    pass


def _notice_to_errata(notice):
    """
    Notice metadata examples:

    packages:

     'pkglist': [
        {'name': 'Red Hat Enterprise Linux Server (v. 6 for 64-bit x86_64)',
         'packages': [
            {'arch': 'x86_64',
             'epoch': '0',
             'filename': 'xorg-x11-drv-fbdev-0.4.3-16.el6.x86_64.rpm',
             'name': 'xorg-x11-drv-fbdev',
             'release': '16.el6',
             'src': 'xorg-x11-drv-fbdev-0.4.3-16.el6.src.rpm',
             'sum': ('sha256', '8f3da83bb19c3776053c543002c9...'),
             'version': '0.4.3'},
             ...
        },
        ...
     ]

    cve in notice_metadata["references"]:

    {'href': 'https://www.redhat.com/security/data/cve/CVE-2013-1994.html',
     'id': 'CVE-2013-1994',
     'title': 'CVE-2013-1994',
     'type': 'cve'}
    """
    nmd = notice.get_metadata()

    errata = dict(advisory=nmd["update_id"], synopsis=nmd["title"],
                  description=nmd["description"], update_date=nmd["updated"],
                  issue_date=nmd["issued"], solution=nmd["solution"],
                  type=nmd["type"], severity=nmd.get("severity", "N/A"))

    errata["bzs"] = filter(lambda r: r.get("type") == "bugzilla",
                           nmd.get("references", []))
    errata["cves"] = filter(lambda r: r.get("type") == "cve",
                            nmd.get("references", []))

    errata["packages"] = RU.concat(nps["packages"] for nps in
                                   nmd.get("pkglist", []))
    return errata


def _to_pkg(pkg, extras=[]):
    """
    Convert Package object, instance of yum.rpmsack.RPMInstalledPackage,
    yum.sqlitesack..YumAvailablePackageSqlite, etc., to
    rpmkit.updateinfo.base.Package object.

    :param pkg: Package object which Base.list_installed(), etc. returns

    NOTE: Take care of rpm db session.
    """
    if extras:
        if pkg.name in (p.name for p in extras):
            originally_from = pkg.vendor
        else:
            originally_from = "Unknown"
    else:
        originally_from = "TBD"

    return rpmkit.updateinfo.base.Package(pkg.name, pkg.version, pkg.release,
                                          pkg.arch, pkg.epoch, pkg.summary,
                                          pkg.vendor, pkg.buildhost,
                                          originally_from=originally_from)


class Base(rpmkit.updateinfo.base.Base):

    def __init__(self, root, repos=[], disabled_repos=['*'], **kwargs):
        """
        Create an initialized yum.YumBase instance.
        Created instance has no enabled repos by default.

        :param root: RPM DB root dir in absolute path
        :param repos: List of Yum repos to enable
        :param disabled_repos: List of Yum repos to disable

        >>> import os.path
        >>> if os.path.exists("/etc/redhat-release"):
        ...     base = Base('/')
        ...     assert isinstance(base.base, yum.YumBase)
        ...     base.base.repos.listEnabled() == []
        True
        """
        super(Base, self).__init__(root, repos, disabled_repos, **kwargs)
        self.base = yum.YumBase()

        try:
            self.base.conf.installroot = self.root
        except AttributeError:
            self.base.preconf.root = self.root

        self.base.conf.cachedir = os.path.join(self.root, "var/cache")
        self.base.logger = self.base.verbose_logger = LOG
        self._activate_repos()

        self.packages = dict()

    def _toggle_repos(self, repos, action):
        """
        Toggle enabled/disabled status of repos.

        :param repos: A list of repos to enable/disable
        :param action: Action for repos, enalbe or disable

        see also: the :method:``findRepos`` of the
        :class:``yum.repos.RepoStorage``.
        """
        assert action in _REPO_ACTIONS, "Invalid action for repos: %s" % action

        for repo_name in repos:
            for repo in self.base.repos.findRepos(repo_name):
                getattr(repo, action, noop)()

    def _activate_repos(self):
        """
        :param repos: A list of repos to enable
        :param disabled_repos: A list of repos to disable

        NOTE: It must take of the order of to disable and enable repos because
        it's common way to disable all repos w/ glob pattern repo name *and
        then* enable specific repos.
        """
        self._toggle_repos(self.disabled_repos, "disable")
        self._toggle_repos(self.repos, "enable")

    def list_packages(self, pkgnarrows=None, extras=[]):
        """
        List installed or update RPMs similar to
        "repoquery --pkgnarrow=updates --all --plugins --qf '%{nevra}'".

        :param pkgnarrows: A list of package list narrowing factors

        :return: A dict contains lists of dicts of packages

        >>> import os.path
        >>> if os.path.exists("/etc/redhat-release"):
        ...     base = Base('/')
        ...     pkgs = base.list_packages()
        ...     for narrow in _PKG_NARROWS:
        ...         assert isinstance(pkgs[narrow], list)
        ...     assert pkgs["installed"]
        """
        if not pkgnarrows:
            pkgnarrows = _PKG_NARROWS

        if len(pkgnarrows) > 1 or pkgnarrows[0] != "installed":
            self.base.repos.populateSack()  # It takes some time.

        for pn in pkgnarrows:
            ygh = self.base.doPackageLists(pn)
            self.packages[pn] = [_to_pkg(p, extras) for p in getattr(ygh, pn)]

        return self.packages

    def list_extras(self):
        """
        Method to mimic "yum list extras" to list the packages installed on the
        system that are not available in any yum repository listed in the
        config file.

        :return: List of dicts of extra RPMs info
        """
        eps = self.packages.get("extras", [])
        return eps if eps else self.list_packages(("extras", "distro-extras"))

    def list_installed(self, mark_extras=False):
        """
        :return: List of dicts of installed RPMs info
        """
        ips = self.packages.get("installed", [])
        if ips:
            return ips

        if mark_extras:
            extras = self.list_packages(("extras", ))["extras"]
            ips = self.list_packages(("installed", ), extras)["installed"]
        else:
            ips = self.list_packages(("installed", ))["installed"]

        return ips

    def list_updates(self, obsoletes=True):
        """
        Method to mimic "yum check-update".

        :param obsoletes: Include obsoletes in updates list if True
        :return: List of dicts of update RPMs info
        """
        ups = self.packages.get("updates", [])
        obs = self.packages.get("obsoletes", [])

        if ups and obs and obsoletes:
            return ups + obs
        elif ups and not obsoletes:
            return ups

        xs = self.list_packages()
        return xs["updates"] + xs["obsoletes"] if obsoletes else xs["updates"]

    def list_errata(self):
        """
        List applicable Errata.

        :param root: RPM DB root dir in absolute path
        :param repos: List of Yum repos to enable
        :param disabled_repos: List of Yum repos to disable

        :return: A dict contains lists of dicts of errata
        """
        self.base.repos.populateSack()

        oldpkgtups = [t[1] for t in self.base.up.getUpdatesTuples()]
        npss_g = itertools.ifilter(None,
                                   (self.base.upinfo.get_applicable_notices(o)
                                    for o in oldpkgtups))
        es = itertools.chain(*((_notice_to_errata(t[1]) for t in ts) for ts
                               in npss_g))
        return list(es)

# vim:sw=4:ts=4:et:
