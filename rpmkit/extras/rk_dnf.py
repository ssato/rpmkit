#
# Copyright (C) 2013, 2014 Red Hat, Inc.
# Author: Satoru SATOH <ssato@redhat.com>
# License: GPLv3+
#
"""Some utility routines utilize DNF/Hawkey.
"""
from __future__ import print_function

import dnf.cli.cli
import dnf.exceptions
import dnf.subject
import dnf.transaction
import glob
import librepo
import logging
import os.path
import shutil
import tempfile

try:
    # NOTE: Required dnf >= 0.6.0
    import dnf.cli.commands.updateinfo as DCCU
except ImportError:
    logging.warn("dnf >= 0.6.0 supports updateinfo is not available. "
                 "FYI. dnf >= 0.6.0 for Fedora 20 is available from my copr "
                 "repo: http://copr.fedoraproject.org/coprs/ssato/dnf/")
    DCCU = None


def base_create(root):
    """
    Create and initialize dnf.base object.

    :param root: RPM DB root dir
    :return: A dnf.cli.cli.BaseCli (dnf.base) object
    """
    base = dnf.cli.cli.BaseCli()

    if root != '/':
        base.conf.installroot = base.conf.cachedir = os.path.abspath(root)

    base.conf.clean_requirements_on_remove = True

    return base


def base_create_2(root='/', repos=[]):
    """
    :param repos: A list of repos to enable or []. [] means that all available
        system repos to be enabled.

    :return: dnf.base.Base instance

    :see: :function:`dnf.automatic.main.main`
    """
    base = dnf.Base()
    if root != '/':
        base.conf.installroot = base.conf.cachedir = os.path.abspath(root)

    base.read_all_repos()
    if repos:
        for rid, repo in base.repos.iteritems():
            if rid in enabled_repos:
                repo.enable()
                logging.debug("Enabled the repo: " + rid)
            else:
                repo.disable()

    base.fill_sack()  # It will take some time to fetch repo metadata.
    # base.resolve()

    return base


def base_setup_excludes(base, excludes):
    """
    :param base: An initialized dnf.cli.cli.BaseCli (dnf.base) object
    :param excludes: A list of names or wildcards specifying packages must be
        excluded from the erasure list
    """
    # if excludes:
    #    matches = dnf.subject.Subject('*').get_best_query(base.sack)
    #    installed = matches.installed().run()

    # see :method:`dnf.base.Base._setup_excludes`.
    for excl in excludes:
        pkgs = base.sack.query().filter_autoglob(name=excl)

        if not pkgs:
            logging.debug("Not installed and ignored: " + excl)
            continue

        # pylint: disable=E1101
        base.sack.add_excludes(pkgs)
        # pylint: enable=E1101

        logging.debug("Excluded: " + excl)


def list_installed(root):
    """
    :param root: RPM DB root dir (relative or absolute)
    """
    base = base_create(root)
    base.fill_sack(load_available_repos=False)

    return base.sack.query().installed().run()


PROGRESSBAR_LEN = 50


def download_updateinfo_xml(repo):
    """
    TODO: This code is a quick and dirty hack; too much low level and I guess
    there is a way to do same things in DNF/Hawkey level.

    see also:
        * rhbz#850912 RFE: support updateinfo:
          https://bugzilla.redhat.com/show_bug.cgi?id=850912

        * http://tojaj.github.io/librepo/examples.html

    :param repo: An initialized :class:`dnf.repo.Repo` instance
    """
    h = repo.get_handle()
    h.setopt(librepo.LRO_YUMDLIST, ["updateinfo"])

    tmpdir = tempfile.mkdtemp(dir=repo.cachedir, prefix="tmp-updateinfo-")
    h.setopt(librepo.LRO_DESTDIR, tmpdir)
    h.setopt(librepo.LRO_PROGRESSCB, lambda *args, **kwargs: None)

    h.perform()  # FIXME: Handle exceptions.

    updixml = glob.glob(os.path.join(tmpdir, 'repodata', '*updateinfo*'))[0]
    shutil.move(updixml, os.path.join(repo.cachedir, "repodata",
                                      os.path.basename(updixml)))
    shutil.rmtree(tmpdir)


def compute_removed(pkgspecs, root, excludes=[]):
    """
    :param pkgspecs: A list of names or wildcards specifying packages to erase
    :param root: RPM DB root dir (relative or absolute)
    :param excludes: A list of names or wildcards specifying packages must be
        excluded from the erasure list

    :return: A pair of a list of name of packages to be excluded and removed
    """
    base = base_create(root)

    # Load RPM DB (system repo) only.
    base.fill_sack(load_available_repos=False)
    base_setup_excludes(base, excludes)

    removes = []
    for pspec in pkgspecs:
        try:
            base.remove(pspec)
            base.resolve(allow_erasing=True)
            rs = [x.erased.name for x in
                  base.transaction.get_items(dnf.transaction.ERASE)]
            removes.extend(rs)

        except dnf.exceptions.PackagesNotInstalledError:
            logging.info("Excluded or no package matched: " + pspec)

        except dnf.exceptions.DepsolveError:
            logging.warn("Depsolv error! Make it excluded: " + pspec)
            excludes.append(pspec)
            base_setup_excludes(base, [pspec])

    del base.ts  # Needed to release RPM DB session ?

    return (sorted(set(excludes)), sorted(set(removes)))


def compute_updates(root, repos=[], updateinfo=False, setup_callbacks=False):
    """
    :param root: RPM DB root dir (relative or absolute)
    :param repos: A list of repos to enable or []. [] means that all available
        system repos to be enabled.
    :param updateinfo: Retrieve updateinfo.xml if True
    :param setup_callbacks: Setup callbacks and progress bar displayed if True

    :return: A pair of a list of packages
    """
    base = base_create(root)
    base.read_all_repos()

    # Only enable repos if ``repos`` is not empty. see
    # :method:`_configure_repos` in :class:`dnf.cli.cli.Cli`.
    if repos:
        for rid, repo in base.repos.iteritems():
            if rid in repos:
                repo.enable()
                repo.gpgcheck = repo.repo_gpgcheck = False
            else:
                repo.disable()

    # see :method:`configure` in :class:`dnf.cli.cli.Cli`.
    base.activate_persistor()

    # see :method:`_configure_repos` in :class:`dnf.cli.cli.Cli`.
    if setup_callbacks:
        (bar, base.ds_callback) = base.output.setup_progress_callbacks()
        base.repos.all.set_progress_bar(bar)
        base.repos.all.confirm_func = base.output._cli_confirm_gpg_key_import

    # It will take some time to get metadata from remote repos.
    # see :method:`run` in :class:`dnf.cli.cli.Cli`.
    base.fill_sack(load_system_repo='auto',
                   load_available_repos=base.repos.enabled())

    if DCCU is None:
        if updateinfo:
            for rid, repo in base.repos.iteritems():
                if repo.enabled:
                    download_updateinfo_xml(repo)

    # see :method:`run` in :class:`dnf.cli.commands.CheckUpdateCommand`.
    ypl = base.returnPkgLists(["updates"])

    del base.ts  # Needed to release RPM DB session ?

    return ypl.updates

# vim:sw=4:ts=4:et:
