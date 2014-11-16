#
# Copyright (C) 2013, 2014 Red Hat, Inc.
# Author: Satoru SATOH <ssato@redhat.com>
# License: GPLv3+
#
"""Some utility routines utilize DNF/Hawkey.
"""
import rpmkit.updateinfo.base
import rpmkit.utils

import collections
import dnf.cli.cli
import dnf
import hawkey
import logging
import operator
import os.path

try:
    # NOTE: Required dnf >= 0.6.0
    import dnf.cli.commands.updateinfo as DCCU
except ImportError:
    logging.warn("dnf >= 0.6.0 supports updateinfo is not available. "
                 "FYI. dnf >= 0.6.0 for Fedora 20 is available from my copr "
                 "repo: http://copr.fedoraproject.org/coprs/ssato/dnf/")
    DCCU = None

LOG = logging.getLogger("rpmkit.updateinfo.dnfbase")
_REPO_ACTIONS = (_REPO_ENABLE, _REPO_DISABLE) = ("enable", "disable")
_PKG_NARROWS = ("installed", "updates", "obsoletes", "all")


def noop(*args, **kwargs):
    pass


def _toggle_repos(base, repos, action):
    """
    Toggle enabled/disabled status of repos.

    :param base: dnf.Base instance
    :param repos: A list of repos to enable/disable
    :param action: Action for repos, enalbe or disable
    """
    assert isinstance(base, dnf.Base), "Wrong base object: %s" % str(base)
    assert action in _REPO_ACTIONS, "Invalid action for repos: %s" % action

    for rid in repos:
        rs = base.repos.get_matching(rid)
        if rs:
            getattr(rs, action, noop)()
        else:
            LOG.warn("Unknown repo %s", rid)


def _activate_repos(base, repos=[], disabled_repos=['*']):
    """
    :param base: dnf.Base instance
    :param repos: A list of repos to enable
    :param disabled_repos: A list of repos to disable

    NOTE: It must take of the order of to disable and enable repos because it's
    common way to disable all repos w/ glob pattern repo name *and then* enable
    specific repos explicitly.

    see also: :method:`_configure_repos` in :class:`dnf.cli.cli.Cli`
    """
    assert isinstance(base, dnf.Base), "Wrong base object: %s" % str(base)

    base.read_all_repos()
    _toggle_repos(base, disabled_repos, _REPO_DISABLE)
    _toggle_repos(base, repos, _REPO_ENABLE)


def _to_pkg(pkg, extras=[]):
    """
    Convert Package object :: hawkey.Package to rpmkit.updateinfo.base.Package
    object.

    :param pkg: Package object which Base.list_installed(), etc. returns
    :param extras: A list of dicts represent extra packages which is installed
        but not available from yum repos available.
    """
    if extras:
        if pkg.name in (e["name"] for e in extras):
            originally_from = pkg.packager  # FIXME
        else:
            originally_from = "Unknown"
    else:
        originally_from = "TBD"

    if isinstance(pkg, collections.Mapping):
        return pkg

    # TODO: hawkey.Package.packager != vendor, buildhost is not available, etc.
    return rpmkit.updateinfo.base.Package(pkg.name, pkg.v, pkg.r, pkg.a,
                                          pkg.epoch, pkg.summary,
                                          pkg.packager, "N/A",
                                          originally_from=originally_from)


# see dnf.cli.commands.updateinfo.UpdateInfoCommand.TYPE2LABEL:
HADV_TYPE2LABEL = {hawkey.ADVISORY_BUGFIX: 'bugfix',
                   hawkey.ADVISORY_ENHANCEMENT: 'enhancement',
                   hawkey.ADVISORY_SECURITY: 'security',
                   hawkey.ADVISORY_UNKNOWN: 'unknown'}

HAREF_TYPE2LABEL = {hawkey.REFERENCE_BUGZILLA: "bugzilla",
                    hawkey.REFERENCE_CVE: "cve",
                    hawkey.REFERENCE_VENDOR: "vendor",
                    hawkey.REFERENCE_UNKNOWN: "unknown"}


def type_from_hawkey_adv(hadv):
    return HADV_TYPE2LABEL[hadv.type]


def type_from_hawkey_aref(haref):
    return HAREF_TYPE2LABEL[haref.type]


def get_severity_from_hadv(hadv, default="N/A"):
    sevref_base = "https://access.redhat.com/security/updates/classification/#"

    if hadv.type != hawkey.ADVISORY_SECURITY:
        return default

    sevrefs = [r for r in hadv.references if r.title is None]
    if not sevrefs or not sevrefs[0].startswith(sevref_base):
        return default

    return sevrefs[0].replace(sevref_base, '').title()


def hawkey_adv_to_errata(hadv):
    """
    Make an errata dict from _hawkey.Advisory object.

    :param hadv: A _hawkey.Advisory object
    """
    assert hadv.id, "Not _hawkey.Advisory ?: {}".format(hadv)
        
    errata = dict(advisory=hadv.id, synopsis=hadv.title,
                  description=hadv.description,
                  update_date=hadv.update.strftime("%Y-%m-%d"),
                  issue_date=hadv.update.strftime("%Y-%m-%d"),  # TODO
                  type=type_from_hawkey_adv(hadv),
                  severity=get_severity_from_hadv(hadv),  # FIXME
                  )

    errata["bzs"] = [dict(id=r.id, summary=r.title, url=r.url) for r
                     in hadv.references if r.type == hawkey.REFERENCE_BUGZILLA]

    errata["cves"] = [dict(id=r.id, cve=r.id, url=r.url) for r
                     in hadv.references if r.type == hawkey.REFERENCE_CVE]

    errata["packages"] = [dict(name=p.name, arch=p.arch, evr=p.evr) for p
                          in hadv.packages]

    errata["package_names"] = rpmkit.utils.uniq(p.name for p in hadv.packages)
    errata["url"] = rpmkit.updateinfo.utils.errata_url(hadv.id)

    return errata


class Base(rpmkit.updateinfo.base.Base):

    def __init__(self, root='/', repos=[], disabled_repos=['*'],
                 workdir=None, cli=True, cacheonly=False, **kwargs):
        """
        Create and initialize dnf.Base or dnf.cli.cli.BaseCli object.

        :param root: RPM DB root dir
        :param repos: A list of repos to enable
        :param disabled_repos: A list of repos to disable
        :param workdir: Working dir to save logs and results
        :param cli: Which objects to instanciate? dnf.cli.cli.BaseCli
            if True or dnf.Base

        see also: :function:`dnf.automatic.main.main`

        >>> if os.path.exists("/etc/redhat-release"):
        ...     base = Base(cli=False)
        ...     assert isinstance(base.base, dnf.Base)
        ...
        ...     base = Base(cli=True)
        ...     assert isinstance(base.base, dnf.cli.cli.BaseCli)
        """
        super(Base, self).__init__(root, repos, disabled_repos, **kwargs)
        self.base = (dnf.cli.cli.BaseCli if cli else dnf.Base)()

        if self.root != '/':
            self.base.conf.installroot = self.base.conf.cachedir = self.root

        self.cacheonly = cacheonly

        # TODO: Ugly
        self.ready_list_install = False
        self.ready_list_x = False

        # see: :method:`__init__` of the class
        # :class:`dnf.cli.commands.updateinfo.UpdateInfoCommand`
        self._ina2evr_cache = None
        self._hpackages = collections.defaultdict(list)

    def prepare(self, pkgnarrow="installed"):
        if pkgnarrow == "installed":  # Make it just loading RPM DB.
            if self.ready_list_install:
                return

            self.base.fill_sack(load_system_repo='auto',
                                load_available_repos=False)
            self.ready_list_install = True
        else:
            if self.ready_list_x:
                return

            self.base.read_all_repos()
            _activate_repos(self.base, self.repos, self.disabled_repos)

            for repo in self.base.repos.iter_enabled():
                repo.skip_if_unavailable = True

                if self.cacheonly:
                    repo.md_only_cached = True

            self.ready_list_x = True

    def load_repos(self, setup_callbacks=False):
        """
        Activate and load metadata of base's repos, etc.

        :param setup_callbacks: Setup callbacks and progress bar displayed
            if True

        see also: :function:`dnf.automatic.main.main`
        """
        base = self.base

        # see :method:`configure` in :class:`dnf.cli.cli.Cli`.
        base.activate_persistor()

        # see :method:`_configure_repos` in :class:`dnf.cli.cli.Cli`.
        if setup_callbacks:
            (bar, base.ds_callback) = base.output.setup_progress_callbacks()
            base.repos.all.set_progress_bar(bar)
            # pylint: disable=no-member
            base.repos.all.confirm_func = \
                base.output._cli_confirm_gpg_key_import
            # pylint: enable=no-member

        # It will take some time to get metadata from remote repos.
        # see :method:`run` in :class:`dnf.cli.cli.Cli`.
        base.fill_sack(load_system_repo="auto")

    def list_installed_impl(self, **kwargs):
        """
        >>> if os.path.exists("/etc/redhat-release"):
        ...     base = Base(cacheonly=True)
        ...     ipkgs = base.list_installed_impl()
        ...     assert len(ipkgs) > 0
        """
        self.prepare()
        ips = self.base.sack.query().installed()
        if not isinstance(ips, list):
            ips = ips.run()

        self._hpackages["installed"] = ips

        return [_to_pkg(p) for p in ips]

    def list_updates_impl(self, obsoletes=True, **kwargs):
        """
        :param obsoletes: Include obsoletes in updates list if True

        >>> if os.path.exists("/etc/redhat-release"):
        ...     base = Base(repos=['*'], disabled_repos=[], cacheonly=True)
        ...     xs = base.list_updates_impl()
        ...     assert isinstance(xs, list), str(xs)
        """
        self.prepare("all")
        self.load_repos()

        # see :method:`check_updates` in :class:`dnf.cli.cli.BaseCli`
        ups = self.base.check_updates(print_=False)
        if not isinstance(ups, list):
            ups = ups.run()
        # del self.base.ts  # Needed to release RPM DB session ?

        self._hpackages["updates"] = ups

        # TODO: Pass extras.
        return [_to_pkg(p) for p in ups]

    def refresh_installed_cache(self):
        """
        see :method:`refresh_installed_cache` of the class
        :class:`dnf.cli.commands.updateinfo.UpdateInfoCommand`.
        """
        self._ina2evr_cache = {(p.name, p.arch): p.evr for p in
                               self._hpackages["installed"]}

    def _cmp_installed(self, apkg, op):
        ievr = self._ina2evr_cache.get((apkg.name, apkg.arch), None)
        if ievr is None:
            return False

        return op(self.base.sack.evr_cmp(ievr, apkg.evr), 0)

    def _older_installed(self, apkg):
        """
        Stolen from :class:`dnf.cli.commands.updateinfo.UpdateInfoCommand`.
        """
        return self._cmp_installed(apkg, operator.lt)

    def _newer_equal_installed(self, apkg):
        """
        Stolen from :class:`dnf.cli.commands.updateinfo.UpdateInfoCommand`.
        """
        return self._cmp_installed(apkg, operator.ge)

    def _apackage_advisory_installeds(self, pkgs, cmptype, req_apkg, specs=()):
        """
        Stolen from :class:`dnf.cli.commands.updateinfo.UpdateInfoCommand`.
        """
        for package in pkgs:
            for advisory in package.get_advisories(cmptype):
                for apkg in advisory.packages:
                    if req_apkg(apkg):
                        # installed = self._newer_equal_installed(apkg)
                        # yield apkg, advisory, installed
                        yield advisory  # we just need advisory object.

    def list_available_errata(self, specs=()):
        """
        Stolen from :method:`available_apkg_adv_insts` in
        :class:`dnf.cli.commands.updateinfo.UpdateInfoCommand`.
        """
        return self._apackage_advisory_installeds(self._hpackages["installed"],
                                                  DCCU.hawkey.GT,
                                                  self._older_installed,
                                                  specs)

    def list_errata_impl(self, **kwargs):
        """
        Stolen from :class:`dnf.cli.commands.updateinfo.UpdateInfoCommand`.

        TODO: Maybe it's better to inherit that class or write dnf plugin
        to acomplish the goal.
        """
        self.prepare("all")
        self.load_repos()
        self.refresh_installed_cache()

        hadvs = rpmkit.utils.uniq(self.list_available_errata())
        return [hawkey_adv_to_errata(hadv) for hadv in hadvs]

# vim:sw=4:ts=4:et:
