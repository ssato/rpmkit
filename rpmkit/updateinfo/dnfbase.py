#
# Copyright (C) 2013, 2014 Red Hat, Inc.
# Author: Satoru SATOH <ssato@redhat.com>
# License: GPLv3+
#
"""Some utility routines utilize DNF/Hawkey.
"""
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


def create(root, repos=[], disabled_repos=['*'], cli=True,
           pkgnarrow="installed"):
    """
    Create and initialize dnf.Base object.

    :param root: RPM DB root dir
    :param repos: A list of repos to enable
    :param disabled_repos: A list of repos to disable
    :param cli: Return an instance of dnf.cli.cli.BaseCli instead of dnf.Base
        if True
    :return: A dnf.cli.cli.BaseCli (dnf.Base) object

    see also: :function:`dnf.automatic.main.main`

    >>> if os.path.exists("/etc/redhat-release"):
    ...     base = create('/')
    ...     assert isinstance(base, dnf.Base)
    ...
    ...     base = create('/', pkgnarrow='all')
    ...     assert isinstance(base, dnf.Base)
    """
    base = (dnf.cli.cli.BaseCli if cli else dnf.Base)()

    if root != '/':
        root = os.path.abspath(root)
        base.conf.installroot = base.conf.cachedir = os.path.abspath(root)

    if pkgnarrow == "installed":  # Make it just loading RPM DB.
        base.fill_sack(load_system_repo='auto', load_available_repos=False)
    else:
        base.read_all_repos()
        _activate_repos(base, repos, disabled_repos)

    return base


def load_repos(base, setup_callbacks=False):
    """
    Activate and load metadata of base's repos, etc.

    :param base: dnf.Base instance
    :param setup_callbacks: Setup callbacks and progress bar displayed if True

    see also: :function:`dnf.automatic.main.main`
    """
    assert isinstance(base, dnf.cli.cli.BaseCli), \
        "Wrong base object: %s" % str(base)

    # see :method:`configure` in :class:`dnf.cli.cli.Cli`.
    base.activate_persistor()

    # see :method:`_configure_repos` in :class:`dnf.cli.cli.Cli`.
    if setup_callbacks:
        (bar, base.ds_callback) = base.output.setup_progress_callbacks()
        base.repos.all.set_progress_bar(bar)
        # pylint: disable=no-member
        base.repos.all.confirm_func = base.output._cli_confirm_gpg_key_import
        # pylint: enable=no-member

    # It will take some time to get metadata from remote repos.
    # see :method:`run` in :class:`dnf.cli.cli.Cli`.
    base.fill_sack(load_system_repo="auto")


# functions to mimic some yum commands.
def list_installed(root):
    """
    :param root: RPM DB root dir (relative or absolute)

    >>> if os.path.exists("/etc/redhat-release"):
    ...     ipkgs = list_installed('/')
    ...     assert len(ipkgs) > 0
    """
    base = create(root, cli=False)
    return base.sack.query().installed().run()


def list_updates(root, repos=[], disabled_repos=['*'], obsoletes=True):
    """
    :param root: RPM DB root dir (relative or absolute)
    :param repos: List of Yum repos to enable
    :param disabled_repos: List of Yum repos to disable
    :param obsoletes: Include obsoletes in updates list if True

    >>> if os.path.exists("/etc/redhat-release"):
    ...     xs = list_updates('/', repos=['*'], disabled_repos=[])
    ...     assert isinstance(xs, list), str(xs)
    """
    base = create(root, pkgnarrow="all")
    load_repos(base)

    # see :method:`check_updates` in :class:`dnf.cli.cli.BaseCli`
    ups = base.check_updates(print_=False).run()
    # del base.ts  # Needed to release RPM DB session ?

    return ups

# vim:sw=4:ts=4:et:
