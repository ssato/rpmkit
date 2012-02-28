#
# Copyright (C) 2011 Satoru SATOH <satoru.satoh at gmail.com>
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
from __future__ import print_function

import rpmkit.myrepo.parser as P

import os
import os.path
import sys
import unittest


class Test_00_parse_conf_value(unittest.TestCase):

    def test_00_int1(self):
        self.assertEquals(P.parse_conf_value("0"), 0)

    def test_01_ints(self):
        self.assertEquals(P.parse_conf_value("123"), 123)

    def test_10_bool_True(self):
        self.assertEquals(P.parse_conf_value("True"), True)

    def test_11_bool_False(self):
        self.assertEquals(P.parse_conf_value("False"), False)

    def test_12_bool_true(self):
        self.assertEquals(P.parse_conf_value("true"), True)

    def test_13_bool_false(self):
        self.assertEquals(P.parse_conf_value("false"), False)

    def test_20_list(self):
        self.assertEquals(P.parse_conf_value("[1,2,3]"), [1, 2, 3])

    def test_30_string(self):
        self.assertEquals(P.parse_conf_value("a string"), "a string")

    def test_40_float(self):
        self.assertEquals(P.parse_conf_value("0.1"), "0.1")


class Test_10_parse_dist_option(unittest.TestCase):

    def test_00_invalid_dist(self):
        with self.assertRaises(AssertionError) as cm:
            P.parse_dist_option("invalid_dist_label.i386")

    def test_01_no_arch_dist(self):
        with self.assertRaises(AssertionError) as cm:
            P.parse_dist_option("feodra-16-x86_64:no-arch-dist")

    def test_02_invalid_arch_dist(self):
        with self.assertRaises(AssertionError) as cm:
            P.parse_dist_option("feodra-16-x86_64:invalid-arch-dist-i386")

    def test_10_single_dist(self):
        self.assertEquals(
            P.parse_dist_option("fedora-16-i386"),
            ('fedora', '16', 'i386', 'fedora-16')
        )

    def test_20_single_dist_w_bdist(self):
        self.assertEquals(
            P.parse_dist_option("fedora-16-i386:fedora-extras-16-i386"),
            ('fedora', '16', 'i386', 'fedora-extras-16')
        )

    def test_21_single_dist_w_bdist_w_custom_sep(self):
        self.assertEquals(
            P.parse_dist_option("fedora-16-i386|fedora-extras-16-i386", "|"),
            ('fedora', '16', 'i386', 'fedora-extras-16')
        )

    def test_30_single_dist_w_bdists(self):
        self.assertEquals(
            P.parse_dist_option(
                "fedora-16-i386:fedora-extras-16-i386:fedora-foo-bar"
            ),
            ('fedora', '16', 'i386', 'fedora-extras-16')
        )


class Test_20_parse_dists_option(unittest.TestCase):

    def test_00_single_dist(self):
        self.assertEquals(
            P.parse_dists_option("fedora-16-i386"),
            [('fedora', '16', 'i386', 'fedora-16')]
        )

    def test_10_single_dist_w_bdist(self):
        self.assertEquals(
            P.parse_dists_option("fedora-16-i386:fedora-extras-16-i386"),
            [('fedora', '16', 'i386', 'fedora-extras-16')]
        )

    def test_20_multi_dists_w_bdist(self):
        ds = "fedora-16-i386:fedora-extras-16-i386"
        ds += ",rhel-6-i386:rhel-extras-6-i386"

        self.assertEquals(
            P.parse_dists_option(ds),
            [
                ('fedora', '16', 'i386', 'fedora-extras-16'),
                ('rhel', '6', 'i386', 'rhel-extras-6')
            ]
        )


# vim:sw=4 ts=4 et:
