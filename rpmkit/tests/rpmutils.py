#
# Copyright (C) 2012 Red Hat, Inc.
# Red Hat Author(s): Satoru SATOH <ssato at redhat.com>
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
import rpmkit.rpmutils as RU
import rpmkit.utils as U

import random
import unittest


PACKAGES_0 = [dict(name="gpg-pubkey", version="00a4d52b", release="4cb9dd70",
                   arch="noarch", epoch=0),
              dict(name="gpg-pubkey", version="069c8460", release="4d5067bf",
                   arch="noarch", epoch=0)]

PACKAGES_1 = [dict(name="kernel", version="2.6.38.8", release="32",
                   arch="x86_64", epoch=0),
              dict(name="kernel", version="2.6.38.8", release="35",
                   arch="x86_64", epoch=0),
              dict(name="kernel", version="2.6.38.9", release="35",
                   arch="x86_64", epoch=0)]

PACKAGES_2 = [dict(name="rsync", version="2.6.8", release="3.1",
                   arch="x86_64", epoch=0),
              dict(name="rsync", version="3.0.6", release="4.el5",
                   arch="x86_64", epoch=0),
              dict(name="rsync", version="3.0.6", release="5.el5",
                   arch="x86_64", epoch=0)]

PACKAGES_3 = [dict(name="zfoobar", version="3.0.6", release="4.el5",
                   arch="x86_64", epoch=0),
              dict(name="zfoobar", version="3.0.6", release="5.el5",
                   arch="x86_64", epoch=0),
              dict(name="zfoobar", version="2.6.8", release="3.1",
                   arch="x86_64", epoch=1)]


class Test_00(unittest.TestCase):

    def test_10__is_noarch(self):
        """test for _is_noarch: TBD"""


class Test_40_find_latest(unittest.TestCase):

    def test_00__different_packages(self):
        p1 = dict(name="foo", version="1.0", release="1",
                  epoch=0, arch="x86_64")
        p2 = dict(name="bar", version="1.0", release="1",
                  epoch=0, arch="x86_64")

        with self.assertRaises(AssertionError):
            RU.find_latest([p1, p2])

    def test_00__empty_packages_list(self):
        with self.assertRaises(AssertionError):
            RU.find_latest([])

    def test_10_w_version(self):
        def gen_p(v):
            return dict(name="foo", version=str(v), release="1",
                        arch="x86_64", epoch="(none)")

        vmax = 10
        ps = [gen_p(v) for v in range(vmax + 1)]
        random.shuffle(ps)

        self.assertEquals(RU.find_latest(ps)["version"], str(vmax))

    def test_20_w_release(self):
        def gen_p(r):
            return dict(name="foo", version="0.1", release=str(r),
                        arch="x86_64", epoch="(none)")

        rmax = 10
        ps = [gen_p(r) for r in range(rmax + 1)]
        random.shuffle(ps)

        self.assertEquals(RU.find_latest(ps)["release"], str(rmax))

    def test_30_w_release(self):
        def gen_p(e):
            return dict(name="foo", version="0.1", release="1",
                        arch="x86_64", epoch=str(e))

        emax = 10
        ps = [gen_p(e) for e in range(emax + 1)]
        random.shuffle(ps)

        self.assertEquals(RU.find_latest(ps)["epoch"], str(emax))


class Test_50_find_latests(unittest.TestCase):

    def test_00(self):
        ps = PACKAGES_0 + PACKAGES_1 + PACKAGES_2 + PACKAGES_3
        random.shuffle(ps)

        latests = RU.find_latests(ps)
        expected = [PACKAGES_0[-1], PACKAGES_1[-1], PACKAGES_2[-1],
                    PACKAGES_3[-1]]

        self.assertEquals(latests, expected)


class Test_60_find_updates_g(unittest.TestCase):

    def test_00(self):
        ps = PACKAGES_0 + PACKAGES_1 + PACKAGES_2 + PACKAGES_3
        random.shuffle(ps)

        ps0 = [PACKAGES_0[0], PACKAGES_1[0], PACKAGES_2[0], PACKAGES_3[0]]

        updates = U.concat(us for us in RU.find_updates_g(ps, ps0))
        expected = sorted(PACKAGES_0[1:] + PACKAGES_1[1:] +
                          PACKAGES_2[1:] + PACKAGES_3[1:])

        self.assertEquals(updates, expected)

# vim:sw=4:ts=4:et:
