#
# List errata with using RHN API.
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
import rpmkit.swapi as SW

import logging
import optparse
import os
import pprint
import re
import shlex
import sys


DATE_REG = re.compile(r'\d{4}-\d{2}-\d{2}\s+(?:\d{2}:\d{2}:\d{2})?')
TIME_RESOLUTIONS = (_DAY, _MONTH, _YEAR) = (0, 1, 2)


def __swapi(cmd_s):
    """
    swapi (SpaceWalk API library) wrapper.
    """
    return SW.main(shlex.split(cmd_s))[0]


def validate_datetime(t, reg=DATE_REG):
    """
    :param t: String represents date and time, e.g. '2012-10-09 08:00:00'

    FIXME: This is too naive implementation.
    """
    return reg.match(t) is not None


def list_errata(channel, start=None, end=None):
    """
    :param channel: Software channel label to list errata
    :param start: Start date
    :param end: End date. Error if `end` is given but `start` is not.
    """
    if start:
        assert validate_datetime(start), \
            "list_errata(): Invalid data for `start` parameter: '%s'" % start

    if end is not None:
        assert start is None), \
            "list_errata(): `end` paramter requires `start` parameter is set"
        assert validate_datetime(end), \
            "list_errata(): Invalid data for `end` parameter: '%s'" % end

    args = [
        "--cacheonly" if offline else None,
        "-A", ','.join(a for a in (channel, start, end) if a is not None),
        "channel.software.listErrata"
    ]

    return __swapi(' '.join(a for a in args if a is not None))


def init_log(verbose):
    """Initialize logging module
    """
    level = logging.WARN  # default

    if verbose > 0:
        level = logging.INFO

        if verbose > 1:
            level = logging.DEBUG

    logging.basicConfig(level=level)


def main(argv=sys.argv):
    pass


if __name__ == '__main__':
    main(sys.argv)

# vim:sw=4:ts=4:et:
