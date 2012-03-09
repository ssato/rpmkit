#
# Copyright (C) 2011, 2012 Red Hat, Inc.
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
import rpmkit.shell as SH

import glob
import logging
import os
import os.path
import subprocess
import tempfile


def __setup_workdir(prefix, topdir="/tmp"):
    return tempfile.mkdtemp(dir=topdir, prefix=prefix)


def build(repo, srpm):
    return RO.build(repo, srpm)


def update(repo):
    """Update and synchronize repository's metadata.
    """
    return repo.update_metadata()


def deploy(repo, srpm, build_=True):
    """
    FIXME: ugly code around signkey check.
    """
    if build_:
        assert all(rc == 0 for rc in build(repo, srpm))

    destdir = repo.destdir()
    rpms_to_deploy = []  # :: [(rpm_path, destdir)]
    rpms_to_sign = []

    for d in RO.dists_by_srpm(repo, srpm):
        rpmdir = d.rpmdir()

        srpms_to_copy = glob.glob(rpmdir + "/*.src.rpm")
        assert srpms_to_copy, "Could not find src.rpm in " + rpmdir

        srpm_to_copy = srpms_to_copy[0]
        rpms_to_deploy.append((srpm_to_copy, os.path.join(destdir, "sources")))

        brpms = [
            f for f in glob.glob(rpmdir + "/*.rpm") \
                if not f.endswith(".src.rpm")
        ]
        logging.debug("rpms=" + str([os.path.basename(f) for f in brpms]))

        for p in brpms:
            rpms_to_deploy.append((p, os.path.join(destdir, d.arch)))

        rpms_to_sign += brpms

    if repo.signkey:
        c = sign_rpms_cmd(repo.signkey, rpms_to_sign)
        subprocess.check_call(c, shell=True)

    tasks = [
        SH.Task(
            RO.copy_cmd(repo, rpm, dest), timeout=repo.timeout
        ) for rpm, dest in rpms_to_deploy
    ]
    rcs = SH.prun(tasks)
    assert all(rc == 0 for rc in rcs), "results=" + str(rcs)

    rcs = update(repo)
    assert all(rc == 0 for rc in rcs), "results=" + str(rcs)

    return 0


def init(repo):
    """Initialize yum repository.
    """
    rc = SH.run(
        "mkdir -p " + " ".join(repo.rpmdirs()), repo.user, repo.server,
        timeout=repo.timeout,
    )
    
    if repo.genconf and rc == 0:
        rc = genconf(repo)

    return rc


def genconf(repo):
    workdir = __setup_workdir("myrepo_" + repo.name + "-release-")

    srpms = [
        RO.build_release_srpm(repo, workdir),
        RO.build_mock_cfg_srpm(repo, workdir)
    ]

    assert len(srpms) == 2, "Failed to make release and/or mock.cfg SRPMs"

    for srpm in srpms:
        deploy(repo, srpm, True)

    return 0


# vim:sw=4 ts=4 et:
