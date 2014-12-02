#
# -*- coding: utf-8 -*-
#
# extend rpmkit.updateinfo.main for multiple host analysis.
#
# Copyright (C) 2013, 2014 Satoru SATOH <ssato@redhat.com>
# Copyright (C) 2014 Red Hat, Inc.
# License: GPLv3+
#
from rpmkit.globals import _

import rpmkit.updateinfo.main as RUM
import rpmkit.updateinfo.utils

# It looks available in EPEL for RHELs:
#   https://apps.fedoraproject.org/packages/python-bunch
import bunch
import glob
import itertools
import logging
import operator
import os
import os.path


LOG = logging.getLogger("rpmkit.updateinfo")


def hosts_rpmroot_g(hosts_datadir):
    """
    List system names from assessment datadir.

    This function expects that assessment data (rpm db files) of each hosts are
    found under $host_identity/ in `datadir`, that is,
    `datadir`/<host_identity>/var/lib/rpm/Packages exists. If rpm db file[s]
    are not found for a host, that host will be simply ignored.

    <host_identity> may be a hostname, host id, fqdn or something to
    identify that host.

    :param hosts_datadir: Dir in which rpm db roots of hosts exist
    :return: A generator to yield a tuple,
        (host_identity, host_rpmroot or None)
    """
    for hostdir in glob.glob(os.path.join(hosts_datadir, '*')):
        if rpmkit.updateinfo.utils.check_rpmdb_root(hostdir):
            yield (os.path.basename(hostdir), hostdir)
        else:
            LOG.warn(_("Failed to find RPM DBs under %s"), hostdir)
            yield (os.path.basename(hostdir), None)


def touch(filepath):
    open(filepath, 'w').write()


def prepare(hosts_datadir, workdir=None, repos=[],
            backend=RUM.DEFAULT_BACKEND, backends=RUM.BACKENDS):
    """
    Scan and collect hosts' basic data (installed rpms list, etc.).

    :param hosts_datadir: Dir in which rpm db roots of hosts exist
    :param workdir: Working dir to save results
    :param repos: List of yum repos to get updateinfo data (errata and updtes)
    :param backend: Backend module to use to get updates and errata
    :param backends: Backend list

    :return: A generator to yield a tuple,
        (host_identity, host_rpmroot or None)
    """
    if workdir is None:
        LOG.info(_("Set workdir to hosts_datadir: %s"), hosts_datadir)
        workdir = hosts_datadir
    else:
        if not os.path.exists(workdir):
            LOG.debug(_("Creating working dir: %s"), workdir)
            os.makedirs(workdir)

    for h, root in hosts_rpmroot_g(hosts_datadir):
        hworkdir = os.path.join(workdir, h)
        if not hworkdir:
            os.makedirs(hworkdir)

        if root is None:
            touch(os.path.join(hworkdir, "RPMDB_NOT_AVAILABLE"))
            yield bunch.bunchify(dict(id=h, workdir=hworkdir, available=False))
        else:
            yield RUM.prepare(root, hworkdir, repos, h, backend, backends)


def p2nevra(p):
    """
    :param p: A dict represents package info including N, E, V, R, A
    """
    return operator.itemgetter("name", "epoch", "version", "release",
                               "arch")(p)


def mk_symlinks_to_results_of_ref_host(href, hsrest, curdir=os.curdir):
    """
    :param href: Reference host object
    :param hsrest: A list of hosts having same installed rpms as `href`
    :param curdir: Current dir to go back

    TODO: Ugly code around symlinks ...
    """
    for h in hsrest:
        os.chdir(h.workdir)
        href_workdir = os.path.join('..', href.id)
        for src in glob.glob(os.path.join(href_workdir, '*')):
            dst = os.path.join(href_workdir, os.path.basename(src))
            if not os.path.exists(dst):
                LOG.debug("Symlink from %s to %s", src, dst)
                os.symlink(src, dst)
        os.chdir(curdir)


def main(hosts_datadir, workdir=None, repos=[], score=-1,
         keywords=RUM.ERRATA_KEYWORDS, refdir=None,
         backend=RUM.DEFAULT_BACKEND, backends=RUM.BACKENDS):
    """
    :param hosts_datadir: Dir in which rpm db roots of hosts exist
    :param workdir: Working dir to save results
    :param repos: List of yum repos to get updateinfo data (errata and updtes)
    :param score: CVSS base metrics score
    :param keywords: Keyword list to filter 'important' RHBAs
    :param refdir: A dir holding reference data previously generated to
        compute delta (updates since that data)
    :param backend: Backend module to use to get updates and errata
    :param backends: Backend list
    """
    all_hosts = list(prepare(hosts_datadir, workdir, repos, backend, backends))
    hosts = filter(operator.itemgetter("available"), all_hosts)

    LOG.info(_("Analyze %d hosts (Skipped %d hosts lack valid RPM DBs)"),
             len(hosts), len(all_hosts) - len(hosts))

    ilen = lambda h: len(h.installed)
    hps = lambda h: [p2nevra(p) for p in h.installed]
    gby = lambda xs, kf: itertools.groupby(sorted(xs, key=kf), kf)

    # Group hosts by installed rpms to degenerate. his :: [[[h]]]
    his = [[list(g2) for _k2, g2 in gby(g, hps)] for _k, g in gby(hosts, ilen)]

    for hss in his:
        for hs in hss:
            (h, hsrest) = (hs[0], hs[1:])
            RUM.analyze(h, score, keywords, refdir)

            if hsrest:
                LOG.info(_("Skip to analyze %s as its installed RPMs are "
                           "exactly same as %s's"),
                         ','.join(x.id for x in hsrest), h)
                mk_symlinks_to_results_of_ref_host(h, hsrest, os.curdir)

# vim:sw=4:ts=4:et:
