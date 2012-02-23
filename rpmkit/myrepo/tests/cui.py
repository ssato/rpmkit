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
import rpmkit.myrepo.cui as CUI
import rpmkit.myrepo.config as C
import rpmkit.myrepo.repo as R
import rpmkit.myrepo.utils as U

import optparse
import unittest


# FIXME: These are very simple test cases such like type checking of given or
# returned values.
class Test_00(unittest.TestCase):

    def test_00_create_repos_from_dists_option_g(self):
        cfg = C.init()

        for repo in CUI.create_repos_from_dists_option_g(cfg):
            U.typecheck(repo, R.Repo)

    def test_10_opt_parser(self):
        p = CUI.opt_parser()
        U.typecheck(p, optparse.OptionParser)

        defaults = C.init()
        (opts, _args) = p.parse_args("dummy_args ...".split())
        cfg = opts.__dict__.copy()

        for k, v in defaults.iteritems():
            self.assertEquals(cfg.get(k, None), v)


# vim:sw=4 ts=4 et:
