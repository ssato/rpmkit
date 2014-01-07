#
# Copyright (C) 2014 Red Hat, Inc.
# Author: Satoru SATOH <ssato@redhat.com>
# License: GPLv3+
#
from __future__ import print_function
from logging import DEBUG, INFO

import rpmkit.rpmutils as RR
import rpmkit.utils as RU
import rpmkit.globals as G

import anyconfig
import anyconfig.utils as AU
import bunch
import logging
import optparse
import os.path
import sys


_DATA_0 = anyconfig.container()


def load_profiles(profilesdir, data=_DATA_0,
                  merge_strategy=anyconfig.MS_DICTS_AND_LISTS):
    """
    :param profiles:
    """
    ps = os.path.join(profilesdir, "*.yml")
    diff = anyconfig.load(ps, merge=merge_strategy)

    if diff:
        if data:
            data.update(diff)
        else:
            data = diff

    return data


def parse_install_pred(pexp, system_profile={}, fallback=None):
    """
    FIXME: Implement real parser instead of 'eval' call.

    >>> parse_install_pred("always")
    True
    >>> parse_install_pred("never")
    False
    >>> prof = bunch.bunchify(dict(hardware=dict(is_numa=True, ),
    ...                            services=dict(enabled=["sshd"],
    ...                                          disabled=["snmpd"]),
    ...                            ))
    >>> parse_install_pred("hardware.is_numa", prof)
    True
    >>> pexp = ("'snmpd' in services.enabled or 'snmpd' not in "
    ...         "services.disabled")
    >>> parse_install_pred(pexp, prof)
    False
    """
    if not pexp:
        return fallback

    pexp = str(pexp).lower()

    if pexp in ("always", 1, "1", "true", "yes"):
        return True
    elif pexp in ("never", 0, "0", "false", "no"):
        return False
    else:
        try:
            return eval(pexp, system_profile)  # FIXME: Unsafe.
        except (NameError, SyntaxError) as e:
            return fallback


def load_package_groups_data_g(paths=[], data=_DATA_0,
                               profkey="system_profile"):
    """
    :param paths: A list of package group data dirs
    """
    sysprof = bunch.bunchify(data.get(profkey, {}))

    for path in paths:
        logging.debug("Loading profiles from: " + path)
        pgdata = load_profiles(path)

        for grp in pgdata.get("groups", []):
            instif = grp.get("install_if", '')
            grp["install_if"] = parse_install_pred(instif, sysprof, True)
            logging.debug("install_if: %s -> %s" % (instif, grp["install_if"]))

            # TODO: Is 'type' of the packages (mandatory | default | optional)
            # to be checked?
            inst_pkgs = RU.uniq2(p["name"] for p in grp.get("packages", [])
                                 if grp["install_if"])
            uninst_pkgs = RU.uniq2(p["name"] for p in grp.get("packages", [])
                                   if not grp["install_if"])
            grp["install_pkgs"] = inst_pkgs
            grp["remove_pkgs"] = uninst_pkgs

            yield grp


# e.g. /etc/rpmkit/optimizer.d/{default, server, www_server, kvm_host}
_SYS_PROFILES_TOPDIR = os.path.join(G.RPMKIT_SYSCONFDIR, "optimizer.d")
_SYS_PROFILES_DIR_DEFAULT = os.path.join(_SYS_PROFILES_TOPDIR, "default")

# e.g. /usr/share/rpmkit/optimizer/pgroups.d/{default, ...}
_GRP_PKGS_TOPDIR = os.path.join(G.RPMKIT_DATADIR, "optimizer/pgroups.d")
_GRP_PKGS_DIR_DEFAULT = os.path.join(_GRP_PKGS_TOPDIR, "default")


def init_ppaths_and_gpaths(ppaths=[os.curdir, _SYS_PROFILES_DIR_DEFAULT],
                           gpaths=[os.curdir, _GRP_PKGS_DIR_DEFAULT]):
    """
    Initialize a couple of lists of search paths of profiles and RPM
    package groups.

    :param ppaths: A list of search paths of profiles data
    :param gpaths: A list of search paths of package groups data
    """
    return (ppaths, gpaths)


## Plan:
# 1. load system/site-specific profile data
# 2. load package groups files and:
#    a. make up a list of necessary (kept) RPMs from ref. -> excludes list
#    b. make up a list of remove candidates from ref.
# 3. Make up a list of installed RPMs
# 4. optimize the list of installed RPMs:
#    a. find standadlones also in remove candidates
#    b. try remove candidates and filter our RPMs
#       ...
#


def make_excl_packages_list(ppaths, gpaths, profkey="system_profile"):
    """
    :param ppaths: A list of profile data dirs
    :param gpaths: A list of package group data dirs
    """
    (ppaths, gpaths) = init_ppaths_and_gpaths(ppaths, gpaths)

    prof_data = _DATA_0
    for ppath in ppaths:
        prof_data = load_profiles(ppath, prof_data)

    pgrps = list(load_package_groups_data_g(gpaths, {profkey: prof_data}))

    excludes = RU.uconcat(g["install_pkgs"] for g in pgrps)
    removes = RU.uconcat(g["remove_pkgs"] for g in pgrps)

    logging.info("Excldues: %d, Removes: %d" % (len(excludes), len(removes)))

    return (excludes, removes)


_USAGE = """\
%prog [OPTION ...] HOST_PROF_SPEC

Arguments:
  HOST_PROF_SPEC  host profile data file path or dir having that files

Examples:
  %prog -R ./rhel-6-client-1 -P /etc/rpmkit/optimizer.d/default \\
      -G /usr/share/rpmkit/pgroups.d/default \\
      ./rhel-6-client-1/prof_spec.yml"""


def option_parser(usage=_USAGE):
    defaults = dict(verbose=False, root='/', output=None, ppaths=[], gpaths=[])

    p = optparse.OptionParser(usage)
    p.set_defaults(**defaults)

    p.add_option("-R", "--root",
                 help="Relative or absolute path to root dir where "
                      "var/lib/rpm exists. [/]")
    p.add_option("-o", "--output", help="Output file path [stdout]")
    p.add_option("-P", "--ppaths", action="append",
                 help="List of host profile paths [%default]. "
                      "It is possible to specify this option multiple "
                      "times (data files will be loaded in that order).")
    p.add_option("-G", "--gpaths", action="append",
                 help="List of package groups data paths [%default]. "
                      "It is possible to specify this option multiple "
                      "times (data files will be loaded in that order).")
    p.add_option("-v", "--verbose", action="store_true", help="Verbose mode")

    return p


def main():
    p = option_parser()
    (options, args) = p.parse_args()

    RU.init_log(DEBUG if options.verbose else INFO)

    if not args:
        p.print_usage()
        sys.exit(1)

    host_prof_specs = args[0]

    root = os.path.abspath(options.root)
    all_rpms = [p["name"] for p in RR.list_installed_rpms(root)]

    (excludes, removes) = make_excl_packages_list(options.ppaths, options.gpaths)
    remove_candidates = RU.select_from_list(removes, all_rpms)

    xs = RR.compute_removed(remove_candidates, root, excludes=excludes)
    data = dict(removed=xs, excludes=excludes)

    output = open(options.output, 'w') if options.output else sys.stdout

    if options.output:
        anyconfig.dump(dict(data=data, ), options.output, forced_type="yaml")
    else:
        res = anyconfig.dumps(dict(data=data, ), forced_type="yaml")
        print(res)

if __name__ == "__main__":
    main()

# vim:sw=4:ts=4:et:
