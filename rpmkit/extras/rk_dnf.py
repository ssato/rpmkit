#
# Copyright (C) 2013, 2014 Red Hat, Inc.
# Author: Satoru SATOH <ssato@redhat.com>
# License: GPLv3+
#
"""Some utility routines utilize DNF/Hawkey.
"""
import dnf.cli.cli
import dnf.exceptions
import dnf.subject
import dnf.transaction
import logging
import os.path


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
    base.fill_sack(load_available_repos=False)

    return base


def base_setup_excludes(base, excludes):
    """
    :param base: An initialized dnf.cli.cli.BaseCli (dnf.base) object
    :param excludes: A list of names or wildcards specifying packages must be
        excluded from the erasure list
    """
    #if excludes:
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
    return base.sack.query().installed().run()


def compute_removed(pkgspecs, root, excludes=[]):
    """
    :param root: RPM DB root dir (relative or absolute)
    :param pkgspecs: A list of names or wildcards specifying packages to erase
    :param excludes: A list of names or wildcards specifying packages must be
        excluded from the erasure list

    :return: A pair of a list of name of packages to be excluded and removed
    """
    base = base_create(root)
    base.goal_parameters.allow_uninstall = True

    base_setup_excludes(base, excludes)

    removes = []
    for pspec in pkgspecs:
        try:
            base.remove(pspec)
            _transaction = base.resolve()
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

# vim:sw=4:ts=4:et:
