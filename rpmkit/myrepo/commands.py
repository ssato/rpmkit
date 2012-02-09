#
# Copyright (C) 2011 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato@redhat.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
import rpmkit.myrepo.repoops as RO
import rpmkit.myrepo.shell as SH

import glob
import logging
import os
import os.path
import subprocess


def build(repo, srpm):
    return SH.prun(repo.build_cmds(srpm))


def update(repo):
    """'createrepo --update ...', etc.
    """
    destdir = repo.destdir()

    # hack: degenerate noarch rpms
    if repo.multiarch:
        c = "for d in %s; do (cd $d && ln -sf ../%s/*.noarch.rpm ./); done"
        c = c % (" ".join(repo.archs[1:]), repo.primary_arch)

        SH.run(c, repo.user, repo.server, destdir, timeout=repo.timeout)

    c = "test -d repodata"
    c += " && createrepo --update --deltas --oldpackagedirs . --database ."
    c += " || createrepo --deltas --oldpackagedirs . --database ."

    cs = [
        SH.ThreadedCommand(c, repo.user, repo.server, d, timeout=repo.timeout)
            for d in rpmdirs(repo, destdir)
    ]

    return SH.prun(cs)


def deploy(repo, srpm, build=True):
    """
    FIXME: ugly code around signkey check.
    """
    if build:
        assert all(rc == 0 for rc in build(repo, srpm))

    destdir = repo.destdir()
    rpms_to_deploy = []   # :: [(rpm_path, destdir)]
    rpms_to_sign = []

    for d in dists_by_srpm(repo, srpm):
        srpm_to_copy = glob.glob("%s/*.src.rpm" % d.mockdir())[0]
        rpms_to_deploy.append((srpm_to_copy, os.path.join(destdir, "sources")))

        brpms = [
            f for f in glob.glob("%s/*.*.rpm" % d.mockdir())\
                if not f.endswith(".src.rpm")
        ]
        logging.debug("rpms=" + str([os.path.basename(f) for f in brpms]))

        for p in brpms:
            rpms_to_deploy.append((p, os.path.join(destdir, d.arch)))

        rpms_to_sign += brpms

    if repo.signkey:
        c = sign_rpms_cmd(repo.signkey, rpms_to_sign)
        subprocess.check_call(c, shell=True)

    cs = [
        SH.ThreadedCommand(repo.copy_cmd(rpm, dest), timeout=repo.timeout) \
            for rpm, dest in rpms_to_deploy
    ]
    assert all(rc == 0 for rc in SH.prun(cs))

    return update(repo)


def init(repo):
    """Initialize yum repository.
    """
    rc = SH.run(
        "mkdir -p " + " ".join(rpmdirs(repo, repo.destdir())),
        repo.user, repo.server,
        timeout=repo.timeout
    )

    return RO.deploy_release_rpm(repo)


# vim:sw=4 ts=4 et:
