#
# Copyright (C) 2014 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato@redhat.com>
#
# This software is licensed to you under the GNU General Public License,
# version 3 (GPLv3). There is NO WARRANTY for this software, express or
# implied, including the implied warranties of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. You should have received a copy of GPLv3 along with this
# software; if not, see http://www.gnu.org/licenses/gpl.html
#
import logging
import yum


LOG = logging.getLogger("rpmkit.updateinfo.yumbase")

_REPO_ACTIONS = (_REPO_ENABLE, _REPO_DISABLE) = ("enable", "disable")
_PKG_NARROWS = ("installed", "updates", "obsoletes")


def noop(*args, **kwargs):
    pass


def _toggle_repos(base, repos, action):
    """
    Toggle enabled/disabled status of repos.

    :param base: yum.YumBase instance
    :param repos: A list of repos to enable/disable
    :param action: Action for repos, enalbe or disable

    see also: the :method:``findRepos`` of the :class:``yum.repos.RepoStorage``
    """
    assert isinstance(base, yum.YumBase), "Wrong base object: %s" % str(base)
    assert action in _REPO_ACTIONS, "Invalid action for repos: %s" % action

    for repo_name in repos:
        for repo in base.repos.findRepos(repo_name):
            getattr(repo, action, noop)()


def _activate_repos(base, repos=[], repos_to_disable=['*']):
    """
    :param base: yum.YumBase instance
    :param repos: A list of repos to enable

    NOTE: It must take of the order of to disable and enable repos because it's
    common way to disable all repos w/ glob pattern repo name *and then* enable
    specific repos.
    """
    assert isinstance(base, yum.YumBase), "Wrong base object: %s" % str(base)

    _toggle_repos(base, repos_to_disable, "disable")
    _toggle_repos(base, repos, "enable")


def create(root, repos=[], repos_to_disable=['*']):
    """
    Create an initialized yum.YumBase instance.
    Created instance has no enabled repos by default.

    :param root: RPM DB root dir in absolute path
    :param repos: List of Yum repos to enable
    :param repos_to_disable: List of Yum repos to disable

    >>> import os.path
    >>> if os.path.exists("/etc/redhat-release"):
    ...     base = create('/')
    ...     assert isinstance(base, yum.YumBase)
    ...     base.repos.listEnabled() == []
    True
    """
    base = yum.YumBase()

    try:
        base.preconf.root = root
    except AttributeError:
        base.conf.installroot = root

    base.logger = base.verbose_logger = LOG
    _activate_repos(base, repos, repos_to_disable)

    return base


def list_packages(root, repos=[], repos_to_disable=['*'],
                  pkgnarrows=_PKG_NARROWS):
    """
    List installed or update RPMs similar to
    "repoquery --pkgnarrow=updates --all --plugins --qf '%{nevra}'".

    :param root: RPM DB root dir in absolute path
    :param repos: List of Yum repos to enable
    :param repos_to_disable: List of Yum repos to disable
    :param pkgnarrows: List of types to narrrow packages list

    :return: A dict contains lists of dicts of packages

    >>> import os.path
    >>> if os.path.exists("/etc/redhat-release"):
    ...     pkgs = list_packages('/')
    ...     for narrow in _PKG_NARROWS:
    ...         assert isinstance(pkgs[narrow], list)
    ...     assert pkgs["installed"]
    """
    base = create(root, repos, repos_to_disable)

    if pkgnarrows != ("installed", ):
        base.repos.populateSack()

    ret = dict()

    for pn in pkgnarrows:
        ygh = base.doPackageLists(pn)
        ret[pn] = getattr(ygh, pn)

    return ret


# functions to mimic some yum commands.
def list_errata(root, repos=[], disabled_repos=['*'], **_kwargs):
    """
    function to mimic "yum list-sec" / "yum updateinfo list".

    :param root: RPM DB root dir in absolute path
    :param repos: List of Yum repos to enable
    :param disabled_repos: List of Yum repos to disable

    :return: List of dicts of errata info
    """
    raise NotImplementedError("This function is not implemented yet.")


def list_updates(root, repos=[], disabled_repos=['*'], obsoletes=True,
                 **_kwargs):
    """
    function to mimic "yum check-update".

    :param root: RPM DB root dir in absolute path
    :param repos: List of Yum repos to enable
    :param disabled_repos: List of Yum repos to disable
    :param obsoletes: Include obsoletes in updates list if True

    :return: List of dicts of update RPMs info
    """
    xs = list_packages(root, repos, disabled_repos)
    return xs["updates"] + xs["obsoletes"] if obsoletes else xs["updates"]

# vim:sw=4:ts=4:et:
