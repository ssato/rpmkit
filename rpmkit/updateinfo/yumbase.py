#
# Copyright (C) 2014 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato@redhat.com>
# License: GPLv3+
#
import rpmkit.utils as RU
import itertools
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


def _activate_repos(base, repos=[], disabled_repos=['*']):
    """
    :param base: yum.YumBase instance
    :param repos: A list of repos to enable

    NOTE: It must take of the order of to disable and enable repos because it's
    common way to disable all repos w/ glob pattern repo name *and then* enable
    specific repos.
    """
    assert isinstance(base, yum.YumBase), "Wrong base object: %s" % str(base)

    _toggle_repos(base, disabled_repos, "disable")
    _toggle_repos(base, repos, "enable")


def create(root, repos=[], disabled_repos=['*']):
    """
    Create an initialized yum.YumBase instance.
    Created instance has no enabled repos by default.

    :param root: RPM DB root dir in absolute path
    :param repos: List of Yum repos to enable
    :param disabled_repos: List of Yum repos to disable

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
    _activate_repos(base, repos, disabled_repos)

    return base


def list_packages(root, repos=[], disabled_repos=['*'],
                  pkgnarrows=_PKG_NARROWS):
    """
    List installed or update RPMs similar to
    "repoquery --pkgnarrow=updates --all --plugins --qf '%{nevra}'".

    :param root: RPM DB root dir in absolute path
    :param repos: List of Yum repos to enable
    :param disabled_repos: List of Yum repos to disable
    :param pkgnarrows: List of types to narrrow packages list

    :return: A dict contains lists of dicts of packages

    >>> import os.path
    >>> if os.path.exists("/etc/redhat-release"):
    ...     pkgs = list_packages('/')
    ...     for narrow in _PKG_NARROWS:
    ...         assert isinstance(pkgs[narrow], list)
    ...     assert pkgs["installed"]
    """
    base = create(root, repos, disabled_repos)

    if pkgnarrows != ("installed", ):
        base.repos.populateSack()  # It takes some time.

    ret = dict()

    for pn in pkgnarrows:
        ygh = base.doPackageLists(pn)
        ret[pn] = getattr(ygh, pn)

    return ret


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
                  type=nmd["type"], severity=nmd["severity"])

    errata["bzs"] = filter(lambda r: r.get("type") == "bugzilla",
                           nmd.get("references", []))
    errata["cves"] = filter(lambda r: r.get("type") == "cve",
                            nmd.get("references", []))

    errata["packages"] = RU.concat(nps["packages"] for nps in
                                   errata["pkglist"])
    return errata


# functions to mimic some yum commands.
def list_errata(root, repos=[], disabled_repos=['*']):
    """
    List applicable Errata.

    :param root: RPM DB root dir in absolute path
    :param repos: List of Yum repos to enable
    :param disabled_repos: List of Yum repos to disable

    :return: A dict contains lists of dicts of errata
    """
    base = create(root, repos, disabled_repos)
    base.repos.populateSack()

    oldpkgtups = [t[1] for t in base.up.getUpdatesTuples()]
    npss_g = itertools.ifilter(None,
                               (base.upinfo.get_applicable_notices(o) for o
                                in oldpkgtups))
    es = itertools.chain(*((_notice_to_errata(t[1]) for t in ts) for ts
                           in npss_g))
    return list(es)


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
