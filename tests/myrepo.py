#! /usr/bin/python
#
# Tests for myrepo.py
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
# Requirements: createrepo, ssh, packagemaker (see below)
#
import copy
import doctest
import logging
import optparse
import os
import os.path
import shlex
import sys
import tempfile
import unittest

pkgdir = os.path.abspath(os.path.join(os.path.dirname(sys.argv[0]), "../"))
print "# path=" + pkgdir
sys.path.append(pkgdir)

from rpmkit.myrepo import *


TEST_CHOICES = (TEST_BASIC, TEST_FULL) = ("basic", "full")
TEST_RHOSTS = ("192.168.122.1", "127.0.0.1")


@memoize
def find_accessible_remote_host(user=None, rhosts=TEST_RHOSTS):
    if user is None:
        user = get_username()

    def check_cmd(uesr, rhost):
        c = "ping -q -c 1 -w 1 %s > /dev/null 2> /dev/null" % rhost
        c += " && ssh %s@%s -o ConnectTimeout=5 true >/dev/null 2>/dev/null" \
            % (user, rhost)

        return ThrdCommand(c, user, timeout=5, stop_on_failure=False)

    checks = [check_cmd(user, rhost) for rhost in rhosts]
    for rhost in rhosts:
        rc = check_cmd(user, rhost).run()
        if rc == 0:
            return  rhost

    return None


class TestThrdCommand(unittest.TestCase):

    def run_ok(self, cmd, rc_expected=0, out_expected="", err_expected=""):
        """Helper method.

        @cmd  ThrdCommand object
        """
        rc = cmd.run()

        self.assertEquals(rc, rc_expected)

    def test_run_minimal_args(self):
        cmd = "true"
        c = ThrdCommand(cmd)

        self.run_ok(c)

    def test_run_max_args(self):
        cmd = "true"
        c = ThrdCommand(
            cmd, get_username(), "localhost", os.curdir, True, None
        )

        self.run_ok(c)

    def test_run_max_kwargs(self):
        cmd = "true"
        c = ThrdCommand(cmd, user=get_username(), host="localhost",
            workdir=os.curdir, stop_on_failure=True, timeout=None)

        self.run_ok(c)

    def test_run_timeout(self):
        cmd = "sleep 10"
        c = ThrdCommand(cmd, stop_on_failure=False, timeout=1)

        rc = c.run()

        self.assertFalse(rc == 0)


class TestMemoizedFuncs(unittest.TestCase):
    """
    Doctests in memoized functions and methods are not run as these are
    rewritten by memoize decorator. So tests of these must be re-defined as
    this.
    """

    _multiprocess_can_split_ = True

    def test_memoize(self):
        fun_0 = lambda a: a * 2
        memoized_fun_0 = memoize(fun_0)

        self.assertEquals(fun_0(2), memoized_fun_0(2))
        self.assertEquals(memoized_fun_0(3), memoized_fun_0(3))

    def test_list_archs(self):
        """list_archs() depends on platform.machine() which returns read-only
        system dependent value so full covered test is almost impossible.

        Tests here covers some limited cases.
        """
        self.assertListEqual(list_archs("i586"), ["i386"])
        self.assertListEqual(list_archs("i686"), ["i386"])
        self.assertListEqual(list_archs("x86_64"), ["x86_64", "i386"])

    def test_list_dists(self):
        """TODO: write tests
        """
        pass

    def test_is_git_available(self):
        """TODO: write tests
        """
        pass

    def test_hostname(self):
        self.assertEquals(
            hostname(), subprocess.check_output("hostname").rstrip()
        )

    def test_username(self):
        self.assertEquals(
            get_username(),
            subprocess.check_output("id -un", shell=True).rstrip()
        )

    def test_get_email(self):
        """TODO: write tests
        """
        pass

    def test_get_fullname(self):
        """TODO: write tests
        """
        pass

    def test_get_distribution(self):
        """TODO: write tests
        """
        pass


class TestMiscFuncs(unittest.TestCase):

    _multiprocess_can_split_ = True

    is_ssh_host_available = False

    def setUp(self):
        self.workdir = tempfile.mkdtemp(dir="/tmp", prefix="myrepo-tests")

    def tearDown(self):
        rm_rf(self.workdir)

    def test_rm_rf_twice(self):
        d = self.workdir

        rm_rf(d)
        rm_rf(d)

    def test_rm_rf_dirs(self):
        d = self.workdir

        for c in "abc":
            os.makedirs(os.path.join(d, c))

        os.makedirs(os.path.join(d, "c", "d"))

        open(os.path.join(d, 'x'), "w").write("test")
        open(os.path.join(d, 'a', 'y'), "w").write("test")
        open(os.path.join(d, 'c', 'd', 'z'), "w").write("test")

        rm_rf(d)


class TestDistribution(unittest.TestCase):

    _multiprocess_can_split_ = True

    def setUp(self):
        self.workdir = tempfile.mkdtemp(dir="/tmp", prefix="myrepo-tests")

    def tearDown(self):
        rm_rf(self.workdir)

    def test__init__(self):
        d = Distribution("fedora-14", "x86_64")

        self.assertEquals(d.name, "fedora")
        self.assertEquals(d.version, "14")
        self.assertEquals(d.arch, "x86_64")
        self.assertEquals(d.label, "fedora-14-x86_64")
        self.assertEquals(d.bdist_label, d.label)

    def test__init__2(self):
        d = Distribution("fedora-xyz-variant-14", "i386")

        self.assertEquals(d.name, "fedora-xyz-variant")
        self.assertEquals(d.version, "14")
        self.assertEquals(d.arch, "i386")
        self.assertEquals(d.label, "fedora-xyz-variant-14-i386")
        self.assertEquals(d.bdist_label, d.label)

    def test__init__3(self):
        d = Distribution("fedora-14", "x86_64", "fedora-xyz-variant-14-x86_64")

        self.assertEquals(d.name, "fedora")
        self.assertEquals(d.version, "14")
        self.assertEquals(d.arch, "x86_64")
        self.assertEquals(d.label, "fedora-14-x86_64")
        self.assertEquals(d.bdist_label, "fedora-xyz-variant-14-x86_64")

    def test_mockdir(self):
        d = Distribution("fedora-14", "x86_64")

        self.assertEquals(d.mockdir(), "/var/lib/mock/fedora-14-x86_64/result")

    def test_mockcfg(self):
        d = Distribution("fedora-14", "x86_64")

        self.assertEquals(d.mockcfg(), "/etc/mock/fedora-14-x86_64.cfg")

    def test_build_cmd(self):
        dn = "fedora-16"
        arch = "x86_64"
        srpm = "python-virtinst-0.500.5-1.fc16.src.rpm"

        d = Distribution(dn, arch)

        logging.getLogger().setLevel(logging.WARNING)
        c = d.build_cmd(srpm)
        cref = "mock -r %s-%s %s > /dev/null 2> /dev/null" % (dn, arch, srpm)
        self.assertEquals(c, cref)

        logging.getLogger().setLevel(logging.INFO)
        c = d.build_cmd(srpm)
        cref = "mock -r %s-%s %s" % (dn, arch, srpm)
        self.assertEquals(c, cref)

    def test_arch_pattern(self):
        d = Distribution("fedora-14", "x86_64")
        self.assertEquals(d.arch_pattern, "x86_64")

        d = Distribution("fedora-14", "i386")
        self.assertEquals(d.arch_pattern, "i*86")


class TestRepo(unittest.TestCase):

    _multiprocess_can_split_ = True

    def setUp(self):
        self.workdir = tempfile.mkdtemp(prefix="myrepo-repo-tests")
        self.config = init_defaults()

        # overrides some parameters:
        self.config["topdir"] = os.path.join(self.workdir,
                                             "repos",
                                             "%(subdir)s"
                                             )
        self.config["baseurl"] = "file://%(topdir)s/%(distdir)s"
        self.config["dist"] = "%s-%s" % get_distribution()
        self.config["archs"] = list_archs()[:1]

    def tearDown(self):
        rm_rf(self.workdir)

    def test_copy_cmd(self):
        repo = Repo("localhost",
                    self.config["user"],
                    self.config["email"],
                    self.config["fullname"],
                    self.config["dist"],
                    self.config["archs"],
                    topdir=self.config["topdir"],
                    baseurl=self.config["baseurl"]
        )

        (src, dst) = ("foo.txt", "bar.txt")

        c0 = repo.copy_cmd(src, dst)
        c1 = "cp -a %s %s" % (src, dst)
        self.assertEquals(c0, c1)

        (src, dst) = ("foo.txt", "~/bar.txt")

        c2 = repo.copy_cmd(src, dst)
        c3 = "cp -a %s %s" % \
            (src, ("~" in dst and os.path.expanduser(dst) or dst))
        self.assertEquals(c2, c3)

        server = "repo-server.example.com"
        repo = Repo(server,
                    self.config["user"],
                    self.config["email"],
                    self.config["fullname"],
                    self.config["dist"],
                    self.config["archs"],
                    topdir=self.config["topdir"],
                    baseurl=self.config["baseurl"]
        )

        c4 = repo.copy_cmd(src, dst)
        c5 = "scp -p %s %s@%s:%s" % (src, self.config["user"], server, dst)
        self.assertEquals(c4, c5)

    def test_release_file_content(self):
        repo = Repo("localhost",
                    self.config["user"],
                    self.config["email"],
                    self.config["fullname"],
                    self.config["dist"],
                    self.config["archs"],
                    topdir=self.config["topdir"],
                    baseurl=self.config["baseurl"]
        )

        repo.release_file_content()
        #compile_template(self.release_file_tmpl, params)

    def test_mock_file_content(self):
        repo = Repo("localhost",
                    self.config["user"],
                    self.config["email"],
                    self.config["fullname"],
                    self.config["dist"],
                    self.config["archs"],
                    topdir=self.config["topdir"],
                    baseurl=self.config["baseurl"]
        )

        rfc = repo.release_file_content()

        for dist in repo.dists:
            repo.mock_file_content(dist, rfc)
            repo.mock_file_content(dist)


class TestFuncsWithSideEffects(unittest.TestCase):

    _multiprocess_can_split_ = True

    def setUp(self):
        self.workdir = tempfile.mkdtemp(dir="/tmp", prefix="myrepo-tests")

    def tearDown(self):
        rm_rf(self.workdir)

    def test_init_defaults_by_conffile_config(self):
        conf = """\
[DEFAULT]
a: aaa
b: bbb
"""
        path = os.path.join(self.workdir, "config")
        open(path, "w").write(conf)

        params = init_defaults_by_conffile(path)
        self.assertEquals(params["a"], "aaa")
        self.assertEquals(params["b"], "bbb")

    def test_init_defaults_by_conffile_config_and_profile_0(self):
        conf = """\
[profile0]
a: aaa
b: bbb
"""
        path = os.path.join(self.workdir, "config")
        open(path, "w").write(conf)

        params = init_defaults_by_conffile(path, "profile0")
        self.assertEquals(params["a"], "aaa")
        self.assertEquals(params["b"], "bbb")


class TestProgramLocal(unittest.TestCase):

    _multiprocess_can_split_ = True

    def setUp(self):
        self.workdir = tempfile.mkdtemp(prefix="myrepo-test-tpl-")

    def tearDown(self):
        rm_rf(self.workdir)

    def test_init_with_all_options_set_explicitly(self):
        config = copy.copy(init_defaults())

        # force set some parameters:
        config["server"] = "localhost"
        config["topdir"] = os.path.join(self.workdir,
                                        "%(user)s",
                                        "public_html",
                                        "%(subdir)s"
                                        )
        config["baseurl"] = "file://" + config["topdir"] + "/%(distdir)s"

        cmd = " init "
        cmd += " --server '%(server)s' --user '%(user)s'"
        cmd += " --email '%(email)s' --fullname '%(fullname)s'"
        cmd += " --dists %(dists)s --name '%(name)s'"
        cmd += " --subdir '%(subdir)s' --topdir '%(topdir)s' "
        cmd += " --baseurl '%(baseurl)s' "
        cmd += " -C /dev/null "
        cmd = cmd % config
        cs = shlex.split(cmd)

        logging.info("args: " + str(cs))
        self.assertEquals(main(["argv0"] + cs), 0)

    def test_init_with_all_options_set_explicitly_multi_dists(self):
        config = copy.copy(init_defaults())

        # force set some parameters:
        config["server"] = "localhost"
        config["topdir"] = os.path.join(self.workdir,
                                        "%(user)s",
                                        "public_html",
                                        "%(subdir)s"
                                        )
        config["baseurl"] = "file://" + config["topdir"] + "/%(distdir)s"

        config["dists"] = "rhel-6-i386"

        try:
            key_list = subprocess.check_output(
                "gpg --list-keys %s 2>/dev/null" % get_username(), shell=True
            )
            keyid = key_list.split()[1].split("/")[1]
            keyopt = " "  # Disabled for a while.

        except Exception, e:
            logging.warn(
                "Cannot get the default gpg key list. " + \
                    "Test w/o --signkey: err=%s" % str(e)
            )
            keyopt = ""

        cmd = " init "
        cmd += " --server '%(server)s' --user '%(user)s'"
        cmd += " --email '%(email)s' --fullname '%(fullname)s'"
        cmd += " --dists %(dists)s --name '%(name)s'"
        cmd += " --subdir '%(subdir)s' --topdir '%(topdir)s' "
        cmd += " --baseurl '%(baseurl)s' "
        cmd += keyopt
        cmd += " -C /dev/null "
        cmd = cmd % config
        cs = shlex.split(cmd)

        logging.info("args: " + str(cs))
        self.assertEquals(main(["argv0"] + cs), 0)

    def test_init_with_config(self):
        config = copy.copy(init_defaults())

        (dist_name, dist_version) = get_distribution()
        archs = list_archs()

        config["dists"] = "%s-%s-%s" % (dist_name, dist_version, archs[0])

        config["tmp_workdir"] = os.path.join(self.workdir, "repos")

        config_content = """
[DEFAULT]
server: localhost
baseurl: file://%%(topdir)s/%%(distdir)s
topdir: %s/var/lib/myrepo
name: foo-bar
dists: fedora-14-i386

fullname: John DOe
email: jdoe@example.com
"""

        conf = os.path.join(self.workdir, "myrepo.conf")
        open(conf, "w").write(config_content % self.workdir)

        cmd = "init -C " + conf
        cmd = cmd % config
        cs = shlex.split(cmd)

        logging.info("args: " + str(cs))
        self.assertEquals(main(["argv0"] + cs), 0)

    def test_build(self):
        pass

    def test_deploy(self):
        pass

    def test_update(self):
        pass


class TestProgramRemote(unittest.TestCase):

    _multiprocess_can_split_ = True

    def setUp(self):
        self.workdir = tempfile.mkdtemp(prefix="myrepo-test-tpr-")

    def tearDown(self):
        rm_rf(self.workdir)

    def test_init_with_all_options_set_explicitly(self):
        rc = run_and_get_status(
            "test -x /sbin/service && " + \
                "/sbin/service sshd status > /dev/null 2> /dev/null"
        )

        if rc != 0:
            logging.info(
                "sshd is not working on this host. " + \
                    "Skip this test: " + \
                    "TestProgramRemote." + \
                    "test_init_with_all_options_set_explicitly"
            )
            return

        rhost = find_accessible_remote_host()

        if not rhost:
            logging.info(
                "target host is not accessible via ssh. " + \
                    "Skip this test: test_rshell"
            )
            return

        config = copy.copy(init_defaults())

        # force set some parameters:
        config["server"] = rhost
        config["topdir"] = os.path.join(self.workdir,
                                        "%(user)s",
                                        "public_html",
                                        "%(subdir)s"
                                        )

        cmd = "init "
        cmd += " --server '%(server)s' --user '%(user)s'"
        cmd += " -email '%(email)s' --fullname '%(fullname)s' "
        cmd += " --dists %(dists)s --name '%(name)s'"
        cmd += " --subdir '%(subdir)s' --topdir '%(topdir)s' "
        cmd += " --baseurl '%(baseurl)s' "
        cmd += " -C /dev/null "
        cmd = cmd % config
        cs = shlex.split(cmd)

        logging.info("args: " + str(cs))
        self.assertEquals(main(["argv0"] + cs), 0)


def main(verbose, test_choice=TEST_BASIC):
    def tsuite(testcase):
        return unittest.TestLoader().loadTestsFromTestCase(testcase)

    basic_tests = (
        TestMemoizedFuncs,
        TestMiscFuncs,
        TestThrdCommand,
        TestDistribution,
        TestFuncsWithSideEffects,
        TestRepo,
    )

    system_tests = (
        TestProgramLocal,
        TestProgramRemote,
    )

    (major, minor) = sys.version_info[:2]

    suites = [tsuite(c) for c in basic_tests]

    if test_choice == TEST_FULL:
        suites += [tsuite(c) for c in system_tests]

    tests = unittest.TestSuite(suites)

    doctest.testmod(verbose=verbose)

    if major == 2 and minor < 5:
        unittest.TextTestRunner().run(tests)
    else:
        unittest.TextTestRunner(verbosity=(verbose and 2 or 0)).run(tests)


def realmain(test_choices=TEST_CHOICES):
    p = optparse.OptionParser()

    p.add_option("-v", "--verbose", action="store_true", default=False,
        help="Verbose mode")
    p.add_option("", "--level", type="choice", choices=test_choices,
        default="basic",
        help="Select the level of tests to run. Choices are " + \
            ", ".join(test_choices) + " [%default]"
    )

    (options, args) = p.parse_args()

    main(options.verbose, options.level)
    sys.exit()


if __name__ == '__main__':
    realmain()


# vim:sw=4 ts=4 et:
