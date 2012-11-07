#
# test code for swapi.py
#
# Copyright (C) 2011 Satoru SATOH <ssato@redhat.com>
#
# This software is licensed to you under the GNU General Public License,
# version 2 (GPLv2). There is NO WARRANTY for this software, express or
# implied, including the implied warranties of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. You should have received a copy of GPLv2
# along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.
#
import rpmkit.swapi as S
import rpmkit.tests.common as C

import os.path
import os
import shlex
import sys
import unittest


SYSTEST_ENABLED = os.environ.get("SWAPI_SYSTEST", False)
NET_ENABLED = os.environ.get("SWAPI_NETTEST", False)


def _systest_helper(args):
    if not SYSTEST_ENABLED:
        return

    common_opts = ["--no-cache"]
    (res, _opts) = S.main(common_opts + shlex.split(args))
    assert res, "args=" + args


class Test_10_pure_functions(unittest.TestCase):

    def test_01_sorted_by(self):
        (a, b, c) = (dict(a=1, b=2), dict(a=0, b=3), dict(a=3, b=0))
        xs = [a, b, c]

        self.assertEquals(S.sorted_by(xs, "a"), [b, a, c])


class Test_20_effectful_functions(unittest.TestCase):

    def test_05_urlread(self):
        if not NET_ENABLED:
            return

        self.assertTrue(S.urlread("http://www.example.com") is not None)

    def test_10_get_cvss_for_cve(self):
        if not NET_ENABLED:
            return

        # "CVE-2010-1585" has CVSS metrics data.
        self.assertTrue(S.get_cvss_for_cve("CVE-2010-1585") is not None)

        # "CVE-2008-0001" does not have CVSS metrics data
        self.assertTrue(S.get_cvss_for_cve("CVE-2008-0001") is None)

    def test_12_get_all_cve(self):
        if not NET_ENABLED:
            return

        self.assertTrue(S.get_all_errata())
        self.assertTrue(S.get_all_errata(True))

    def test_14_run(self):
        self.assertTrue(S.run(" ls /dev"))


class Test_30_Cache(unittest.TestCase):

    def setUp(self):
        self.workdir = C.setup_workdir()
        self.cachedir = os.path.join(self.workdir, "cache")

    def tearDown(self):
        C.cleanup_workdir(self.workdir)

    def test_01_save_and_load(self):
        k = ("k0", "k1")
        c = S.Cache("domain0", self.cachedir, {k: 1})
        d = dict(a=1, b=[2, 3], c=dict(d=4, e=[5, 6]))

        self.assertTrue(c.save(k, d))
        self.assertTrue(os.path.exists(c.path(k)))
        self.assertTrue(os.path.isfile(c.path(k)))
        self.assertEquals(c.load(k), d)
        self.assertFalse(c.needs_update(k))  # As just cached.
        self.assertTrue(c.needs_update("not_existent_obj"))


class Test_32_ReadOnlyCache(unittest.TestCase):

    def setUp(self):
        self.workdir = C.setup_workdir()
        self.cachedir = os.path.join(self.workdir, "cache")

    def tearDown(self):
        C.cleanup_workdir(self.workdir)

    def test_01_save_and_load(self):
        k = ("k0", "k1")
        c = S.ReadOnlyCache("domain0", self.cachedir, {k: 1})
        d = dict(a=1, b=[2, 3], c=dict(d=4, e=[5, 6]))

        self.assertTrue(c.save(k, d))
        self.assertFalse(os.path.exists(c.path(k)))
        self.assertFalse(c.needs_update(k))
        self.assertFalse(c.needs_update("not_existent_obj"))


class Test_40_RpcApi__wo_caches(unittest.TestCase):

    def test_00___init__(self):
        conn_params = dict(protocol="https", server="rhns.example.com",
                           userid="foo", passwd="secret", timeout=600)
        rapi = S.RpcApi(conn_params, enable_cache=False, debug=True)

        self.assertEquals(rapi.caches, [])
        self.assertTrue(
            rapi.get_result_from_caches("not_existent_key") is None
        )


class Test_42_RpcApi__w_caches(unittest.TestCase):
    """FIXME: Test cases for RpcApi class w/ caches"""
    pass


class Test_99_system_tests(unittest.TestCase):

    def test_01_api_wo_arg_and_sid(self):
        _systest_helper("api.getVersion")

    def test_02_api_wo_arg(self):
        _systest_helper("channel.listSoftwareChannels")

    def test_03_api_w_arg(self):
        _systest_helper(
            "--args=rhel-i386-server-5 channel.software.getDetails"
        )

    def test_04_api_w_arg_and_format_option(self):
        _systest_helper(
            "-A rhel-i386-server-5 --format '%%(channel_description)s' " + \
                "channel.software.getDetails"
        )

    def test_05_api_w_arg_multicall(self):
        _systest_helper(
            "--list-args='rhel-i386-server-5,rhel-x86_64-server-5' " + \
                "channel.software.getDetails"
        )

    def test_06_api_w_args(self):
        _systest_helper(
            "-A 'rhel-i386-server-5,2010-04-01 08:00:00' " + \
                "channel.software.listAllPackages"
        )

    def test_07_api_w_args_as_list(self):
        _systest_helper(
            "-A '[\"rhel-i386-server-5\",\"2010-04-01 08:00:00\"]' " + \
                "channel.software.listAllPackages"
        )


# vim:sw=4:ts=4:et:
