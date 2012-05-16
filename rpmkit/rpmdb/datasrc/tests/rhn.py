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
import rpmkit.rpmdb.models.packages as P
import random
import unittest


CHANNELS = []


class Test_00_functions(unittest.TestCase):

    def test_00_rpc(self):
        global CHANNELS

        self.assertTrue(bool(R.rpc("api.getVersion")))

        CHANNELS = R.rpc("channel.listSoftwareChannels")
        self.assertTrue(bool(CHANNELS))

    def test_10_get_packages(self):
        global CHANNELS

        chan = random.choice(CHANNELS)
        xs = R.get_packages(chan["label"])

        self.assertTrue(bool(xs))

    def test_20_get_errata(self):
        global CHANNELS

        chan = random.choice(CHANNELS)
        xs = R.get_errata(chan["label"])

        self.assertTrue(bool(xs))

    def test_30_find_packages_by_nvrea(self):
        global CHANNELS

        chan = random.choice(CHANNELS)
        xs = R.get_packages(chan["label"])
        x = random.choice(xs)

        ys = R.find_packages_by_nvrea(
            x.name, x.version, x.release, x.epoch, x.arch
        )
        self.assertTrue(bool(ys))

    def test_40_get_package_files(self):
        global CHANNELS

        chan = random.choice(CHANNELS)
        xs = R.get_packages(chan["label"])
        x = random.choice(xs)

        ys = R.get_package_files(x.name, x.version, x.release, x.epoch, x.arch)
        self.assertTrue(bool(ys))

    def test_40_get_package_errata(self):
        global CHANNELS

        chan = random.choice(CHANNELS)
        xs = R.get_packages(chan["label"])
        x = random.choice(xs)

        ys = R.get_package_errata(
            x.name, x.version, x.release, x.epoch, x.arch
        )
        self.assertTrue(bool(ys))

    def test_40_get_package_dependencies(self):
        global CHANNELS

        chan = random.choice(CHANNELS)
        xs = R.get_packages(chan["label"])
        x = random.choice(xs)

        ys = R.get_package_dependencies(
            x.name, x.version, x.release, x.epoch, x.arch
        )
        self.assertTrue(bool(ys))

    def test_50_get_package_dependencies_by_type(self):
        global CHANNELS

        chan = random.choice(CHANNELS)
        xs = R.get_packages(chan["label"])
        x = random.choice(xs)

        nvrea = R.package_to_nvrea(x)

        for dtype in ("requires", "conflicts", "obsoletes", "provides"):
            ys = R.get_package_dependencies_by_type(nvrea, dtype)
            #self.assertTrue(bool(ys))  # may be empty

    def test_50_get_cves(self):
        global CHANNELS

        xs = []

        while not xs:
            chan = random.choice(CHANNELS)
            xs = [
                x for x in R.get_errata(chan["label"]) \
                    if P.is_security_errata(x)
            ]

        x = random.choice(xs)

        ys = R.get_cves(x.advisory)
        self.assertTrue(bool(ys))


class Test_10_Swapi(unittest.TestCase):

    def setUp(self):
        self.channels = [
            c["label"] for c in R.rpc("channel.listSoftwareChannels")
        ]

    def test_00__init__(self):
        s = R.Swapi(random.choice(self.channels))
        self.assertTrue(isinstance(s, R.Swapi))

        self.assertTrue(bool(s.get_packages()))
        self.assertTrue(bool(s.get_errata()))

    def test_00_get_package_files(self):
        s = R.Swapi("rhel-i386-server-cluster-5")

        """FIXME:

        while True:
            chan = random.choice(self.channels)
            xs = R.get_packages(chan)

            if len(xs) < 30:
                s = R.Swapi(chan)
                break
        """
        return   # disabled for a while as it takes much time.

        self.assertTrue(bool(s.get_package_files()))

    def test_10_get_package_requires(self):
        s = R.Swapi(random.choice(self.channels))
        self.assertTrue(bool(s.get_package_requires()))

    def test_10_get_package_provides(self):
        s = R.Swapi(random.choice(self.channels))
        self.assertTrue(bool(s.get_package_provides()))

    def test_20_get_package_errata(self):
        s = R.Swapi(random.choice(self.channels))
        self.assertTrue(bool(s.get_package_errata()))

    def test_30_get_errata_cves(self):
        s = R.Swapi(random.choice(self.channels))
        self.assertTrue(bool(s.get_errata_cves()))


# vim:sw=4:ts=4:et:
