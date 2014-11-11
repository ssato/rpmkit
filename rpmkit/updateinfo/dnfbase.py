#
# Copyright (C) 2013, 2014 Red Hat, Inc.
# Author: Satoru SATOH <ssato@redhat.com>
# License: GPLv3+
#
"""Some utility routines utilize DNF/Hawkey.
"""
import rpmkit.updateinfo.base

import dnf.cli.cli
import dnf
import logging
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
        return self.base.sack.query().installed().run()

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

        return ups

    def list_errata_impl(self, **kwargs):
        """
        TBD.
        """
        raise NotImplementedError("dnfbase.Base.list_updates")

# vim:sw=4:ts=4:et:
