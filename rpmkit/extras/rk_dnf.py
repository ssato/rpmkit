#
# Copyright (C) 2013, 2014 Red Hat, Inc.
# Author: Satoru SATOH <ssato@redhat.com>
# License: GPLv3+
#
"""Some utility routines utilize DNF/Hawkey.
"""
from __future__ import print_function
from dnf.i18n import _, ucd
from dnf.repo import _subst2tuples

import dnf.base
# import dnf.conf.read  # It exists in git but not available in
                        # dnf-0.5.4-2.fc20.noarch
import dnf.cli.cli
import dnf.exceptions
import dnf.repo
import dnf.subject
import dnf.transaction
import functools
import glob
import librepo
import logging
import os.path
import shutil
import tempfile


# Inherit and extend some classes in dnf to support updateinfo.
#
# This is required to get support updateinfo in dnf until patches in the
# following pull request is merged:
#   https://github.com/akozumpl/dnf/pull/143/files
#
class _Handle(dnf.repo._Handle):

    def __init__(self, gpgcheck, max_mirror_tries):
        super(_Handle, self).__init__(gpgcheck, max_mirror_tries)
        self.yumdlist.append("updateinfo")


class Metadata(dnf.repo.Metadata):

    @property
    def updateinfo_fn(self):
        return self.repo_dct.get('updateinfo')


class Repo(dnf.repo.Repo):

    def _handle_load(self, handle):
        """
        Extended version of dnf.repo.Repo._handle_load to make and return an
        instance of the above :class:`Metadata` instead of :class:`.

        (Actually, I just copied the original w/o any modifications.)
        """
        if handle.progresscb:
            self._md_pload.start(self.name)
        result = handle.perform()
        if handle.progresscb:
            self._md_pload.end()
        return Metadata(result, handle)

    def _handle_new_local(self, destdir):
        """Likewise."""
        return _Handle.new_local(self.substitutions, self.repo_gpgcheck,
                                 self.max_mirror_tries, destdir)

    def _handle_new_remote(self, destdir, mirror_setup=True):
        """Likewise."""
        h = _Handle(self.repo_gpgcheck, self.max_mirror_tries)
        h.varsub = _subst2tuples(self.substitutions)
        h.destdir = destdir
        self._set_ip_resolve(h)

        # setup mirror URLs
        mirrorlist = self.metalink or self.mirrorlist
        if mirrorlist:
            if mirror_setup:
                h.setopt(librepo.LRO_MIRRORLIST, mirrorlist)
                h.setopt(librepo.LRO_FASTESTMIRROR, self.fastestmirror)
                h.setopt(librepo.LRO_FASTESTMIRRORCACHE,
                         os.path.join(self.basecachedir, 'fastestmirror.cache'))
            else:
                # use already resolved mirror list
                h.setopt(librepo.LRO_URLS, self.metadata.mirrors)
        elif self.baseurl:
            h.setopt(librepo.LRO_URLS, self.baseurl)
        else:
            msg = 'Cannot find a valid baseurl for repo: %s' % self.id
            raise dnf.exceptions.RepoError(msg)

        # setup download progress
        h.progresscb = self._md_pload._progress_cb
        self._md_pload.fm_running = False
        h.fastestmirrorcb = self._md_pload._fastestmirror_cb

        # apply repo options
        h.maxspeed = self.throttle if type(self.throttle) is int \
                     else int(self.bandwidth * self.throttle)
        h.proxy = self.proxy
        h.sslverifypeer = h.sslverifyhost = self.sslverify

        return h

    @property
    def updateinfo_fn(self):
        """Added property."""
        return self.metadata.updateinfo_fn


class BaseCli(dnf.cli.cli.BaseCli):
    """
    Extend to override some methods in :class:`dnf.base.Base`, base class
    of :class:`dnf.cli.cli.BaseCli`, to utilize some classes above instead
    of original ones.
    """

    def _add_repo_to_sack(self, name):
        repo = self.repos[name]
        try:
            repo.load()
        except dnf.exceptions.RepoError as e:
            if repo.skip_if_unavailable is False:
                raise
            self.logger.warning(_("%s, disabling."), e)
            repo.disable()
            return
        hrepo = repo.hawkey_repo
        hrepo.repomd_fn = repo.repomd_fn
        hrepo.primary_fn = repo.primary_fn
        hrepo.filelists_fn = repo.filelists_fn
        hrepo.cost = repo.cost
        if repo.presto_fn:
            hrepo.presto_fn = repo.presto_fn
        else:
            self.logger.debug("not found deltainfo for: %s" % repo.name)

        # Added to load updateinfo metadata.
        if repo.updateinfo_fn:
            hrepo.updateinfo_fn = repo.updateinfo_fn
        else:
            self.logger.debug("not found updateinfo for: %s" % repo.name)
        repo.hawkey_repo = hrepo
        self._sack.load_yum_repo(hrepo, build_cache=True, load_filelists=True,
                                 load_presto=repo.deltarpm,
                                 load_updateinfo=bool(repo.updateinfo_fn))

    def readRepoConfig(self, parser, section):
        repo = Repo(section, self.conf.cachedir)  # Changed: s/dnf.repo.Repo/Repo/
        try:
            repo.populate(parser, section, self.conf)
        except ValueError as e:
            msg = _('Repository %r: Error parsing config: %s' % (section, e))
            raise dnf.exceptions.ConfigError(msg)

        # Ensure that the repo name is set
        if not repo.name:
            repo.name = section
            self.logger.error(_('Repository %r is missing name in configuration, '
                    'using id') % section)
        repo.name = ucd(repo.name)

        repo.substitutions.update(self.conf.substitutions)
        repo.cfg = parser

        return repo


def base_create(root):
    """
    Create and initialize dnf.base object.

    :param root: RPM DB root dir
    :return: A Base object (see above)
    """
    base = BaseCli()

    if root != '/':
        base.conf.installroot = base.conf.cachedir = os.path.abspath(root)

    base.conf.clean_requirements_on_remove = True

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
    NOTE: This code is a quick and dirty hack.

    see also:
        * https://github.com/akozumpl/dnf/pull/143
        * rhbz#850912 RFE: support updateinfo:
        * rhbz#1101029: [rfe][plugins] yum-plugin-security (list-sec) or ...
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
    updixml_new = os.path.join(repo.cachedir, "repodata",
                               os.path.basename(updixml))
    shutil.move(updixml, updixml_new)
    shutil.rmtree(tmpdir)

    return updixml_new


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


def base_fill_sack(root, repos=[], setup_callbacks=False):
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
    return base


def compute_updates(root, repos=[], setup_callbacks=False):
    """
    :param root: RPM DB root dir (relative or absolute)
    :param repos: A list of repos to enable or []. [] means that all available
        system repos to be enabled.
    :param setup_callbacks: Setup callbacks and progress bar displayed if True

    :return: A pair of a list of packages
    """
    base = base_fill_sack(root, repos, setup_callbacks)

    # see :method:`run` in :class:`dnf.cli.commands.CheckUpdateCommand`.
    ypl = base.returnPkgLists(["updates"])

    del base.ts  # Needed to release RPM DB session ?

    return ypl.updates

# vim:sw=4:ts=4:et:
