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
import rpmkit.myrepo.globals as G
import rpmkit.myrepo.shell as SH
import rpmkit.myrepo.utils as U
import rpmkit.memoize as M
import rpmkit.rpmutils as RU

import glob
import logging
import os
import os.path


def dists_by_srpm(repo, srpm):
    is_noarch = RU.is_noarch(srpm)
    logging.info("srpm=%s, noarch=%s" % (srpm, is_noarch))

    return repo.dists[:1] if is_noarch else repo.dists


@M.memoize
def release_file_content(repo):
    return U.compile_template("release_file", repo.as_dict())


def mock_cfg_content(repo, dist):
    """
    Updated mock.cfg with addingg repository definitions in
    given content and returns it.

    :param repo:  Repo object
    :param dist:  Distribution object
    """
    cfg_opts = dist.load_mockcfg_config_opts()

    cfg_opts["root"] = "%s-%s" % (repo.name, dist.label)
    cfg_opts["myrepo_distname"] = dist.name
    cfg_opts["yum.conf"] += "\n" + release_file_content(repo)

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


def release_file_gen(repo, workdir):
    """Generate release file (repo file) and returns its path.
    """
    reldir = os.path.join(workdir, "etc", "yum.repos.d")
    os.makedirs(reldir)

    relpath = os.path.join(reldir, repo.name + ".repo")

    open(relpath, 'w').write(release_file_content(repo))  # may throw IOError.
    return relpath


def mock_cfg_gen_g(repo, workdir):
    """Generate mock.cfg file and yield its path.
    """
    mockcfgdir = os.path.join(workdir, "etc", "mock")
    os.makedirs(mockcfgdir)

    for dist in repo.dists:
        mc = mock_cfg_content(repo, dist)
        mcpath = os.path.join(
            mockcfgdir, "%s-%s.cfg" % (repo.name, dist.label)
        )
        open(mcpath, "w").write(mc)  # may throw IOError.

        yield mcpath


def mock_cfg_gen(repo, workdir):
    """Generate mock.cfg files and returns these paths.
    """
    return [p for p in mock_cfg_gen_g(repo, workdir)]


def rpm_build_cmd(repo, workdir, listfile, pname):
    logopt = logging.getLogger().level < logging.INFO and "--verbose" or ""

    context = repo.as_dict()
    context.update({
        "workdir": workdir, "logopt": logopt, "listfile": listfile,
        "pkgname": pname,
    })

    return U.compile_template("rpmbuild", context)


def build_cmds(repo, srpm):
    return [
        SH.ThreadedCommand(d.build_cmd(srpm), timeout=repo.timeout) \
            for d in dists_by_srpm(repo, srpm)
    ]


def build_mock_cfg_srpm(repo, workdir):
    """Generate mock.cfg files and corresponding RPMs.
    """
    mcfiles = mock_cfg_gen(repo, workdir)
    c = "\n".join(
        mc + ",rpmattr=%config(noreplace)" for mc in mcfiles
    ) + "\n"

    listfile = os.path.join(workdir, "mockcfg.files.list")
    open(listfile, "w").write(c)

    pname = "mock-data-" + repo.name

    rc = SH.run(
        rpm_build_cmd(repo, workdir, listfile, pname),
        repo.user,
        timeout=G.BUILD_TIMEOUT
    )
    if rc != 0:
        raise RuntimeError("Failed to create mock.cfg rpm")

    pattern = "%(wdir)s/mock-data-%(repo)s-%(dver)s/mock-data-*.src.rpm" % \
        {"wdir": workdir, "repo": repo.name, "dver": repo.distversion}
    srpms = glob.glob(pattern)

    if not srpms:
        raise RuntimeError("Failed to build src.rpm. pattern=" + pattern)

    return srpms[0]


def build_release_srpm(repo, workdir):
    """Generate (yum repo) release package.

    :param repo: Repository object
    :param workdir: Working directory in which build rpms
    """
    relpath = release_file_gen(repo, workdir)
    c = relpath + ",rpmattr=%config\n"

    if repo.signkey:
        keydir = os.path.join(workdir, repo.keydir[1:])
        os.makedirs(keydir)

        rc = SH.run(
            "gpg --export --armor %s > ./%s" % (repo.signkey, repo.keyfile),
            workdir=workdir,
            timeout=G.MIN_TIMEOUT,
        )
        c += workdir + repo.keyfile + "\n"

    listfile = os.path.join(workdir, "release.files.list")
    open(listfile, "w").write(c)

    pname = repo.name + "-release"

    rc = SH.run(
        rpm_build_cmd(repo, workdir, listfile, pname),
        repo.user,
        timeout=G.BUILD_TIMEOUT
    )

    pattern = "%s/%s-release-%s/%s-release*.src.rpm" % \
        (workdir, repo.name, repo.distversion, repo.name)
    srpms = glob.glob(pattern)

    if not srpms:
        raise RuntimeError("Failed to build src.rpm. pattern=" + pattern)

    return srpms[0]


# vim:sw=4 ts=4 et:
