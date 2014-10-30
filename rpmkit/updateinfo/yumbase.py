#
# Copyright (C) 2014 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato@redhat.com>
# License: GPLv3+
#
import rpmkit.updateinfo.base
import rpmkit.updateinfo.utils
import rpmkit.utils as RU

import collections
import itertools
import logging
import os.path
import yum


LOG = logging.getLogger("rpmkit.updateinfo.yumbase")

_REPO_ACTIONS = (_REPO_ENABLE, _REPO_DISABLE) = ("enable", "disable")
_PKG_NARROWS = ["installed", "available", "updates", "extras", "obsoletes",
                "recent"]


def noop(*args, **kwargs):
    pass


RHBZ_URL_BASE = "https://bugzilla.redhat.com/bugzilla/show_bug.cgi?id="


def normalize_bz(bz, urlbase=RHBZ_URL_BASE):
    """
    Normalize bz dict came from updateinfo.
    """
    bz["summary"] = bz["title"]
    bz["url"] = bz.get("href", urlbase + str(bz["id"]))

    return bz


def normalize_cve(cve):
    """
    Normalize cve dict came from updateinfo.
    """
    cve["cve"] = cve["id"]
    cve["url"] = cve["href"]

    return cve


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

    errata["bzs"] = [normalize_bz(bz) for bz in
                     filter(lambda r: r.get("type") == "bugzilla",
                            nmd.get("references", []))]
    errata["cves"] = [normalize_cve(cve) for cve in
                      filter(lambda r: r.get("type") == "cve",
                             nmd.get("references", []))]

    errata["packages"] = RU.concat(nps["packages"] for nps in
                                   nmd.get("pkglist", []))

    errata["package_names"] = ','.join(RU.uniq(p["name"] for p
                                               in errata["packages"]))
    errata["url"] = rpmkit.updateinfo.utils.errata_url(errata["advisory"])

    return errata


def _to_pkg(pkg, extras=[]):
    """
    Convert Package object, instance of yum.rpmsack.RPMInstalledPackage,
    yum.sqlitesack..YumAvailablePackageSqlite, etc., to
    rpmkit.updateinfo.base.Package object.

    :param pkg: Package object which Base.list_installed(), etc. returns
    :param extras: A list of dicts represent extra packages which is installed
        but not available from yum repos available.

    NOTE: Take care of rpm db session.
    """
    if extras:
        if pkg.name in (e["name"] for e in extras):
            originally_from = pkg.vendor
        else:
            originally_from = "Unknown"
    else:
        originally_from = "TBD"

    if isinstance(pkg, collections.Mapping):
        return pkg

    return rpmkit.updateinfo.base.Package(pkg.name, pkg.version, pkg.release,
                                          pkg.arch, pkg.epoch, pkg.summary,
                                          pkg.vendor, pkg.buildhost,
                                          originally_from=originally_from)


class Base(rpmkit.updateinfo.base.Base):

    def __init__(self, root='/', repos=[], disabled_repos=['*'],
                 load_available_repos=True, **kwargs):
        """
        Create an initialized yum.YumBase instance.
        Created instance has no enabled repos by default.

        :param root: RPM DB root dir in absolute path
        :param repos: List of Yum repos to enable
        :param disabled_repos: List of Yum repos to disable
        :param load_available_repos: It will populates the package sack from
            the repositories if True

        >>> import os.path
        >>> if os.path.exists("/etc/redhat-release"):
        ...     base = Base()
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
        self.load_available_repos = load_available_repos
        self.populated = False

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
        self._toggle_repos(self.disabled_repos, _REPO_DISABLE)
        self._toggle_repos(self.repos, _REPO_ENABLE)

    def _load_repos(self):
        """
        Populates the package sack from the repositories.  Network access
        happens if any non-local repos activated and it will take some time
        to finish.
        """
        if self.load_available_repos and not self.populated:
            LOG.debug("Loading yum repo metadata from repos: %s",
                      ','.join(r.id for r in self.base.repos.listEnabled()))
            # self.base._getTs()
            self.base._getSacks()
            self.base._getUpdates()
            self.populated = True

    def list_packages(self, pkgnarrow="installed"):
        """
        List installed or update RPMs similar to
        "repoquery --pkgnarrow=updates --all --plugins --qf '%{nevra}'".

        :param pkgnarrow: Package list narrowing factor
        :return: A dict contains lists of dicts of packages

        TODO: Find out better and correct ways to activate repo and sacks.

        >>> import os.path
        >>> if os.path.exists("/etc/redhat-release"):
        ...     base = Base()
        ...     pkgs = base.list_packages()
        ...     assert isinstance(pkgs, list)
        """
        assert pkgnarrow in _PKG_NARROWS, "Invalid pkgnarrow: " + pkgnarrow

        xs = self.packages.get(pkgnarrow)
        if xs:
            return xs

        self._load_repos()

        ygh = self.base.doPackageLists(pkgnarrow)
        xs = [_to_pkg(p) for p in getattr(ygh, pkgnarrow, [])]
        self.packages[pkgnarrow] = xs

        return xs

    def list_installed(self):
        """
        :return: List of dicts of installed RPMs info

        see also: yum.updateinfo.exclude_updates
        """
        extras = self.list_packages("extras")

        ygh = self.base.doPackageLists("installed")
        ips = [_to_pkg(p, extras) for p in ygh.installed]
        self.packages["installed"] = ips

        return ips

    def list_updates(self, obsoletes=True):
        """
        Method to mimic "yum check-update".

        :param obsoletes: Include obsoletes in updates list if True
        :return: List of dicts of update RPMs info
        """
        ups = self.list_packages("updates")

        if obsoletes:
            obs = self.list_packages("obsoletes")
            return ups + obs
        else:
            return ups

    def list_errata(self):
        """
        List applicable Errata.

        :param root: RPM DB root dir in absolute path
        :param repos: List of Yum repos to enable
        :param disabled_repos: List of Yum repos to disable

        :return: A dict contains lists of dicts of errata
        """
        self._load_repos()
        oldpkgtups = [t[1] for t in self.base.up.getUpdatesTuples()]
        npss_g = itertools.ifilter(None,
                                   (self.base.upinfo.get_applicable_notices(o)
                                    for o in oldpkgtups))
        es = itertools.chain(*((_notice_to_errata(t[1]) for t in ts) for ts
                               in npss_g))
        return list(es)

# vim:sw=4:ts=4:et:
