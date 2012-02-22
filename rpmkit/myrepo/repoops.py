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
import rpmkit.myrepo.shell as SH
import rpmkit.myrepo.utils as U
import rpmkit.rpmutils as RU

import glob
import logging
import os
import os.path
import tempfile


# timeouts:
(BUILD_TIMEOUT, MIN_TIMEOUT) = (60 * 10, 5)  # [sec]


def dists_by_srpm(repo, srpm):
    return repo.dists[:1] if RU.is_noarch(srpm) else repo.dists


def mock_cfg_content(repo, dist):
    """
    Updated mock.cfg with addingg repository definitions in
    given content and returns it.

    :param repo:  Repo object
    :param dist:  Distribution object
    """
    cfg_opts = dist.mockcfg_opts()
    repo_defs = U.compile_template("release_file", repo.as_dict())

    cfg_opts["root"] = "%s-%s" % (repo.name, dist.label)
    cfg_opts["myrepo_distname"] = dist.name
    cfg_opts["yum.conf"] += "\n\n" + repo_defs

    context = {"cfg": cfg_opts}

    return U.compile_template("mock.cfg", context)


def sign_rpms_cmd(keyid, rpms):
    """
    TODO: It might ask user about the gpg passphrase everytime this method is
    called.  How to store the passphrase or streamline that with gpg-agent ?

    :param keyid:  GPG Key ID to sign with :: str
    :param rpms:  RPM file path list :: [str]
    """
    return U.compile_template("sign_rpms", {"keyid": keyid, "rpms": rpms})


def copy_cmd(repo, src, dst):
    if U.is_local(repo.server):
        if "~" in dst:
            dst = os.path.expanduser(dst)

        cmd = "cp -a %s %s" % (src, dst)
    else:
        cmd = "scp -p %s %s@%s:%s" % (src, repo.user, repo.server, dst)

    return cmd


def mock_cfg_gen(repo, workdir):
    """Generate mock.cfg files and corresponding RPMs.
    """
    mockcfgdir = os.path.join(workdir, "etc", "mock")
    os.makedirs(mockcfgdir)

    files = []

    for dist in repo.dists:
        mc = mock_cfg_content(repo, dist)
        mock_cfg_path = os.path.join(
            mockcfgdir, "%s-%s.cfg" % (repo.name, dist.label)
        )

        open(mock_cfg_path, "w").write(mc)

        files.append(mock_cfg_path)

    return files


def release_rpm_build_cmd(repo, workdir, release_file_path):
    logopt = logging.getLogger().level < logging.INFO and "--verbose" or ""

    context = repo.as_dict()
    context.update({
        "release_file": release_file_path,
        "workdir": workdir,
        "logopt": logopt,
        "release_file_list": os.path.join(workdir, "files.list"),
    })

    return U.compile_template("release_file_build", context)


def mock_cfg_rpm_build_cmd(repo, workdir, mock_cfg_file_list_path):
    context = repo.as_dict()
    context.update({
        "workdir": workdir,
        "mock_cfg_file_list": mock_cfg_file_list_path
    })

    return U.compile_template("mock_cfg_build", context)


def build_cmds(repo, srpm):
    return [
        SH.ThreadedCommand(d.build_cmd(srpm), timeout=repo.timeout) \
            for d in dists_by_srpm(repo, srpm)
    ]


def settup_workdir(prefix, topdir="/tmp"):
    return tempfile.mkdtemp(dir=topdir, prefix=prefix)


def build_mock_cfg_srpm(repo, workdir):
    """Generate mock.cfg files and corresponding RPMs.
    """
    mockcfgdir = os.path.join(workdir, "etc", "mock")
    os.makedirs(mockcfgdir)

    mock_cfg_files = []

    for dist in repo.dists:
        mc = mock_cfg_content(repo, dist)
        mock_cfg_path = os.path.join(
            mockcfgdir, "%s-%s.cfg" % (repo.name, dist.label)
        )

        open(mock_cfg_path, "w").write(mc)

        mock_cfg_files.append(mock_cfg_path)

    listfile_path = os.path.join(workdir, "mockcfg.files.list")
    open(listfile_path, "w").write(
        "\n".join(
            "%s,rpmattr=%%config(noreplace)" % mcfg \
                for mcfg in mock_cfg_files) + "\n"
    )

    rc = SH.run(
        mock_cfg_rpm_build_cmd(repo, workdir, listfile_path),
        repo.user,
        timeout=BUILD_TIMEOUT
    )
    if rc != 0:
        raise RuntimeError("Failed to create mock.cfg rpm")

    srpms = glob.glob(
        "%(wdir)s/mock-data-%(repo)s-%(dver)s/mock-data-*.src.rpm" % \
            {"wdir": workdir, "repo": repo.name, "dver": repo.distversion}
    )
    if not srpms:
        raise RuntimeError("Failed to build src.rpm")

    return srpms[0]


def build_release_srpm(repo, workdir):
    """Generate (yum repo) release package.

    @workdir str   Working directory
    """
    reldir = os.path.join(workdir, "etc", "yum.repos.d")
    os.makedirs(reldir)

    release_file_path = os.path.join(reldir, "%s.repo" % repo.name)
    rfc = U.compile_template("release_file", repo.as_dict())

    open(release_file_path, 'w').write(rfc)

    if repo.signkey:
        keydir = os.path.join(workdir, repo.keydir[1:])
        os.makedirs(keydir)

        rc = SH.run(
            "gpg --export --armor %s > ./%s" % (repo.signkey, repo.keyfile),
            workdir=workdir,
            timeout=MIN_TIMEOUT,
        )

        release_file_list = os.path.join(workdir, "files.list")
        open(release_file_list, "w").write(
            release_file_path + ",rpmattr=%config\n" + workdir + \
                repo.keyfile + "\n"
        )

    rc = SH.run(
        release_rpm_build_cmd(repo, workdir, release_file_path),
        repo.user,
        timeout=BUILD_TIMEOUT
    )

    srpms = glob.glob(
        "%s/%s-release-%s/%s-release*.src.rpm" % \
            (workdir, repo.name, repo.distversion, repo.name)
    )
    if not srpms:
        raise RuntimeError("Failed to build src.rpm")

    return srpms[0]


# vim:sw=4 ts=4 et:
