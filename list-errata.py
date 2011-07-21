#! /usr/bin/python
#
# Sample python script utilizes swapi.py to:
#
#  * List updates for given RPM list
#  * List errata for given RPM list
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
# Requirements: swapi
#
# SEE ALSO: https://access.redhat.com/knowledge/docs/Red_Hat_Network/API_Documentation/
#
import itertools
import os
import subprocess
import sys



LIST_ALL_RPMS_GROUPED_BY_NAME = "swapi -A %(channel_label)s --group name channel.software.listAllPackages"



def rpm_metadata_from_list_g(list_file, sep=",", keys=("name", "version", "release", "arch", "epoch")):
    for l in open(list_file).readlines():
        l = l.rstrip()

        if not l or l.startswith("#"):
            continue

        yield dict(itertools.izip_longest(keys, l.split(sep))


def main():
    pass


if __name__ == '__main__':
    main()

# vim: set sw=4 ts=4 expandtab:
