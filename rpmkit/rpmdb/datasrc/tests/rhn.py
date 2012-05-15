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
import rpmkit.rpmdb.datasrc.rhn as R
import random
import unittest


CHANNELS = []


class TestFunctions(unittest.TestCase):

    def test_00_rpc(self):
        global CHANNELS

        self.assertTrue(bool(R.rpc("api.getVersion")))

        CHANNELS = R.rpc("channel.listSoftwareChannels")
        self.assertTrue(bool(CHANNELS))

    def test_10_get_packages(self):
        global CHANNELS

        chan = random.choice(CHANNELS)
        ps = R.get_packages(chan["label"])

        self.assertTrue(bool(ps))


# vim:sw=4:ts=4:et:
