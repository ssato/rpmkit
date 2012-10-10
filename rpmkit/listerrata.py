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

import datetime
import logging
import optparse
import os
import os.path
import pprint
import re
import shlex
import sys

try:
    import json
except ImportError:
    try:
        import simplejson as json
    except ImportError:
        json = object()

        def __dump(obj, fp, **kwargs):
            pprint.pprint(obj, fp)

        setattr(json, "dump", __dump)  # Looks almost same.

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as pyplot


_DATE_REG = re.compile(r'\d{4}-\d{2}-\d{2}(?:\s+(?:\d{2}:\d{2}:\d{2})?)?')

_TIME_RESOLUTIONS = (_DAY, _MONTH, _YEAR) = (0, 1, 2)
_TIME_RESOLUTION_S = dict(day=_DAY, month=_MONTH, year=_YEAR)


def _simple_fmt_g(result):
    """
    :param result: [(key, [errata])] where key = year | month | day, 
        e.g. "2012" (year), "2012-09" (month) and "2012-09-01" (day).
    """
    for k, es in result:
        yield '\n'.join(("# " + k, '\n'.join(e["advisory"] for e in es)))


def _simple_fmt(result, fp=sys.stdout):
    for x in _simple_fmt_g(result):
        fp.write(x + '\n')

def _json_dump(obj, fp):
    return json.dump(obj, fp, indent=2)


def plotchart(title, xlabel, ylabel, dataset, output,
        xtick_labels=(), ytick_labels=()):
    """
    :param title: Title of the chart
    :param xlabel: Label of X axis of the chart
    :param ylabel: Label of Y axis of the chart
    :param dataset: 2D-array dataset :: [(x, y)]
    :param output: Output filename
    :param xtick_labels: List of xtick lablels :: [str => tick_label]
    :param ytick_labels: List of ytick lablels :: [str => tick_label]
    """
    logging.debug("dataset=" + str(dataset))

    xs = [x for x, _ in dataset]
    ys = [y for _, y in dataset]

    fig = pyplot.figure()

    pyplot.title(title)
    pyplot.xlabel(xlabel)
    pyplot.ylabel(ylabel)

    if xtick_labels:
        pyplot.xticks(range(len(xtick_labels)), xtick_labels)

    if ytick_labels:
        pyplot.yticks(range(len(ytick_labels)), ytick_labels)

    pyplot.plot(xs, ys, "ro")

    fig.savefig(output, format="png")


def barchart(title, xlabel, ylabel, dataset, output,
        xtick_labels=(), ytick_labels=(),
        *args, **kwargs
    ):
    """
    :param title: Title of the chart
    :param xlabel: Label of X axis of the chart
    :param ylabel: Label of Y axis of the chart
    :param dataset: 2D-array dataset :: [(x, y)]
    :param output: Output filename
    """
    logging.debug("dataset=" + str(dataset))

    xs = [x for x, _ in dataset]
    ys = [y for _, y in dataset]

    fig = pyplot.figure()

    pyplot.title(title)
    pyplot.xlabel(xlabel)
    pyplot.ylabel(ylabel)

    if xtick_labels:
        pyplot.xticks(
            range(len(xtick_labels)), xtick_labels, rotation='vertical'
        )

    if ytick_labels:
        pyplot.yticks(range(len(ytick_labels)), ytick_labels)

    pyplot.bar(xs, ys)

    fig.savefig(output, format="png")


def errata_barchart_by_key(errata, key, output):
    """
    :param errata: [(key, [errata])] where key = year | month | day,
        e.g. "2012" (year), "2012-09" (month) and "2012-09-01" (day).
    :param key: Grouping key for `errata` list
    :param output: Output filepath
    """
    args = (
        "number of errata by " + key,
        "time period",
        "number of errata",
        [(i, len(es)) for i, (k, es) in enumerate(errata)],
        output,
        [k for k, _es in errata],
    )
    barchart(*args)


_FORMAT_TYPES = (_SIMPLE_FMT, _JSON_FMT) = ("simple", "json")
_FORMAT_MAP = dict(simple=_simple_fmt, json=_json_dump)


def __swapi(cmd):
    """
    swapi (SpaceWalk API library) wrapper.

    :param cmd: command args :: [str]
    """
    return swmain(cmd)[0]


def validate_datetime(t, reg=_DATE_REG):
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


_ERRATA_TYPES_MAP = dict(SA="RHSA", BA="RHBA", EA="RHEA")


def classify_errata(errata):
    """Classify errata by its type, RH(SA|BA|EA).

    :param errata: errata
    """
    return _ERRATA_TYPES_MAP[errata["advisory"][2:4]]


def classify_errata_list(errata):
    """
    Classify `errata` list by each type, RH(SA|BA|EA).

    :param errata: [errata]
    """
    kf = classify_errata
    return [(k, list(es)) for k, es in groupby(sorted(errata, key=kf), key=kf)]


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
    return [(k, list(g)) for k, g in groupby(es, key=__keyfunc(resolution))]


def init_log(level):
    lvl = [logging.DEBUG, logging.INFO, logging.WARN][level]
    logging.basicConfig(format="[%(levelname)s] %(message)s", level=lvl)


def option_parser():
    p = optparse.OptionParser("%prog [OPTION ...] SW_CHANNEL_LABEL")

    defaults = dict(
        outdir="list-errata-" + datetime.datetime.now().strftime("%Y%m%d"),
        resolution="day", start=None, end=None, verbose=1,
        format="simple", dumpcharts=False,
    )
    p.set_defaults(**defaults)

    p.add_option("-o", "--outdir", help="Specify output dir [%default]")
    p.add_option(
        "-r", "--resolution", type="choice", choices=_TIME_RESOLUTION_S.keys(),
        help="Specify time resolution to group errata list [%default]"
    )
    p.add_option("-s", "--start", help="Specify start date to list errata from")
    p.add_option("-e", "--end", help="Specify end date to list errata to")

    p.add_option(
        "-F", "--format", type="choice", choices=_FORMAT_MAP.keys(),
        help="Specify format type for outputs [%default]"
    )
    p.add_option("-d", "--dumpcharts", action="store_true",
        help="File path to dump errata count charts if given"
    )
    p.add_option("-D", "--debug", action="store_const", const=0,
        dest="verbose", help="Debug mode"
    )
    p.add_option("-q", "--quiet", action="store_const", const=2,
        dest="verbose", help="Quiet mode"
    )
    return p


def __errata_file(etype, outdir, ext=".dat"):
    return os.path.join(outdir, etype.lower() + "-errata" + ext)


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
    es_by_types = classify_errata_list(es)

    fmtr = _FORMAT_MAP.get(options.format, "simple")

    if not os.path.exists(options.outdir):
        os.makedirs(options.outdir)

    for etype, es in es_by_types:
        res = div_errata_list_by_time_resolution(es, resolution)
        with open(__errata_file(etype, options.outdir), 'w') as f:
            fmtr(res, f)

        if options.dumpcharts:
            with open(__errata_file(etype, options.outdir, ".png"), 'w') as f:
                errata_barchart_by_key(res, options.resolution, f)


if __name__ == '__main__':
    main(sys.argv)

# vim:sw=4:ts=4:et:
