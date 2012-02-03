#
# Copyright (C) 2011 Satoru SATOH <ssato at redhat.com>
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
import rpmkit.tenjinwrapper as TW
import rpmkit.tests.common as C

import os.path
import unittest


TEMPLATES_DIR = os.path.abspath(os.path.join(C.selfdir(), "../../templates"))


class Test_00(unittest.TestCase):

    def test_00_template_compile_0(self):
        TW.template_compile_0(
            os.path.join(TEMPLATES_DIR, "1/myrepo/mock.cfg"), {"cfg": dict()}
        )

    def test_10_find_template__abspath(self):
        t = TW.find_template(
            os.path.join(TEMPLATES_DIR, "1/myrepo/mock.cfg"), {"cfg": dict()}
        )

    def test_11_find_template__relpath_w_search_paths(self):
        t = TW.find_template("1/myrepo/mock.cfg", [TEMPLATES_DIR])

    def test_20_template_compile__abspath(self):
        TW.template_compile(
            os.path.join(TEMPLATES_DIR, "1/myrepo/mock.cfg"), {"cfg": dict()}
        )

    def test_21_template_compile__relpath_w_search_paths(self):
        TW.template_compile(
            "1/myrepo/mock.cfg", {"cfg": dict()}, [TEMPLATES_DIR]
        )


# vim:sw=4 ts=4 et:
