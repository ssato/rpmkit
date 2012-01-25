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
import rpmkit.tenjinwrapper as T
import tests.common as C
import os.path
import unittest


def tmplpath(fname):
    return os.path.abspath(
        os.path.join(C.selfdir(), "../templates/1/myrepo", fname)
    )


class Test_00(unittest.TestCase):

    def test_00_mock_cfg(self):
        tmpl = tmplpath("mock.cfg")

        context = dict(
            cfg=dict(
                root='fedora-16-i386',
                legal_host_arches=('i386', 'i586', 'i686'),
                chroot_setup_cmd='groupinstall buildsys-build',
                yumconf="""
...
[main]
...""",
            ),
        )
        c = T.template_compile(tmpl, context)

    def test_01_release_file(self):
        tmpl = tmplpath("release_file")

        context = dict(
            name="fedora",
            server="repo.example.com",
            user="foo",
            baseurl="http://repo.example.com/repo",
            metadata_expire="2h",
            signkey=0,
        )
        c = T.template_compile(tmpl, context)


# vim:sw=4 ts=4 et:
