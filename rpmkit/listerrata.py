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
from rpmkit.swapi import main as swmain
from itertools import groupby


import logging
import optparse
import os
import pprint
import re
import shlex
import sys


DATE_REG = re.compile(r'\d{4}-\d{2}-\d{2}\s+(?:\d{2}:\d{2}:\d{2})?')


def __swapi(cmd):
    """
    swapi (SpaceWalk API library) wrapper.

    :param cmd: command args :: [str]
    """
    return swmain(cmd)[0]


def validate_datetime(t, reg=DATE_REG):
    """
    :param t: String represents date and time, e.g. '2012-10-09 08:00:00'

    FIXME: This is too naive implementation.
    """
    return reg.match(t) is not None


def list_errata(channel, start=None, end=None, offline=False):
    """
    :param channel: Software channel label to list errata
    :param start: Start date
    :param end: End date. Error if `end` is given but `start` is not.
    """
    if start:
        assert validate_datetime(start), \
            "list_errata(): Invalid data for `start` parameter: '%s'" % start

    if end is not None:
        assert start is None, \
            "list_errata(): `end` paramter requires `start` parameter is set"
        assert validate_datetime(end), \
            "list_errata(): Invalid data for `end` parameter: '%s'" % end

    args = [
        "--cacheonly" if offline else None,
        "-A", ','.join(a for a in (channel, start, end) if a is not None),
        "channel.software.listErrata"
    ]

    return __swapi([a for a in args if a is not None])


_TIME_RESOLUTIONS = (_DAY, _MONTH, _YEAR) = (0, 1, 2)
_TIME_RESOLUTION_S = dict(day=_DAY, month=_MONTH, year=_YEAR)


def __keyfunc(resolution):
    """
    >>> e = {"issue_date": "2012-09-03 13:00:00"}
    >>> __keyfunc(_DAY)(e)
    '2012-09-03'
    >>> __keyfunc(_MONTH)(e)
    '2012-09'
    >>> __keyfunc(_YEAR)(e)
    '2012'
    """
    def f(errata):
        try:
            return errata["issue_date"].split()[0].rsplit('-', resolution)[0]
        except (IndexError, TypeError):
            raise RuntimeError("errata was '%s'" % str(errata))

    return f


def div_errata_list_by_time_resolution(es, resolution=_DAY):
    """
    Divides given errata list (gotten by `list_errata` defined above) by given
    time period `resolution`, returns list of list of errata.

    :param es: Errata list
    :param resolution: Time resolution
    """
    return [list(g) for k, g in groupby(es, key=__keyfunc(resolution))]


def init_log(level):
    lvl = [logging.DEBUG, logging.INFO, logging.WARN][level]
    logging.basicConfig(format="[%(levelname)s] %(message)s", level=lvl)


def option_parser():
    p = optparse.OptionParser("%prog [OPTION ...] SW_CHANNEL_LABEL")

    defaults = dict(
        resolution="day", start=None, end=None, outdir=None, verbose=1,
    )
    p.set_defaults(**defaults)

    p.add_option(
        "-r", "--resolution", type="choice", choices=_TIME_RESOLUTION_S.keys(),
        help="Specify time resolution to group errata list [%default]"
    )
    p.add_option("-s", "--start", help="Specify start date to list errata from")
    p.add_option("-e", "--end", help="Specify end date to list errata to")

    p.add_option("-D", "--debug", action="store_const", const=0,
        dest="verbose", help="Debug mode"
    )
    p.add_option("-q", "--quiet", action="store_const", const=2,
        dest="verbose", help="Quiet mode"
    )
    return p


def main(argv=sys.argv):
    p = option_parser()
    (options, args) = p.parse_args(argv[1:])

    if not args:
        p.print_help()
        print >> sys.stderr, \
            "\nTry `swapi channel.listSoftwareChannels` to get sw channels"
        sys.exit(0)

    init_log(options.verbose)

    channel = args[0]
    resolution = _TIME_RESOLUTION_S.get(options.resolution, "day")

    es = list_errata(channel, options.start, options.end)
    res = div_errata_list_by_time_resolution(es, resolution)

    pprint.pprint(res)


if __name__ == '__main__':
    main(sys.argv)

# vim:sw=4:ts=4:et:
