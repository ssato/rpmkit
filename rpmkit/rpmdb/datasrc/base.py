#
# Copyright (C) 2012 Red Hat, Inc.
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
class Base(object):

    def __init__(self, repo):
        self.repo = repo
        self._init_packages()
        self._init_errata()

    def _init_packages(self):
        self.packages = []

    def _init_errata(self):
        self.errata = []

    def get_packages(self):
        pass

    def get_errata(self):
        pass

    def get_package_files(self):
        pass

    def get_package_requires(self):
        pass

    def get_package_provides(self):
        pass

    def get_package_errata(self):
        pass

    def get_errata_cves(self):
        pass


# vim:sw=4:ts=4:et:
